# main.py — Recommendation API (specs/recommendation-api/spec.md).
# NFR (PRD §15 Latency): serves only from prepared artifacts, never trains in the
# request path. Dependency injection (`get_repository`) lets tests swap in an
# in-memory FakeServingRepository without a live MongoDB (tests/unit/test_api.py).
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
import uuid
from pathlib import Path

from confluent_kafka import Producer
from fastapi import Depends, FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi import Query, Response
from fastapi.responses import FileResponse

from serving.config import ServingConfig, load_serving_config
from serving.repository import MongoServingRepository, ServingRepository
from serving.service import get_recommendations
from streaming.events import VALID_RATINGS
from streaming.producer import make_producer

from .schemas import (
    DebugPipelineOut,
    DebugUserOut,
    DemoMovieOut,
    DemoSettingsOut,
    GateCheckOut,
    ModelVersionOut,
    MovieCreated,
    MovieIn,
    RatedMovieOut,
    RatingAccepted,
    RatingHistoryOut,
    RatingIn,
    RatingStatus,
    RecommendationResponseOut,
    RetrainProgressOut,
    SystemStatusOut,
)

app = FastAPI(title="MovieLens Recommendation API")
STATIC_DIR = Path(__file__).resolve().parent / "static"
log = logging.getLogger("api")

# The React build (web/ -> `npm run build`). Outside src/, which the api container mounts over, so the
# Docker image keeps it (design D-9/D-10). Read at request time so tests and `docker run -e` can change it.
DEFAULT_WEB_DIST_DIR = "/app/web-dist"

# Pages are small and their asset names change with every build, so a browser must ask again each time;
# assets carry a content hash in their name and never change under the same name.
PAGE_CACHE = {"Cache-Control": "no-cache"}
ASSET_CACHE = {"Cache-Control": "public, max-age=31536000, immutable"}

MOVIELENS_GENRES = frozenset({
    "Action", "Adventure", "Animation", "Children", "Comedy", "Crime", "Documentary", "Drama",
    "Fantasy", "Film-Noir", "Horror", "IMAX", "Musical", "Mystery", "Romance", "Sci-Fi",
    "Thriller", "War", "Western",
})
MAX_TITLE_LENGTH = 200

_cfg: ServingConfig = load_serving_config()
_repo_singleton: ServingRepository | None = None
_producer_singleton: Producer | None = None


def get_config() -> ServingConfig:
    return _cfg


def get_repository() -> ServingRepository:
    """Real dependency: a process-wide MongoServingRepository. Overridden in tests
    via `app.dependency_overrides[get_repository]`."""
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = MongoServingRepository(_cfg.mongo.uri, _cfg.mongo)
    return _repo_singleton


def require_demo(cfg: ServingConfig = Depends(get_config)) -> None:
    """Demo-only routes answer 404 when api.demo_enabled is false. As a dependency this
    runs before request-body validation, so a disabled route never reveals itself with a 422."""
    if not cfg.api.demo_enabled:
        raise HTTPException(status_code=404)


