# Tests: specs/recommendation-api/spec.md "Recommendation endpoint and input validation",
# "Response contract", "Unknown user is valid". Uses FastAPI TestClient with the real
# `api.main.app`, but with FakeServingRepository injected via dependency_overrides —
# no live MongoDB needed. This is a wiring/contract test, not the live-stack
# integration test required by task 4.7.
import json

from fakes import FakeServingRepository
from fastapi.testclient import TestClient

from api.main import app, get_repository

POPULAR = [
    {"movieId": 900, "title": "Pop A", "genres": "Comedy", "rank": 1, "score": 4.5, "support": 1000},
    {"movieId": 901, "title": "Pop B", "genres": "Drama", "rank": 2, "score": 4.4, "support": 900},
]
MOVIES = {900: {"title": "Pop A", "genres": "Comedy"}, 901: {"title": "Pop B", "genres": "Drama"}}


def make_client(repo: FakeServingRepository) -> TestClient:
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_health_endpoint():
    client = make_client(FakeServingRepository())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_user_returns_200_with_zero_history_tier():
    """spec: 'Unknown user is valid' — no user_history document is NOT an error."""
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    client = make_client(repo)
    resp = client.get("/recommendations/999999")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "0_history"
    assert body["modelVersion"] == "v1.0.0"


def test_default_k_is_ten():
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR * 6}, movies=MOVIES)  # 12 popular items
    client = make_client(repo)
    resp = client.get("/recommendations/1")
    assert resp.status_code == 200
    assert len(resp.json()["recommendations"]) <= 10


def test_k_out_of_bounds_rejected_with_422_and_no_store_lookup():
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    client = make_client(repo)
    for bad_k in (0, 51):
        resp = client.get(f"/recommendations/1?k={bad_k}")
        assert resp.status_code == 422
    assert repo.calls == []  # spec: "no store lookup"


def test_non_positive_user_id_rejected_with_422():
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    client = make_client(repo)
    resp = client.get("/recommendations/0")
    assert resp.status_code == 422
    resp2 = client.get("/recommendations/-5")
    assert resp2.status_code == 422
    assert repo.calls == []


def test_response_contract_fields_present():
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    client = make_client(repo)
    resp = client.get("/recommendations/1?k=2")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("userId", "strategy", "modelVersion", "generatedAt", "tier", "fallbackReason", "recommendations"):
        assert field in body
    item = body["recommendations"][0]
    for field in ("movieId", "title", "genres", "rank", "score", "source"):
        assert field in item
    assert item["rank"] == 1


def test_request_is_logged(tmp_path, monkeypatch):
    import dataclasses

    import api.main as main_module

    log_path = tmp_path / "api.jsonl"
    # ServingConfig is frozen (immutable) — rebind the module-level `_cfg` name to a
    # copy with a test-local log path, rather than mutating the instance in place.
    monkeypatch.setattr(main_module, "_cfg", dataclasses.replace(main_module._cfg, api_log_path=str(log_path)))
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    client = make_client(repo)
    resp = client.get("/recommendations/1?k=2")
    assert resp.status_code == 200
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["userId"] == 1
    assert record["k"] == 2
    assert record["n_returned"] == 2
    assert "latency_ms" in record
