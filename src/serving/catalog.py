# catalog.py — movie catalog search for the demo pages (change movie-catalog-search).
# Spec: openspec/changes/movie-catalog-search/specs/movie-catalog. Design D-1..D-4.
#
# `search` is pure: entries in, a page of rows out. The statistics (average rating, WR) come from the same baseline-plus-ledger numbers as the
# popular list; sorting by them cannot be pushed down to Mongo, so the whole catalog (about 87k small entries) is sorted in memory.
# That sort takes 0.2-1 s, so `OrderCache` keeps each order until the data it came from changes, and a search only filters and slices it.
# `CatalogCache` keeps the entries for 30 seconds so a search does not read the `movies` collection each time.
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Hashable, Mapping, Sequence

from .popularity import Stats, weighted_rating

log = logging.getLogger("api.catalog")

SORTS = ("title", "ratings", "avg", "wr")
ORDERS = ("asc", "desc")
NO_GENRES = "(no genres listed)"
CACHE_SECONDS = 30
MAX_ORDERS = 16             # (sort, direction, m, c) combinations kept at once

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
    train_ratings: int              # ratings in the baseline (training split); 0 when the movie has none
    new_ratings: int                # ratings counted from the ledger; 0 when there are none
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


def _order(base: Sequence[CatalogEntry], stats: Stats | None, deltas: Stats, sort: str, descending: bool, m: float, c: float) -> list[CatalogEntry]:
    """Every entry of `base` (in movieId order) in the order of `sort`. Ties keep movieId ascending (Python's sort is stable, also with
    reverse=True); a movie without a value for avg / wr comes last in both directions."""
    if sort == "title":
        return sorted(base, key=lambda e: e.title_lc, reverse=descending)
    if sort == "ratings":
        deltas_get = deltas.get
        return sorted(base, key=lambda e: e.support + deltas_get(e.movie_id, _NONE)[0], reverse=descending)
    index = 3 if sort == "avg" else 4
    have: list[tuple[float, CatalogEntry]] = []
    missing: list[CatalogEntry] = []
    for e in base:
        if e.movie_id not in stats and e.movie_id not in deltas:            # most of the catalog: no rating in the baseline or the ledger
            missing.append(e)
            continue
        value = _metrics(e, stats, deltas, m, c)[index]
        if value is None:
            missing.append(e)
        else:
            have.append((value, e))
    have.sort(key=lambda t: t[0], reverse=descending)                       # on the value only: a CatalogEntry is never compared
    return [e for _v, e in have] + missing


def _same(a: tuple, b: tuple) -> bool:
    return len(a) == len(b) and all(x is y for x, y in zip(a, b))