def _short(text: str, limit: int = 200) -> str:
    """Gate details can carry a whole Java stack trace (e.g. an unreadable model file);
    the page only needs the first line. The full text stays in model_registry."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first if len(first) <= limit else first[: limit - 1] + "…"


def _iso(value) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else value.isoformat()


def get_producer() -> Producer:
    """Lazy, process-wide Kafka producer (design.md D-6). Constructing a Producer
    does not connect eagerly, so this succeeds even if Kafka is currently down —
    only produce()/flush() surface an outage (design.md D-7: no hard dependency).
    Overridden in tests via `app.dependency_overrides[get_producer]`."""
    global _producer_singleton
    if _producer_singleton is None:
        bootstrap = os.environ.get(_cfg.api.kafka_bootstrap_servers_env, "kafka:9092")
        _producer_singleton = make_producer(bootstrap)
    return _producer_singleton


def _log_request(cfg: ServingConfig, record: dict) -> None:
    """spec: 'Request observability' — never let logging break the response."""
    try:
        path = Path(cfg.api_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/recommendations/{userId}", response_model=RecommendationResponseOut)
def recommendations(
    userId: int = PathParam(..., gt=0),
    k: int = Query(default=_cfg.api.k_default, ge=_cfg.api.k_min, le=_cfg.api.k_max),
    repo: ServingRepository = Depends(get_repository),
    cfg: ServingConfig = Depends(get_config),
) -> RecommendationResponseOut:
    # userId/k are validated by FastAPI (Path gt=0 / Query ge,le) before this body
    # runs, so an invalid request never reaches get_recommendations (no store lookup).
    start = time.monotonic()
    try:
        result = get_recommendations(userId, k, repo, cfg.routing, cfg.new_items)
    except RuntimeError as exc:
        # e.g. serving_meta has no active pointer — bootstrap load has not run yet.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    latency_ms = (time.monotonic() - start) * 1000

    _log_request(cfg, {
        "userId": userId,
        "tier": result.tier,
        "strategy": result.strategy,
        "fallbackReason": result.fallback_reason,
        "modelVersion": result.model_version,
        "k": k,
        "n_returned": len(result.recommendations),
        "latency_ms": round(latency_ms, 2),
    })

    return RecommendationResponseOut.from_domain(result)


@app.post("/ratings", response_model=RatingAccepted, status_code=202)
def submit_rating(
    body: RatingIn,
    repo: ServingRepository = Depends(get_repository),
    cfg: ServingConfig = Depends(get_config),
    producer: Producer = Depends(get_producer),
) -> RatingAccepted:
    """specs/rating-ingestion-api/spec.md "Submit a rating over HTTP" +
    "API-side validation before publishing" + "202 means durably accepted, not
    applied". Validation order matches design.md/tasks.md 1.5: userId, rating,
    movieId, then eventId — all 422s happen before anything touches Kafka."""
    if body.userId <= 0:
        raise HTTPException(status_code=422, detail="userId must be a positive integer")
    if body.rating not in VALID_RATINGS:
        raise HTTPException(status_code=422, detail=f"rating must be one of {sorted(VALID_RATINGS)}")
    if not repo.movie_exists(body.movieId):
        raise HTTPException(status_code=422, detail=f"unknown movieId {body.movieId}")

    if body.eventId is not None:
        if len(body.eventId) == 0 or len(body.eventId) > 64:
            raise HTTPException(status_code=422, detail="eventId must be 1-64 characters when supplied")
        event_id = body.eventId
    else:
        event_id = str(uuid.uuid4())

    # Server-assigned timestamp regardless of any timestamp the client might send
    # (spec: "Server-assigned timestamp") — RatingIn has no timestamp field at all.
    payload = {
        "eventId": event_id,
        "userId": body.userId,
        "movieId": body.movieId,
        "rating": body.rating,
        "timestamp": int(time.time()),
        "source": "demo",
    }

    delivery: dict = {}

    def _on_delivery(err, msg) -> None:
        delivery["err"] = err

    try:
        producer.produce(
            cfg.api.ratings_topic,
            key=str(body.userId),
            value=json.dumps(payload).encode("utf-8"),
            callback=_on_delivery,
        )
        remaining = producer.flush(cfg.api.produce_timeout_seconds)
    except BufferError as exc:
        raise HTTPException(status_code=503, detail=f"kafka producer queue full: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - any producer/broker failure -> 503, never a 500
        raise HTTPException(status_code=503, detail=f"kafka producer error: {exc}") from exc

    if remaining > 0:
        # The message is already in the producer queue and may still reach Kafka after this response
        # (design D-6): the outcome is unknown, so a retry must carry the same eventId to be deduplicated.
        raise HTTPException(
            status_code=503,
            detail="kafka delivery timed out; the rating may still be delivered, retry with the same eventId",
        )
    if delivery.get("err") is not None:
        raise HTTPException(status_code=503, detail=f"kafka delivery failed: {delivery['err']}")

    return RatingAccepted(eventId=event_id, status="accepted")


@app.get("/ratings/{eventId}", response_model=RatingStatus)
def rating_status(
    eventId: str = PathParam(...),
    repo: ServingRepository = Depends(get_repository),
) -> RatingStatus:
    """specs/rating-ingestion-api/spec.md "Rating status lookup". `rating_events`
    only holds an eventId after serve_batch has applied it (pipeline.py: ledger
    insert happens after effects), so absence means pending, not unknown."""
    doc = repo.get_rating_event(eventId)
    if doc is None:
        return RatingStatus(eventId=eventId, status="pending")
    ingested_at = doc.get("ingestedAt")
    return RatingStatus(
        eventId=eventId,
        status="applied",
        batchId=doc.get("batchId"),
        ingestedAt=ingested_at.isoformat() if ingested_at is not None else None,
    )


@app.get("/debug/users/{userId}", response_model=DebugUserOut)
def debug_user(
    userId: int = PathParam(..., gt=0),
    repo: ServingRepository = Depends(get_repository),
    cfg: ServingConfig = Depends(get_config),
) -> DebugUserOut:
    """specs/demo-web-client/spec.md "Debug state endpoint" — demo-only, 404 when
    `api.demo_enabled` is false (spec: "Disabled in production")."""
    if not cfg.api.demo_enabled:
        raise HTTPException(status_code=404)

    history = repo.get_user_history(userId)
    if history is None:
        interaction_count, recent_ids, positive_ids, last_updated = 0, [], [], None
    else:
        interaction_count = history.interaction_count
        recent_ids = list(history.recent_movie_ids)
        positive_ids = list(history.positive_movie_ids)
        last_updated = (
            dt.datetime.fromtimestamp(history.last_updated, tz=dt.timezone.utc).isoformat()
            if history.last_updated is not None else None
        )

    pointer = repo.get_active_pointer()
    state = repo.get_pipeline_state()
    last_run_at = state.get("lastRunAt") if state else None

    return DebugUserOut(
        userId=userId,
        interaction_count=interaction_count,
        recent_movieIds=recent_ids,
        positive_movieIds=positive_ids,
        lastUpdated=last_updated,
        pipeline=DebugPipelineOut(
            lastBatchId=state.get("lastBatchId") if state else None,
            lastRunAt=last_run_at.isoformat() if last_run_at is not None else None,
        ),
        modelVersion=pointer.model_version,
    )


@app.post("/movies", response_model=MovieCreated, status_code=201, dependencies=[Depends(require_demo)])
def create_movie(
    body: MovieIn,
    repo: ServingRepository = Depends(get_repository),
    cfg: ServingConfig = Depends(get_config),
) -> MovieCreated:
    """specs/new-movie-cold-start/spec.md "Create a demo movie". The movie goes only into
    MongoDB (design D-10): it is a demo shortcut, not a catalog ETL."""
    title = body.title.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        raise HTTPException(status_code=422, detail=f"title must be 1-{MAX_TITLE_LENGTH} characters")
    genres = list(dict.fromkeys(body.genres))
    if not genres:
        raise HTTPException(status_code=422, detail="at least one genre is required")
    unknown = [g for g in genres if g not in MOVIELENS_GENRES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown genre(s) {unknown}; allowed: {sorted(MOVIELENS_GENRES)}")

    doc = repo.create_demo_movie(title, genres, cfg.new_items.id_range_start, dt.datetime.now(dt.timezone.utc))
    return MovieCreated(movieId=doc["_id"], title=doc["title"], genres=genres, addedAt=_iso(doc["addedAt"]))


@app.delete("/movies/{movieId}", status_code=204, response_class=Response, dependencies=[Depends(require_demo)])
def delete_movie(
    movieId: int = PathParam(...),
    repo: ServingRepository = Depends(get_repository),
    cfg: ServingConfig = Depends(get_config),
) -> Response:
    """Only the reserved demo range can be deleted, so the MovieLens catalog is protected.
    Ratings already given to the movie stay in user_rated."""
    if not repo.delete_demo_movie(movieId, cfg.new_items.id_range_start):
        raise HTTPException(status_code=404, detail="no such demo movie")
    return Response(status_code=204)


@app.get("/debug/system", response_model=SystemStatusOut, dependencies=[Depends(require_demo)])
def debug_system(
    repo: ServingRepository = Depends(get_repository),
    cfg: ServingConfig = Depends(get_config),
) -> SystemStatusOut:
    """specs/demo-case-scenarios/spec.md "Model lifecycle and retrain progress view" — read
    only: nothing here starts retraining or changes the active version."""
    versions = [
        ModelVersionOut(
            version=doc["_id"],
            status=doc.get("status", "unknown"),
            importedAt=_iso(doc.get("importedAt")),
            activatedAt=_iso(doc.get("activatedAt")),
            gateChecks=[
                GateCheckOut(name=c["name"], passed=bool(c.get("pass")), detail=_short(str(c.get("detail", ""))))
                for c in (doc.get("gateReport") or {}).get("checks", [])
            ],
        )
        for doc in repo.get_model_registry()
    ]
    progress = repo.get_retrain_progress()
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    demo_movies = sorted(repo.get_demo_movies(cfg.new_items.id_range_start, epoch), key=lambda m: m["_id"])
    return SystemStatusOut(
        activeVersion=repo.get_active_pointer().model_version,
        versions=versions,
        retrainProgress=RetrainProgressOut(
            pending=progress["pending"],
            nMin=cfg.retrain_n_min_events,
            watermark=_iso(progress.get("watermark")),
        ),
        demo=DemoSettingsOut(
            ratingPollTimeoutSeconds=cfg.api.rating_poll_timeout_seconds,
            newItemsEnabled=cfg.new_items.enabled,
            demoMovieIdStart=cfg.new_items.id_range_start,
            tierThreshold=cfg.routing.threshold_t,
        ),
        demoMovies=[
            DemoMovieOut(
                movieId=m["_id"], title=m["title"],
                genres=[g for g in m.get("genres", "").split("|") if g], addedAt=_iso(m.get("addedAt")),
            )
            for m in demo_movies
        ],
    )


@app.get("/users/{userId}/ratings", response_model=RatingHistoryOut, dependencies=[Depends(require_demo)])
def user_ratings(
    userId: int = PathParam(..., gt=0),
    limit: int = Query(default=20, ge=1, le=50),
    repo: ServingRepository = Depends(get_repository),
) -> RatingHistoryOut:
    """specs/user-rating-history-api/spec.md — what a user rated most recently. Like
    /debug/users it exposes viewing history by userId, so it is demo-only."""
    total, items = repo.get_rating_history(userId, limit)
    return RatingHistoryOut(userId=userId, total=total, items=[RatedMovieOut(**item) for item in items])


def get_web_dist() -> Path:
    return Path(os.environ.get("WEB_DIST_DIR", DEFAULT_WEB_DIST_DIR))


def _built_page(name: str) -> Path | None:
    page = get_web_dist() / name
    return page if page.is_file() else None


_warned_missing_build = False


def _page(cfg: ServingConfig, built_name: str, legacy_name: str, *, force: str | None = None) -> FileResponse:
    """One of the two UIs (specs/web-frontend "Switch the default pages by configuration").
    `force` is "react" for the -next routes (404 without a build) or "legacy" for /legacy/*;
    None follows `api.ui` and falls back to the old page, with one warning, when the build is missing."""
    global _warned_missing_build
    if not cfg.api.demo_enabled:
        raise HTTPException(status_code=404)
    use = force or cfg.api.ui
    if use == "react":
        built = _built_page(built_name)
        if built is not None:
            return FileResponse(built, headers=PAGE_CACHE)
        if force == "react":
            raise HTTPException(status_code=404)
        if not _warned_missing_build:
            _warned_missing_build = True
            log.warning("api.ui is 'react' but %s has no %s: serving the legacy page (run `npm run build` in web/)",
                        get_web_dist(), built_name)
    return FileResponse(STATIC_DIR / legacy_name, headers=PAGE_CACHE)


@app.get("/demo", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def admin_page(cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    """The admin console. `/admin` is its name now; `/demo` stays so existing docs and
    evidence keep working (specs/demo-admin-console/spec.md). Demo-only: 404 when the flag is off."""
    return _page(cfg, "admin.html", "demo.html")


@app.get("/app", include_in_schema=False)
def user_app_page(cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    """The user-facing page (specs/demo-user-app/spec.md). Demo-only: 404 when the flag is off."""
    return _page(cfg, "app.html", "app.html")


@app.get("/app-next", include_in_schema=False)
def user_app_next(cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    return _page(cfg, "app.html", "app.html", force="react")


@app.get("/admin-next", include_in_schema=False)
def admin_next(cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    return _page(cfg, "admin.html", "demo.html", force="react")


@app.get("/legacy/app", include_in_schema=False)
def legacy_user_app(cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    return _page(cfg, "app.html", "app.html", force="legacy")


@app.get("/legacy/admin", include_in_schema=False)
def legacy_admin(cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    return _page(cfg, "admin.html", "demo.html", force="legacy")


@app.get("/ui/{asset_path:path}", include_in_schema=False)
def ui_asset(asset_path: str, cfg: ServingConfig = Depends(get_config)) -> FileResponse:
    """Files of the React build under /ui/ (Vite `base: "/ui/"`). Only dist/assets is served, and a
    path that leaves it is refused. 404 whenever the demo is off, so a disabled demo exposes no UI code."""
    if not cfg.api.demo_enabled:
        raise HTTPException(status_code=404)
    try:
        root = (get_web_dist() / "assets").resolve()
        target = (get_web_dist() / asset_path).resolve()
        inside = asset_path.startswith("assets/") and root in target.parents and target.is_file()
    except (ValueError, OSError):      # e.g. a NUL byte in the path: not a file, so 404 rather than a 500
        inside = False
    if not inside:
        raise HTTPException(status_code=404)
    return FileResponse(target, headers=ASSET_CACHE)
