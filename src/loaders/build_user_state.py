#!/usr/bin/env python3
"""build_user_state.py — WBS 3.3. From `user_history_seed.parquet` (userId,
movieId, rating, rating_ts — 32,000,204 rows, one row per distinct (userId,
movieId) per Person 1's curated_ratings dedup), build:

  - `user_rated`   (design.md D-4/D-7): one doc per (userId, movieId), the
    exact rated set used for exclusion.
  - `user_history` (CONTRACTS.md §3.4): one doc per user, aggregated with the
    SAME rule as src/serving/history.recompute_history (design.md D-10 step 5)
    — recomputed from the full set, not incremented, so a rerun is idempotent.

Run inside the spark container:
    python -m loaders.build_user_state
"""
from __future__ import annotations

import sys

from pyspark.sql import Window
from pyspark.sql import functions as F

from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, write_collection


def _ranked_movie_id_list(df, order_col: str, cap: int, out_col: str):
    """Rank rows per userId by (order_col desc, movieId asc), keep top `cap`,
    return one row per userId with an ordered array `out_col` of movieId —
    same tie-break rule as src/serving/history.py's recompute_history."""
    w = Window.partitionBy("userId").orderBy(F.desc(order_col), F.asc("movieId"))
    ranked = (
        df.withColumn("rn", F.row_number().over(w))
        .filter(F.col("rn") <= cap)
        .groupBy("userId")
        .agg(F.sort_array(F.collect_list(F.struct("rn", "movieId"))).alias("ranked"))
        .withColumn(out_col, F.expr("transform(ranked, x -> x.movieId)"))
        .select("userId", out_col)
    )
    return ranked


def main() -> int:
    streaming_cfg = load_streaming_config()
    serving_cfg = load_serving_config()
    paths = streaming_cfg["paths"]
    hist_cfg = streaming_cfg["user_history_update"]
    db = serving_cfg["mongo"]["db"]
    collections = serving_cfg["mongo"]["collections"]

    recent_cap = int(hist_cfg["recent_cap"])
    positive_cap = int(hist_cfg["positive_cap"])
    positive_threshold = float(hist_cfg["positive_threshold"])

    seed_path = f"{paths['artifacts']}/user_history_seed.parquet"

    spark = build_spark("movielens-build-user-state")
    try:
        seed = spark.read.parquet(seed_path)
        # rating_ts is a TimestampType (see src/etl/write_curated.py); convert to
        # epoch seconds so `ratingTs` matches the epoch-second convention used by
        # the rating event contract (CONTRACTS.md §5) and src/serving/history.py.
        seed = seed.withColumn("ratingTsEpoch", F.col("rating_ts").cast("long"))

        n_seed = seed.count()

        # --- user_rated -----------------------------------------------------
        user_rated = seed.select(
            "userId", "movieId", "rating", F.col("ratingTsEpoch").alias("ratingTs")
        )
        write_collection(user_rated, db, collections["user_rated"], operation_type="insert")

        # --- user_history -----------------------------------------------------
        counts = seed.groupBy("userId").agg(
            F.count("*").alias("interaction_count"),
            F.max("ratingTsEpoch").alias("lastUpdatedEpoch"),
        )
        recent = _ranked_movie_id_list(
            seed.select("userId", "movieId", "ratingTsEpoch"),
            "ratingTsEpoch", recent_cap, "recent_movieIds",
        )
        positive_source = seed.filter(F.col("rating") >= positive_threshold).select(
            "userId", "movieId", "ratingTsEpoch"
        )
        positive = _ranked_movie_id_list(positive_source, "ratingTsEpoch", positive_cap, "positive_movieIds")

        history = (
            counts.join(recent, "userId", "left")
            .join(positive, "userId", "left")
            .withColumn("recent_movieIds", F.coalesce(F.col("recent_movieIds"), F.array()))
            .withColumn("positive_movieIds", F.coalesce(F.col("positive_movieIds"), F.array()))
            .withColumn("lastUpdated", F.to_timestamp(F.col("lastUpdatedEpoch")))
            .select("userId", "interaction_count", "recent_movieIds", "positive_movieIds", "lastUpdated")
        )

        n_users = history.count()
        total_interactions = history.agg(F.sum("interaction_count")).first()[0]
        write_collection(history, db, collections["user_history"], operation_type="insert")

        print(f"OK: user_rated + user_history loaded -> {db}")
        print(f"  seed rows:              {n_seed:,}")
        print(f"  user_rated docs:        {n_seed:,} (1:1 with seed)")
        print(f"  user_history docs:      {n_users:,}")
        print(f"  sum(interaction_count): {total_interactions:,}")
        if total_interactions != n_seed:
            print(f"FAIL: sum(interaction_count) != seed rows ({total_interactions:,} != {n_seed:,})")
            return 1
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