class OrderCache:
    """The whole catalog in one sort order, kept for as long as the objects it was computed from are the same ones: the entries (CatalogCache
    replaces its list when it re-reads), the baseline and the ledger deltas (LivePopularity hands out the same objects while nothing changed).
    One order is built at a time; a request that needs the same one waits for it and reuses it, so concurrent searches do not each sort 87k
    entries (measured: four of them slowed /recommendations from 50 ms to over a second)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: dict[Hashable, tuple[tuple, list[CatalogEntry]]] = {}

    def get(self, key: Hashable, sources: tuple, build: Callable[[], list[CatalogEntry]]) -> list[CatalogEntry]:
        hit = self._orders.get(key)
        if hit is not None and _same(hit[0], sources):
            return hit[1]
        with self._lock:
            hit = self._orders.get(key)
            if hit is not None and _same(hit[0], sources):
                return hit[1]
            ordered = build()
            if key not in self._orders and len(self._orders) >= MAX_ORDERS:
                self._orders.clear()
            self._orders[key] = (sources, ordered)
            return ordered


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
    orders: OrderCache | None = None,
) -> SearchResult:
    """One page of the catalog. `stats` is None when there is no baseline (then `avg` and `wr` do not exist and sorting by them raises
    StatsUnavailable). Order: the sort key, then movieId ascending; a movie without a value for the key comes last in both directions.
    `assume_sorted` says `entries` are already in movieId order (CatalogCache keeps them so). `orders` keeps the sorted catalog between
    searches (the same `entries`, `stats` and `deltas` objects give the same order); without it every call sorts."""
    if sort not in SORTS:
        raise ValueError(f"sort must be one of {SORTS}")
    if order is not None and order not in ORDERS:
        raise ValueError(f"order must be one of {ORDERS}")
    if page < 1 or size < 1:
        raise ValueError("page and size must be at least 1")
    if sort in ("avg", "wr") and stats is None:
        raise StatsUnavailable("average rating and WR are not available: the training statistics (movie_stats) are not loaded")
    descending = (order or ("asc" if sort == "title" else "desc")) == "desc"

    def build() -> list[CatalogEntry]:
        return _order(entries if assume_sorted else sorted(entries, key=lambda e: e.movie_id), stats, deltas, sort, descending, m, c)

    if orders is None:
        ordered = build()
    else:
        sources = (entries,) if sort == "title" else (entries, deltas) if sort == "ratings" else (entries, stats, deltas)
        ordered = orders.get((sort, descending, m, c, assume_sorted), sources, build)

    # Filtering an ordered list keeps the order, so the filters run on the cached order and a search never sorts.
    matched = ordered
    if genre:
        wanted = genre.lower()
        matched = [e for e in matched if wanted in e.genres_lc]
    for w in tokens(q):
        matched = [e for e in matched if w in e.title_lc]

    total = len(matched)
    pages = math.ceil(total / size) if total else 0
    start = (page - 1) * size
    rows = []
    for e in matched[start:start + size]:
        train, new, ratings, avg, wr = _metrics(e, stats, deltas, m, c)
        rows.append(CatalogRow(e.movie_id, e.title, e.genres, ratings, train, new, avg, wr, e.is_demo))
    return SearchResult(total=total, pages=pages, rows=tuple(rows))


class CatalogCache:
    """The catalog entries (sorted by movieId once), read from the repository. After `ttl` seconds a request gets the previous copy at once and a
    refresh runs in the background, so no search waits for the read of 87k documents. `invalidate()` (a demo movie was added or removed) drops
    the copy without waiting for a read in progress: the next request reads it again and sees the change. `orders` holds the sorted catalog."""

    def __init__(self, repo, demo_start: int, *, clock: Callable[[], float] = time.monotonic, ttl: float = CACHE_SECONDS):
        self._repo = repo
        self._demo_start = demo_start
        self._clock = clock
        self._ttl = ttl
        self._lock = threading.Lock()           # whoever reads the movies collection holds it: the first read, or the background refresh
        self._state = threading.Lock()          # guards _entries and _gen, held for an instant only (never while reading)
        self._gen = 0                           # bumped by invalidate(); a read that started before it is not published
        self._entries: list[CatalogEntry] | None = None
        self._read_at = 0.0
        self._worker: threading.Thread | None = None
        self.orders = OrderCache()

    @property
    def demo_start(self) -> int:
        return self._demo_start

    def get(self) -> list[CatalogEntry]:
        entries = self._entries
        if entries is not None:
            if self._clock() - self._read_at >= self._ttl and self._lock.acquire(blocking=False):
                self._start_refresh()
            return entries
        with self._lock:                                          # nothing cached yet (first request, or after invalidate): wait for the read
            entries = self._entries
            return entries if entries is not None else self._load()

    def _load(self) -> list[CatalogEntry]:
        gen = self._gen
        entries = sorted((make_entry(doc, self._demo_start) for doc in self._repo.get_catalog()), key=lambda e: e.movie_id)
        with self._state:
            if gen == self._gen:                                  # invalidate() was not called while reading: this copy may be the cached one
                self._entries = entries
                self._read_at = self._clock()
        return entries

    def _start_refresh(self) -> None:
        """The caller holds `_lock`; the worker releases it, or this does when no worker could start (thread limit, memory): the lock must not
        stay held forever, or the catalog would never refresh again and invalidate() / the next cold read would hang."""
        try:
            worker = threading.Thread(target=self._refresh_in_background, daemon=True)
            worker.start()
        except Exception as exc:  # noqa: BLE001
            self._read_at = self._clock() - self._ttl + min(5.0, self._ttl)
            self._lock.release()
            log.warning("catalog refresh could not start (%s: %s); serving the previous copy", type(exc).__name__, exc)
            return
        self._worker = worker

    def _refresh_in_background(self) -> None:
        try:
            self._load()
        except Exception as exc:  # noqa: BLE001 - keep serving the previous copy; the next request after a few seconds tries again
            self._read_at = self._clock() - self._ttl + min(5.0, self._ttl)
            log.warning("catalog refresh failed (%s: %s); serving the previous copy", type(exc).__name__, exc)
        finally:
            self._lock.release()

    def wait(self, timeout: float = 10.0) -> None:
        """Wait for a refresh in progress (used by tests)."""
        worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def invalidate(self) -> None:
        with self._state:
            self._gen += 1
            self._entries = None
