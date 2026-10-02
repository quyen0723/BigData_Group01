#!/usr/bin/env python3
"""build_movies.py — WBS 3.2. Load the additive `movies` collection (design.md D-4)
from curated_movies + a rating-count `support` computed from curated_ratings.
`_id` = movieId, so reruns are idempotent (operationType=replace matches by _id).

Run inside the spark container:
    python -m loaders.build_movies
"""
from __future__ import annotations

import sys

from pyspark.sql import functions as F

from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, write_collection


def main() -> int:
    streaming_cfg = load_streaming_config()
    serving_cfg = load_serving_config()
    paths = streaming_cfg["paths"]
    db = serving_cfg["mongo"]["db"]
    collection = serving_cfg["mongo"]["collections"]["movies"]

    spark = build_spark("movielens-build-movies")
    try:
        movies = spark.read.parquet(paths["curated_movies"])
        ratings = spark.read.parquet(paths["curated_ratings"])

        support = ratings.groupBy("movieId").agg(F.count("*").alias("support"))
        out = (
            movies.join(support, "movieId", "left")
            .withColumn("support", F.coalesce(F.col("support"), F.lit(0)))
            .select(
                F.col("movieId").alias("_id"),
                "title",
                "genres",
                "support",
            )
        )

        n_movies = movies.count()
        n_out = out.count()
        write_collection(out, db, collection, operation_type="replace", id_field="_id")

        print(f"OK: movies loaded -> {db}.{collection}")
        print(f"  curated_movies rows: {n_movies:,}")
        print(f"  written docs:        {n_out:,}")
        if n_movies != n_out:
            print(f"FAIL: row count mismatch ({n_movies:,} != {n_out:,})")
            return 1
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
