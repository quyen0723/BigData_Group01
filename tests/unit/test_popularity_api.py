# Tests: openspec/changes/live-weighted-popularity/specs/demo-popularity-live "Popularity debug endpoint" and
# specs/live-popularity "Recommendations use the live list for the popularity source" through the HTTP layer.
import dataclasses
import datetime as dt

import pytest
from fakes import FakeServingRepository
from fastapi.testclient import TestClient

import api.main as main_module
from api.main import app, get_config, get_repository
from serving.config import PopularityConfig
from serving.popularity import BaselineStats

C = 3.5
STATS = {
    1: (60_000, 60_000 * 4.4),
    2: (20_000, 20_000 * 4.3),
    3: (12_000, 12_000 * 4.3),
    4: (170, 170 * 4.9),
    9: (50, 50 * 5.0),
}
MOVIES = {mid: {"title": f"Movie {mid}", "genres": "Drama"} for mid in (1, 2, 3, 4, 9)}
ARTIFACT = [
    {"movieId": 3, "title": "Movie 3", "genres": "Drama", "rank": 1, "score": 4.3, "support": 12_000},
    {"movieId": 2, "title": "Movie 2", "genres": "Drama", "rank": 2, "score": 4.2, "support": 20_000},
]


def baseline(generated_at="g1"):
    return BaselineStats(stats=STATS, c=C, cutoff=1476348398.0, ratings=sum(n for n, _ in STATS.values()),
                         movies=len(STATS), generated_at=generated_at)


def one_star_events(n, movie=2):
    return [
        {"_id": f"e{i}", "userId": 1000 + i, "movieId": movie, "rating": 1.0, "timestamp": 1000 + i,
         "ingestedAt": dt.datetime(2026, 10, 3, 9, 0, 0)}
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def reset():
    yield
    app.dependency_overrides.clear()
    main_module._popularity_singleton = None


def make_client(*, live=True, demo=True, stats=True, events=None, top_n=3, ttl=0):
    repo = FakeServingRepository(
        popular={"v1.0.0": ARTIFACT}, movies=MOVIES, movie_stats=baseline() if stats else None,
        ledger_events=events or [],
    )
    cfg = dataclasses.replace(
        main_module._cfg,
        api=dataclasses.replace(main_module._cfg.api, demo_enabled=demo),
        popularity=PopularityConfig(live=live, m=1000, min_support=100, top_n=top_n, cache_ttl_seconds=ttl),
    )
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_config] = lambda: cfg
    return TestClient(app), repo


def test_the_live_list_with_the_numbers_behind_it():
    client, _ = make_client()
    body = client.get("/debug/popularity?n=3").json()
    assert body["source"] == "live" and body["liveEnabled"] is True and body["preview"] is False
    assert body["m"] == 1000 and body["c"] == C and body["minSupport"] == 100
    assert body["baseline"] == {"generatedAt": "g1", "cutoff": 1476348398.0, "ratings": 60_000 + 20_000 + 12_000 + 170 + 50}
    assert body["appliedEvents"] == 0
    first = body["items"][0]
    assert [i["movieId"] for i in body["items"]] == [1, 2, 3]
    assert first["rank"] == 1 and first["title"] == "Movie 1" and first["genres"] == "Drama"
    assert first["avgRating"] == pytest.approx(4.4) and first["support"] == 60_000 and first["baseSupport"] == 60_000
    assert first["newRatings"] == 0 and first["baseRank"] == 1
    assert first["wr"] == pytest.approx((60_000 * 4.4 + 1000 * C) / 61_000)


def test_new_ratings_show_up_with_the_baseline_rank_for_comparison():
    client, _ = make_client(events=one_star_events(600, movie=2))
    body = client.get("/debug/popularity?n=3").json()
    assert [i["movieId"] for i in body["items"]] == [1, 3, 2]
    assert body["appliedEvents"] == 600
    two = body["items"][2]
    assert two["newRatings"] == 600 and two["support"] == 20_600 and two["baseSupport"] == 20_000
    assert two["baseRank"] == 2 and body["items"][1]["baseRank"] == 3      # movie 3 moved up one place


def test_preview_with_another_m_does_not_change_serving():
    client, _ = make_client()
    body = client.get("/debug/popularity?n=3&m=0").json()
    assert body["preview"] is True and body["m"] == 0
    assert [i["movieId"] for i in body["items"]] == [4, 1, 2]              # plain averages: 4.9, 4.4, 4.3
    recs = client.get("/recommendations/1?k=3").json()
    assert [r["movieId"] for r in recs["recommendations"]] == [1, 2, 3]    # still the configured m = 1000


def test_deltas_false_is_the_baseline_only():
    client, _ = make_client(events=one_star_events(600, movie=2))
    body = client.get("/debug/popularity?n=3&deltas=false").json()
    assert body["appliedEvents"] == 0
    assert [i["movieId"] for i in body["items"]] == [1, 2, 3]
    assert all(i["newRatings"] == 0 for i in body["items"])


def test_the_endpoint_answers_while_live_is_off_and_says_so():
    client, _ = make_client(live=False)
    body = client.get("/debug/popularity?n=3").json()
    assert body["source"] == "live" and body["liveEnabled"] is False
    recs = client.get("/recommendations/1?k=3").json()
    assert [r["movieId"] for r in recs["recommendations"]] == [3, 2]       # /recommendations still serves the artifact


def test_without_a_baseline_the_endpoint_shows_the_artifact():
    client, _ = make_client(stats=False)
    body = client.get("/debug/popularity?n=5").json()
    assert body["source"] == "artifact" and body["baseline"] is None and body["c"] is None
    assert [i["movieId"] for i in body["items"]] == [3, 2]
    assert body["items"][0]["avgRating"] is None and body["items"][0]["newRatings"] == 0
    assert body["items"][0]["wr"] == 4.3 and body["items"][0]["support"] == 12_000


def test_recommendations_follow_the_flag_through_the_api():
    on, _ = make_client(live=True)
    assert [r["movieId"] for r in on.get("/recommendations/1?k=3").json()["recommendations"]] == [1, 2, 3]
    off, _ = make_client(live=False)
    assert [r["movieId"] for r in off.get("/recommendations/1?k=3").json()["recommendations"]] == [3, 2]


def test_recommendations_still_answer_200_when_live_is_on_but_unavailable():
    client, repo = make_client(live=True, events=one_star_events(3))
    repo.ledger_error = RuntimeError("mongo gone")
    response = client.get("/recommendations/1?k=3")
    assert response.status_code == 200
    assert [r["movieId"] for r in response.json()["recommendations"]] == [3, 2]


def test_demo_off_hides_the_route_even_for_bad_parameters():
    client, _ = make_client(demo=False)
    assert client.get("/debug/popularity").status_code == 404
    assert client.get("/debug/popularity?n=0").status_code == 404           # the gate runs before parameter validation
    assert client.get("/recommendations/1?k=3").status_code == 200           # the public route is untouched


@pytest.mark.parametrize("query", ["n=0", "n=51", "m=-1", "m=100001", "n=abc", "deltas=maybe"])
def test_bad_parameters_are_422(query):
    client, _ = make_client()
    assert client.get(f"/debug/popularity?{query}").status_code == 422


def test_the_cache_stays_bounded_when_clients_vary_m():
    client, _ = make_client(ttl=1000)                  # nothing expires, so the bound has to evict
    for m in range(0, 80):
        assert client.get(f"/debug/popularity?n=3&m={m}").status_code == 200
    live = main_module._popularity_singleton[2]
    assert len(live._cache) <= 32
