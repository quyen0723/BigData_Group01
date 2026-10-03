# catalog.py — movie catalog search for the demo pages (change movie-catalog-search).
# Spec: openspec/changes/movie-catalog-search/specs/movie-catalog. Design D-1..D-4.
#
# `search` is pure: entries in, a page of rows out. The statistics (average rating, WR) come from the same baseline-plus-ledger numbers as the
# popular list; sorting by them cannot be pushed down to Mongo, so the whole catalog (about 87k small entries) is filtered and sorted in memory.
# `CatalogCache` keeps the entries for 30 seconds so a search does not read the `movies` collection each time.
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .popularity import Stats, weighted_rating

SORTS = ("title", "ratings", "avg", "wr")
ORDERS = ("asc", "desc")
NO_GENRES = "(no genres listed)"
CACHE_SECONDS = 30

_NONE = (0, 0.0)


class StatsUnavailable(ValueError):
    """Sorting by `avg` or `wr` was asked for but there is no baseline to compute them from."""


@dataclass(frozen=True)
class CatalogEntry:
    movie_id: int
    title: str
    title_lc: str
    genres: tuple[str, ...]
    genres_lc: tuple[str, ...]
    support: int
    is_demo: bool


@dataclass(frozen=True)
class CatalogRow:
    movie_id: int
    title: str
    genres: tuple[str, ...]
    ratings: int                    # support + ratings applied since
    train_ratings: int              # ratings in the baseline (training split)
    new_ratings: int                # ratings counted from the ledger
    avg_rating: float | None        # None when the movie has no rating in the baseline or the ledger
    wr: float | None
    is_demo: bool


@dataclass(frozen=True)
class SearchResult:
    total: int
    pages: int
    rows: tuple[CatalogRow, ...]


def make_entry(doc: Mapping, demo_start: int) -> CatalogEntry:
    """A `movies` document ({_id, title, genres "Crime|Drama", support}) as an entry; the lower-case copies are made once."""
    title = str(doc.get("title", ""))
    genres = tuple(g for g in str(doc.get("genres", "")).split("|") if g and g != NO_GENRES)
    return CatalogEntry(
        movie_id=int(doc["_id"]),
        title=title,
        title_lc=title.lower(),
        genres=genres,
        genres_lc=tuple(g.lower() for g in genres),
        support=int(doc.get("support") or 0),
        is_demo=int(doc["_id"]) >= demo_start,
    )


def tokens(q: str | None) -> list[str]:
    """The words of the query, lower-case. Every one of them must occur in a title for the movie to match."""
    return (q or "").lower().split()


def _metrics(entry: CatalogEntry, stats: Stats | None, deltas: Stats, m: float, c: float) -> tuple[int, int, int, float | None, float | None]:
    n0, s0 = (stats or {}).get(entry.movie_id, _NONE)
    dn, ds = deltas.get(entry.movie_id, _NONE)
    v = n0 + dn
    if v <= 0:
        return n0, dn, entry.support + dn, None, None
    total = s0 + ds
    return n0, dn, entry.support + dn, total / v, weighted_rating(v, total, m, c)


