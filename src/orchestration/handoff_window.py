# handoff_window.py — which ledger events belong in a retraining handoff package (pure).
# Spec: specs/model-refresh-orchestration/spec.md "Handoff window bounded by committed events".
# Design: address-person1-review-findings D-1.
#
# serve_batch stamps one `ingestedAt` on a whole batch, inserts its ledger documents
# (insert_many, not atomic) and only then records `lastRunAt` in
# pipeline_state.ratings_stream. Batches run one at a time, so every event with
# `ingestedAt <= lastRunAt` belongs to a batch that has fully committed, and a batch still
# being written always has `ingestedAt > lastRunAt`. Bounding the window above by `lastRunAt`
# therefore never exports half of a batch, and using that same bound as the next watermark
# leaves no gap between two handoffs. No import from pyspark/pymongo on purpose (unit tests).
from __future__ import annotations

import datetime as dt

from serving.timeutil import as_utc


def committed_up_to(stream_state: dict | None) -> dt.datetime | None:
    """`lastRunAt` of the last committed micro-batch (UTC), or None when streaming has
    never committed a batch (no state document, or one without `lastRunAt`)."""
    if not stream_state:
        return None
    last_run = stream_state.get("lastRunAt")
    return as_utc(last_run) if last_run else None


def in_window(ingested_at: dt.datetime, since: dt.datetime, upper: dt.datetime) -> bool:
    """True for ledger events in `(since, upper]`."""
    moment = as_utc(ingested_at)
    return as_utc(since) < moment <= as_utc(upper)


def window_query(since: dt.datetime, upper: dt.datetime) -> dict:
    """Mongo filter for `rating_events` selecting exactly what `in_window` accepts."""
    return {"ingestedAt": {"$gt": as_utc(since), "$lte": as_utc(upper)}}
