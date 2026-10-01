#!/usr/bin/env python3
"""stage_candidate.py — WBS 7.3. Import a candidate's 3 serving artifacts as
STAGED (design.md D-12 step 4): loaded into Mongo under their own `version`, but
nothing serves them yet — the API always reads `serving_meta`'s pointer, and
this script never touches it (design.md D-5: only `activate.py` does, and only
after promotion_gate PASSes).

Expects a candidate directory with the same layout Person 1's notebooks produce:
  <candidate-dir>/popular_movies.json
  <candidate-dir>/similar_movies.json
  <candidate-dir>/als_topn.json
  <candidate-dir>/model_card.json

Run inside the spark container:
    python -m orchestration.stage_candidate --version v1.1.0 --candidate-dir /data/candidates/v1.1.0
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from pymongo import MongoClient

from loaders.load_artifacts import ARTIFACTS, load_one
from loaders.spark_mongo import build_spark, load_serving_config, mongo_uri


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--candidate-dir", required=True, help="e.g. /data/candidates/v1.1.0")
    args = parser.parse_args()

    cand_dir = Path(args.candidate_dir)
    serving_cfg = load_serving_config()
    db_name = serving_cfg["mongo"]["db"]

    spark = build_spark("movielens-stage-candidate")
    results: dict[str, dict] = {}
    try:
        for key, spec in ARTIFACTS.items():
            path = cand_dir / spec["filename"]
            if not path.exists():
                print(f"FAIL: missing {path} for artifact '{key}'")
                return 1
            try:
                results[key] = load_one(spark, key, args.version, str(path))
            except ValueError as exc:
                print(f"FAIL: {exc}")
                return 1
            print(f"OK: staged {key} -> {results[key]['collection']} ({results[key]['docsWritten']:,} docs)")
    finally:
        spark.stop()

    model_card_path = cand_dir / "model_card.json"
    model_card = json.loads(model_card_path.read_text(encoding="utf-8")) if model_card_path.exists() else {}
    if model_card and model_card.get("modelVersion") != args.version:
        print(f"FAIL: model_card.json modelVersion ({model_card.get('modelVersion')}) != --version ({args.version})")
        return 1

    client = MongoClient(mongo_uri(), serverSelectionTimeoutMS=5000)
    db = client[db_name]
    db.model_registry.replace_one(
        {"_id": args.version},
        {
            "_id": args.version,
            "status": "staged",
            "modelCard": model_card,
            "loadResults": results,
            "candidateDir": str(cand_dir),
            "importedAt": dt.datetime.now(dt.timezone.utc),
        },
        upsert=True,
    )
    client.close()

    print(f"\nOK: {args.version} staged (model_registry.status=staged). Not serving yet.")
    print(f"Next: python -m orchestration.promotion_gate --version {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
