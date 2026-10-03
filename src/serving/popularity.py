# popularity.py — live weighted-rating popularity (pure; no I/O).
# Spec: openspec/changes/live-weighted-popularity/specs/live-popularity. Design D-1, D-2, D-4, D-7.
#
# The offline list (Person 1, src/modeling/split_baselines.py) ranks movies by
#     WR = v/(v+m)*R + m/(v+m)*C        R = average rating, v = rating count,
# with C = mean rating of the training split and m = 1000. Here the same formula is applied to the
# training-split statistics (`baseline`) plus the ratings the streaming pipeline applied since (`deltas`,
# taken from the rating_events ledger), so the list moves when ratings arrive.
from __future__ import annotations

import datetime as dt
import heapq
from dataclasses import dataclass
from typing import Iterable, Mapping

from .timeutil import as_utc

# movieId -> (rating count, rating sum). Both for the baseline and for the ledger deltas.
Stats = Mapping[int, tuple[int, float]]

_NO_DELTA = (0, 0.0)


@dataclass(frozen=True)
class PopStat:
    movie_id: int
    v: int              # live rating count (baseline + new)
    r: float            # live average rating
    wr: float           # weighted rating with the m and C that were asked for
    base_v: int         # rating count in the baseline
    new_ratings: int    # ratings counted from the ledger


@dataclass(frozen=True)
class BaselineStats:
    """The training-split statistics (collection `movie_stats`) and what the loader recorded about them."""
    stats: Stats
    c: float                        # mean rating of the training split (the C of the formula)
    cutoff: float                   # epoch seconds: ratings strictly before it are in the baseline
    ratings: int
    movies: int
    generated_at: str               # changes whenever the loader rebuilds the baseline
    ledger_since: dt.datetime | None = None     # ledger events ingested up to here are already inside the baseline


def weighted_rating(v: int, total: float, m: float, c: float) -> float:
    """WR = v/(v+m)*R + m/(v+m)*C, written on the rating sum (R = total/v): (total + m*C)/(v + m)."""
    return (total + m * c) / (v + m)


def rank_top(baseline: Stats, deltas: Stats, *, m: float, c: float, min_support: int, n: int) -> list[PopStat]:
    """Top `n` movies by WR descending, then rating count descending, then movieId ascending (the offline order).

    Only movies with at least `min_support` ratings (baseline + new) are eligible. A movie that is in `deltas`
    but not in `baseline` starts from zero. Result is deterministic for identical inputs.
    """
    def scored():
        for movie_id, (n0, sum0) in baseline.items():
            dn, dsum = deltas.get(movie_id, _NO_DELTA) if deltas else _NO_DELTA
            v = n0 + dn
            if v >= min_support:
                total = sum0 + dsum
                # -movie_id last: with equal WR and v the smaller id must win under "largest first"
                yield (weighted_rating(v, total, m, c), v, -movie_id, total, n0)
        for movie_id, (dn, dsum) in deltas.items():
            if movie_id not in baseline and dn >= min_support:
                yield (weighted_rating(dn, dsum, m, c), dn, -movie_id, dsum, 0)

    top = heapq.nlargest(n, scored())
    return [
        PopStat(movie_id=-neg_id, v=v, r=total / v, wr=wr, base_v=n0, new_ratings=v - n0)
        for wr, v, neg_id, total, n0 in top
    ]


def deltas_from_events(events: Iterable[Mapping], since: dt.datetime | None = None) -> dict[int, tuple[int, float]]:
    """Ledger events -> per-movie (count, sum) of ratings that are not in the baseline yet.

    One rating per (userId, movieId): the latest by (timestamp, ingestedAt, _id), like `user_rated`
    (latest timestamp wins). When `since` is given, an event counts only if its `ingestedAt` is after it (the
    baseline already contains everything up to that moment). This is the reference for the Mongo pipeline in
    MongoServingRepository.get_rating_deltas; the fake repository of the tests uses it directly.
    """
    since_utc = as_utc(since) if since is not None else None
    latest: dict[tuple[int, int], tuple[tuple, float]] = {}
    for e in events:
        ingested = e.get("ingestedAt")
        if since_utc is not None and (ingested is None or as_utc(ingested) <= since_utc):
            continue
        order = (e.get("timestamp") or 0, as_utc(ingested).timestamp() if ingested is not None else 0.0, str(e.get("_id", "")))
        key = (e["userId"], e["movieId"])
        if key not in latest or order >= latest[key][0]:
            latest[key] = (order, float(e["rating"]))

    out: dict[int, tuple[int, float]] = {}
    for (_user, movie_id), (_order, rating) in latest.items():
        n, total = out.get(movie_id, _NO_DELTA)
        out[movie_id] = (n + 1, total + rating)
    return out
