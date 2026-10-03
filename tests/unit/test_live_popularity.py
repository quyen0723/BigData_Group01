# Tests: openspec/changes/live-weighted-popularity/specs/live-popularity — configuration, the cached live source,
# the fall back to the artifact, and the wiring into service.get_recommendations.
import dataclasses
import datetime as dt
import logging
import threading
import time
from pathlib import Path

import pytest
import yaml
from fakes import FakeServingRepository

from serving import router, service
from serving.config import (
    DEFAULT_CONFIG_PATH,
    FusionConfig,
    PopularityConfig,
    RoutingConfig,
    _popularity_config,
    load_serving_config,
)
from serving.live_popularity import STALE_SECONDS, LivePopularity
from serving.models import HistorySnapshot
from serving.popularity import BaselineStats

ROUTING = RoutingConfig(
    threshold_t=10, seeds_per_user=10, recent_cap=50, positive_cap=50,
    fusion=FusionConfig(rrf_k=60, weight_popularity_in_few=0.3, weight_content_in_enough=0.3),
)
LIVE_ON = PopularityConfig(live=True, m=1000, min_support=100, top_n=3, cache_ttl_seconds=2)
C = 3.5


def baseline(stats, generated_at="g1", ledger_since=None):
    return BaselineStats(
        stats=stats, c=C, cutoff=1.0, ratings=sum(n for n, _ in stats.values()), movies=len(stats),
        generated_at=generated_at, ledger_since=ledger_since,
    )


# movieId -> (count, sum). 1 is the best movie, 3 trails 2 by a hair, 9 has too few ratings, 4 is a low-support star.
STATS = {
    1: (60_000, 60_000 * 4.4),
    2: (20_000, 20_000 * 4.3),
    3: (12_000, 12_000 * 4.3),
    4: (170, 170 * 4.9),
    9: (50, 50 * 5.0),
}
MOVIES = {mid: {"title": f"Movie {mid}", "genres": "Drama"} for mid in (1, 2, 3, 4, 9, 100, 200, 300)}
ARTIFACT = [   # a stale artifact with a different order, to see which list is used
    {"movieId": 3, "title": "Movie 3", "genres": "Drama", "rank": 1, "score": 4.3, "support": 12_000},
    {"movieId": 2, "title": "Movie 2", "genres": "Drama", "rank": 2, "score": 4.2, "support": 20_000},
    {"movieId": 1, "title": "Movie 1", "genres": "Drama", "rank": 3, "score": 4.1, "support": 60_000},
]


def ev(eid, user, movie, rating, ts=1000, ingested=dt.datetime(2026, 10, 3, 9, 0, 0)):
    return {"_id": eid, "userId": user, "movieId": movie, "rating": rating, "timestamp": ts, "ingestedAt": ingested}


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def make(repo=None, cfg=LIVE_ON, clock=None):
    repo = repo or FakeServingRepository(popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=baseline(STATS))
    clock = clock or Clock()
    return repo, clock, LivePopularity(repo, cfg, clock=clock)


def ids(result):
    return [p.movie_id for p in result.items]


# ---- configuration -----------------------------------------------------------------

def test_a_config_without_the_block_keeps_the_artifact():
    assert _popularity_config(None) == PopularityConfig(live=False, m=1000.0, min_support=100, top_n=10, cache_ttl_seconds=2.0)
    assert _popularity_config({}).live is False


def test_the_config_file_has_the_block_with_the_documented_defaults():
    raw = yaml.safe_load(Path(DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))["popularity"]
    assert {"live", "m", "min_support", "top_n", "cache_ttl_seconds"} <= set(raw)
    cfg = load_serving_config().popularity
    assert (cfg.m, cfg.min_support, cfg.top_n, cfg.cache_ttl_seconds) == (1000.0, 100, 10, 2.0)


