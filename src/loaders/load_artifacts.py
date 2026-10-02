#!/usr/bin/env python3
"""load_artifacts.py — WBS 3.4. Load the 3 contract serving artifacts (CONTRACTS.md
§3.1-3.3) into MongoDB with explicit schemas (no inferSchema — same convention as
Person 1's src/etl/ingest.py). Idempotent per modelVersion: deletes any existing
docs of that version before inserting (design.md D-3), so a rerun for the same
version reproduces the same document count instead of erroring or duplicating.

`als_topn.json` -> collection `user_recommendations` (CONTRACTS.md §3.3 naming rule).
`popular_movies.json` is a single JSON OBJECT (not an array) — read with
`multiLine=True`, which also correctly parses the compact (single-line) JSON
ARRAYS in similar_movies.json / als_topn.json (94/82 MB, too large for
`mongoimport --jsonArray`'s 16 MB limit — this is why we use Spark instead).

Run inside the spark container:
    python -m loaders.load_artifacts --artifact popular  --version v1.0.0
    python -m loaders.load_artifacts --artifact similar  --version v1.0.0
    python -m loaders.load_artifacts --artifact als_topn --version v1.0.0
"""
from __future__ import annotations

import argparse
import sys

from pymongo import MongoClient
from pyspark.sql.types import ArrayType, DoubleType, IntegerType, StringType, StructField, StructType

from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, mongo_uri, write_collection

SIMILAR_ITEM = StructType([
    StructField("movieId", IntegerType()),
    StructField("score", DoubleType()),
    StructField("rank", IntegerType()),
])

REC_ITEM = StructType([
    StructField("movieId", IntegerType()),
    StructField("score", DoubleType()),
    StructField("rank", IntegerType()),
])

POPULAR_ITEM = StructType([
    StructField("movieId", IntegerType()),
    StructField("title", StringType()),
    StructField("genres", StringType()),
    StructField("rank", IntegerType()),
    StructField("score", DoubleType()),
    StructField("support", IntegerType()),
])

ARTIFACTS = {
    "popular": dict(
        filename="popular_movies.json",
        top_level="object",
        schema=StructType([
            StructField("scope", StringType()),
            StructField("modelVersion", StringType()),
            StructField("generatedAt", StringType()),
            StructField("items", ArrayType(POPULAR_ITEM)),
        ]),
        collection_key="popular_movies",
    ),
    "similar": dict(
        filename="similar_movies.json",
        top_level="array",
        schema=StructType([
            StructField("movieId", IntegerType()),
            StructField("modelVersion", StringType()),
            StructField("generatedAt", StringType()),
            StructField("similar", ArrayType(SIMILAR_ITEM)),
        ]),
        collection_key="similar_movies",
    ),
    "als_topn": dict(
        filename="als_topn.json",
        top_level="array",
        schema=StructType([
            StructField("userId", IntegerType()),
            StructField("modelVersion", StringType()),
            StructField("generatedAt", StringType()),
            StructField("strategy", StringType()),
            StructField("recommendations", ArrayType(REC_ITEM)),
        ]),
        # CONTRACTS.md §3.3: file als_topn.json -> collection user_recommendations.
        collection_key="user_recommendations",
    ),
}


def delete_existing_version(db_name: str, collection: str, version: str) -> int:
    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=5000)
    result = client[db_name][collection].delete_many({"modelVersion": version})
    client.close()
    return result.deleted_count


def load_one(spark, artifact_key: str, version: str, path_override: str | None = None) -> dict:
    """Load one artifact file into its collection. Reused by this module's CLI
    (WBS 3.4) and by orchestration/stage_candidate.py (WBS 7.3) — staging a
    candidate is exactly this load, just for a not-yet-active `version`; nothing
    reads staged docs until serving_meta's pointer is switched (design.md D-5).
    Returns a summary dict; raises ValueError on a version mismatch or 0 rows.
    """
    spec = ARTIFACTS[artifact_key]
    streaming_cfg = load_streaming_config()
    serving_cfg = load_serving_config()
    db = serving_cfg["mongo"]["db"]
    collection = serving_cfg["mongo"]["collections"][spec["collection_key"]]
    path = path_override or f"{streaming_cfg['paths']['artifacts']}/{spec['filename']}"

    df = spark.read.schema(spec["schema"]).option("multiLine", True).json(path)

    versions = [r["modelVersion"] for r in df.select("modelVersion").distinct().collect()]
    if versions != [version]:
        raise ValueError(f"--version {version} does not match modelVersion(s) found in {path}: {versions}")

    n = df.count()
    if n == 0:
        raise ValueError(f"{path} parsed to 0 rows — check schema/path (multiLine JSON shape)")

    deleted = delete_existing_version(db, collection, version)
    write_collection(df, db, collection, operation_type="insert")

    return {
        "artifact": artifact_key, "path": path, "database": db, "collection": collection,
        "modelVersion": version, "docsWritten": n, "previousDocsReplaced": deleted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True, choices=list(ARTIFACTS))
    parser.add_argument("--version", required=True, help='e.g. v1.0.0 (must match modelVersion in the file)')
    parser.add_argument("--file", default=None, help="override the default artifacts_dir/<filename> path")
    args = parser.parse_args()

    spark = build_spark(f"movielens-load-artifact-{args.artifact}")
    try:
        try:
            result = load_one(spark, args.artifact, args.version, args.file)
        except ValueError as exc:
            print(f"FAIL: {exc}")
            return 1

        print(f"OK: {result['artifact']} ({result['path']}) -> {result['database']}.{result['collection']}")
        print(f"  modelVersion:      {result['modelVersion']}")
        print(f"  docs written:      {result['docsWritten']:,}")
        print(f"  previous docs replaced (deleted before insert): {result['previousDocsReplaced']:,}")
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
