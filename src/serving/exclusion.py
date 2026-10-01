# exclusion.py — exact already-rated exclusion (pure).
# Spec: specs/recommendation-api/spec.md "Exact already-rated exclusion".
# Design: design.md D-7. The caller is responsible for fetching `rated_movie_ids`
# from MongoDB's `user_rated` collection (covered $in query) — this module only
# applies the set-difference so the rule is unit-testable without a live database.
from __future__ import annotations

from typing import Iterable

from .models import Candidate


def exclude_rated(candidates: Iterable[Candidate], rated_movie_ids: frozenset[int]) -> list[Candidate]:
    """Drop every candidate whose movie_id is in the user's exact rated set.

    Order of the surviving candidates is preserved (callers rely on this for
    rank-stable fusion input).
    """
    return [c for c in candidates if c.movie_id not in rated_movie_ids]


def exclude_rated_ids(movie_ids: Iterable[int], rated_movie_ids: frozenset[int]) -> list[int]:
    """Same rule, but for plain movieId lists (e.g. content-similarity seeds)."""
    return [m for m in movie_ids if m not in rated_movie_ids]
