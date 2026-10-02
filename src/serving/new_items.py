# new_items.py — "new movie" candidate source (pure; no I/O).
# Spec: specs/new-movie-cold-start/spec.md "New-movie candidate source".
# Design: demo-use-case-scenarios design.md D-5, D-6.
#
# similar_movies is precomputed per movie, so a movie created after the model was
# built is in nobody's list. This module matches such movies to a user's taste
# directly from genres, and places them in a reserved slot instead of competing in RRF.
from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Iterable

from .models import Candidate
from .timeutil import as_utc

NEW_SOURCE = "new"
GENRE_SEPARATOR = "|"
NO_GENRES = "(no genres listed)"


def _genres_of(genres: str) -> list[str]:
    return [g for g in genres.split(GENRE_SEPARATOR) if g and g != NO_GENRES]


def genre_profile(seed_genres: Iterable[str]) -> dict[str, float]:
    """`seed_genres` is the `genres` string of each seed movie (e.g. "Crime|Drama").
    Returns genre -> share of the user's seed genres; shares sum to 1, empty when no seed has genres."""
    counts = Counter(g for genres in seed_genres for g in _genres_of(genres))
    total = sum(counts.values())
    if total == 0:
        return {}
    return {genre: n / total for genre, n in counts.items()}


def _epoch(value: dt.datetime) -> float:
    return as_utc(value).timestamp()


def score_new_movies(profile: dict[str, float], movies: Iterable[dict]) -> list[tuple[int, float]]:
    """Each movie is a dict with `_id`, `genres` and `addedAt`. Score = sum of the profile
    share of every genre the movie has; movies with no overlap are dropped. Order: score
    descending, then newest `addedAt`, then lowest movieId (deterministic)."""
    scored = []
    for movie in movies:
        score = sum(profile.get(g, 0.0) for g in _genres_of(movie.get("genres", "")))
        if score > 0:
            scored.append((movie["_id"], score, _epoch(movie["addedAt"])))
    scored.sort(key=lambda t: (-t[1], -t[2], t[0]))
    return [(movie_id, score) for movie_id, score, _ in scored]


def place_new_items(
    final: list[Candidate],
    new_movie_ids: list[int],
    slots: int,
    position: int,
    k: int,
) -> list[Candidate]:
    """Insert up to `slots` new movies starting at 1-based rank `position`, shifting the rest
    down, and cut back to `k`. Every placed item takes the fused score of the FIRST item it displaces
    (the last item's score when placing at the end) so the response scores never increase, for any
    number of slots (genre scores live on a different scale from RRF scores). Movies already in
    `final` are skipped."""
    present = {c.movie_id for c in final}
    to_place = [mid for mid in new_movie_ids if mid not in present][:slots]
    if not to_place:
        return final[:k]

    index = min(max(position, 1) - 1, len(final))
    if index < len(final):
        placed_score = final[index].score
    else:
        placed_score = final[-1].score if final else 0.0
    placed = [Candidate(movie_id=mid, rank=0, support=0, score=placed_score) for mid in to_place]
    return (final[:index] + placed + final[index:])[:k]
