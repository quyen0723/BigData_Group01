#!/usr/bin/env python3
"""pipeline.py — WBS 5.1/5.2, 6.2-6.5. The 3-query Structured Streaming topology
(design.md D-9/D-10):

  Q1 raw:       Kafka -> parquet file sink (raw_events/, its own checkpoint)
  parsed:       readStream on raw_events -> from_json -> broadcast join movies
                -> first-failing-rule `reason` (src/streaming/events.py)
  Q3 quarantine: parsed where reason IS NOT NULL -> parquet file sink
  Q2 valid:     parsed where reason IS NULL -> watermark + dedup(eventId)
                -> foreachBatch(serve_batch)

`curated_ratings` is written by `serve_batch` with a plain BATCH writer
(mode="append"), never a streaming file sink — a streaming sink there would
create `_spark_metadata/`, which makes any later batch read of the path see
ONLY the streamed files and silently hide the 32M historical rows
(design.md D-9, verified against Spark 3.5's DataSource.resolveRelation).

Run inside the spark container:
    python -m streaming.pipeline
"""
from __future__ import annotations

import datetime as dt
import os
import sys

from pymongo import MongoClient, UpdateOne
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, LongType, StringType, StructField, StructType

from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, mongo_uri
from serving.history import recompute_history
from serving.models import RatedMovie

EVENT_SCHEMA = StructType([
    StructField("eventId", StringType()),
    StructField("userId", IntegerType()),
    StructField("movieId", IntegerType()),
    StructField("rating", DoubleType()),
    StructField("timestamp", LongType()),
    StructField("source", StringType()),
])

VALID_RATINGS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]

REASON_BAD_EVENT_ID = "invalid_event_id"
REASON_BAD_USER_ID = "invalid_user_id"
REASON_UNKNOWN_MOVIE = "unknown_movie_id"
REASON_BAD_RATING = "invalid_rating_value"
REASON_BAD_TIMESTAMP = "invalid_timestamp"


def start_raw_query(spark: SparkSession, kafka_servers: str, topic: str, paths: dict, trigger_seconds: int,
                     max_offsets: int):
    """Q1: Kafka -> raw_events/ (partitioned by ingest_date), its own checkpoint."""
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", kafka_servers)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", max_offsets)
        .load()
        .selectExpr(
            "CAST(key AS STRING) as kafkaKey",
            "CAST(value AS STRING) as value",
            "partition as kafkaPartition",
            "offset as kafkaOffset",
            "timestamp as kafkaTimestamp",
        )
        .withColumn("ingest_date", F.to_date(F.current_timestamp()))
    )
    return (
        raw.writeStream.format("parquet")
        .option("path", paths["raw_events"])
        .option("checkpointLocation", paths["checkpoints"]["raw"])
        .partitionBy("ingest_date")
        .trigger(processingTime=f"{trigger_seconds} seconds")
        .start()
    )


def build_parsed_stream(spark: SparkSession, movies_df: DataFrame, paths: dict, max_future_skew_days: int) -> DataFrame:
    """readStream on raw_events -> parsed event + `reason` (first failing rule,
    same rule order as src/streaming/events.py.validate_event, reimplemented as
    Spark column expressions since events.py's plain-Python version can't run
    per-row inside a distributed streaming query)."""
    raw = spark.readStream.schema(
        StructType([
            StructField("kafkaKey", StringType()),
            StructField("value", StringType()),
            StructField("kafkaPartition", IntegerType()),
            StructField("kafkaOffset", LongType()),
            StructField("kafkaTimestamp", StringType()),
            StructField("ingest_date", StringType()),
        ])
    ).parquet(paths["raw_events"])

    parsed = (
        raw.select(F.from_json(F.col("value"), EVENT_SCHEMA).alias("e")).select("e.*")
        .withColumn("event_time", F.to_timestamp(F.from_unixtime(F.col("timestamp"))))
    )

    max_future_ts = F.unix_timestamp(F.current_timestamp()) + F.lit(max_future_skew_days * 86400)

    # Left join against a broadcast set of known movieIds; `_known` is null for
    # any movieId not present in `movies` (unknown-movie rule).
    known_movies = F.broadcast(movies_df.select(F.col("_id").alias("movieId")).withColumn("_known", F.lit(True)))
    parsed = parsed.join(known_movies, on="movieId", how="left")

    parsed = parsed.withColumn(
        "reason",
        F.when(F.col("eventId").isNull() | (F.trim(F.col("eventId")) == ""), F.lit(REASON_BAD_EVENT_ID))
        .when(F.col("userId").isNull() | (F.col("userId") <= 0), F.lit(REASON_BAD_USER_ID))
        .when(F.col("_known").isNull(), F.lit(REASON_UNKNOWN_MOVIE))
        .when(~F.col("rating").isin(VALID_RATINGS), F.lit(REASON_BAD_RATING))
        .when(
            F.col("timestamp").isNull() | (F.col("timestamp") <= 0) | (F.col("timestamp") > max_future_ts),
            F.lit(REASON_BAD_TIMESTAMP),
        )
        .otherwise(F.lit(None).cast("string")),
    ).drop("_known")

    return parsed


