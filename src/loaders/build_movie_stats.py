#!/usr/bin/env python3
"""build_movie_stats.py — baseline for live weighted-rating popularity (change live-weighted-popularity, D-2/D-3).

For every movie rated in the TRAINING split of Person 1's run, store the rating count `n0` and the rating sum `sum0`
in `movie_stats` (`_id` = movieId), plus one metadata document `_id: "_meta"` (C, cutoff, counts, generatedAt,
ledgerSince). The training split is `timestamp < cut_val` from evidence/split_stats.csv; the job refuses to write
when the count differs from `n_train` there or the mean differs from the C recorded in evidence/b3_1_split_baseline.txt,
so streamed ratings or val/test ratings can never leak in.

Run inside the spark container (one pass over 32M rows: do not run it while a demo is on, it competes with `streaming`):
    python -m loaders.build_movie_stats
    python -m loaders.build_movie_stats --dry-run            # compute and verify, write nothing
    python -m loaders.build_movie_stats --ledger-since 2026-10-03T00:00:00Z   # a rebuilt baseline that already contains the ledger up to then
Safe to run again: the old contents are replaced. While it writes there is no `_meta`, so the API serves the artifact list.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from loaders.movie_stats_core import (
    META_ID,
    BaselineMismatch,
    make_meta,
    parse_ledger_since,
    read_recorded_c,
    read_split_stats,
    verify_baseline,
    verify_stored,
)

ROOT = Path(__file__).resolve().parents[2]
SPLIT_STATS = ROOT / "evidence" / "split_stats.csv"
SPLIT_EVIDENCE = ROOT / "evidence" / "b3_1_split_baseline.txt"
COLLECTION = "movie_stats"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cutoff", type=float, default=None, help="epoch seconds; default: cut_val from evidence/split_stats.csv")
    ap.add_argument("--ledger-since", default=None, help="ISO time: the baseline already contains ledger events up to it")
    ap.add_argument("--dry-run", action="store_true", help="compute and verify, write nothing")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    split = read_split_stats(SPLIT_STATS.read_text(encoding="utf-8"))
    recorded_c = read_recorded_c(SPLIT_EVIDENCE.read_text(encoding="utf-8"))
    if recorded_c is None:
        print(f"FAIL: no recorded C (mean=...) in {SPLIT_EVIDENCE}")
        return 1
    cutoff = args.cutoff if args.cutoff is not None else split["cut_val"]
    ledger_since = None
    if args.ledger_since:
        ledger_since = parse_ledger_since(args.ledger_since)          # no offset means UTC, never the machine's local time

    # Spark and pymongo are imported here so the pure helpers above stay importable without them.
    from pyspark.sql import functions as F
    from pymongo import MongoClient

    from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, mongo_uri, write_collection

    paths = load_streaming_config()["paths"]
    db_name = load_serving_config()["mongo"]["db"]

    started = dt.datetime.now(dt.timezone.utc)
    spark = build_spark("movielens-build-movie-stats")
    try:
        ratings = spark.read.parquet(paths["curated_ratings"])
        train = ratings.filter(F.col("timestamp") < F.lit(cutoff))
        stats = (
            train.groupBy("movieId")
            .agg(F.count("*").alias("n0"), F.sum("rating").cast("double").alias("sum0"))
            .cache()
        )
        totals = stats.agg(F.sum("n0").alias("n"), F.sum("sum0").alias("s"), F.count("*").alias("movies")).first()
        if not totals["n"]:
            print(f"FAIL: the cutoff {cutoff:.0f} selects no ratings (nothing written)")
            return 1
        n_ratings, total_sum, n_movies = int(totals["n"]), float(totals["s"]), int(totals["movies"])
        mean = total_sum / n_ratings
        print(f"cutoff {cutoff:.0f}: {n_ratings:,} ratings on {n_movies:,} movies, mean {mean:.6f}")
        print(f"split recorded: n_train {split['n_train']:,}, C {recorded_c}")

        try:
            verify_baseline(n_ratings=n_ratings, mean=mean, n_train=split["n_train"], recorded_c=recorded_c)
        except BaselineMismatch as exc:
            print(f"FAIL: {exc}")
            print("nothing was written")
            return 1
        print("checks: rating count equals n_train, mean equals the recorded C -> PASS")
        if args.dry_run:
            print("--dry-run: nothing written")
            return 0

        client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=10000)
        coll = client[db_name][COLLECTION]
        coll.delete_one({"_id": META_ID})         # no _meta while loading: the API falls back to the artifact
        coll.delete_many({})
        out = stats.select(F.col("movieId").alias("_id"), "n0", "sum0")
        write_collection(out, db_name, COLLECTION, operation_type="replace", id_field="_id")

        written = coll.count_documents({})
        if written != n_movies:
            print(f"FAIL: wrote {written:,} documents, expected {n_movies:,}; no _meta written, the API keeps using the artifact")
            return 1
        landed = next(coll.aggregate([
            {"$match": {"_id": {"$type": "number"}}},
            {"$group": {"_id": None, "n": {"$sum": "$n0"}, "s": {"$sum": "$sum0"}}},
        ]), {"n": 0, "s": 0.0})
        try:
            verify_stored(stored_ratings=int(landed["n"]), stored_sum=float(landed["s"]), n_ratings=n_ratings, mean=mean)
        except BaselineMismatch as exc:
            print(f"FAIL: {exc}; no _meta written, the API keeps using the artifact")
            return 1
        coll.insert_one(make_meta(
            c=mean, recorded_c=recorded_c, cutoff=cutoff,
            cutoff_source=SPLIT_STATS.name if args.cutoff is None else "--cutoff",
            ratings=n_ratings, movies=n_movies, generated_at=dt.datetime.now(dt.timezone.utc), ledger_since=ledger_since,
        ))
        took = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
        print(f"OK: {db_name}.{COLLECTION}: {written:,} movies + _meta (ledgerSince={ledger_since}) in {took:.0f} s")
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
