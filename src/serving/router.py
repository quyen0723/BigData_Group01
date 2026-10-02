# router.py — history-tier routing + degradation chain (pure).
# Spec: specs/recommendation-api/spec.md "History-tier routing" + "Degradation chain".
# Design: design.md D-6. No I/O here: caller supplies interaction_count and artifact
# availability flags already read from MongoDB.
from __future__ import annotations

from .models import RoutingPlan, SourceWeight

TIER_0 = "0_history"
TIER_FEW = "few_history"
TIER_ENOUGH = "enough_history"

STRATEGY_POPULARITY = "POPULARITY"
STRATEGY_CONTENT_POPULARITY = "CONTENT+POPULARITY"
STRATEGY_ALS_CONTENT = "ALS+CONTENT"

REASON_ALS_MISSING = "als_artifact_missing"
REASON_NO_CONTENT = "no_content_candidates"
REASON_FILLED = "filled_from_popularity"


def decide_tier(interaction_count: int, threshold_t: int) -> str:
    """CONTRACTS.md §4: 0 history / few (1..T-1) / enough (>=T)."""
    if interaction_count <= 0:
        return TIER_0
    if interaction_count < threshold_t:
        return TIER_FEW
    return TIER_ENOUGH


def select_seeds(
    positive_movie_ids: tuple[int, ...],
    recent_movie_ids: tuple[int, ...],
    seeds_per_user: int,
) -> tuple[int, ...]:
    """positive_movieIds first (already most-recent-first); recent_movieIds when positives empty."""
    source = positive_movie_ids if positive_movie_ids else recent_movie_ids
    return tuple(source[:seeds_per_user])


def build_initial_plan(
    interaction_count: int,
    threshold_t: int,
    has_als_doc: bool,
    weight_content_in_enough: float,
    weight_popularity_in_few: float,
) -> RoutingPlan:
    """Decide tier + source list before any candidate is fetched (design.md D-6).

    enough_history without an ALS document degrades to the few_history shape
    (content + popularity) with fallback_reason = REASON_ALS_MISSING — this is
    exactly the path the 46,340 cold-start users (no ALS doc, but >=20 ratings) take.
    """
    tier = decide_tier(interaction_count, threshold_t)

    if tier == TIER_0:
        return RoutingPlan(
            tier=tier,
            strategy=STRATEGY_POPULARITY,
            sources=(SourceWeight("popularity", 1.0),),
            fallback_reason=None,
        )

    if tier == TIER_FEW:
        return RoutingPlan(
            tier=tier,
            strategy=STRATEGY_CONTENT_POPULARITY,
            sources=(
                SourceWeight("content", 1.0),
                SourceWeight("popularity", weight_popularity_in_few),
            ),
            fallback_reason=None,
        )

    # tier == TIER_ENOUGH
    if has_als_doc:
        return RoutingPlan(
            tier=tier,
            strategy=STRATEGY_ALS_CONTENT,
            sources=(
                SourceWeight("als", 1.0),
                SourceWeight("content", weight_content_in_enough),
            ),
            fallback_reason=None,
        )

    # Degrade: ALS -> Content (+ Popularity), report why.
    return RoutingPlan(
        tier=tier,
        strategy=STRATEGY_CONTENT_POPULARITY,
        sources=(
            SourceWeight("content", 1.0),
            SourceWeight("popularity", weight_popularity_in_few),
        ),
        fallback_reason=REASON_ALS_MISSING,
    )


def drop_empty_content(plan: RoutingPlan) -> RoutingPlan:
    """When the content source came back with zero candidates at query time, drop it
    and record why (design.md D-6: "content rỗng ⇒ bỏ nguồn đó"). If content was the
    only source with weight 1.0 (few_history / degraded enough_history) and popularity
    is already present, this just removes the empty content source.

    Overrides any earlier fallback_reason: this function runs later in the pipeline
    (after sources are fetched) and its reason is the more proximate cause of the
    response the caller is about to build.
    """
    remaining = tuple(s for s in plan.sources if s.name != "content")
    if len(remaining) == len(plan.sources):
        return plan  # no content source was present; nothing to drop
    return RoutingPlan(
        tier=plan.tier,
        strategy=plan.strategy,
        sources=remaining,
        fallback_reason=REASON_NO_CONTENT,
    )


def mark_filled_from_popularity(plan: RoutingPlan) -> RoutingPlan:
    """Record that the response needed popularity padding to reach k (design.md D-6).
    Runs last in the pipeline, so it overrides any earlier fallback_reason — it is the
    most proximate cause of what the caller actually sees in the response."""
    return RoutingPlan(
        tier=plan.tier,
        strategy=plan.strategy,
        sources=plan.sources,
        fallback_reason=REASON_FILLED,
    )
