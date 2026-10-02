# Tests: specs/user-rating-history-api/spec.md, specs/demo-admin-console/spec.md "Admin console routes",
# specs/demo-user-app/spec.md "User app served by the API" (gating).
import dataclasses

from fakes import FakeServingRepository
from fastapi.testclient import TestClient

import api.main as main_module
from api.main import app, get_config, get_repository
from serving.models import HistorySnapshot

MOVIES = {
    296: {"title": "Pulp Fiction (1994)", "genres": "Comedy|Crime|Drama|Thriller"},
    318: {"title": "Shawshank Redemption, The (1994)", "genres": "Crime|Drama"},
    858: {"title": "Godfather, The (1972)", "genres": "Crime|Drama"},
}


def make_client(repo, demo_enabled=True):
    cfg = dataclasses.replace(main_module._cfg, api=dataclasses.replace(main_module._cfg.api, demo_enabled=demo_enabled))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_config] = lambda: cfg
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def history_repo():
    # recent_movie_ids are newest first, like user_history written by the pipeline
    return FakeServingRepository(
        movies=dict(MOVIES),
        histories={5: HistorySnapshot(interaction_count=149, recent_movie_ids=(858, 318, 296), positive_movie_ids=(858,), last_updated=1)},
        stars={5: {858: 5.0, 318: 4.0, 296: 3.5}},
    )


# ---- GET /users/{userId}/ratings ---------------------------------------------

def test_history_lists_newest_first_with_stars_titles_and_total():
    body = make_client(history_repo()).get("/users/5/ratings?limit=50").json()
    assert body["userId"] == 5
    assert body["total"] == 149            # the user's real count, not the length of the list
    assert [i["movieId"] for i in body["items"]] == [858, 318, 296]
    assert [i["rating"] for i in body["items"]] == [5.0, 4.0, 3.5]
    assert body["items"][0]["title"] == "Godfather, The (1972)"
    assert body["items"][0]["inCatalog"] is True


def test_history_respects_limit():
    body = make_client(history_repo()).get("/users/5/ratings?limit=2").json()
    assert [i["movieId"] for i in body["items"]] == [858, 318]


def test_history_default_limit_is_20():
    many = tuple(range(1000, 1030))
    repo = FakeServingRepository(
        movies={mid: {"title": f"M{mid}", "genres": "Drama"} for mid in many},
        histories={7: HistorySnapshot(30, many, many, 1)},
    )
    assert len(make_client(repo).get("/users/7/ratings").json()["items"]) == 20


def test_history_of_unknown_user_is_empty_not_an_error():
    resp = make_client(FakeServingRepository(movies=dict(MOVIES))).get("/users/999999/ratings")
    assert resp.status_code == 200
    assert resp.json() == {"userId": 999999, "total": 0, "items": []}


def test_deleted_movie_is_listed_but_flagged_not_in_catalog():
    repo = FakeServingRepository(
        movies=dict(MOVIES),
        histories={5: HistorySnapshot(2, (9000000, 296), (296,), 1)},
        stars={5: {9000000: 5.0, 296: 4.0}},
    )
    items = make_client(repo).get("/users/5/ratings").json()["items"]
    assert items[0] == {"movieId": 9000000, "title": "", "genres": "", "rating": 5.0, "inCatalog": False}
    assert items[1]["inCatalog"] is True


def test_invalid_parameters_are_422_without_touching_the_store():
    repo = history_repo()
    client = make_client(repo)
    for url in ("/users/0/ratings", "/users/-3/ratings", "/users/5/ratings?limit=0", "/users/5/ratings?limit=51"):
        assert client.get(url).status_code == 422, url
    assert "get_rating_history" not in repo.calls


# ---- gating -----------------------------------------------------------------

def test_history_app_and_admin_are_404_when_flag_off():
    client = make_client(history_repo(), demo_enabled=False)
    for url in ("/users/5/ratings", "/app", "/admin", "/demo"):
        assert client.get(url).status_code == 404, url


def test_admin_and_demo_serve_the_same_page():
    client = make_client(history_repo())
    admin, demo = client.get("/admin"), client.get("/demo")
    assert admin.status_code == 200 and demo.status_code == 200
    assert admin.text == demo.text


def test_user_app_page_is_served_when_flag_on_and_is_a_different_page_from_admin():
    client = make_client(history_repo())
    page = client.get("/app")
    assert page.status_code == 200
    assert "Chọn tài khoản" in page.text
    assert page.text != client.get("/admin").text


def test_user_app_loads_nothing_from_the_internet():
    """specs/demo-user-app: "Offline" — no external script, stylesheet, font or image."""
    import re

    html = make_client(history_repo()).get("/app").text
    assert not re.search(r'(?:src|href)\s*=\s*"https?://', html)
    assert "@import" not in html and "googleapis" not in html
