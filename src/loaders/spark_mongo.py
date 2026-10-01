# spark_mongo.py — shared Spark session + Mongo write helper for the loader jobs
# (WBS 3.1-3.5). Connector option names verified against MongoDB Spark Connector
# v10.x docs (mongodb.com/docs/spark-connector/v10.x/batch-mode/batch-write-config/):
# format "mongodb", options connection.uri / database / collection / operationType.
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pyspark.sql import DataFrame, SparkSession

ROOT = Path(__file__).resolve().parents[2]


def load_streaming_config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "streaming.yaml").read_text(encoding="utf-8"))


def load_serving_config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "serving.yaml").read_text(encoding="utf-8"))


def mongo_uri() -> str:
    return os.environ.get("MONGO_URI", "mongodb://localhost:27017")


def build_spark(app_name: str) -> SparkSession:
    cfg = load_streaming_config()["spark"]
    packages = ",".join(cfg["packages"])
    builder = (
        SparkSession.builder.appName(app_name)
        .master(cfg["master"])
        .config("spark.driver.memory", cfg["driver_memory"])
        .config("spark.sql.shuffle.partitions", cfg["shuffle_partitions"])
        .config("spark.jars.packages", packages)
    )
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark


def write_collection(
    df: DataFrame,
    database: str,
    collection: str,
    operation_type: str = "insert",
    id_field: str | None = None,
) -> None:
    """Insert-only by default (WBS 3.4/3.5 load fresh per version after an explicit
    delete). Pass operation_type="replace" + id_field for idempotent upsert-by-key
    loads (e.g. `movies`, keyed by movieId as _id)."""
    writer = (
        df.write.format("mongodb")
        .mode("append")
        .option("connection.uri", mongo_uri())
        .option("database", database)
        .option("collection", collection)
        .option("operationType", operation_type)
    )
    if id_field:
        writer = writer.option("idFieldList", id_field)
    writer.save()
