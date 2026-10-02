# history.py — recompute user_history from a user's rated-movie set (pure).
# Spec: specs/serving-store/spec.md "User history aggregation" +
#       specs/rating-stream-ingestion/spec.md "Immediate serving-state update".
# Design: design.md D-10 step 5 — the state is *recomputed* from the full rated
# set (not incremented), which is what makes the streaming write idempotent under
# at-least-once replay (spec: "Batch replay after crash", "Re-rating a movie").
from __future__ import annotations

from .models import HistorySnapshot, RatedMovie


def recompute_history(
    rated_movies: list[RatedMovie],
    recent_cap: int,
    positive_cap: int,
    positive_threshold: float = 4.0,
) -> HistorySnapshot:
    """Derive a CONTRACTS.md §3.4 document from a user's full rated-movie set.

    `rated_movies` MUST already be deduplicated by movie_id with latest-timestamp-wins
    (that is `user_rated`'s job, design.md D-7) — re-rating the same movie must appear
    at most once here, which is what makes `interaction_count` "distinct movies rated".

    Ordering within recent/positive: most recent rating_ts first, ties broken by
    movie_id ascending (deterministic replay — same input always yields the same
    bounded arrays, regardless of the order events arrived in this batch).
    """
    if not rated_movies:
        return HistorySnapshot(
            interaction_count=0,
            recent_movie_ids=(),
            positive_movie_ids=(),
            last_updated=None,
        )

    by_recency = sorted(rated_movies, key=lambda r: (-r.rating_ts, r.movie_id))

    recent_ids = tuple(r.movie_id for r in by_recency[:recent_cap])
    positive_ids = tuple(
        r.movie_id for r in by_recency if r.rating >= positive_threshold
    )[:positive_cap]

    return HistorySnapshot(
        interaction_count=len(rated_movies),
        recent_movie_ids=recent_ids,
        positive_movie_ids=positive_ids,
        last_updated=max(r.rating_ts for r in rated_movies),
    )


def apply_rating(
    existing_rated: list[RatedMovie],
    new_movie_id: int,
    new_rating: float,
    new_rating_ts: int,
) -> list[RatedMovie]:
    """Merge one new/updated rating into a user's rated-movie set with
    latest-timestamp-wins (design.md D-7, spec: "Re-rating a movie").

    Returns a NEW list; does not mutate `existing_rated`. Applying the exact same
    (movie_id, rating, ts) twice is a no-op on the resulting set, which is what
    makes `serve_batch` step 4+5 safe to replay (spec: "Batch replay after crash").
    """
    kept = [r for r in existing_rated if r.movie_id != new_movie_id]
    current = next((r for r in existing_rated if r.movie_id == new_movie_id), None)
    if current is not None and current.rating_ts > new_rating_ts:
        # An existing rating is newer than the incoming one: latest-wins keeps it.
        kept.append(current)
    else:
        kept.append(RatedMovie(movie_id=new_movie_id, rating=new_rating, rating_ts=new_rating_ts))
    return kept
