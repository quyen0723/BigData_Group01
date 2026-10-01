# models.py — shared dataclasses for the serving layer (Person 2).
# Pure data containers only; no I/O, no Mongo/HTTP dependency here (contract: CONTRACTS.md §3, §4).
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceWeight:
    """One ranked candidate source going into fusion, with its weight (design.md D-8)."""
    name: str            # "als" | "content" | "popularity"
    weight: float


@dataclass(frozen=True)
class RoutingPlan:
    """Output of the router (design.md D-6): which sources to fetch and why."""
    tier: str                      # "0_history" | "few_history" | "enough_history"
    strategy: str                  # "POPULARITY" | "CONTENT+POPULARITY" | "ALS+CONTENT"
    sources: tuple[SourceWeight, ...]
    fallback_reason: str | None = None


@dataclass(frozen=True)
class Candidate:
    """One recommendation candidate before/after fusion."""
    movie_id: int
    rank: int                      # 1-based rank within its source list
    support: int = 0                # tie-break signal (rating count); 0 if unknown
    score: float = 0.0               # fused score once produced by fusion.weighted_rrf


@dataclass(frozen=True)
class RatedMovie:
    """One (userId, movieId) row from `user_rated`, latest-wins per movieId (design.md D-7)."""
    movie_id: int
    rating: float
    rating_ts: int   # epoch seconds


@dataclass(frozen=True)
class HistorySnapshot:
    """Result of history.recompute_history — maps 1:1 to CONTRACTS.md §3.4 fields."""
    interaction_count: int
    recent_movie_ids: tuple[int, ...]
    positive_movie_ids: tuple[int, ...]
    last_updated: int | None   # epoch seconds; None when no ratings


@dataclass(frozen=True)
class RecommendationItem:
    """One item in the final API response (matches contract response shape)."""
    movie_id: int
    title: str
    genres: str
    rank: int
    score: float
    source: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str | None = None   # first failing rule name, per rating-stream-ingestion spec
