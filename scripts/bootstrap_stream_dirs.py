#!/usr/bin/env python3
"""bootstrap_stream_dirs.py — WBS 2.5 (Person 2).

Creates the stream/ subdirectories under the local `movielens32m/` bundle and
fails fast, naming the missing path, when a required M2 artifact is absent —
so a broken environment is caught before `docker compose up` instead of failing
deep inside a Spark job. Run on the HOST before starting the stack (paths here
are the host-side mount source for docker/docker-compose.yml's `../movielens32m`).

Usage:
    python scripts/bootstrap_stream_dirs.py [--bundle-root PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Required M2 handoff artifacts (docs/MODEL_DESIGN.md §7, README_COLAB_SETUP.md §5).
# Parquet outputs are directories (Spark writes them as such); JSON artifacts are files.
REQUIRED_PATHS = [
    "artifacts/popular_movies.json",
    "artifacts/similar_movies.json",
    "artifacts/als_topn.json",
    "artifacts/user_history_seed.parquet",
    "artifacts/model_card.json",
    "models/als_v1.0.0",
    "curated/curated_ratings",
    "curated/curated_movies",
]

STREAM_SUBDIRS = [
    "stream/raw_events",
    "stream/quarantine",
    "stream/checkpoints/raw",
    "stream/checkpoints/valid",
    "stream/checkpoints/invalid",
    "stream/handoff",
    "candidates",
]


def check_required(bundle_root: Path) -> list[str]:
    missing = []
    for rel in REQUIRED_PATHS:
        if not (bundle_root / rel).exists():
            missing.append(rel)
    return missing


def create_stream_dirs(bundle_root: Path) -> list[Path]:
    created = []
    for rel in STREAM_SUBDIRS:
        d = bundle_root / rel
        d.mkdir(parents=True, exist_ok=True)
        created.append(d)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle-root",
        default=str(REPO_ROOT / "movielens32m"),
        help="Path to the downloaded M2 Drive bundle (default: <repo>/movielens32m)",
    )
    args = parser.parse_args()
    bundle_root = Path(args.bundle_root)

    if not bundle_root.exists():
        print(f"FAIL: bundle root not found: {bundle_root}")
        print("  -> download it first: README.md 'M2 package' link "
              "(https://drive.google.com/drive/folders/1nruGnD_DvSZqAfhwpC7tk_Va6pyUw3yF)")
        return 1

    missing = check_required(bundle_root)
    if missing:
        print(f"FAIL: {len(missing)} required M2 artifact(s) missing under {bundle_root}:")
        for rel in missing:
            print(f"  - {rel}")
        print("  -> see notebooks/colab/README_COLAB_SETUP.md section 5 for the expected layout")
        return 1

    (REPO_ROOT / "logs").mkdir(parents=True, exist_ok=True)
    created = create_stream_dirs(bundle_root)

    print(f"OK: all {len(REQUIRED_PATHS)} required artifacts present under {bundle_root}")
    print(f"OK: {len(created)} stream directories ready:")
    for d in created:
        print(f"  - {d.relative_to(bundle_root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
