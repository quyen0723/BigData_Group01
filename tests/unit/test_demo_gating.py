# Tests: specs/demo-web-client/spec.md "Demo page served by the API" (Disabled in
# production scenario), "Debug state endpoint" (Unknown user scenario).
import dataclasses

from fakes import FakeServingRepository
from fastapi.testclient import TestClient

import api.main as main_module
from api.main import app, get_config, get_repository


def make_client(repo: FakeServingRepository, demo_enabled: bool) -> TestClient:
    cfg = dataclasses.replace(main_module._cfg, api=dataclasses.replace(main_module._cfg.api, demo_enabled=demo_enabled))
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_config] = lambda: cfg
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_demo_and_debug_return_404_when_flag_off():
    client = make_client(FakeServingRepository(), demo_enabled=False)
    assert client.get("/demo").status_code == 404
    assert client.get("/debug/users/1").status_code == 404


def test_demo_returns_200_when_flag_on():
    client = make_client(FakeServingRepository(), demo_enabled=True)
    resp = client.get("/demo")
    assert resp.status_code == 200
    assert "Demo web client" in resp.text


def test_debug_returns_200_when_flag_on():
    client = make_client(FakeServingRepository(), demo_enabled=True)
    resp = client.get("/debug/users/1")
    assert resp.status_code == 200


def test_debug_user_with_no_history_returns_zero_counts():
    """spec: 'Unknown user' -> HTTP 200 with interaction_count: 0 and empty lists."""
    client = make_client(FakeServingRepository(), demo_enabled=True)
    resp = client.get("/debug/users/999999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["interaction_count"] == 0
    assert body["recent_movieIds"] == []
    assert body["positive_movieIds"] == []
    assert body["lastUpdated"] is None


def test_debug_user_with_history_and_pipeline_state():
    import datetime as dt

    from serving.models import HistorySnapshot

    repo = FakeServingRepository(
        histories={1: HistorySnapshot(interaction_count=5, recent_movie_ids=(296, 318), positive_movie_ids=(296,), last_updated=1790000000)},
        pipeline_state={"lastBatchId": 7, "lastRunAt": dt.datetime(2026, 9, 29, tzinfo=dt.timezone.utc)},
    )
    client = make_client(repo, demo_enabled=True)
    resp = client.get("/debug/users/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["interaction_count"] == 5
    assert body["recent_movieIds"] == [296, 318]
    assert body["pipeline"]["lastBatchId"] == 7
    assert body["pipeline"]["lastRunAt"] == "2026-09-29T00:00:00+00:00"
    assert body["modelVersion"] == "v1.0.0"
