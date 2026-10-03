"""synthetic_users.py — the one rule about which user ids may be purged (pure; no Spark, no Mongo).
Used by scripts/purge_demo_ratings.py (Mongo) and loaders/purge_curated_synthetic.py (parquet).
Real MovieLens ids stop at about 330,000, the demo personas are 700008 / 1 / 127249, demo accounts made on the page are 500000..599998."""
from __future__ import annotations

RESERVED_LOW = 999_000_000
RESERVED_HIGH = 999_999_999


def validate_range(low: int, high: int) -> None:
    """Only the reserved synthetic range may ever be deleted."""
    if low > high:
        raise ValueError(f"empty range {low}..{high}")
    if low < RESERVED_LOW or high > RESERVED_HIGH:
        raise ValueError(
            f"{low}..{high} is not inside the reserved synthetic range {RESERVED_LOW:,}..{RESERVED_HIGH:,}; "
            "real MovieLens users and the demo personas are never purged"
        )
