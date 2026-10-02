# Tests: specs/new-movie-cold-start/spec.md "Create a demo movie" / "Delete a demo movie",
# specs/demo-case-scenarios/spec.md "Model lifecycle and retrain progress view".
import dataclasses
import datetime as dt

from fakes import FakeServingRepository
from fastapi.testclient import TestClient

import api.main as main_module
from api.main import app, get_config, get_repository

MOVIES = {296: {"title": "Pulp Fiction (1994)", "genres": "Comedy|Crime|Drama|Thriller"}}
GOOD = {"title": "Demo Crime Story", "genres": ["Crime", "Drama"]}


def make_client(repo, demo_enabled=True):
    cfg = dataclasses.replace(main_module._cfg, api=dataclasses.replace(main_module._cfg.api, demo_enabled=demo_enabled))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_config] = lambda: cfg
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


# ---- gating -----------------------------------------------------------------

def test_all_three_routes_are_404_when_flag_off():
    client = make_client(FakeServingRepository(movies=dict(MOVIES)), demo_enabled=False)
    assert client.post("/movies", json=GOOD).status_code == 404
    assert client.delete("/movies/9000000").status_code == 404
    assert client.get("/debug/system").status_code == 404


def test_disabled_route_does_not_leak_through_a_422():
    client = make_client(FakeServingRepository(movies=dict(MOVIES)), demo_enabled=False)
    assert client.post("/movies", json={"title": 5}).status_code == 404


# ---- POST /movies -----------------------------------------------------------

