#!/usr/bin/env python3
"""bootstrap_registry.py — WBS 3.5. First-time activation of a model version: no
previous active version exists yet, so this only runs the artifact-integrity
checks (promotion_gate's G4-G7, design.md D-12) — not the RMSE comparison checks
(G1-G3), which need an existing active version to compare against.

Writes `model_registry{_id: version}` (status="active") and `serving_meta{_id:
"active"}` (the pointer every recommendation request reads, design.md D-5).

Run inside the spark container (or any container with pymongo + the mounted bundle):
    python -m loaders.bootstrap_registry --version v1.0.0

This is the FIRST load only. It refuses to replace an active pointer that names another
version (that is what orchestration.promotion_gate / manage_versions are for, with their
checks), and its exact document counts stop matching once streaming has applied events or a
second version was loaded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from pymongo import MongoClient

# EDA/MODEL_DESIGN.md §4: 80,505 movies have a non-empty similar list (7,080 have
# no genres and are excluded by design, not a bug). Not a hard assert — a WARN
# lets a legitimately different M2 handoff still bootstrap, but the number is
# printed so a real mismatch is visible immediately.
EXPECTED = {
    "popular_movies": 1,
    "movies": 87_585,
    "user_history": 200_948,
    "user_rated": 32_000_204,
}
EXPECTED_SIMILAR_MOVIES_APPROX = 80_505


def active_pointer_conflict(existing: dict | None, version: str) -> str | None:
    """Reason to refuse when `serving_meta.active` already names a different version, else None."""
    if not existing or existing.get("modelVersion") in (None, version):
        return None
    return (
        f"{existing['modelVersion']} is already the active serving version; refusing to replace it with {version}. "
        "Change the active version with orchestration.promotion_gate (new version) or "
        "orchestration.manage_versions (rollback), which run their checks first."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--model-card", default="/data/artifacts/model_card.json")
    args = parser.parse_args()

    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB", "movielens")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    db = client[db_name]

    conflict = active_pointer_conflict(db["serving_meta"].find_one({"_id": "active"}), args.version)
    if conflict:
        print(f"REFUSED: {conflict}")
        client.close()
        return 2

    checks: list[tuple[str, bool, str]] = []

    for collection, expected in EXPECTED.items():
        actual = db[collection].count_documents({})
        ok = actual == expected
        checks.append((f"G4 {collection} count", ok, f"expected {expected:,}, got {actual:,}"))

    n_recs = db["user_recommendations"].count_documents({"modelVersion": args.version})
    checks.append(("G4 user_recommendations has docs", n_recs > 0, f"{n_recs:,} docs for {args.version}"))

    n_similar = db["similar_movies"].count_documents({"modelVersion": args.version})
    similar_ok = abs(n_similar - EXPECTED_SIMILAR_MOVIES_APPROX) < 1000
    checks.append((
        "G4 similar_movies count (~expected)", similar_ok,
        f"expected ~{EXPECTED_SIMILAR_MOVIES_APPROX:,}, got {n_similar:,}",
    ))

    # G5: no already-rated movie in any user_recommendations doc (full check via
    # aggregation, not a sample — mirrors Person 1's notebook 03 KILL-CONTRACT gate).
    leaked = db["user_recommendations"].aggregate([
        {"$match": {"modelVersion": args.version}},
        {"$unwind": "$recommendations"},
        {"$lookup": {
            "from": "user_rated",
            "let": {"uid": "$userId", "mid": "$recommendations.movieId"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$userId", "$$uid"]}, {"$eq": ["$movieId", "$$mid"]},
                ]}}},
            ],
            "as": "rated_match",
        }},
        {"$match": {"rated_match": {"$ne": []}}},
        {"$count": "n_leaked"},
    ])
    leaked_count = next(leaked, {"n_leaked": 0})["n_leaked"]
    checks.append(("G5 no already-rated in user_recommendations", leaked_count == 0, f"{leaked_count} leaked"))

    print(f"=== Bootstrap gate for {args.version} ===")
    all_ok = True
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        all_ok = all_ok and ok

    if not all_ok:
        print("\nBootstrap gate FAILED — serving_meta NOT written. Fix the load and rerun.")
        return 1

    model_card = {}
    card_path = Path(args.model_card)
    if card_path.exists():
        model_card = json.loads(card_path.read_text(encoding="utf-8"))

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    db["model_registry"].replace_one(
        {"_id": args.version},
        {
            "_id": args.version,
            "status": "active",
            "modelCard": model_card,
            "gateReport": {"mode": "bootstrap", "checks": [
                {"name": n, "pass": ok, "detail": d} for n, ok, d in checks
            ]},
            "importedAt": now,
            "activatedAt": now,
        },
        upsert=True,
    )
    db["serving_meta"].replace_one(
        {"_id": "active"},
        {
            "_id": "active",
            "modelVersion": args.version,
            "previousVersion": None,
            "artifacts": {
                "user_recommendations": args.version,
                "similar_movies": args.version,
                "popular_movies": args.version,
            },
            "activatedAt": now,
        },
        upsert=True,
    )

    print(f"\nOK: {args.version} is now the active serving version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