def search(
    entries: Sequence[CatalogEntry],
    stats: Stats | None,
    deltas: Stats,
    *,
    q: str | None = None,
    genre: str | None = None,
    sort: str = "ratings",
    order: str | None = None,
    page: int = 1,
    size: int = 20,
    m: float = 1000.0,
    c: float = 3.5,
    assume_sorted: bool = False,
) -> SearchResult:
    """One page of the catalog. `stats` is None when there is no baseline (then `avg` and `wr` do not exist and sorting by them raises
    StatsUnavailable). Order: the sort key, then movieId ascending; a movie without a value for the key comes last in both directions.
    `assume_sorted` says `entries` are already in movieId order (CatalogCache keeps them so), which saves sorting 87k entries per search."""
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {SORTS}")
    if order is not None and order not in ORDERS:
        raise ValueError(f"order must be one of {ORDERS}")
    if sort in ("avg", "wr") and stats is None:
        raise StatsUnavailable("average rating and WR are not available: the training statistics (movie_stats) are not loaded")
    descending = (order or ("asc" if sort == "title" else "desc")) == "desc"

    words = tokens(q)
    wanted = genre.lower() if genre else None
    matched = list(entries)
    if wanted is not None:
        matched = [e for e in matched if wanted in e.genres_lc]
    for w in words:
        matched = [e for e in matched if w in e.title_lc]
    if not assume_sorted:
        matched.sort(key=lambda e: e.movie_id)                  # ties keep movieId ascending: Python's sort is stable, also with reverse=True

    if sort == "title":
        ordered = sorted(matched, key=lambda e: e.title_lc, reverse=descending)
    elif sort == "ratings":
        deltas_get = deltas.get
        ordered = sorted(matched, key=lambda e: e.support + deltas_get(e.movie_id, _NONE)[0], reverse=descending)
    else:
        index = 3 if sort == "avg" else 4
        have: list[tuple[float, CatalogEntry]] = []
        missing: list[CatalogEntry] = []
        for e in matched:
            if e.movie_id not in stats and e.movie_id not in deltas:        # most of the catalog: no rating in the baseline or the ledger
                missing.append(e)
                continue
            value = _metrics(e, stats, deltas, m, c)[index]
            if value is None:
                missing.append(e)
            else:
                have.append((value, e))
        have.sort(key=lambda t: t[0], reverse=descending)
        ordered = [e for _v, e in have] + missing

    total = len(ordered)
    pages = math.ceil(total / size) if total else 0
    start = (page - 1) * size
    rows = []
    for e in ordered[start:start + size]:
        train, new, ratings, avg, wr = _metrics(e, stats, deltas, m, c)
        rows.append(CatalogRow(e.movie_id, e.title, e.genres, ratings, train, new, avg, wr, e.is_demo))
    return SearchResult(total=total, pages=pages, rows=tuple(rows))


class CatalogCache:
    """The catalog entries (sorted by movieId once), read from the repository. After `ttl` seconds a request gets the previous copy at once and a
    refresh runs in the background, so no search waits for the read of 87k documents. `invalidate()` (a demo movie was added or removed) drops
    the copy: the next request reads it again and sees the change."""

    def __init__(self, repo, demo_start: int, *, clock: Callable[[], float] = time.monotonic, ttl: float = CACHE_SECONDS):
        self._repo = repo
        self._demo_start = demo_start
        self._clock = clock
        self._ttl = ttl
        self._lock = threading.Lock()
        self._entries: list[CatalogEntry] | None = None
        self._read_at = 0.0
        self._worker: threading.Thread | None = None

    @property
    def demo_start(self) -> int:
        return self._demo_start

    def get(self) -> list[CatalogEntry]:
        entries = self._entries
        if entries is not None:
            if self._clock() - self._read_at >= self._ttl and self._lock.acquire(blocking=False):
                self._worker = threading.Thread(target=self._refresh_in_background, daemon=True)
                self._worker.start()
            return entries
        with self._lock:                                          # nothing cached yet (first request, or after invalidate): wait for the read
            if self._entries is None:
                self._load()
            return self._entries  # type: ignore[return-value]

    def _load(self) -> None:
        entries = sorted((make_entry(doc, self._demo_start) for doc in self._repo.get_catalog()), key=lambda e: e.movie_id)
        self._entries = entries
        self._read_at = self._clock()

    def _refresh_in_background(self) -> None:
        try:
            self._load()
        except Exception:  # noqa: BLE001 - keep serving the previous copy; the next request after the TTL tries again
            self._read_at = self._clock() - self._ttl + min(5.0, self._ttl)
        finally:
            self._lock.release()

    def wait(self, timeout: float = 10.0) -> None:
        """Wait for a refresh in progress (used by tests)."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def invalidate(self) -> None:
        with self._lock:
            self._entries = None
