#!/usr/bin/env python3
"""check_live_popularity_store.py — checks the MongoDB side of live popularity against a REAL Mongo (change live-weighted-popularity).

The unit tests use a fake repository, so the aggregation pipeline and the movie_stats reader are exercised here, on scratch
collections (`_check_rating_events`, `_check_movie_stats`) that are dropped at the end. The real ledger and movie_stats are never touched.

  1. rating_deltas_pipeline on 6,000 random ledger events (tied timestamps, repeated (user, movie) pairs, some without ingestedAt)
     must equal serving.popularity.deltas_from_events computed in Python from the same documents, with and without a ledger mark.
  2. get_movie_stats: reads a complete baseline, keeps it until _meta.generatedAt changes, refuses an incomplete load and an
     incomplete _meta, and returns None once _meta is gone (so the API serves the artifact).

    .venv-serving/Scripts/python scripts/check_live_popularity_store.py        (MONGO_URI, default mongodb://localhost:27017)
Exit code 0 = PASS, 1 = a check failed.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pymongo  # noqa: E402

from serving.config import load_serving_config  # noqa: E402
from serving.popularity import deltas_from_events  # noqa: E402
from serving.repository import MongoServingRepository  # noqa: E402

LEDGER = "_check_rating_events"
STATS = "_check_movie_stats"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{' - ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def same(a: dict, b: dict) -> bool:
    return a.keys() == b.keys() and all(a[k][0] == b[k][0] and abs(a[k][1] - b[k][1]) < 1e-9 for k in a)


def main() -> int:
    cfg = load_serving_config()
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    mongo_cfg = dataclasses.replace(cfg.mongo, collections={**cfg.mongo.collections, "rating_events": LEDGER, "movie_stats": STATS})
    repo = MongoServingRepository(uri, mongo_cfg)
    db = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)[cfg.mongo.db]
    db[LEDGER].drop()
    db[STATS].drop()
    try:
        print(f"1. ledger aggregation vs the Python reference ({LEDGER})")
        rng = random.Random(20261003)
        base = dt.datetime(2026, 10, 3, 9, 0, 0)
        docs = []
        for i in range(6000):
            docs.append({
                "_id": f"e{i:06d}", "userId": 999_700_000 + rng.randint(1, 400), "movieId": rng.randint(1, 150),
                "rating": float(rng.choice([0.5, 1, 2.5, 3, 4, 5])), "timestamp": 1_800_000_000 + rng.randint(0, 900), "batchId": 1,
                "ingestedAt": base + dt.timedelta(seconds=rng.randint(0, 120)) if rng.random() > 0.02 else None,
            })
        db[LEDGER].insert_many(docs, ordered=False)
        stored = list(db[LEDGER].find({}))                                   # read back: the types and precision pymongo really returns
        for label, since in (("no mark", None), ("mark inside the range", base + dt.timedelta(seconds=60)), ("mark after everything", base + dt.timedelta(days=1))):
            got, ref = repo.get_rating_deltas(since), deltas_from_events(stored, since)
            check(f"{label}: Mongo pipeline == Python reference ({len(ref)} movies, {sum(n for n, _ in ref.values())} ratings)", same(got, ref))
        pairs = {(d["userId"], d["movieId"]) for d in stored}
        check("one rating per (user, movie): ratings counted == distinct pairs", sum(n for n, _ in repo.get_rating_deltas(None).values()) == len(pairs))

        print(f"2. get_movie_stats ({STATS})")
        meta = {"_id": "_meta", "generatedAt": "g1", "movies": 3, "C": 3.5, "cutoff": 1.0, "ratings": 600, "ledgerSince": None}
        db[STATS].insert_many([meta, {"_id": 1, "n0": 100, "sum0": 400.0}, {"_id": 2, "n0": 200, "sum0": 800.0}, {"_id": 3, "n0": 300, "sum0": 1200.0}])
        first = repo.get_movie_stats()
        check("complete baseline is read, _meta is not a movie", first is not None and set(first.stats) == {1, 2, 3} and first.ratings == 600)
        check("cached while _meta.generatedAt is unchanged", repo.get_movie_stats() is first)
        db[STATS].update_one({"_id": "_meta"}, {"$set": {"generatedAt": "g2"}})
        second = repo.get_movie_stats()
        check("rebuilt baseline (new generatedAt) is reloaded", second is not first and second.generated_at == "g2")
        db[STATS].update_one({"_id": "_meta"}, {"$set": {"movies": 4}})
        try:
            db[STATS].update_one({"_id": "_meta"}, {"$set": {"generatedAt": "g3"}})
            repo.get_movie_stats()
            check("an incomplete load is refused", False, "no error raised")
        except RuntimeError as exc:
            check("an incomplete load is refused", "incomplete load" in str(exc), str(exc))
        db[STATS].update_one({"_id": "_meta"}, {"$set": {"movies": 3}, "$unset": {"C": ""}})
        try:
            repo.get_movie_stats()
            check("a _meta without C is refused", False, "no error raised")
        except RuntimeError as exc:
            check("a _meta without C is refused and says which key", "missing" in str(exc) and "C" in str(exc), str(exc))
        db[STATS].delete_one({"_id": "_meta"})
        check("no _meta -> None (the API serves the artifact)", repo.get_movie_stats() is None)
    finally:
        db[LEDGER].drop()
        db[STATS].drop()
        print("  scratch collections dropped")
    print("RESULT: " + ("FAIL (" + ", ".join(failures) + ")" if failures else "PASS"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
