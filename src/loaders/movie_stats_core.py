"""movie_stats_core.py — the pure part of build_movie_stats (no Spark, no Mongo), so it can be unit-tested.
Spec: openspec/changes/live-weighted-popularity/specs/live-popularity "Baseline statistics from the training split";
design D-2, D-3, D-8."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re

META_ID = "_meta"


class BaselineMismatch(Exception):
    """The ratings counted for the baseline are not the training split of Person 1's run."""


def read_split_stats(text: str) -> dict:
    """evidence/split_stats.csv (one header row, one data row) -> {"n_train": int, "cut_val": float}."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) != 1:
        raise ValueError(f"split_stats.csv must have exactly one data row, found {len(rows)}")
    row = rows[0]
    return {"n_train": int(float(row["n_train"])), "cut_val": float(row["cut_val"])}


def read_recorded_c(text: str) -> float | None:
    """evidence/b3_1_split_baseline.txt records the training-set mean as 'MovieMean global fallback mean=3.5287'."""
    found = re.search(r"global fallback mean=([0-9]+\.[0-9]+)", text)
    return float(found.group(1)) if found else None


def verify_baseline(*, n_ratings: int, mean: float, n_train: int, recorded_c: float) -> None:
    """Refuse a baseline that is not the offline training split: the count must equal `n_train` exactly and the
    mean must equal the recorded C at four decimals (so streamed ratings, val/test ratings or a wrong cutoff are caught)."""
    if n_ratings != n_train:
        raise BaselineMismatch(
            f"counted {n_ratings:,} ratings below the cutoff but the split recorded n_train = {n_train:,}: wrong cutoff "
            "or curated_ratings differs from the run that made the split"
        )
    if round(mean, 4) != round(recorded_c, 4):
        raise BaselineMismatch(f"training mean is {mean:.6f} but the split recorded C = {recorded_c}")


def parse_ledger_since(text: str) -> dt.datetime:
    """`--ledger-since` as the naive-UTC datetime that is stored and compared with `ingestedAt` (pymongo returns naive UTC).
    A value without an offset is UTC, the project rule (serving/timeutil.py): `astimezone` on a naive value would read it as the
    local time of the machine and shift the mark by its UTC offset, double-counting ledger events the baseline already has."""
    value = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value
    return value.astimezone(dt.timezone.utc).replace(tzinfo=None)


def verify_stored(*, stored_ratings: int, stored_sum: float, n_ratings: int, mean: float) -> None:
    """After the write: the n0 values that actually landed in Mongo must add up to the ratings that were counted, and their sums to the
    same mean. Catches a write that has the right number of documents but wrong contents (cast, partial retry)."""
    if stored_ratings != n_ratings:
        raise BaselineMismatch(f"stored n0 add up to {stored_ratings:,} ratings but {n_ratings:,} were counted")
    if stored_ratings and round(stored_sum / stored_ratings, 4) != round(mean, 4):
        raise BaselineMismatch(f"stored sums give a mean of {stored_sum / stored_ratings:.6f}, expected {mean:.6f}")


def make_meta(
    *,
    c: float,
    recorded_c: float,
    cutoff: float,
    cutoff_source: str,
    ratings: int,
    movies: int,
    generated_at: dt.datetime,
    ledger_since: dt.datetime | None,
) -> dict:
    return {
        "_id": META_ID,
        "C": c,                                     # full-precision training mean, what the formula uses
        "cRecorded": recorded_c,                    # 3.5287 as written in the evidence
        "cutoff": cutoff,
        "cutoffSource": cutoff_source,
        "ratings": ratings,
        "movies": movies,
        "generatedAt": generated_at.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "ledgerSince": ledger_since,                # None for a baseline built from the original split
    }
