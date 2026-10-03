#!/usr/bin/env python3
"""purge_curated_synthetic.py — remove the ratings of synthetic demo users from the curated_ratings parquet
(change live-weighted-popularity, design D-12, task 7.4).

The streaming pipeline appends every rating it applies to curated_ratings/year=<year of the rating>. Ratings sent by
scripts/wr_live_demo.py (users 999200001 and up) are made "now", so they all sit in the partition of the current year (a few hundred KB).
Parquet files cannot be edited, so the partition is rewritten without those users: read, filter, write to a temp directory, check the
count, then swap the directories. The old partition is kept next to it as `_purge_old_year=<year>` until you delete it (Spark ignores
directories that start with an underscore).

Run it INSIDE the spark container, and ONLY while the streaming service is stopped (it appends to the same directory):
    docker compose -f docker/docker-compose.yml stop streaming
    docker compose -f docker/docker-compose.yml exec spark python -m loaders.purge_curated_synthetic                 # dry run: counts only
    docker compose -f docker/docker-compose.yml exec spark python -m loaders.purge_curated_synthetic --apply --streaming-stopped
    docker compose -f docker/docker-compose.yml start streaming
Use --path to rehearse on a copy of the bundle. Users outside 999,000,000..999,999,999 are never touched (loaders/synthetic_users.py).
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from loaders.synthetic_users import RESERVED_HIGH, RESERVED_LOW, validate_range

DEFAULT_PATH = "/data/curated/curated_ratings"
DEFAULT_LOW = 999_200_000
DEFAULT_HIGH = 999_299_999


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--path", default=DEFAULT_PATH, help="the curated_ratings directory (default %(default)s)")
    ap.add_argument("--year", type=int, default=time.gmtime().tm_year, help="partition to rewrite (default: the current year)")
    ap.add_argument("--from", dest="low", type=int, default=DEFAULT_LOW)
    ap.add_argument("--to", dest="high", type=int, default=DEFAULT_HIGH)
    ap.add_argument("--all-synthetic", action="store_true", help=f"the whole reserved range {RESERVED_LOW:,}..{RESERVED_HIGH:,}")
    ap.add_argument("--apply", action="store_true", help="rewrite the partition (without it: counts only)")
    ap.add_argument("--streaming-stopped", action="store_true", help="confirm that the streaming service is stopped (required with --apply)")
    args = ap.parse_args(argv)
    low, high = (RESERVED_LOW, RESERVED_HIGH) if args.all_synthetic else (args.low, args.high)
    try:
        validate_range(low, high)
    except ValueError as exc:
        print(f"REFUSED: {exc}")
        return 2
    if args.apply and not args.streaming_stopped:
        print("REFUSED: --apply needs --streaming-stopped (the streaming service appends to this partition; stop it first)")
        return 2

    root = Path(args.path)
    partition = root / f"year={args.year}"
    tmp = root / f"_purge_tmp_year={args.year}"
    old = root / f"_purge_old_year={args.year}"
    if not partition.is_dir() and (tmp.exists() or old.exists()):
        # a run was interrupted between the two renames (see below): the data is safe in the underscore directories
        print(f"{partition} is MISSING but {tmp.name} / {old.name} exist: an earlier run stopped between the two renames.")
        print(f"  roll forward (keep the purged data):  mv {tmp} {partition}")
        print(f"  roll back (the original, unpurged):   mv {old} {partition}")
        return 2
    if not partition.is_dir():
        print(f"no partition {partition}: nothing to do")
        return 0

    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = (SparkSession.builder.appName("movielens-purge-curated-synthetic").master("local[2]")
             .config("spark.ui.showConsoleProgress", "false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    try:
        df = spark.read.parquet(str(partition))
        in_range = (F.col("userId") >= low) & (F.col("userId") <= high)
        total = df.count()
        remove = df.filter(in_range).count()
        users = df.filter(in_range).select("userId").distinct().count()
        print(f"{partition}: {total:,} ratings, {remove:,} from {users} synthetic users in {low}..{high}")
        if remove == 0:
            print("nothing to remove")
            return 0
        if not args.apply:
            print("dry run: nothing changed. Add --apply --streaming-stopped to rewrite the partition.")
            return 0

        if tmp.exists():
            print(f"REFUSED: {tmp} exists: an earlier run stopped while writing the purged copy. It is incomplete: delete it, then run again.")
            return 2
        if old.exists():
            print(f"REFUSED: {old} exists: it is the original partition kept by an earlier purge. Delete it (or move it away) once you are "
                  "satisfied, then run again.")
            return 2
        df.filter(~in_range).write.mode("errorifexists").parquet(str(tmp))
        kept = spark.read.parquet(str(tmp)).count()
        # This count is not a formality: a row whose userId is NULL satisfies neither `in_range` nor `~in_range`, so the filter above
        # would silently drop it. If this check ever fails, look for NULL userIds before "simplifying" it away.
        if kept != total - remove:
            print(f"FAIL: the rewritten copy has {kept:,} ratings, expected {total - remove:,}; the original partition was not touched")
            shutil.rmtree(tmp, ignore_errors=True)
            return 1
        print(f"swapping: if this is interrupted between the two renames, {partition.name} will be missing; rerun this command for the "
              f"recovery commands (roll forward: mv {tmp.name} {partition.name}; roll back: mv {old.name} {partition.name}).")
        partition.rename(old)
        tmp.rename(partition)
        print(f"OK: {partition} rewritten with {kept:,} ratings. The old partition is kept at {old} ({total:,} ratings): delete it when satisfied.")
        return 0
    finally:
        spark.stop()


if __name__ == "__main__":
    sys.exit(main())
