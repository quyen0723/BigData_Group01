# Tests: specs/recommendation-api/spec.md — end-to-end pipeline via a FakeServingRepository.
# Not a substitute for task 4.7's live-stack integration test; this covers the WIRING of
# router + fusion + exclusion + history against the repository interface.
from fakes import FakeServingRepository

from serving import router, service
from serving.config import FusionConfig, RoutingConfig
from serving.models import HistorySnapshot

CFG = RoutingConfig(
    threshold_t=10,
    seeds_per_user=10,
    recent_cap=50,
    positive_cap=50,
    fusion=FusionConfig(rrf_k=60, weight_popularity_in_few=0.3, weight_content_in_enough=0.3),
)

POPULAR = [
    {"movieId": 900, "title": "Pop A", "genres": "Comedy", "rank": 1, "score": 4.5, "support": 1000},
    {"movieId": 901, "title": "Pop B", "genres": "Drama", "rank": 2, "score": 4.4, "support": 900},
    {"movieId": 902, "title": "Pop C", "genres": "Action", "rank": 3, "score": 4.3, "support": 800},
]
MOVIES = {
    900: {"title": "Pop A", "genres": "Comedy"},
    901: {"title": "Pop B", "genres": "Drama"},
    902: {"title": "Pop C", "genres": "Action"},
    200: {"title": "Similar A", "genres": "Crime|Drama"},
    201: {"title": "Similar B", "genres": "Crime|Drama"},
    300: {"title": "ALS A", "genres": "Sci-Fi"},
    301: {"title": "ALS B", "genres": "Sci-Fi"},
}


def test_zero_history_user_gets_popularity():
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    resp = service.get_recommendations(user_id=1, k=3, repo=repo, cfg=CFG)
    assert resp.tier == router.TIER_0
    assert resp.strategy == router.STRATEGY_POPULARITY
    assert resp.fallback_reason is None
    assert resp.model_version == "v1.0.0"
    assert [item.movie_id for item in resp.recommendations] == [900, 901, 902]
    assert resp.recommendations[0].title == "Pop A"


def test_few_history_user_gets_content_plus_popularity():
    repo = FakeServingRepository(
        histories={5: HistorySnapshot(3, recent_movie_ids=(100,), positive_movie_ids=(100,), last_updated=1)},
        similar={(100, "v1.0.0"): [{"movieId": 200, "score": 0.9, "rank": 1}, {"movieId": 201, "score": 0.8, "rank": 2}]},
        popular={"v1.0.0": POPULAR},
        movies=MOVIES,
    )
    resp = service.get_recommendations(user_id=5, k=4, repo=repo, cfg=CFG)
    assert resp.tier == router.TIER_FEW
    assert resp.strategy == router.STRATEGY_CONTENT_POPULARITY
    assert resp.fallback_reason is None
    # content has weight 1.0 vs popularity 0.3, so content candidates rank above popularity
    assert resp.recommendations[0].movie_id == 200
    assert resp.recommendations[1].movie_id == 201


def test_enough_history_user_with_als_doc():
    repo = FakeServingRepository(
        histories={7: HistorySnapshot(50, recent_movie_ids=(), positive_movie_ids=(100,), last_updated=1)},
        user_recs={(7, "v1.0.0"): [{"movieId": 300, "score": 4.9, "rank": 1}, {"movieId": 301, "score": 4.2, "rank": 2}]},
        similar={(100, "v1.0.0"): [{"movieId": 200, "score": 0.9, "rank": 1}]},
        popular={"v1.0.0": POPULAR},
        movies=MOVIES,
    )
    resp = service.get_recommendations(user_id=7, k=3, repo=repo, cfg=CFG)
    assert resp.tier == router.TIER_ENOUGH
    assert resp.strategy == router.STRATEGY_ALS_CONTENT
    assert resp.fallback_reason is None
    assert resp.recommendations[0].movie_id == 300  # ALS weight 1.0 dominates


