# live_popularity.py — the live popularity source used by the recommendation service and /debug/popularity.
# Spec: openspec/changes/live-weighted-popularity/specs/live-popularity "Fall back to the artifact, never fail the
# request", "Cached computation". Design D-5, D-6.
#
# `LivePopularity.get()` answers with a PopularityResult, or None when the caller should use the artifact list
# (baseline missing, nothing eligible, or computing failed and nothing recent is available). It never raises.
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .config import PopularityConfig
from .popularity import BaselineStats, PopStat, rank_top
from .repository import ServingRepository

log = logging.getLogger("api.popularity")

STALE_SECONDS = 60          # a result this young is still used when a refresh fails
WARN_EVERY_SECONDS = 60     # at most one warning per cause per minute
MAX_CACHED = 32             # (m, deltas, n) combinations kept at once


@dataclass(frozen=True)
class PopularityResult:
    items: tuple[PopStat, ...]
    m: float
    c: float
    min_support: int
    baseline: BaselineStats
    applied_events: int         # ratings counted from the ledger (one per user and movie)
    deltas: bool                # False: the ledger was ignored (baseline only)
    generated_at: dt.datetime


class LivePopularity:
    def __init__(
        self,
        repo: ServingRepository,
        cfg: PopularityConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.timezone.utc),
    ):
        self._repo = repo
        self._cfg = cfg
        self._clock = clock
        self._now = now
        self._lock = threading.Lock()
        # key -> (expires_at, computed_at, result or None). None is cached too, so a missing baseline costs one read per TTL.
        self._cache: dict[tuple, tuple[float, float, PopularityResult | None]] = {}
        # The ledger aggregation is the expensive part and does not depend on m or n: one per ledger_since and TTL, shared by every key.
        self._deltas: tuple[float, dt.datetime | None, dict] | None = None
        # (expires_at, computed_at, (baseline, deltas) or None) for the catalog search; None is cached too.
        self._snapshot: tuple[float, float, tuple[BaselineStats, dict] | None] | None = None
        self._last_warned: dict[str, float] = {}

    @property
    def cfg(self) -> PopularityConfig:
        return self._cfg

    def get(self, *, m: float | None = None, deltas: bool = True, n: int | None = None) -> PopularityResult | None:
        m = self._cfg.m if m is None else float(m)
        n = self._cfg.top_n if n is None else int(n)
        key = (m, deltas, n)

        hit = self._cache.get(key)
        if hit is not None and self._clock() < hit[0]:
            return hit[2]
        # One refresh at a time. A reader that already has a recent answer does not queue behind the refresh in progress (it can
        # take about a second on a big ledger): it takes that answer. Anybody without one waits and then reuses the fresh result.
        has_recent = hit is not None and hit[2] is not None and self._clock() - hit[1] <= STALE_SECONDS
        if has_recent:
            if not self._lock.acquire(blocking=False):
                return hit[2]
        else:
            self._lock.acquire()
        try:
            hit = self._cache.get(key)
            now = self._clock()
            if hit is not None and now < hit[0]:
                return hit[2]
            try:
                result = self._compute(m, deltas, n, now)
            except Exception as exc:  # noqa: BLE001 - any failure means "serve the artifact", never an error to the client
                self._warn("compute_failed", f"live popularity failed ({type(exc).__name__}: {exc})")
                stale = hit[2] if hit is not None and hit[2] is not None and now - hit[1] <= STALE_SECONDS else None
                # the failure is remembered for one TTL too, so a broken ledger is not retried by every request
                self._cache[key] = (now + self._cfg.cache_ttl_seconds, hit[1] if stale is not None else now, stale)
                self._prune(now)
                return stale
            self._cache[key] = (now + self._cfg.cache_ttl_seconds, now, result)
            self._prune(now)
            return result
        finally:
            self._lock.release()

    def snapshot(self) -> tuple[BaselineStats, dict] | None:
        """The baseline and the ledger deltas, with the same caching as the popular list (a TTL, and a reader that already has a recent statistics
        answer never queues behind a refresh; a cached "no statistics" is served inside the TTL only), for pages that list every movie (the catalog
        search). Never raises; None when there is no baseline or reading it failed and nothing recent is available (the caller then has no
        averages). The same objects come back while nothing changed."""
        hit = self._snapshot
        if hit is not None and self._clock() < hit[0]:
            return hit[2]
        has_recent = hit is not None and hit[2] is not None and self._clock() - hit[1] <= STALE_SECONDS
        if has_recent:
            if not self._lock.acquire(blocking=False):
                return hit[2]
        else:
            self._lock.acquire()
        try:
            hit = self._snapshot
            now = self._clock()
            if hit is not None and now < hit[0]:
                return hit[2]
            computed_at, value = now, None
            try:
                baseline = self._repo.get_movie_stats()
                if baseline is None:
                    self._warn("no_baseline", "movie_stats has no baseline: the movie search has no averages "
                               "(run `python -m loaders.build_movie_stats`)")
                else:
                    value = (baseline, self._ledger_deltas(baseline.ledger_since, now))
            except Exception as exc:  # noqa: BLE001 - the search still works without statistics
                self._warn("snapshot_failed", f"statistics for the movie search failed ({type(exc).__name__}: {exc})")
                if hit is not None and hit[2] is not None and now - hit[1] <= STALE_SECONDS:
                    computed_at, value = hit[1], hit[2]
            self._snapshot = (now + self._cfg.cache_ttl_seconds, computed_at, value)
            return value
        finally:
            self._lock.release()

    def _compute(self, m: float, deltas: bool, n: int, now: float) -> PopularityResult | None:
        baseline = self._repo.get_movie_stats()
        if baseline is None:
            self._warn("no_baseline", "movie_stats has no baseline: serving the popular_movies artifact "
                       "(run `python -m loaders.build_movie_stats`)")
            return None
        new = self._ledger_deltas(baseline.ledger_since, now) if deltas else {}
        items = rank_top(baseline.stats, new, m=m, c=baseline.c, min_support=self._cfg.min_support, n=n)
        if not items:
            # An empty list would leave a tier-0 user with no recommendation at all, so it is "not available", like a missing baseline.
            self._warn("empty_ranking", f"live popularity has no movie with {self._cfg.min_support}+ ratings: serving the artifact "
                       "(popularity.min_support too high, or movie_stats built from a much smaller bundle?)")
            return None
        return PopularityResult(
            items=tuple(items),
            m=m,
            c=baseline.c,
            min_support=self._cfg.min_support,
            baseline=baseline,
            applied_events=sum(count for count, _ in new.values()),
            deltas=deltas,
            generated_at=self._now(),
        )

    def _ledger_deltas(self, since: dt.datetime | None, now: float) -> dict:
        cached = self._deltas
        if cached is not None and cached[1] == since and now < cached[0]:
            return cached[2]
        fresh = self._repo.get_rating_deltas(since)
        if cached is not None and cached[1] == since and cached[2] == fresh:
            fresh = cached[2]                       # nothing new: keep the same object, so what was computed from it (sorted catalog) stays valid
        self._deltas = (now + self._cfg.cache_ttl_seconds, since, fresh)
        return fresh

    def _prune(self, now: float) -> None:
        """`m` and `n` come from a query string on the debug route, so the number of cached keys must stay bounded. The entry that
        /recommendations reads is never the one evicted: debug traffic must not push it out."""
        if len(self._cache) <= MAX_CACHED:
            return
        serving_key = (self._cfg.m, True, self._cfg.top_n)
        for key in [k for k, (expires, _computed, _r) in self._cache.items() if expires <= now and k != serving_key]:
            del self._cache[key]
        while len(self._cache) > MAX_CACHED:                       # all still fresh: drop the oldest computed
            victims = [k for k in self._cache if k != serving_key]
            del self._cache[min(victims, key=lambda k: self._cache[k][1])]

    def _warn(self, cause: str, message: str) -> None:
        now = self._clock()
        last = self._last_warned.get(cause)
        if last is None or now - last >= WARN_EVERY_SECONDS:
            self._last_warned[cause] = now
            log.warning(message)
