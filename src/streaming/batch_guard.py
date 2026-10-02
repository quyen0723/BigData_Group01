# batch_guard.py — decide whether serve_batch may skip a micro-batch (pure apart from one file read).
# Spec: specs/rating-stream-ingestion/spec.md "Batch guard bound to the checkpoint that wrote it".
# Design: address-person1-review-findings D-2.
#
# Spark numbers micro-batches per checkpoint, Mongo's `lastBatchId` outlives the checkpoint. If the
# checkpoint directory is lost, Spark counts from 0 again and a bare `batch_id <= lastBatchId` test
# drops every batch until the counter overtakes the old value, while the log still says "already
# committed". The guard therefore also compares the stream identity Spark keeps in
# `<checkpoint>/metadata`, and skips only when both match.
#
# Skipping is an optimisation, never a correctness requirement: every replay goes through the
# `rating_events` ledger dedup in serve_batch, so processing a batch that was already applied
# writes nothing new. Whenever the identity is unknown or different, the answer is PROCESS.
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SKIP = "skip"
PROCESS = "process"


@dataclass(frozen=True)
class BatchDecision:
    action: str            # SKIP | PROCESS
    reason: str            # log line text
    warn: bool = False     # the situation needs a warning in the log, not just info


def read_stream_id(checkpoint_dir: str | Path) -> str | None:
    """Stream id from `<checkpoint_dir>/metadata` (`{"id": "<uuid>"}`), None when the file is
    missing, unreadable or not what Spark writes."""
    try:
        text = (Path(checkpoint_dir) / "metadata").read_text(encoding="utf-8")
        stream_id = json.loads(text).get("id")
    except (OSError, ValueError, AttributeError):
        return None
    return stream_id if isinstance(stream_id, str) and stream_id else None


def decide_batch_action(state: dict | None, batch_id: int, stream_id: str | None) -> BatchDecision:
    """`state` is the `pipeline_state.ratings_stream` document (or None), `stream_id` the identity
    of the running checkpoint (or None when it could not be read)."""
    if not state or "lastBatchId" not in state:
        return BatchDecision(PROCESS, "no committed batch recorded")

    last_batch_id = state["lastBatchId"]
    recorded = state.get("streamId")

    if stream_id is None:
        return BatchDecision(
            PROCESS, "checkpoint identity unreadable, not skipping any batch (ledger dedup still applies)", warn=True)
    if not recorded:
        return BatchDecision(
            PROCESS, f"no recorded stream identity (lastBatchId={last_batch_id}), processing batch", warn=True)
    if recorded != stream_id:
        return BatchDecision(
            PROCESS,
            f"checkpoint changed (recorded {recorded}, running {stream_id}): lastBatchId={last_batch_id} no longer applies",
            warn=True)
    if batch_id <= last_batch_id:
        return BatchDecision(SKIP, f"already committed (last={last_batch_id}), skipping")
    return BatchDecision(PROCESS, "new batch")
