#!/usr/bin/env python3
"""create_indexes.py — WBS 3.1. Idempotent index creation for the serving store
(design.md D-4). `movies`, `rating_events`, `serving_meta`, `model_registry` and
`pipeline_state` rely on Mongo's automatic unique index on `_id` and need no
extra index here. Safe to re-run (create_index is a no-op if the index exists
with the same spec)."""
from __future__ import annotations

import os
import sys

from pymongo import ASCENDING, MongoClient


def create_indexes(db) -> list[str]:
    created = []

    def ensure(collection: str, keys, **kwargs):
        name = db[collection].create_index(keys, **kwargs)
        created.append(f"{collection}: {name} ({keys})")

    ensure("popular_movies", [("scope", ASCENDING), ("modelVersion", ASCENDING)], unique=True)
    ensure("similar_movies", [("movieId", ASCENDING), ("modelVersion", ASCENDING)], unique=True)
    ensure("user_recommendations", [("userId", ASCENDING), ("modelVersion", ASCENDING)], unique=True)
    ensure("user_history", [("userId", ASCENDING)], unique=True)
    ensure("user_rated", [("userId", ASCENDING), ("movieId", ASCENDING)], unique=True)

    return created


def main() -> int:
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "movielens")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001 - want a clear, fail-fast message
        print(f"FAIL: cannot reach MongoDB at {uri}: {exc}")
        return 1

    db = client[db_name]
    created = create_indexes(db)
    print(f"OK: {len(created)} indexes ensured on database '{db_name}'")
    for line in created:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
