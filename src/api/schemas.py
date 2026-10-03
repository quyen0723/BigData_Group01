# schemas.py — API response contract (CONTRACTS.md §3.3 shape + additive tier/fallbackReason,
# specs/recommendation-api/spec.md "Response contract").
from __future__ import annotations

from pydantic import BaseModel

from serving.service import RecommendationResponse


class RecommendationItemOut(BaseModel):
    movieId: int
    title: str
    genres: str
    rank: int
    score: float
    source: str


class RecommendationResponseOut(BaseModel):
    userId: int
    tier: str
    strategy: str
    modelVersion: str
    generatedAt: str
    fallbackReason: str | None
    recommendations: list[RecommendationItemOut]

    @staticmethod
    def from_domain(resp: RecommendationResponse) -> "RecommendationResponseOut":
        return RecommendationResponseOut(
            userId=resp.user_id,
            tier=resp.tier,
            strategy=resp.strategy,
            modelVersion=resp.model_version,
            generatedAt=resp.generated_at,
            fallbackReason=resp.fallback_reason,
            recommendations=[
                RecommendationItemOut(
                    movieId=item.movie_id,
                    title=item.title,
                    genres=item.genres,
                    rank=item.rank,
                    score=item.score,
                    source=item.source,
                )
                for item in resp.recommendations
            ],
        )


class RatingIn(BaseModel):
    """POST /ratings body (specs/rating-ingestion-api/spec.md "Submit a rating over
    HTTP"). `eventId` is optional: omitted -> server generates a UUID4 (D-5);
    supplied -> used as-is for idempotency, so a retried request applies at most
    once downstream."""
    userId: int
    movieId: int
    rating: float
    eventId: str | None = None


class RatingAccepted(BaseModel):
    eventId: str
    status: str = "accepted"


class RatingStatus(BaseModel):
    eventId: str
    status: str
    batchId: int | None = None
    ingestedAt: str | None = None


class RatedMovieOut(BaseModel):
    movieId: int
    title: str
    genres: str
    rating: float | None
    inCatalog: bool


class RatingHistoryOut(BaseModel):
    """GET /users/{userId}/ratings (specs/user-rating-history-api/spec.md)."""
    userId: int
    total: int
    items: list[RatedMovieOut]


class MovieIn(BaseModel):
    """POST /movies body (specs/new-movie-cold-start/spec.md "Create a demo movie")."""
    title: str
    genres: list[str]


class MovieCreated(BaseModel):
    movieId: int
    title: str
    genres: list[str]
    addedAt: str


class GateCheckOut(BaseModel):
    name: str
    passed: bool
    detail: str


class ModelVersionOut(BaseModel):
    version: str
    status: str
    importedAt: str | None
    activatedAt: str | None
    gateChecks: list[GateCheckOut]


class RetrainProgressOut(BaseModel):
    pending: int
    nMin: int
    watermark: str | None


class DemoSettingsOut(BaseModel):
    ratingPollTimeoutSeconds: int
    newItemsEnabled: bool
    demoMovieIdStart: int
    tierThreshold: int          # routing.T_few_enough: ratings needed before a user leaves the few_history tier


class DemoMovieOut(BaseModel):
    movieId: int
    title: str
    genres: list[str]
    addedAt: str | None


class SystemStatusOut(BaseModel):
    """GET /debug/system — read-only view of the model lifecycle for use cases 5 and 6,
    plus the demo movies the page lets the presenter delete."""
    activeVersion: str
    versions: list[ModelVersionOut]
    retrainProgress: RetrainProgressOut
    demo: DemoSettingsOut
    demoMovies: list[DemoMovieOut]


class PopularityItemOut(BaseModel):
    """One row of GET /debug/popularity: the numbers behind a movie's weighted rating."""
    rank: int
    movieId: int
    title: str
    genres: str
    avgRating: float | None         # R; null when the list comes from the artifact (it only has WR)
    support: int                    # v: rating count, baseline + new
    baseSupport: int                # rating count in the training split
    newRatings: int                 # ratings counted from the ledger
    wr: float
    baseRank: int | None            # rank in the baseline-only ordering (same m); null beyond rank 200 or for the artifact


class PopularityBaselineOut(BaseModel):
    generatedAt: str
    cutoff: float
    ratings: int


class PopularityOut(BaseModel):
    source: str                     # "live" (movie_stats + ledger) or "artifact" (popular_movies.json)
    liveEnabled: bool               # popularity.live: do /recommendations use the live list?
    preview: bool                   # m differs from the configured value (a what-if, serving is unchanged)
    m: float
    c: float | None
    minSupport: int
    baseline: PopularityBaselineOut | None
    appliedEvents: int
    generatedAt: str
    items: list[PopularityItemOut]


class MovieRowOut(BaseModel):
    """One row of GET /movies."""
    movieId: int
    title: str
    genres: list[str]
    ratings: int                    # stored support + ratings applied since
    trainRatings: int               # ratings in the training split (what the average and WR are computed from)
    newRatings: int                 # ratings counted from the ledger
    avgRating: float | None         # null: no rating in the training split or the ledger
    wr: float | None
    isDemo: bool


class MovieListOut(BaseModel):
    total: int
    page: int
    size: int
    pages: int
    hasStats: bool                  # false when movie_stats is not loaded: no averages
    m: float
    c: float | None
    items: list[MovieRowOut]


class DebugPipelineOut(BaseModel):
    lastBatchId: int | None
    lastRunAt: str | None


class DebugUserOut(BaseModel):
    """GET /debug/users/{userId} — demo-only (specs/demo-web-client/spec.md
    "Debug state endpoint"). Field names mirror the Mongo documents directly
    (interaction_count, recent_movieIds, ...) rather than the recommendations
    response's camelCase, since this endpoint exists to show "what's actually
    stored", not a client-facing contract."""
    userId: int
    interaction_count: int
    recent_movieIds: list[int]
    positive_movieIds: list[int]
    lastUpdated: str | None
    pipeline: DebugPipelineOut
    modelVersion: str