def start_quarantine_query(parsed: DataFrame, paths: dict, trigger_seconds: int):
    """Q3: invalid events -> quarantine/ with `reason`, own checkpoint."""
    invalid = parsed.filter(F.col("reason").isNotNull())
    return (
        invalid.writeStream.format("parquet")
        .option("path", paths["quarantine"])
        .option("checkpointLocation", paths["checkpoints"]["invalid"])
        .trigger(processingTime=f"{trigger_seconds} seconds")
        .start()
    )


def make_serve_batch(paths: dict, hist_cfg: dict, db_name: str):
    """Returns the closure `serve_batch(df, batch_id)` bound to config (design.md
    D-10). Mixes a Spark batch write (curated_ratings) with pymongo (everything
    else is per-row/per-user document logic, and the batch is small — bounded by
    maxOffsetsPerTrigger — so collecting it to the driver is safe)."""
    recent_cap = int(hist_cfg["recent_cap"])
    positive_cap = int(hist_cfg["positive_cap"])
    positive_threshold = float(hist_cfg["positive_threshold"])
    curated_ratings_path = paths["curated_ratings"]

    def serve_batch(batch_df: DataFrame, batch_id: int) -> None:
        client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=10000)
        db = client[db_name]
        try:
            state = db.pipeline_state.find_one({"_id": "ratings_stream"})
            last_batch_id = state.get("lastBatchId", -1) if state else -1
            if batch_id <= last_batch_id:
                print(f"serve_batch[{batch_id}]: already committed (last={last_batch_id}), skipping")
                return

            rows = [r.asDict() for r in batch_df.select(
                "eventId", "userId", "movieId", "rating", "timestamp"
            ).collect()]

            if rows:
                event_ids = [r["eventId"] for r in rows]
                existing_ids = {d["_id"] for d in db.rating_events.find(
                    {"_id": {"$in": event_ids}}, {"_id": 1}
                )}
                new_rows = [r for r in rows if r["eventId"] not in existing_ids]
            else:
                new_rows = []

            print(f"serve_batch[{batch_id}]: {len(rows)} row(s), {len(new_rows)} new after ledger dedup")

            if new_rows:
                # 3. append curated_ratings — BATCH writer, never a streaming file sink.
                spark = batch_df.sparkSession
                curated_schema = StructType([
                    StructField("userId", IntegerType()),
                    StructField("movieId", IntegerType()),
                    StructField("rating", DoubleType()),
                    StructField("timestamp", LongType()),
                ])
                curated_rows = [
                    (r["userId"], r["movieId"], r["rating"], r["timestamp"]) for r in new_rows
                ]
                curated_df = (
                    spark.createDataFrame(curated_rows, schema=curated_schema)
                    .withColumn("rating_ts", F.to_timestamp(F.from_unixtime(F.col("timestamp"))))
                    .withColumn("year", F.year(F.col("rating_ts")))
                )
                curated_df.write.mode("append").partitionBy("year").parquet(curated_ratings_path)

                # 4. upsert user_rated, latest-timestamp-wins (pipeline update).
                rated_ops = [
                    UpdateOne(
                        {"userId": r["userId"], "movieId": r["movieId"]},
                        [{"$set": {
                            "rating": {"$cond": [
                                {"$gte": [r["timestamp"], {"$ifNull": ["$ratingTs", -1]}]},
                                r["rating"], "$rating",
                            ]},
                            "ratingTs": {"$cond": [
                                {"$gte": [r["timestamp"], {"$ifNull": ["$ratingTs", -1]}]},
                                r["timestamp"], "$ratingTs",
                            ]},
                        }}],
                        upsert=True,
                    )
                    for r in new_rows
                ]
                db.user_rated.bulk_write(rated_ops, ordered=False)

                # 5. recompute user_history for affected users (reuses
                #    src/serving/history.recompute_history — same tested logic).
                affected_users = sorted({r["userId"] for r in new_rows})
                hist_ops = []
                for uid in affected_users:
                    rated_docs = db.user_rated.find(
                        {"userId": uid}, {"movieId": 1, "rating": 1, "ratingTs": 1, "_id": 0}
                    )
                    rated = [RatedMovie(d["movieId"], d["rating"], d["ratingTs"]) for d in rated_docs]
                    snap = recompute_history(rated, recent_cap, positive_cap, positive_threshold)
                    last_updated = (
                        dt.datetime.fromtimestamp(snap.last_updated, tz=dt.timezone.utc)
                        if snap.last_updated else None
                    )
                    hist_ops.append(UpdateOne(
                        {"userId": uid},
                        {"$set": {
                            "userId": uid,
                            "interaction_count": snap.interaction_count,
                            "recent_movieIds": list(snap.recent_movie_ids),
                            "positive_movieIds": list(snap.positive_movie_ids),
                            "lastUpdated": last_updated,
                        }},
                        upsert=True,
                    ))
                if hist_ops:
                    db.user_history.bulk_write(hist_ops, ordered=False)

                # 6. ledger insert (idempotency marker) — AFTER effects are applied,
                #    so "in ledger" always means "already applied".
                now = dt.datetime.now(dt.timezone.utc)
                ledger_docs = [
                    {"_id": r["eventId"], "userId": r["userId"], "movieId": r["movieId"],
                     "rating": r["rating"], "timestamp": r["timestamp"], "batchId": batch_id, "ingestedAt": now}
                    for r in new_rows
                ]
                try:
                    db.rating_events.insert_many(ledger_docs, ordered=False)
                except Exception as exc:  # noqa: BLE001 - duplicate key on replay is expected/fine
                    if "E11000" not in str(exc):
                        raise

            # 7. commit batch id (always, even for an empty/all-duplicate batch).
            db.pipeline_state.update_one(
                {"_id": "ratings_stream"},
                {"$set": {"lastBatchId": batch_id, "lastRunAt": dt.datetime.now(dt.timezone.utc)}},
                upsert=True,
            )
            print(f"serve_batch[{batch_id}]: committed")
        finally:
            client.close()

    return serve_batch


