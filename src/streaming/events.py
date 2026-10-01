# events.py — rating event schema + validation rules (pure).
# Spec: specs/rating-stream-ingestion/spec.md "Validation and quarantine".
# Contract: contracts/CONTRACTS.md §5. Design: design.md D-9.
#
# This module has no Spark/Kafka dependency on purpose: the same rule set is used
# by (1) the Structured Streaming job (wrapped in a pandas UDF / plain function call
# per micro-batch row) and (2) unit tests that run without any live infra.
from __future__ import annotations

from typing import Iterable

from streaming.schemas import RatingEvent
from serving.models import ValidationResult

VALID_RATINGS = frozenset({0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0})

REASON_BAD_EVENT_ID = "invalid_event_id"
REASON_BAD_USER_ID = "invalid_user_id"
REASON_UNKNOWN_MOVIE = "unknown_movie_id"
REASON_BAD_RATING = "invalid_rating_value"
REASON_BAD_TIMESTAMP = "invalid_timestamp"


def validate_event(
    event: RatingEvent,
    known_movie_ids: Iterable[int] | frozenset[int],
    now_ts: int,
    max_future_skew_days: int = 1,
) -> ValidationResult:
    """Apply CONTRACTS.md §5 rules in order; return the FIRST failing rule as the
    quarantine reason (spec: "first failing rule"). `known_movie_ids` should be a
    frozenset for O(1) lookup in the streaming job (broadcast join in Spark; plain
    set here for unit tests)."""
    if not isinstance(known_movie_ids, frozenset):
        known_movie_ids = frozenset(known_movie_ids)

    if not event.event_id or not event.event_id.strip():
        return ValidationResult(False, REASON_BAD_EVENT_ID)

    if event.user_id <= 0:
        return ValidationResult(False, REASON_BAD_USER_ID)

    if event.movie_id not in known_movie_ids:
        return ValidationResult(False, REASON_UNKNOWN_MOVIE)

    if event.rating not in VALID_RATINGS:
        return ValidationResult(False, REASON_BAD_RATING)

    max_future_ts = now_ts + max_future_skew_days * 86400
    if event.timestamp <= 0 or event.timestamp > max_future_ts:
        return ValidationResult(False, REASON_BAD_TIMESTAMP)

    return ValidationResult(True, None)
