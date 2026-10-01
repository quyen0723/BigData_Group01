# Tests: specs/rating-ingestion-api/spec.md "Submit a rating over HTTP",
# "202 means durably accepted, not applied", "API-side validation before
# publishing", "Client-supplied idempotency key", "Rating status lookup".
# Uses FastAPI TestClient with the real `api.main.app`, FakeServingRepository +
# FakeProducer injected via dependency_overrides — no live Kafka/MongoDB needed.
import json

from fakes import FakeServingRepository
from fastapi.testclient import TestClient

from api.main import app, get_producer, get_repository

MOVIES = {296: {"title": "Pulp Fiction", "genres": "Crime"}}


class FakeProducer:
    """Double for confluent_kafka.Producer: `produce()` queues a call and stores
    the delivery callback; `flush()` decides what that callback reports and
    whether any message is left "in flight" (spec: 503 on timeout)."""

    def __init__(self, deliver_error: str | None = None, timeout: bool = False):
        self.deliver_error = deliver_error
        self.timeout = timeout
        self.calls: list[dict] = []
        self._callback = None

    def produce(self, topic, key=None, value=None, callback=None):
        self.calls.append({"topic": topic, "key": key, "value": value})
        self._callback = callback

    def flush(self, timeout=None):
        if self.timeout:
            return 1  # message still "in flight" -> caller treats as 503
        if self._callback is not None:
            self._callback(self.deliver_error, None)
        return 0


def make_client(repo: FakeServingRepository, producer: FakeProducer) -> TestClient:
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_producer] = lambda: producer
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_valid_rating_returns_202_and_publishes_to_kafka():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 500001, "movieId": 296, "rating": 4.0})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["eventId"]  # server-generated UUID4

    assert len(producer.calls) == 1
    call = producer.calls[0]
    assert call["topic"] == "ratings.v1"
    assert call["key"] == "500001"
    payload = json.loads(call["value"])
    assert payload["eventId"] == body["eventId"]
    assert payload["userId"] == 500001
    assert payload["movieId"] == 296
    assert payload["rating"] == 4.0
    assert payload["timestamp"] > 0  # server-assigned, not client-supplied


def test_client_supplied_event_id_is_preserved():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post(
        "/ratings", json={"userId": 1, "movieId": 296, "rating": 4.5, "eventId": "client-fixed-id"}
    )

    assert resp.status_code == 202
    assert resp.json()["eventId"] == "client-fixed-id"
    payload = json.loads(producer.calls[0]["value"])
    assert payload["eventId"] == "client-fixed-id"


def test_non_positive_user_id_rejected_with_422_and_no_publish():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 0, "movieId": 296, "rating": 4.0})

    assert resp.status_code == 422
    assert producer.calls == []


def test_invalid_rating_value_rejected_with_422_and_no_publish():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 1, "movieId": 296, "rating": 7.0})

    assert resp.status_code == 422
    assert producer.calls == []


def test_unknown_movie_rejected_with_422_and_no_publish():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 1, "movieId": 999999999, "rating": 4.0})

    assert resp.status_code == 422
    assert producer.calls == []


def test_event_id_too_long_rejected_with_422_and_no_publish():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post(
        "/ratings", json={"userId": 1, "movieId": 296, "rating": 4.0, "eventId": "x" * 65}
    )

    assert resp.status_code == 422
    assert producer.calls == []


def test_empty_event_id_rejected_with_422_and_no_publish():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 1, "movieId": 296, "rating": 4.0, "eventId": ""})

    assert resp.status_code == 422
    assert producer.calls == []


def test_kafka_delivery_failure_returns_503():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer(deliver_error="broker down")
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 1, "movieId": 296, "rating": 4.0})

    assert resp.status_code == 503


def test_kafka_delivery_timeout_returns_503():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer(timeout=True)
    client = make_client(repo, producer)

    resp = client.post("/ratings", json={"userId": 1, "movieId": 296, "rating": 4.0})

    assert resp.status_code == 503


def test_recommendations_still_200_when_kafka_down():
    """spec: 'Reads unaffected by Kafka outage' — GET /recommendations never
    touches the producer dependency at all."""
    repo = FakeServingRepository(
        popular={"v1.0.0": [
            {"movieId": 296, "title": "Pulp Fiction", "genres": "Crime", "rank": 1, "score": 4.5, "support": 100},
        ]},
        movies=MOVIES,
    )
    producer = FakeProducer(deliver_error="broker down")
    client = make_client(repo, producer)

    resp = client.get("/recommendations/999999")
    assert resp.status_code == 200


def test_rating_status_pending_when_not_in_ledger():
    repo = FakeServingRepository(movies=MOVIES)
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.get("/ratings/not-in-ledger-yet")
    assert resp.status_code == 200
    assert resp.json() == {"eventId": "not-in-ledger-yet", "status": "pending", "batchId": None, "ingestedAt": None}


def test_rating_status_applied_when_in_ledger():
    import datetime as dt

    repo = FakeServingRepository(
        movies=MOVIES,
        rating_events={
            "already-applied": {"batchId": 3, "ingestedAt": dt.datetime(2026, 9, 29, tzinfo=dt.timezone.utc)}
        },
    )
    producer = FakeProducer()
    client = make_client(repo, producer)

    resp = client.get("/ratings/already-applied")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert body["batchId"] == 3
    assert body["ingestedAt"] == "2026-09-29T00:00:00+00:00"
