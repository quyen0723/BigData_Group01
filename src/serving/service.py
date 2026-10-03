# service.py — end-to-end recommendation pipeline (design.md diagram 2 / D-6..D-8).
# Orchestrates router + fusion + exclusion + history against a ServingRepository.
# Depends only on the ServingRepository Protocol, so it is unit-testable with an
# in-memory fake (tests/unit/test_service.py) without a live MongoDB.
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from . import exclusion, fusion, new_items, router
from .config import NewItemsConfig, RoutingConfig
from .live_popularity import LivePopularity
from .models import Candidate, RecommendationItem
from .repository import ServingRepository


@dataclass(frozen=True)
class RecommendationResponse:
    user_id: int
    tier: str
    strategy: str
    model_version: str
    generated_at: str
    fallback_reason: str | None
    recommendations: tuple[RecommendationItem, ...]


def _origin_label(origins: set[str]) -> str:
    return "+".join(sorted(origins))


def _place_new_movies(
    user_id: int,
    seeds: tuple[int, ...],
    final_candidates: list[Candidate],
    k: int,
    repo: ServingRepository,
    cfg: NewItemsConfig,
) -> tuple[list[Candidate], list[int]]:
    """Genre-matched demo movies into their reserved slot (new_items.py). Returns the new
    candidate list and the movie ids that were actually placed. The demo-movie lookup runs
    first and is a cheap range query on `_id`, so with no demo movies this costs one read."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=cfg.window_days)
    demo_movies = repo.get_demo_movies(cfg.id_range_start, since)
    if not demo_movies or not seeds:
        return final_candidates, []

    seed_docs = repo.get_movies(frozenset(seeds))
    profile = new_items.genre_profile(doc.get("genres", "") for doc in seed_docs.values())
    scored = new_items.score_new_movies(profile, demo_movies)
    if not scored:
        return final_candidates, []

    already_rated = repo.get_rated_movie_ids(user_id, frozenset(mid for mid, _ in scored))
    new_ids = [mid for mid, _ in scored if mid not in already_rated]
    placed = new_items.place_new_items(final_candidates, new_ids, cfg.slots, cfg.position, k)
    candidate_ids = set(new_ids)
    return placed, [c.movie_id for c in placed if c.movie_id in candidate_ids]


def _popularity_items(repo: ServingRepository, pointer, live: LivePopularity | None) -> list[dict]:
    """The popularity list: live weighted rating when it is on and available, otherwise the artifact of the active
    model version (spec live-popularity "Fall back to the artifact"). `live.get()` never raises."""
    if live is not None:
        result = live.get()
        if result is not None and result.items:
            return [{"movieId": p.movie_id, "score": p.wr, "support": p.v} for p in result.items]
    return repo.get_popular_movies(pointer.artifacts["popular_movies"])


def get_recommendations(
    user_id: int,
    k: int,
    repo: ServingRepository,
    cfg: RoutingConfig,
    new_items_cfg: NewItemsConfig | None = None,
    popularity: LivePopularity | None = None,
) -> RecommendationResponse:
    pointer = repo.get_active_pointer()

    history = repo.get_user_history(user_id)
    interaction_count = history.interaction_count if history else 0
    positive = history.positive_movie_ids if history else ()
    recent = history.recent_movie_ids if history else ()

    tier_guess = router.decide_tier(interaction_count, cfg.threshold_t)

    als_candidates: list[Candidate] = []
    if tier_guess == router.TIER_ENOUGH:
        raw_als = repo.get_user_recommendations(user_id, pointer.artifacts["user_recommendations"])
        if raw_als:
            als_candidates = fusion.rank_candidates([(r["movieId"], r["score"], 0) for r in raw_als])

    plan = router.build_initial_plan(
        interaction_count,
        cfg.threshold_t,
        has_als_doc=bool(als_candidates),
        weight_content_in_enough=cfg.fusion.weight_content_in_enough,
        weight_popularity_in_few=cfg.fusion.weight_popularity_in_few,
    )

    content_candidates: list[Candidate] = []
    if any(s.name == "content" for s in plan.sources):
        seeds = router.select_seeds(positive, recent, cfg.seeds_per_user)
        if seeds:
            similar_map = repo.get_similar_movies(list(seeds), pointer.artifacts["similar_movies"])
            best: dict[int, float] = {}
            for items in similar_map.values():
                for item in items:
                    mid = item["movieId"]
                    if mid not in best or item["score"] > best[mid]:
                        best[mid] = item["score"]
            content_candidates = fusion.rank_candidates([(mid, score, 0) for mid, score in best.items()])
        if not content_candidates:
            plan = router.drop_empty_content(plan)

    popularity_items = _popularity_items(repo, pointer, popularity)
    popularity_candidates = fusion.rank_candidates(
        [(item["movieId"], item["score"], item.get("support", 0)) for item in popularity_items]
    )

    origins: dict[int, set[str]] = {}
    sources_map: dict[str, list[Candidate]] = {}
    for source_weight in plan.sources:
        candidates = {
            "als": als_candidates,
            "content": content_candidates,
            "popularity": popularity_candidates,
        }[source_weight.name]
        sources_map[source_weight.name] = candidates
        for c in candidates:
            origins.setdefault(c.movie_id, set()).add(source_weight.name)

    all_candidate_ids = frozenset(mid for lst in sources_map.values() for mid in (c.movie_id for c in lst))
    rated_ids = repo.get_rated_movie_ids(user_id, all_candidate_ids) if all_candidate_ids else frozenset()

    for name in list(sources_map.keys()):
        sources_map[name] = exclusion.exclude_rated(sources_map[name], rated_ids)

    weights = {s.name: s.weight for s in plan.sources}
    support_lookup = {c.movie_id: c.support for c in popularity_candidates}
    fused = fusion.weighted_rrf(sources_map, weights, cfg.fusion.rrf_k, support_lookup)

    popularity_for_fill = exclusion.exclude_rated(popularity_candidates, rated_ids)
    final_candidates, was_filled = fusion.fill_from_popularity(
        fused, popularity_for_fill, k, exclude_ids=rated_ids
    )
    if was_filled:
        plan = router.mark_filled_from_popularity(plan)
        for c in final_candidates:
            origins.setdefault(c.movie_id, set()).add("popularity")

    if new_items_cfg is not None and new_items_cfg.enabled and plan.tier != router.TIER_0:
        seeds = router.select_seeds(positive, recent, cfg.seeds_per_user)
        final_candidates, placed_ids = _place_new_movies(user_id, seeds, final_candidates, k, repo, new_items_cfg)
        for mid in placed_ids:
            origins[mid] = {new_items.NEW_SOURCE}

    movies = repo.get_movies(frozenset(c.movie_id for c in final_candidates))
    items = tuple(
        RecommendationItem(
            movie_id=c.movie_id,
            title=movies.get(c.movie_id, {}).get("title", ""),
            genres=movies.get(c.movie_id, {}).get("genres", ""),
            rank=i + 1,
            score=c.score,
            source=_origin_label(origins.get(c.movie_id, {"popularity"})),
        )
        for i, c in enumerate(final_candidates)
    )

    return RecommendationResponse(
        user_id=user_id,
        tier=plan.tier,
        strategy=plan.strategy,
        model_version=pointer.model_version,
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        fallback_reason=plan.fallback_reason,
        recommendations=items,
    )
