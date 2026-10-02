#!/usr/bin/env python3
"""manage_versions.py — WBS 7.6. Rollback the active pointer to the previous
version, or clean up documents of retired versions beyond the retention window
(design.md D-5, D-12). Runs with plain pymongo (no Spark needed).

Run inside the spark container (or any container with pymongo + network access):
    python -m orchestration.manage_versions rollback
    python -m orchestration.manage_versions cleanup --keep 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from pymongo import MongoClient

from loaders.spark_mongo import load_serving_config, mongo_uri


def cmd_rollback(db) -> int:
    pointer = db.serving_meta.find_one({"_id": "active"})
    if not pointer:
        print("FAIL: no active pointer — nothing to roll back")
        return 1
    prev = pointer.get("previousVersion")
    if not prev:
        print("FAIL: no previousVersion recorded — nothing to roll back to")
        return 1

    coll = load_serving_config()["mongo"]["collections"]["user_recommendations"]
    if db[coll].count_documents({"modelVersion": prev}, limit=1) == 0:
        print(f"FAIL: previous version {prev}'s documents no longer exist (cleaned up?) — cannot roll back")
        return 1

    current = pointer["modelVersion"]
    now = dt.datetime.now(dt.timezone.utc)
    artifacts_map = dict(pointer.get("artifacts", {}))
    for key in artifacts_map:
        artifacts_map[key] = prev

    db.serving_meta.replace_one(
        {"_id": "active"},
        {"_id": "active", "modelVersion": prev, "previousVersion": current,
         "artifacts": artifacts_map, "activatedAt": now, "rolledBackFrom": current},
    )
    db.model_registry.update_one({"_id": prev}, {"$set": {"status": "active", "activatedAt": now}})
    db.model_registry.update_one({"_id": current}, {"$set": {"status": "retired", "retiredAt": now}})

    print(f"OK: rolled back active version {current} -> {prev}")
    return 0


def cmd_cleanup(db, keep: int) -> int:
    pointer = db.serving_meta.find_one({"_id": "active"})
    if not pointer:
        print("FAIL: no active pointer")
        return 1

    keep_versions = {pointer["modelVersion"]}
    if pointer.get("previousVersion"):
        keep_versions.add(pointer["previousVersion"])

    retired_desc = list(db.model_registry.find({"status": "retired"}).sort("retiredAt", -1))
    for r in retired_desc:
        if len(keep_versions) >= keep:
            break
        keep_versions.add(r["_id"])

    to_delete = [
        r["_id"] for r in db.model_registry.find({"status": "retired", "_id": {"$nin": list(keep_versions)}})
    ]
    collections = load_serving_config()["mongo"]["collections"]
    removed: dict[str, int] = {}
    if to_delete:
        for key in ("popular_movies", "similar_movies", "user_recommendations"):
            coll = collections[key]
            res = db[coll].delete_many({"modelVersion": {"$in": to_delete}})
            removed[coll] = res.deleted_count

    print(f"OK: kept versions {sorted(keep_versions)}, deleted versions {to_delete}")
    print(f"    docs removed per collection: {removed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rollback")
    p_cleanup = sub.add_parser("cleanup")
    p_cleanup.add_argument("--keep", type=int, default=2)
    args = parser.parse_args()

    db_name = load_serving_config()["mongo"]["db"]
    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=5000)
    db = client[db_name]
    try:
        return cmd_rollback(db) if args.cmd == "rollback" else cmd_cleanup(db, args.keep)
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
