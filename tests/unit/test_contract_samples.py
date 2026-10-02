# Tests: task 4.6 — exercise router/fusion/history against the frozen contract
# samples in contracts/samples/ (CONTRACTS.md §3), not synthetic data, so a schema
# drift in the samples breaks a test here before it breaks anything downstream.
import json
from pathlib import Path

import pytest

from serving import fusion, history, router
from serving.models import Candidate, RatedMovie

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "contracts" / "samples"
T = 10


def load_sample(name: str) -> dict:
    return json.loads((SAMPLES_DIR / name).read_text(encoding="utf-8"))


def test_user_history_sample_routes_to_enough_history():
    sample = load_sample("user_history.sample.json")
    plan = router.build_initial_plan(
        sample["interaction_count"], T, has_als_doc=True,
        weight_content_in_enough=0.3, weight_popularity_in_few=0.3,
    )
    assert sample["interaction_count"] == 42
    assert plan.tier == router.TIER_ENOUGH
    assert plan.strategy == router.STRATEGY_ALS_CONTENT


def test_user_history_sample_seeds_use_positive_movie_ids():
    sample = load_sample("user_history.sample.json")
    seeds = router.select_seeds(
        tuple(sample["positive_movieIds"]), tuple(sample["recent_movieIds"]), seeds_per_user=10,
    )
    assert seeds == (1193,)  # the sample's only positive movie


def test_als_topn_sample_recommendations_rank_ascending_from_1():
    sample = load_sample("als_topn.sample.json")
    recs = sample["recommendations"]
    assert [r["rank"] for r in recs] == list(range(1, len(recs) + 1))


def test_als_topn_sample_feeds_fusion_as_top_source():
    sample = load_sample("als_topn.sample.json")
    als_candidates = [
        Candidate(movie_id=r["movieId"], rank=r["rank"], support=0, score=r["score"])
        for r in sample["recommendations"]
    ]
    fused = fusion.weighted_rrf({"als": als_candidates}, {"als": 1.0}, rrf_k=60)
    assert fused[0].movie_id == als_candidates[0].movie_id


def test_similar_movies_sample_excludes_self_reference():
    """CONTRACTS.md §3.2 constraint: movieId not in similar.movieId — the pure
    exclusion helper enforces it if the loader ever produced a self-reference."""
    sample = load_sample("similar_movies.sample.json")
    similar_ids = frozenset(item["movieId"] for item in sample["similar"])
    assert sample["movieId"] not in similar_ids


def test_popular_movies_sample_items_sorted_by_rank():
    sample = load_sample("popular_movies.sample.json")
    ranks = [item["rank"] for item in sample["items"]]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1


def test_history_recompute_reproduces_sample_shape_when_seeded_from_it():
    """Feed history.recompute_history with rated movies matching the sample's
    recent_movieIds/positive_movieIds and check the output round-trips."""
    sample = load_sample("user_history.sample.json")
    rated = [
        RatedMovie(movie_id=1193, rating=5.0, rating_ts=2),  # positive, most recent
        RatedMovie(movie_id=296, rating=3.0, rating_ts=1),   # in recent, not positive
    ]
    snap = history.recompute_history(rated, recent_cap=50, positive_cap=50, positive_threshold=4.0)
    assert snap.interaction_count == 2
    assert list(snap.recent_movie_ids) == sample["recent_movieIds"]
    assert list(snap.positive_movie_ids) == sample["positive_movieIds"]


@pytest.mark.parametrize("filename", [
    "als_topn.sample.json",
    "popular_movies.sample.json",
    "similar_movies.sample.json",
    "user_history.sample.json",
])
def test_sample_files_still_exist_and_parse(filename):
    assert load_sample(filename)  # non-empty dict