@pytest.mark.parametrize("block,key", [
    ({"top_n": 0}, "popularity.top_n"),
    ({"top_n": 51}, "popularity.top_n"),
    ({"m": -1}, "popularity.m"),
    ({"min_support": 0}, "popularity.min_support"),
    ({"cache_ttl_seconds": -0.5}, "popularity.cache_ttl_seconds"),
    ({"live": "yes"}, "popularity.live"),
    ({"m": "big"}, "popularity.m"),
])
def test_an_invalid_value_names_its_key(block, key):
    with pytest.raises(ValueError, match=key):
        _popularity_config(block)


# ---- the live source ----------------------------------------------------------------

def test_without_events_the_list_is_the_baseline_ranking():
    _repo, _clock, live = make()
    result = live.get()
    assert ids(result) == [1, 2, 3]                     # 4 is below the cut: v=170 shrinks it; 9 has < 100 ratings
    assert result.deltas is True and result.applied_events == 0
    assert result.items[0].wr == pytest.approx((60_000 * 4.4 + 1000 * C) / 61_000)


def test_enough_new_ratings_change_the_order():
    # 3 trails 2 by ~0.0x; push 2 down with 1-star ratings from many users
    events = [ev(f"e{i}", 1000 + i, 2, 1.0) for i in range(600)]
    repo = FakeServingRepository(movie_stats=baseline(STATS), ledger_events=events)
    _repo, _clock, live = make(repo)
    result = live.get()
    assert ids(result) == [1, 3, 2]
    assert result.applied_events == 600
    two = result.items[2]
    assert two.base_v == 20_000 and two.new_ratings == 600 and two.v == 20_600


def test_deltas_false_ignores_the_ledger():
    repo = FakeServingRepository(movie_stats=baseline(STATS), ledger_events=[ev("a", 1, 4, 5.0)] * 3)
    _repo, _clock, live = make(repo)
    result = live.get(deltas=False)
    assert result.applied_events == 0 and result.deltas is False
    assert "get_rating_deltas" not in repo.calls


def test_a_preview_m_does_not_change_the_configured_one():
    _repo, _clock, live = make()
    plain = live.get(m=0)
    assert plain.m == 0 and live.get().m == 1000
    assert ids(plain)[:3] == [4, 1, 2]                  # m=0 is the plain average: 4.9 > 4.4 > 4.3
    assert ids(live.get()) == [1, 2, 3]


def test_many_requests_in_one_ttl_compute_once():
    repo, clock, live = make()
    for _ in range(50):
        live.get()
    assert repo.calls.count("get_rating_deltas") == 1 and repo.calls.count("get_movie_stats") == 1
    clock.advance(2.5)                                  # past the TTL
    live.get()
    assert repo.calls.count("get_rating_deltas") == 2