def start_valid_query(parsed: DataFrame, paths: dict, watermark: str, trigger_seconds: int,
                       hist_cfg: dict, db_name: str):
    """Q2: valid events -> watermark + dedup(eventId) -> foreachBatch(serve_batch)."""
    valid = (
        parsed.filter(F.col("reason").isNull())
        .withWatermark("event_time", watermark)
        .dropDuplicatesWithinWatermark(["eventId"])
    )
    serve_batch = make_serve_batch(paths, hist_cfg, db_name)
    return (
        valid.writeStream.foreachBatch(serve_batch)
        .option("checkpointLocation", paths["checkpoints"]["valid"])
        .trigger(processingTime=f"{trigger_seconds} seconds")
        .start()
    )


def main() -> int:
    cfg = load_streaming_config()
    serving_cfg = load_serving_config()
    paths = cfg["paths"]
    db_name = serving_cfg["mongo"]["db"]

    spark = build_spark("movielens-streaming-pipeline")
    spark.conf.set("spark.sql.streaming.schemaInference", "true")

    movies_df = spark.read.format("mongodb") \
        .option("connection.uri", mongo_uri()) \
        .option("database", db_name) \
        .option("collection", serving_cfg["mongo"]["collections"]["movies"]) \
        .load()

    kafka_servers = os.environ.get(cfg["kafka"]["bootstrap_servers_env"], "kafka:9092")
    q1 = start_raw_query(
        spark, kafka_servers, cfg["kafka"]["topic"], paths,
        cfg["spark"]["trigger_seconds"], cfg["spark"]["max_offsets_per_trigger"],
    )

    parsed = build_parsed_stream(spark, movies_df, paths, cfg["validation"]["max_future_skew_days"])
    q3 = start_quarantine_query(parsed, paths, cfg["spark"]["trigger_seconds"])
    q2 = start_valid_query(
        parsed, paths, cfg["validation"]["watermark"], cfg["spark"]["trigger_seconds"],
        cfg["user_history_update"], db_name,
    )

    print("Streaming pipeline started: Q1 raw, Q2 valid (serve_batch), Q3 quarantine")
    for q in (q1, q2, q3):
        print(f"  {q.name}: id={q.id}")

    # Any of the three queries ending must end the process, so the container's restart policy
    # brings the whole pipeline back; waiting on q2 alone left a dead Q1/Q3 unnoticed.
    spark.streams.awaitAnyTermination()
    return 0


if __name__ == "__main__":
    sys.exit(main())
