#!/usr/bin/env python3
"""purge_demo_ratings.py — remove the ratings of synthetic demo users from MongoDB (change live-weighted-popularity, design D-12).

wr_live_demo.py sends ratings from users 999200001 and up. They end up in four places:
    rating_events   the ledger (live popularity counts it, and retrain_trigger exports it in the handoff package!)
    user_rated      one document per (user, movie)
    user_history    one document per user
    curated_ratings the parquet bundle (NOT touched here: it is append-only files, see docs/TESTING_GUIDE.md "Dọn dữ liệu giả")
so run this BEFORE any retrain handoff. It never touches a user id outside 999,000,000..999,999,999 (real MovieLens ids stop at
about 330,000 and the demo personas are 700008, 1 and 127249).

    .venv-serving/Scripts/python scripts/purge_demo_ratings.py # dry run: counts only (default range 999200000..999299999)
    .venv-serving/Scripts/python scripts/purge_demo_ratings.py --yes   # delete
    .venv-serving/Scripts/python scripts/purge_demo_ratings.py --all-synthetic --yes   # the whole reserved range, incl. the older 999100001..999100010
Mongo: MONGO_URI (default mongodb://localhost:27017, the port the compose file publishes), database from configs/serving.yaml.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from loaders.synthetic_users import RESERVED_HIGH, RESERVED_LOW, validate_range  # noqa: E402  (the one rule, shared with the parquet job)

DEFAULT_LOW = 999_200_000
DEFAULT_HIGH = 999_299_999
COLLECTIONS = ("rating_events", "user_rated", "user_history")      # logical names; all three have the user in `userId`


def real_names(collections: dict[str, str] | None) -> dict[str, str]:
    """Logical name -> the collection name the stack really uses (`mongo.collections` in configs/serving.yaml), so an overridden name
    can never make the purge count and delete in a collection that nothing reads."""
    mapping = collections or {}
    return {logical: mapping.get(logical, logical) for logical in COLLECTIONS}


def user_filter(low: int, high: int) -> dict:
    return {"userId": {"$gte": low, "$lte": high}}


def count(db, low: int, high: int, names: dict[str, str] | None = None) -> dict[str, int]:
    names = names or real_names(None)
    flt = user_filter(low, high)
    return {logical: db[names[logical]].count_documents(flt) for logical in COLLECTIONS}


def purge(db, low: int, high: int, apply: bool, names: dict[str, str] | None = None) -> dict[str, dict[str, int]]:
    """Counts before, what was deleted (empty on a dry run) and what is left, by logical collection name. The ledger is deleted last:
    it is what live popularity and the retrain handoff read, so if the run stops half way it still lists the rest and running the
    same command again finishes the job."""
    validate_range(low, high)
    names = names or real_names(None)
    before = count(db, low, high, names)
    deleted: dict[str, int] = {}
    if apply:
        flt = user_filter(low, high)
        for logical in ("user_history", "user_rated", "rating_events"):
            deleted[logical] = db[names[logical]].delete_many(flt).deleted_count
    return {"before": before, "deleted": deleted, "after": count(db, low, high, names) if apply else before}


def main(argv: list[str] | None = None, db=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="low", type=int, default=DEFAULT_LOW)
    ap.add_argument("--to", dest="high", type=int, default=DEFAULT_HIGH)
    ap.add_argument("--all-synthetic", action="store_true", help=f"the whole reserved range {RESERVED_LOW:,}..{RESERVED_HIGH:,}")
    ap.add_argument("--yes", action="store_true", help="really delete (without it nothing is deleted)")
    ap.add_argument("--dry-run", action="store_true", help="the default; accepted so a command line can say it")
    args = ap.parse_args(argv)
    low, high = (RESERVED_LOW, RESERVED_HIGH) if args.all_synthetic else (args.low, args.high)
    apply = args.yes and not args.dry_run

    try:
        validate_range(low, high)
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2

    names = real_names(None)
    if db is None:
        import pymongo
        from serving.config import load_serving_config

        mongo_cfg = load_serving_config().mongo
        client = pymongo.MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000)
        db = client[mongo_cfg.db]
        names = real_names(mongo_cfg.collections)

    result = purge(db, low, high, apply, names)
    print(f"users {low}..{high}")
    for name in COLLECTIONS:
        shown = name if names[name] == name else f"{name} ({names[name]})"
        line = f"  {shown:14s} {result['before'][name]:>6} documents"
        if apply:
            line += f" -> deleted {result['deleted'][name]}, left {result['after'][name]}"
        print(line)
    if not apply:
        print("dry run: nothing deleted. Add --yes to delete.")
        return 0
    if any(result["after"].values()):
        print("WARNING: some documents are still there (another run is writing?)")
        return 1
    print("done. Live popularity drops these ratings within its cache time (a couple of seconds).")
    print("curated_ratings (parquet) still holds the ratings of the purged users: see docs/TESTING_GUIDE.md before a retrain handoff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
