# Tests: specs/web-frontend/spec.md "New pages served side by side", "Switch the default pages by
# configuration", "Built assets follow the demo flag"; specs/demo-user-app/spec.md "System status
# exposes the tier threshold". Design: rebuild-ui-react D-9, D-11.
import dataclasses
import logging

import pytest
from fakes import FakeServingRepository
from fastapi.testclient import TestClient

import api.main as main_module
from api.main import app, get_config, get_repository

OLD_APP_MARK = "Chọn tài khoản"          # in static/app.html
OLD_ADMIN_MARK = "Demo web client"        # in static/demo.html
NEW_APP = "<!doctype html><title>NEW-APP</title><script src=\"/ui/assets/app.js\"></script>"
NEW_ADMIN = "<!doctype html><title>NEW-ADMIN</title><script src=\"/ui/assets/admin.js\"></script>"


@pytest.fixture()
def dist(tmp_path, monkeypatch):
    """A fake `npm run build` output, selected through WEB_DIST_DIR."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "app.html").write_text(NEW_APP, encoding="utf-8")
    (tmp_path / "admin.html").write_text(NEW_ADMIN, encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('app');", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("outside assets", encoding="utf-8")
    monkeypatch.setenv("WEB_DIST_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def no_dist(tmp_path, monkeypatch):
    monkeypatch.setenv("WEB_DIST_DIR", str(tmp_path / "does-not-exist"))


@pytest.fixture(autouse=True)
def reset_state():
    main_module._warned_missing_build = False
    yield
    app.dependency_overrides.clear()


def make_client(ui="legacy", demo_enabled=True) -> TestClient:
    cfg = dataclasses.replace(
        main_module._cfg, api=dataclasses.replace(main_module._cfg.api, demo_enabled=demo_enabled, ui=ui))
    app.dependency_overrides[get_repository] = lambda: FakeServingRepository()
    app.dependency_overrides[get_config] = lambda: cfg
    return TestClient(app)


# ---- the -next routes -------------------------------------------------------------

def test_next_routes_serve_the_build(dist):
    client = make_client()
    assert "NEW-APP" in client.get("/app-next").text
    assert "NEW-ADMIN" in client.get("/admin-next").text


def test_next_routes_are_404_without_a_build(no_dist):
    client = make_client()
    assert client.get("/app-next").status_code == 404
    assert client.get("/admin-next").status_code == 404


def test_next_routes_are_404_when_demo_is_off(dist):
    client = make_client(demo_enabled=False)
    for url in ("/app-next", "/admin-next", "/legacy/app", "/legacy/admin"):
        assert client.get(url).status_code == 404, url


def test_next_routes_ignore_the_ui_flag(dist):
    for ui in ("legacy", "react"):
        client = make_client(ui=ui)
        assert "NEW-APP" in client.get("/app-next").text


# ---- the default pages follow api.ui ------------------------------------------------

def test_legacy_is_the_default_and_keeps_the_old_pages(dist):
    client = make_client(ui="legacy")
    assert OLD_APP_MARK in client.get("/app").text
    for url in ("/admin", "/demo"):
        assert OLD_ADMIN_MARK in client.get(url).text, url


def test_react_serves_the_build_on_app_admin_and_demo(dist):
    client = make_client(ui="react")
    assert "NEW-APP" in client.get("/app").text
    for url in ("/admin", "/demo"):
        assert "NEW-ADMIN" in client.get(url).text, url


def test_legacy_routes_always_serve_the_old_pages(dist):
    client = make_client(ui="react")
    assert OLD_APP_MARK in client.get("/legacy/app").text
    assert OLD_ADMIN_MARK in client.get("/legacy/admin").text


def test_react_without_a_build_falls_back_and_warns_once(no_dist, caplog):
    client = make_client(ui="react")
    with caplog.at_level(logging.WARNING, logger="api"):
        assert OLD_APP_MARK in client.get("/app").text
        assert OLD_ADMIN_MARK in client.get("/admin").text
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "web" in r.getMessage()]
    assert len(warnings) == 1
    assert "build" in warnings[0].getMessage()


def test_rollback_to_legacy_serves_the_old_pages_again(dist):
    assert "NEW-APP" in make_client(ui="react").get("/app").text
    assert OLD_APP_MARK in make_client(ui="legacy").get("/app").text


def test_default_pages_are_404_when_demo_is_off(dist):
    client = make_client(ui="react", demo_enabled=False)
    for url in ("/app", "/admin", "/demo"):
        assert client.get(url).status_code == 404, url


# ---- /ui/ assets ---------------------------------------------------------------------

def test_assets_are_served_when_demo_is_on(dist):
    resp = make_client().get("/ui/assets/app.js")
    assert resp.status_code == 200
    assert "console.log" in resp.text


def test_assets_are_404_when_demo_is_off(dist):
    assert make_client(demo_enabled=False).get("/ui/assets/app.js").status_code == 404


def test_missing_asset_is_404(dist):
    assert make_client().get("/ui/assets/nope.js").status_code == 404


def test_only_the_assets_folder_is_served(dist):
    client = make_client()
    assert client.get("/ui/secret.txt").status_code == 404
    assert client.get("/ui/app.html").status_code == 404


def test_path_traversal_is_refused(dist):
    client = make_client()
    for url in ("/ui/assets/../secret.txt", "/ui/assets/%2e%2e/secret.txt", "/ui/assets/..%2fsecret.txt"):
        assert client.get(url).status_code == 404, url


def test_malformed_asset_paths_are_404_not_500(dist):
    client = make_client()
    for url in ("/ui/assets/%00x", "/ui/assets/a%00.js", "/ui/assets/..%5C..%5Csecret.txt", "/ui/assets/C:/Windows/win.ini", "/ui/assets//etc/passwd"):
        assert client.get(url).status_code == 404, url


# ---- caching ---------------------------------------------------------------------------

def test_pages_are_never_served_from_a_stale_cache(dist):
    client = make_client(ui="react")
    for url in ("/app", "/admin", "/app-next", "/admin-next", "/legacy/app", "/legacy/admin"):
        assert client.get(url).headers["cache-control"] == "no-cache", url


def test_hashed_assets_are_cached_for_a_year_and_marked_immutable(dist):
    resp = make_client().get("/ui/assets/app.js")
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"


# ---- config and system status ----------------------------------------------------------

def test_tier_threshold_is_in_the_system_status_and_old_fields_remain():
    client = make_client()
    body = client.get("/debug/system").json()
    demo = body["demo"]
    assert demo["tierThreshold"] == main_module._cfg.routing.threshold_t
    assert {"ratingPollTimeoutSeconds", "newItemsEnabled", "demoMovieIdStart"} <= set(demo)
    assert {"activeVersion", "versions", "retrainProgress", "demoMovies"} <= set(body)


def test_ui_flag_is_react_in_the_committed_config_and_rejects_unknown_values():
    from serving.config import _ui_choice

    assert main_module._cfg.api.ui == "react"        # task 9.1: /app, /admin and /demo serve the build
    assert _ui_choice("React") == "react"
    with pytest.raises(ValueError):
        _ui_choice("vue")


def test_a_config_without_the_ui_key_keeps_the_old_pages(tmp_path):
    """An older configs/serving.yaml (no `api.ui`) must not switch pages by surprise: the code default is legacy."""
    import yaml

    from serving.config import DEFAULT_CONFIG_PATH, load_serving_config

    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    del raw["api"]["ui"]
    old = tmp_path / "serving.yaml"
    old.write_text(yaml.safe_dump(raw), encoding="utf-8")

    assert load_serving_config(old).api.ui == "legacy"
