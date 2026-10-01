# schemas.py — rating event shape (CONTRACTS.md §5).
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RatingEvent:
    event_id: str
    user_id: int
    movie_id: int
    rating: float
    timestamp: int     # epoch seconds
    source: str = "web"

    @staticmethod
    def from_dict(d: dict) -> "RatingEvent":
        return RatingEvent(
            event_id=str(d.get("eventId", "")),
            user_id=int(d.get("userId", 0)),
            movie_id=int(d.get("movieId", 0)),
            rating=float(d.get("rating", 0.0)),
            timestamp=int(d.get("timestamp", 0)),
            source=str(d.get("source", "web")),
        )
