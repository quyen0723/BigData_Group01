# Tests: openspec/changes/movie-catalog-search/specs/movie-catalog through the HTTP layer.
import dataclasses
import datetime as dt

import pytest
from fakes import FakeServingRepository
from fastapi.testclient import TestClient

import api.main as main_module
import serving.catalog as catalog_module
from api.main import app, get_config, get_repository
from serving.config import PopularityConfig
from serving.popularity import BaselineStats

C = 3.5287
MOVIES = {
    296: {"title": "Pulp Fiction (1994)", "genres": "Comedy|Crime|Drama|Thriller", "support": 98_409},
    59114: {"title": "Pulp (1972)", "genres": "Comedy|Crime|Thriller", "support": 4_000},
    858: {"title": "Godfather, The (1972)", "genres": "Crime|Drama", "support": 60_000},
    1221: {"title": "Godfather: Part II, The (1974)", "genres": "Crime|Drama", "support": 40_000},
    318: {"title": "Shawshank Redemption, The (1994)", "genres": "Crime|Drama", "support": 102_929},
    3000: {"title": "Man from Laramie, The (1955)", "genres": "Western", "support": 2_000},
    3001: {"title": "Shane (1953)", "genres": "Western", "support": 3_000},
    900001: {"title": "Brand New (2019)", "genres": "Drama", "support": 5_000},        # released after the training split: no statistics
}
STATS = {296: (70_000, 70_000 * 4.20), 59114: (3_000, 3_000 * 3.40), 858: (47_709, 47_709 * 4.344), 1221: (31_216, 31_216 * 4.264),
         318: (73_945, 73_945 * 4.428), 3000: (1_500, 1_500 * 3.9), 3001: (2_200, 2_200 * 4.0)}


def baseline():
    return BaselineStats(stats=STATS, c=C, cutoff=1476348398.0, ratings=sum(n for n, _ in STATS.values()), movies=len(STATS), generated_at="g1")


def events(movie, n, rating=5.0):
    return [{"_id": f"e{movie}-{i}", "userId": 7000 + i, "movieId": movie, "rating": rating, "timestamp": 1000 + i,
             "ingestedAt": dt.datetime(2026, 10, 3, 9, 0, 0)} for i in range(n)]


@pytest.fixture(autouse=True)
def reset():
    yield
    app.dependency_overrides.clear()
    main_module._popularity_singleton = None
    main_module._catalog_singleton = None


def make_client(*, demo=True, stats=True, ledger=None):
    repo = FakeServingRepository(movies={k: dict(v) for k, v in MOVIES.items()}, movie_stats=baseline() if stats else None, ledger_events=ledger or [])
    cfg = dataclasses.replace(
        main_module._cfg,
        api=dataclasses.replace(main_module._cfg.api, demo_enabled=demo),
        popularity=PopularityConfig(live=True, m=1000, min_support=100, top_n=10, cache_ttl_seconds=0),
    )
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_config] = lambda: cfg
    return TestClient(app), repo


def titles(body):
    return [i["title"] for i in body["items"]]


def test_search_by_title_ignores_case_and_every_word_must_match():
    client, _ = make_client()
    body = client.get("/movies?q=PULP&sort=title").json()
    assert titles(body) == ["Pulp (1972)", "Pulp Fiction (1994)"] and body["total"] == 2
    assert titles(client.get("/movies?q=godfather%20part").json()) == ["Godfather: Part II, The (1974)"]
    assert client.get("/movies?q=zzzz").json()["total"] == 0


def test_filter_by_genre_in_any_letter_case():
    client, _ = make_client()
    for g in ("Western", "western", "WESTERN"):
        body = client.get(f"/movies?genre={g}&sort=title").json()
        assert titles(body) == ["Man from Laramie, The (1955)", "Shane (1953)"] and body["total"] == 2
    assert client.get("/movies?genre=Drama&q=shawshank").json()["total"] == 1


def test_a_row_carries_the_statistics_of_the_popular_list_and_the_new_ratings():
    client, _ = make_client(ledger=events(318, 9, 5.0))
    body = client.get("/movies?q=shawshank").json()
    assert body["hasStats"] is True and body["m"] == 1000 and body["c"] == C
    row = body["items"][0]
    assert row["movieId"] == 318 and row["genres"] == ["Crime", "Drama"] and row["isDemo"] is False
    assert row["trainRatings"] == 73_945 and row["newRatings"] == 9 and row["ratings"] == 102_929 + 9
    assert row["avgRating"] == pytest.approx((73_945 * 4.428 + 45.0) / 73_954)
    assert row["wr"] == pytest.approx((73_945 * 4.428 + 45.0 + 1000 * C) / (73_954 + 1000))


def test_a_movie_newer_than_the_training_split_has_ratings_but_no_average():
    client, _ = make_client()
    row = client.get("/movies?q=brand%20new").json()["items"][0]
    assert row["ratings"] == 5_000 and row["trainRatings"] == 0
    assert row["avgRating"] is None and row["wr"] is None


