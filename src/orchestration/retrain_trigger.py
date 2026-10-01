#!/usr/bin/env python3
"""retrain_trigger.py — WBS 7.1. Person 2's side of retraining (design.md D-12):
count applied events since the last handoff, and when the threshold is reached
(or --force), export a handoff package for Person 1 to train on — Person 2
never trains; see tasks.md Group 7 header.

Handoff package: <paths.handoff>/<requestId>/
  delta_ratings.parquet  — curated §2.1 schema, the applied events in this window
  manifest.json          — requestId, activeVersion, window, counts, checksum,
                            dedup rule (latest-wins — Open Question D4 with Person 1)

Run inside the spark container:
    python -m orchestration.retrain_trigger [--force]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from pymongo import MongoClient
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType, LongType, StructField, StructType

from loaders.spark_mongo import build_spark, load_serving_config, load_streaming_config, mongo_uri

EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="create a handoff even below the event threshold")
    args = parser.parse_args()

    streaming_cfg = load_streaming_config()
    serving_cfg = load_serving_config()
    n_min = int(streaming_cfg["retrain_trigger"]["n_min_events"])
    db_name = serving_cfg["mongo"]["db"]

    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=10000)
    db = client[db_name]

    state = db.pipeline_state.find_one({"_id": "retrain_handoff"})
    since = state["watermark"] if state and "watermark" in state else EPOCH
    if since.tzinfo is None:
        since = since.replace(tzinfo=dt.timezone.utc)

    pending = list(db.rating_events.find({"ingestedAt": {"$gt": since}}))
    count = len(pending)
    print(f"pending applied events since {since.isoformat()}: {count} (threshold N_min={n_min})")

    if count == 0:
        print("nothing to hand off")
        client.close()
        return 0
    if count < n_min and not args.force:
        print("below threshold and --force not given: no handoff created")
        client.close()
        return 0

    pointer = db.serving_meta.find_one({"_id": "active"})
    active_version = pointer["modelVersion"] if pointer else None

    import uuid
    request_id = str(uuid.uuid4())
    handoff_dir = Path(streaming_cfg["paths"]["handoff"]) / request_id
    handoff_dir.mkdir(parents=True, exist_ok=True)

    spark = build_spark("movielens-retrain-trigger")
    try:
        rows = [(d["userId"], d["movieId"], d["rating"], d["timestamp"]) for d in pending]
        schema = StructType([
            StructField("userId", IntegerType()), StructField("movieId", IntegerType()),
            StructField("rating", DoubleType()), StructField("timestamp", LongType()),
        ])
        delta_df = (
            spark.createDataFrame(rows, schema)
            .withColumn("rating_ts", F.to_timestamp(F.from_unixtime(F.col("timestamp"))))
            .withColumn("year", F.year(F.col("rating_ts")))
        )
        delta_path = str(handoff_dir / "delta_ratings.parquet")
        delta_df.write.mode("overwrite").partitionBy("year").parquet(delta_path)
        n_written = delta_df.count()
    finally:
        spark.stop()

    users = sorted({d["userId"] for d in pending})
    window_start_ts = int(since.timestamp())
    new_user_count = sum(
        1 for uid in users
        if db.user_rated.count_documents({"userId": uid, "ratingTs": {"$lt": window_start_ts}}, limit=1) == 0
    )
    max_event_ts = max(d["timestamp"] for d in pending)
    now = dt.datetime.now(dt.timezone.utc)
    checksum = hashlib.sha256(f"{request_id}:{n_written}:{max_event_ts}".encode()).hexdigest()

    manifest = {
        "requestId": request_id,
        "activeVersion": active_version,
        "proposedVersion": None,  # Person 1 assigns the candidate's semver on handback
        "windowStart": since.isoformat(),
        "windowEnd": now.isoformat(),
        "rowCount": n_written,
        "userCount": len(users),
        "newUserCount": new_user_count,
        "maxEventTimestamp": max_event_ts,
        "dedupRule": "latest-wins per (userId, movieId) by timestamp desc "
                     "(design.md D-12 Open Question D4 — confirm with Person 1)",
        "checksum": checksum,
        "createdAt": now.isoformat(),
    }
    (handoff_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    db.pipeline_state.update_one({"_id": "retrain_handoff"}, {"$set": {"watermark": now}}, upsert=True)
    client.close()

    print(f"OK: handoff package created at {handoff_dir}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
