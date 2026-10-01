# Tests: specs/recommendation-api/spec.md "History-tier routing" + "Degradation chain".
from serving import router
from serving.models import RoutingPlan, SourceWeight

T = 10
W_POP_FEW = 0.3
W_CONTENT_ENOUGH = 0.3


def test_decide_tier_zero_history():
    assert router.decide_tier(0, T) == router.TIER_0


def test_decide_tier_few_history_lower_and_upper_bound():
    assert router.decide_tier(1, T) == router.TIER_FEW
    assert router.decide_tier(T - 1, T) == router.TIER_FEW


def test_decide_tier_enough_history_at_threshold():
    assert router.decide_tier(T, T) == router.TIER_ENOUGH
    assert router.decide_tier(T + 500, T) == router.TIER_ENOUGH


def test_select_seeds_prefers_positive():
    seeds = router.select_seeds(
        positive_movie_ids=(10, 20, 30),
        recent_movie_ids=(99,),
        seeds_per_user=2,
    )
    assert seeds == (10, 20)


def test_select_seeds_falls_back_to_recent_when_no_positive():
    seeds = router.select_seeds(
        positive_movie_ids=(),
        recent_movie_ids=(1, 2, 3),
        seeds_per_user=2,
    )
    assert seeds == (1, 2)


def test_build_initial_plan_zero_history():
    plan = router.build_initial_plan(0, T, has_als_doc=False,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    assert plan == RoutingPlan(
        tier=router.TIER_0,
        strategy=router.STRATEGY_POPULARITY,
        sources=(SourceWeight("popularity", 1.0),),
        fallback_reason=None,
    )


def test_build_initial_plan_few_history():
    plan = router.build_initial_plan(3, T, has_als_doc=False,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    assert plan.tier == router.TIER_FEW
    assert plan.strategy == router.STRATEGY_CONTENT_POPULARITY
    assert plan.sources == (
        SourceWeight("content", 1.0),
        SourceWeight("popularity", W_POP_FEW),
    )
    assert plan.fallback_reason is None


def test_build_initial_plan_enough_history_with_als():
    plan = router.build_initial_plan(50, T, has_als_doc=True,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    assert plan.tier == router.TIER_ENOUGH
    assert plan.strategy == router.STRATEGY_ALS_CONTENT
    assert plan.sources == (
        SourceWeight("als", 1.0),
        SourceWeight("content", W_CONTENT_ENOUGH),
    )
    assert plan.fallback_reason is None


def test_build_initial_plan_cold_start_user_degrades_to_content():
    """spec scenario: 'Cold-start user without ALS document' — 46,340 users
    with interaction_count >= T but no user_recommendations doc."""
    plan = router.build_initial_plan(50, T, has_als_doc=False,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    assert plan.tier == router.TIER_ENOUGH
    assert plan.strategy == router.STRATEGY_CONTENT_POPULARITY
    assert plan.sources == (
        SourceWeight("content", 1.0),
        SourceWeight("popularity", W_POP_FEW),
    )
    assert plan.fallback_reason == router.REASON_ALS_MISSING


def test_drop_empty_content_removes_source_and_sets_reason():
    plan = router.build_initial_plan(3, T, has_als_doc=False,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    updated = router.drop_empty_content(plan)
    assert updated.sources == (SourceWeight("popularity", W_POP_FEW),)
    assert updated.fallback_reason == router.REASON_NO_CONTENT


def test_drop_empty_content_noop_when_no_content_source():
    plan = router.build_initial_plan(0, T, has_als_doc=False,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    assert router.drop_empty_content(plan) == plan


def test_mark_filled_from_popularity_overrides_prior_reason():
    plan = router.build_initial_plan(50, T, has_als_doc=False,
                                      weight_content_in_enough=W_CONTENT_ENOUGH,
                                      weight_popularity_in_few=W_POP_FEW)
    assert plan.fallback_reason == router.REASON_ALS_MISSING
    filled = router.mark_filled_from_popularity(plan)
    assert filled.fallback_reason == router.REASON_FILLED
    assert filled.sources == plan.sources  # only the reason changes