def test_create_movie_returns_201_with_id_in_demo_range():
    repo = FakeServingRepository(movies=dict(MOVIES))
    resp = make_client(repo).post("/movies", json=GOOD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["movieId"] >= 9_000_000
    assert body["genres"] == ["Crime", "Drama"]
    assert repo.movies[body["movieId"]]["genres"] == "Crime|Drama"
    assert repo.movies[body["movieId"]]["support"] == 0


def test_ids_are_allocated_sequentially_in_the_demo_range():
    client = make_client(FakeServingRepository(movies=dict(MOVIES)))
    first = client.post("/movies", json=GOOD).json()["movieId"]
    second = client.post("/movies", json=GOOD).json()["movieId"]
    assert second == first + 1


def test_invalid_genre_rejected_and_nothing_stored():
    repo = FakeServingRepository(movies=dict(MOVIES))
    client = make_client(repo)
    for bad in (["Cooking"], ["(no genres listed)"], ["Crime", "Cooking"]):
        assert client.post("/movies", json={"title": "x", "genres": bad}).status_code == 422
    assert list(repo.movies) == [296]


def test_empty_title_empty_genres_and_long_title_rejected():
    client = make_client(FakeServingRepository(movies=dict(MOVIES)))
    assert client.post("/movies", json={"title": "   ", "genres": ["Drama"]}).status_code == 422
    assert client.post("/movies", json={"title": "x", "genres": []}).status_code == 422
    assert client.post("/movies", json={"title": "x" * 201, "genres": ["Drama"]}).status_code == 422


def test_duplicate_genres_are_collapsed():
    resp = make_client(FakeServingRepository(movies=dict(MOVIES))).post(
        "/movies", json={"title": "x", "genres": ["Drama", "Drama", "Crime"]}
    )
    assert resp.json()["genres"] == ["Drama", "Crime"]


# ---- DELETE /movies/{id} ----------------------------------------------------

def test_delete_demo_movie_204_and_movie_is_gone():
    repo = FakeServingRepository(movies=dict(MOVIES))
    client = make_client(repo)
    movie_id = client.post("/movies", json=GOOD).json()["movieId"]
    assert client.delete(f"/movies/{movie_id}").status_code == 204
    assert movie_id not in repo.movies


def test_movielens_catalog_is_protected_from_delete():
    repo = FakeServingRepository(movies=dict(MOVIES))
    assert make_client(repo).delete("/movies/296").status_code == 404
    assert 296 in repo.movies


def test_delete_unknown_demo_id_is_404():
    assert make_client(FakeServingRepository(movies=dict(MOVIES))).delete("/movies/9000042").status_code == 404


def test_deleting_a_movie_keeps_the_ratings_given_to_it():
    repo = FakeServingRepository(movies=dict(MOVIES), rated={5: frozenset({9000000})})
    client = make_client(repo)
    movie_id = client.post("/movies", json=GOOD).json()["movieId"]
    client.delete(f"/movies/{movie_id}")
    assert 9000000 in repo.rated[5]


# ---- GET /debug/system ------------------------------------------------------

REGISTRY = [
    {
        "_id": "v1.0.0", "status": "active",
        "importedAt": "2026-09-26T15:33:14+00:00", "activatedAt": "2026-09-26T15:33:14+00:00",
        "gateReport": {"mode": "bootstrap", "checks": [{"name": "G4 movies count", "pass": True, "detail": "ok"}]},
    },
    {
        "_id": "v1.1.0", "status": "rejected",
        "importedAt": dt.datetime(2026, 9, 26, 15, 55, tzinfo=dt.timezone.utc),
        "gateReport": {"checks": [
            {"name": "G1 candidate RMSE", "pass": False, "detail": "no active rmse"},
            {"name": "G7 version numbering", "pass": True, "detail": "ok"},
        ]},
    },
]


def test_system_status_lists_versions_with_gate_checks():
    repo = FakeServingRepository(model_registry=REGISTRY, retrain_progress={"pending": 12, "watermark": None})
    body = make_client(repo).get("/debug/system").json()
    assert body["activeVersion"] == "v1.0.0"
    by_version = {v["version"]: v for v in body["versions"]}
    assert by_version["v1.0.0"]["status"] == "active"
    assert by_version["v1.1.0"]["status"] == "rejected"
    assert by_version["v1.1.0"]["activatedAt"] is None
    assert by_version["v1.1.0"]["importedAt"] == "2026-09-26T15:55:00+00:00"
    failed = [c["name"] for c in by_version["v1.1.0"]["gateChecks"] if not c["passed"]]
    assert failed == ["G1 candidate RMSE"]


def test_system_status_reports_retrain_progress_against_threshold():
    repo = FakeServingRepository(
        model_registry=REGISTRY,
        retrain_progress={"pending": 37, "watermark": dt.datetime(2026, 9, 26, 15, 53, tzinfo=dt.timezone.utc)},
    )
    body = make_client(repo).get("/debug/system").json()
    assert body["retrainProgress"]["pending"] == 37
    assert body["retrainProgress"]["nMin"] == main_module._cfg.retrain_n_min_events
    assert body["retrainProgress"]["watermark"] == "2026-09-26T15:53:00+00:00"


def test_system_status_exposes_demo_settings_for_the_page():
    body = make_client(FakeServingRepository(model_registry=REGISTRY)).get("/debug/system").json()
    assert body["demo"]["ratingPollTimeoutSeconds"] == 60
    assert body["demo"]["demoMovieIdStart"] == 9_000_000


def test_system_status_has_no_write_methods():
    client = make_client(FakeServingRepository(model_registry=REGISTRY))
    assert client.post("/debug/system").status_code == 405
    assert client.delete("/debug/system").status_code == 405


def test_system_status_lists_demo_movies_for_deletion():
    repo = FakeServingRepository(movies=dict(MOVIES), model_registry=REGISTRY)
    client = make_client(repo)
    first = client.post("/movies", json=GOOD).json()["movieId"]
    second = client.post("/movies", json={"title": "Other", "genres": ["Western"]}).json()["movieId"]
    listed = client.get("/debug/system").json()["demoMovies"]
    assert [m["movieId"] for m in listed] == [first, second]
    assert listed[0]["genres"] == ["Crime", "Drama"]
    assert 296 not in [m["movieId"] for m in listed]  # the MovieLens catalog is never listed


def test_gate_detail_with_a_stack_trace_is_cut_to_one_short_line():
    trace = "RMSE computation failed: Py4JJavaError: boom\n\tat org.apache.spark.Foo(Foo.scala:1)\n" + "x" * 5000
    registry = [{"_id": "v1.1.0", "status": "rejected", "gateReport": {"checks": [
        {"name": "G1", "pass": False, "detail": trace},
        {"name": "G2", "pass": False, "detail": "y" * 500},
    ]}}]
    body = make_client(FakeServingRepository(model_registry=registry)).get("/debug/system").json()
    checks = body["versions"][0]["gateChecks"]
    assert checks[0]["detail"] == "RMSE computation failed: Py4JJavaError: boom"
    assert len(checks[1]["detail"]) == 200 and checks[1]["detail"].endswith("…")


def test_deleted_demo_movie_id_is_never_reused():
    """Ratings of a deleted movie stay in user_rated; reusing its id would attach them to a new movie."""
    repo = FakeServingRepository(movies=dict(MOVIES))
    client = make_client(repo)
    first = client.post("/movies", json=GOOD).json()["movieId"]
    assert client.delete(f"/movies/{first}").status_code == 204
    second = client.post("/movies", json=GOOD).json()["movieId"]
    assert second == first + 1