def test_cold_start_user_without_als_doc_degrades_to_content():
    """spec: 'Cold-start user without ALS document' — no user_recommendations doc,
    interaction_count >= T (the 46,340-user case)."""
    repo = FakeServingRepository(
        histories={9: HistorySnapshot(50, recent_movie_ids=(), positive_movie_ids=(100,), last_updated=1)},
        user_recs={},  # no ALS doc for this user
        similar={(100, "v1.0.0"): [{"movieId": 200, "score": 0.9, "rank": 1}]},
        popular={"v1.0.0": POPULAR},
        movies=MOVIES,
    )
    resp = service.get_recommendations(user_id=9, k=3, repo=repo, cfg=CFG)
    assert resp.tier == router.TIER_ENOUGH
    assert resp.strategy == router.STRATEGY_CONTENT_POPULARITY
    assert resp.fallback_reason == router.REASON_ALS_MISSING
    assert 200 in [item.movie_id for item in resp.recommendations]


def test_already_rated_movie_never_returned():
    """tier 0_history's only source IS popularity, so once the rated item is
    excluded there is nothing left in the popularity pool to pad with (the
    remaining 2 survivors are already in `fused`) — was_filled correctly stays
    False rather than claiming a fill that added nothing new."""
    repo = FakeServingRepository(
        popular={"v1.0.0": POPULAR},
        rated={1: frozenset({900})},
        movies=MOVIES,
    )
    resp = service.get_recommendations(user_id=1, k=3, repo=repo, cfg=CFG)
    ids = [item.movie_id for item in resp.recommendations]
    assert 900 not in ids
    assert ids == [901, 902]
    assert resp.fallback_reason is None
    assert len(resp.recommendations) == 2  # only 2 non-rated popular movies exist in the fixture


def test_fill_from_popularity_when_als_plus_content_too_small():
    """enough_history's sources are ALS + Content only (no direct popularity
    source, design.md D-6) — so when their combined unique candidates are fewer
    than k, popularity padding is the ONLY way to reach k, and this is the one
    tier where fill_from_popularity actually fires."""
    repo = FakeServingRepository(
        histories={7: HistorySnapshot(50, recent_movie_ids=(), positive_movie_ids=(100,), last_updated=1)},
        user_recs={(7, "v1.0.0"): [{"movieId": 300, "score": 4.9, "rank": 1}]},   # 1 ALS candidate
        similar={(100, "v1.0.0"): [{"movieId": 200, "score": 0.9, "rank": 1}]},   # 1 content candidate
        popular={"v1.0.0": POPULAR},
        movies=MOVIES,
    )
    resp = service.get_recommendations(user_id=7, k=4, repo=repo, cfg=CFG)
    assert resp.fallback_reason == router.REASON_FILLED
    assert len(resp.recommendations) == 4
    ids = [item.movie_id for item in resp.recommendations]
    assert {300, 200}.issubset(ids)
    assert {900, 901} & set(ids)  # padded from popularity to reach k=4


def test_no_content_candidates_falls_back_to_popularity_only():
    """spec: content rỗng -> drop content source, reason no_content_candidates,
    unless it also needed filling (then filled_from_popularity wins, per design.md D-6
    'Runs last in the pipeline ... overrides')."""
    repo = FakeServingRepository(
        histories={5: HistorySnapshot(3, recent_movie_ids=(100,), positive_movie_ids=(100,), last_updated=1)},
        similar={},  # no similar docs at all -> content candidates empty
        popular={"v1.0.0": POPULAR},
        movies=MOVIES,
    )
    resp = service.get_recommendations(user_id=5, k=3, repo=repo, cfg=CFG)
    assert resp.strategy == router.STRATEGY_CONTENT_POPULARITY
    # fused already has all 3 popular items at k=3, so no fill needed -> reason stays no_content_candidates
    assert resp.fallback_reason == router.REASON_NO_CONTENT
    assert [item.movie_id for item in resp.recommendations] == [900, 901, 902]


def test_response_items_are_enriched_with_title_and_genres():
    repo = FakeServingRepository(popular={"v1.0.0": POPULAR}, movies=MOVIES)
    resp = service.get_recommendations(user_id=1, k=1, repo=repo, cfg=CFG)
    item = resp.recommendations[0]
    assert item.title == "Pop A"
    assert item.genres == "Comedy"
    assert item.rank == 1