def test_default_sort_is_most_rated_first_and_ratings_never_increase():
    client, _ = make_client()
    items = client.get("/movies?size=50").json()["items"]
    counts = [i["ratings"] for i in items]
    assert counts == sorted(counts, reverse=True) and items[0]["title"].startswith("Shawshank")


def test_sort_by_average_puts_movies_without_one_last_in_both_directions():
    client, _ = make_client()
    for order in ("asc", "desc"):
        items = client.get(f"/movies?sort=avg&order={order}&size=50").json()["items"]
        values = [i["avgRating"] for i in items]
        present = [v for v in values if v is not None]
        assert present == sorted(present, reverse=(order == "desc")) and values[-1] is None and values[: len(present)] == present


def test_wr_sort_puts_the_big_well_rated_movie_ahead_of_a_small_one_with_a_higher_average():
    client, _ = make_client()
    ids = [i["movieId"] for i in client.get("/movies?sort=wr&size=50").json()["items"]]
    assert ids.index(318) < ids.index(3001) < ids.index(900001)                         # 900001 has no WR: last


def test_pagination():
    client, _ = make_client()
    first = client.get("/movies?size=3&page=1").json()
    third = client.get("/movies?size=3&page=3").json()
    assert (first["total"], first["pages"], first["size"], first["page"], len(first["items"])) == (8, 3, 3, 1, 3)
    assert len(third["items"]) == 2
    beyond = client.get("/movies?size=3&page=9").json()
    assert beyond["items"] == [] and beyond["total"] == 8 and beyond["pages"] == 3


def test_without_a_baseline_the_search_works_but_averages_are_gone():
    client, _ = make_client(stats=False)
    body = client.get("/movies?q=godfather&sort=ratings").json()
    assert body["hasStats"] is False and body["c"] is None
    assert [i["movieId"] for i in body["items"]] == [858, 1221]
    assert all(i["avgRating"] is None and i["wr"] is None for i in body["items"])
    for sort in ("avg", "wr"):
        response = client.get(f"/movies?sort={sort}")
        assert response.status_code == 422 and "movie_stats" in response.json()["detail"]
    assert client.get("/movies?sort=title").status_code == 200


def test_demo_off_hides_the_route_before_any_parameter_is_checked():
    client, _ = make_client(demo=False)
    assert client.get("/movies").status_code == 404
    assert client.get("/movies?size=0").status_code == 404
    assert client.get("/recommendations/1?k=3").status_code == 200                       # the public route is untouched


@pytest.mark.parametrize("query", ["size=51", "size=0", "page=0", "sort=popularity", "order=sideways", "genre=Nonsense", f"q={'a' * 101}"])
def test_bad_parameters_are_422(query):
    client, _ = make_client()
    assert client.get(f"/movies?{query}").status_code == 422


def test_a_new_demo_movie_is_searchable_at_once_and_gone_after_deleting_it():
    client, repo = make_client()
    assert client.get("/movies?q=phim").json()["total"] == 0                              # warms the cache
    created = client.post("/movies", json={"title": "Phim thử", "genres": ["Crime", "Drama"]})
    assert created.status_code == 201
    body = client.get("/movies?q=phim%20th%E1%BB%AD").json()
    assert [i["title"] for i in body["items"]] == ["Phim thử"] and body["items"][0]["isDemo"] is True
    assert body["items"][0]["ratings"] == 0
    assert client.delete(f"/movies/{created.json()['movieId']}").status_code == 204
    assert client.get("/movies?q=phim").json()["total"] == 0


def test_many_searches_read_the_catalog_once():
    client, repo = make_client()
    for q in ("a", "b", "pulp", "godfather", "shane") * 6:
        assert client.get(f"/movies?q={q}").status_code == 200
    assert repo.calls.count("get_catalog") == 1


def test_the_sorted_catalog_is_reused_between_searches_and_rebuilt_when_a_rating_arrives(monkeypatch):
    calls = []
    real = catalog_module._order
    monkeypatch.setattr(catalog_module, "_order", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    client, repo = make_client()                                                          # the statistics TTL is 0: every request re-reads them
    for q in ("", "pulp", "godfather", "shane", ""):
        assert client.get(f"/movies?sort=wr&q={q}").status_code == 200
    assert len(calls) == 1                                                                # nothing changed between them: one sort
    repo.ledger_events.extend(events(318, 3))                                             # ratings arrive through streaming
    assert client.get("/movies?sort=wr&size=50").status_code == 200
    assert len(calls) == 2
    client.get("/movies?sort=wr")
    assert len(calls) == 2
    assert client.get("/movies?q=shawshank").json()["items"][0]["newRatings"] == 3        # the numbers on a row are always current


def test_without_a_baseline_the_order_is_still_reused_between_searches(monkeypatch):
    calls = []
    real = catalog_module._order
    monkeypatch.setattr(catalog_module, "_order", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    client, _ = make_client(stats=False)
    for q in ("a", "b", "pulp"):
        assert client.get(f"/movies?sort=ratings&q={q}").status_code == 200
    assert len(calls) == 1