def test_concurrent_refreshes_collapse_into_one():
    repo = FakeServingRepository(movie_stats=baseline(STATS))
    original = repo.get_rating_deltas

    def slow(since):
        time.sleep(0.15)
        return original(since)

    repo.get_rating_deltas = slow
    _repo, _clock, live = make(repo, clock=time.monotonic)
    out = []
    threads = [threading.Thread(target=lambda: out.append(live.get())) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert repo.calls.count("get_rating_deltas") == 1
    assert len(out) == 12 and all(ids(r) == [1, 2, 3] for r in out)


def test_a_rebuilt_baseline_is_used_without_a_restart():
    repo, clock, live = make()
    assert ids(live.get()) == [1, 2, 3]
    repo.movie_stats = baseline({7: (5000, 5000 * 4.8), **STATS}, generated_at="g2")
    clock.advance(2.5)
    assert ids(live.get())[0] == 7


def test_the_ledger_since_mark_reaches_the_repository():
    mark = dt.datetime(2026, 10, 3, 9, 0, 0)
    events = [ev("old", 1, 1, 1.0, ingested=mark), ev("new", 2, 1, 1.0, ingested=mark + dt.timedelta(seconds=1))]
    repo = FakeServingRepository(movie_stats=baseline(STATS, ledger_since=mark), ledger_events=events)
    _repo, _clock, live = make(repo)
    assert live.get().applied_events == 1


# ---- failures and the artifact fallback ----------------------------------------------

def test_no_baseline_means_none_and_one_warning(caplog):
    repo = FakeServingRepository(movie_stats=None)
    _repo, clock, live = make(repo)
    with caplog.at_level(logging.WARNING, logger="api.popularity"):
        assert live.get() is None
        assert live.get() is None
        clock.advance(2.5)
        assert live.get() is None
    warnings = [r for r in caplog.records if "no baseline" in r.getMessage()]
    assert len(warnings) == 1                           # one per minute per cause
    assert "build_movie_stats" in warnings[0].getMessage()


def test_a_ledger_error_serves_a_recent_result_then_gives_up():
    repo, clock, live = make()
    good = live.get()
    repo.ledger_error = RuntimeError("mongo gone")
    clock.advance(2.5)
    assert live.get() is good                           # 2.5 s old: still used
    clock.advance(STALE_SECONDS + 1)
    assert live.get() is None                           # too old: the caller serves the artifact


def test_a_ledger_error_with_nothing_recent_is_none_and_not_retried_every_request():
    repo = FakeServingRepository(movie_stats=baseline(STATS))
    repo.ledger_error = RuntimeError("mongo gone")
    _repo, clock, live = make(repo)
    for _ in range(20):
        assert live.get() is None
    assert repo.calls.count("get_rating_deltas") == 1   # the failure is remembered for one TTL
    clock.advance(2.5)
    live.get()
    assert repo.calls.count("get_rating_deltas") == 2


def test_get_never_raises_even_when_reading_the_baseline_fails():
    repo = FakeServingRepository()
    repo.stats_error = ValueError("incomplete load")
    _repo, _clock, live = make(repo)
    assert live.get() is None


# ---- wiring into the recommendation service ------------------------------------------

def recs(repo, user_id=1, k=3, live=None):
    return service.get_recommendations(user_id=user_id, k=k, repo=repo, cfg=ROUTING, popularity=live)


def test_a_new_user_gets_the_live_order_not_the_artifact_order():
    repo, _clock, live = make()
    resp = recs(repo, live=live)
    assert resp.tier == router.TIER_0 and resp.strategy == router.STRATEGY_POPULARITY
    assert [i.movie_id for i in resp.recommendations] == [1, 2, 3]       # artifact says 3, 2, 1
    assert all(i.source == "popularity" for i in resp.recommendations)
    assert resp.fallback_reason is None
    assert resp.recommendations[0].title == "Movie 1"                    # titles still come from `movies`


def test_flag_off_means_the_artifact_alone():
    repo, _clock, _live = make()
    resp = recs(repo, live=None)
    assert [i.movie_id for i in resp.recommendations] == [3, 2, 1]


def test_missing_baseline_serves_the_artifact_and_does_not_fail():
    repo = FakeServingRepository(popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=None)
    _repo, _clock, live = make(repo)
    resp = recs(repo, live=live)
    assert [i.movie_id for i in resp.recommendations] == [3, 2, 1]


def test_a_ledger_failure_serves_the_artifact_and_does_not_fail():
    repo = FakeServingRepository(popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=baseline(STATS))
    repo.ledger_error = RuntimeError("boom")
    _repo, _clock, live = make(repo)
    resp = recs(repo, live=live)
    assert [i.movie_id for i in resp.recommendations] == [3, 2, 1]


def test_rated_movies_are_still_excluded_from_the_live_list():
    repo = FakeServingRepository(
        popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=baseline(STATS), rated={1: frozenset({1})},
    )
    _repo, _clock, live = make(repo)
    resp = recs(repo, live=live, k=3)
    assert [i.movie_id for i in resp.recommendations] == [2, 3]


def test_other_tiers_do_not_change_with_live_popularity_on():
    histories = {7: HistorySnapshot(50, recent_movie_ids=(), positive_movie_ids=(100,), last_updated=1)}
    common = dict(
        histories=histories,
        user_recs={(7, "v1.0.0"): [{"movieId": 300, "score": 4.9, "rank": 1}, {"movieId": 200, "score": 4.0, "rank": 2}]},
        similar={(100, "v1.0.0"): [{"movieId": 200, "score": 0.9, "rank": 1}]},
        popular={"v1.0.0": ARTIFACT},
        movies=MOVIES,
    )
    plain = recs(FakeServingRepository(**common), user_id=7, k=2)
    repo_on = FakeServingRepository(**common, movie_stats=baseline(STATS))
    _repo, _clock, live = make(repo_on)
    live_on = recs(repo_on, user_id=7, k=2, live=live)
    assert plain.tier == router.TIER_ENOUGH == live_on.tier
    assert [(i.movie_id, i.source) for i in plain.recommendations] == [(i.movie_id, i.source) for i in live_on.recommendations]


def test_the_support_of_a_live_candidate_is_its_live_rating_count():
    events = [ev(f"e{i}", 5000 + i, 1, 5.0) for i in range(7)]
    repo = FakeServingRepository(popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=baseline(STATS), ledger_events=events)
    _repo, _clock, live = make(repo)
    assert live.get().items[0].v == 60_007
    resp = recs(repo, live=live)
    assert resp.recommendations[0].movie_id == 1                         # ordering untouched by the extra 7 ratings


# ---- review fixes: empty ranking, cache bound on failure, one aggregation for all keys, stale-while-revalidate ----------------

def test_an_empty_ranking_is_not_available_it_never_leaves_a_new_user_with_nothing(caplog):
    repo = FakeServingRepository(popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=baseline(STATS))
    cfg = PopularityConfig(live=True, m=1000, min_support=10_000_000, top_n=3, cache_ttl_seconds=2)    # nothing reaches it
    _repo, _clock, live = make(repo, cfg=cfg)
    with caplog.at_level(logging.WARNING, logger="api.popularity"):
        assert live.get() is None
    assert any("no movie with 10000000+ ratings" in r.getMessage() for r in caplog.records)
    resp = service.get_recommendations(user_id=1, k=3, repo=repo, cfg=ROUTING, popularity=live)
    assert [i.movie_id for i in resp.recommendations] == [3, 2, 1]                  # the artifact, not an empty list


def test_a_failing_ledger_cannot_grow_the_cache_without_bound():
    repo = FakeServingRepository(movie_stats=baseline(STATS))
    repo.ledger_error = RuntimeError("mongo gone")
    _repo, _clock, live = make(repo, cfg=PopularityConfig(live=True, m=1000, min_support=100, top_n=3, cache_ttl_seconds=1000))
    for m in range(100):
        assert live.get(m=m) is None                                                  # every call adds a key that fails
    assert len(live._cache) <= 32


def test_one_ledger_aggregation_serves_every_n_and_m_within_a_ttl():
    repo, clock, live = make()
    live.get(n=3)
    live.get(n=12)
    live.get(n=50)
    live.get(m=0)
    live.get(m=250.5, n=7)
    assert repo.calls.count("get_rating_deltas") == 1
    clock.advance(2.5)
    live.get(n=12)
    assert repo.calls.count("get_rating_deltas") == 2


def test_the_key_that_recommendations_read_is_never_evicted_by_debug_traffic():
    repo, _clock, live = make(cfg=PopularityConfig(live=True, m=1000, min_support=100, top_n=3, cache_ttl_seconds=1000))
    serving = live.get()                                                              # (1000.0, True, 3)
    for m in range(1, 60):
        live.get(m=m)                                                                 # a presenter typing in the preview field
    assert live.get() is serving
    assert repo.calls.count("get_movie_stats") == 60                                  # 59 previews + the first call, none repeated for the serving key


def test_readers_with_a_recent_answer_do_not_wait_for_a_slow_refresh():
    repo = FakeServingRepository(movie_stats=baseline(STATS))
    clock = Clock()
    _repo, _clock, live = make(repo, clock=clock)
    first = live.get()
    release, started = threading.Event(), threading.Event()
    original = repo.get_rating_deltas

    def slow(since):
        started.set()
        assert release.wait(5)
        return original(since)

    repo.get_rating_deltas = slow
    clock.advance(2.5)                                                               # expired: the next get refreshes
    refresher = threading.Thread(target=live.get)
    refresher.start()
    assert started.wait(5)                                                           # the refresh is now inside Mongo
    t0 = time.monotonic()
    assert live.get() is first                                                       # a second reader gets the previous answer at once
    assert time.monotonic() - t0 < 1.0
    release.set()
    refresher.join(5)
    assert live.get() is not first                                                   # and the refresh has replaced it


# ---- snapshot: the numbers behind the movie search ----------------------------------------------------------------------

def test_snapshot_is_cached_for_one_ttl_and_keeps_the_same_objects_while_nothing_changed():
    repo, clock, live = make()
    first = live.snapshot()
    assert first is not None and live.snapshot() is first
    assert repo.calls.count("get_movie_stats") == 1                                  # one read for the whole TTL, however many searches
    clock.advance(2.5)
    again = live.snapshot()
    assert repo.calls.count("get_movie_stats") == 2 and repo.calls.count("get_rating_deltas") == 2
    assert again[0] is first[0] and again[1] is first[1]                             # recomputed, but nothing new: the same objects
    repo.ledger_events.append(ev("e1", 7, 3, 5.0))
    clock.advance(2.5)
    changed = live.snapshot()
    assert changed[1] is not first[1] and changed[1][3][0] == 1                      # a new rating: new deltas


def test_snapshot_without_a_baseline_is_none_and_read_once_per_ttl():
    repo, clock, live = make(FakeServingRepository(movies=MOVIES))
    assert live.snapshot() is None and live.snapshot() is None
    assert repo.calls.count("get_movie_stats") == 1


def test_snapshot_serves_a_recent_result_when_reading_fails_then_gives_up():
    repo, clock, live = make()
    first = live.snapshot()
    repo.stats_error = RuntimeError("mongo gone")
    clock.advance(2.5)
    assert live.snapshot() is first                                                  # recent: still served
    clock.advance(STALE_SECONDS + 1)
    assert live.snapshot() is None                                                   # too old: no statistics rather than old ones


def test_a_snapshot_reader_with_a_recent_answer_does_not_wait_for_a_slow_refresh():
    repo, clock, live = make()
    first = live.snapshot()
    release, started = threading.Event(), threading.Event()
    original = repo.get_rating_deltas

    def slow(since):
        started.set()
        assert release.wait(5)
        return original(since)

    repo.get_rating_deltas = slow
    clock.advance(2.5)
    refresher = threading.Thread(target=live.snapshot)
    refresher.start()
    assert started.wait(5)                                                           # the refresh is inside Mongo and holds the lock
    t0 = time.monotonic()
    assert live.snapshot() is first                                                  # a search does not queue behind it
    assert time.monotonic() - t0 < 1.0
    release.set()
    refresher.join(5)


def test_a_snapshot_inside_its_ttl_is_served_without_taking_the_lock_even_when_it_says_no_statistics():
    repo, clock, live = make(FakeServingRepository(movies=MOVIES))
    assert live.snapshot() is None                                                   # cached as "no statistics" for one TTL (the clock does not move)
    answers = []
    with live._lock:                                                                 # e.g. a popular-list refresh is in progress
        reader = threading.Thread(target=lambda: answers.append(live.snapshot()))
        reader.start()
        reader.join(2)
        assert answers == [None]                                                     # answered from the cache, not queued behind the lock
    reader.join(2)


# ---- configuration: whole numbers --------------------------------------------------------------------------------------

@pytest.mark.parametrize("block,key", [({"top_n": 10.5}, "popularity.top_n"), ({"min_support": 100.7}, "popularity.min_support")])
def test_a_fractional_count_is_refused_not_rounded(block, key):
    with pytest.raises(ValueError, match=key):
        _popularity_config(block)


def test_a_whole_number_written_with_a_decimal_point_is_fine():
    cfg = _popularity_config({"top_n": 10.0, "min_support": 100.0, "m": 250.5, "cache_ttl_seconds": 0.5})
    assert (cfg.top_n, cfg.min_support, cfg.m, cfg.cache_ttl_seconds) == (10, 100, 250.5, 0.5)
