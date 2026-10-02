# Tests: specs/recommendation-api/spec.md "Rank-based fusion and deterministic ordering".
from serving import fusion
from serving.models import Candidate

RRF_K = 60


def test_rank_candidates_tie_break_support_then_movie_id():
    # Three movies tie at cosine score 1.0 (MODEL_DESIGN.md §4 known limitation);
    # design.md D-8: break by support desc, then movie_id asc.
    items = [
        (100, 1.0, 5),
        (50, 1.0, 50),
        (75, 1.0, 50),
        (10, 0.5, 999),
    ]
    ranked = fusion.rank_candidates(items)
    assert [c.movie_id for c in ranked] == [50, 75, 100, 10]
    assert [c.rank for c in ranked] == [1, 2, 3, 4]


def test_weighted_rrf_single_source_preserves_rank_order():
    content = fusion.rank_candidates([(1, 0.9, 0), (2, 0.5, 0), (3, 0.1, 0)])
    fused = fusion.weighted_rrf({"content": content}, {"content": 1.0}, RRF_K)
    assert [c.movie_id for c in fused] == [1, 2, 3]
    # score(1) = 1.0 / (60 + 1)
    assert fused[0].score == 1.0 / (RRF_K + 1)


def test_weighted_rrf_combines_contributions_from_multiple_sources():
    als = fusion.rank_candidates([(1, 5.0, 0), (2, 4.0, 0), (3, 3.0, 0)])
    content = fusion.rank_candidates([(2, 0.9, 0), (4, 0.8, 0)])
    fused = fusion.weighted_rrf(
        {"als": als, "content": content},
        {"als": 1.0, "content": 0.3},
        RRF_K,
    )
    # movie 2 appears in both sources (rank 2 in als, rank 1 in content) -> highest score
    assert fused[0].movie_id == 2
    expected_movie2 = 1.0 / (RRF_K + 2) + 0.3 / (RRF_K + 1)
    assert abs(fused[0].score - expected_movie2) < 1e-12


def test_weighted_rrf_zero_weight_source_ignored():
    als = fusion.rank_candidates([(1, 5.0, 0)])
    content = fusion.rank_candidates([(2, 1.0, 0)])
    fused = fusion.weighted_rrf({"als": als, "content": content}, {"als": 1.0, "content": 0.0}, RRF_K)
    assert [c.movie_id for c in fused] == [1]


def test_weighted_rrf_is_deterministic():
    als = fusion.rank_candidates([(1, 5.0, 10), (2, 5.0, 10)])  # exact tie on raw score+support
    content = fusion.rank_candidates([(3, 1.0, 0)])
    weights = {"als": 1.0, "content": 0.3}
    first = fusion.weighted_rrf({"als": als, "content": content}, weights, RRF_K)
    second = fusion.weighted_rrf({"als": als, "content": content}, weights, RRF_K)
    assert [(c.movie_id, c.score, c.rank) for c in first] == [(c.movie_id, c.score, c.rank) for c in second]


def test_fill_from_popularity_no_fill_needed_when_enough_candidates():
    fused = [Candidate(movie_id=i, rank=i, support=0, score=1.0) for i in range(1, 11)]
    popularity = fusion.rank_candidates([(999, 1.0, 100)])
    result, filled = fusion.fill_from_popularity(fused, popularity, k=10)
    assert len(result) == 10
    assert filled is False
    assert 999 not in [c.movie_id for c in result]


def test_fill_from_popularity_fills_skipping_duplicates_and_rated():
    fused = [Candidate(movie_id=1, rank=1, support=0, score=1.0)]
    popularity = fusion.rank_candidates([(1, 1.0, 100), (2, 0.9, 90), (3, 0.8, 80)])
    result, filled = fusion.fill_from_popularity(fused, popularity, k=3, exclude_ids=frozenset({3}))
    assert filled is True
    # movie 1 already present (skipped as duplicate), movie 3 excluded (already rated)
    assert [c.movie_id for c in result] == [1, 2]


def test_fill_from_popularity_returns_false_when_nothing_available_to_add():
    fused = [Candidate(movie_id=1, rank=1, support=0, score=1.0)]
    popularity = fusion.rank_candidates([(1, 1.0, 100)])  # only duplicate available
    result, filled = fusion.fill_from_popularity(fused, popularity, k=5)
    assert filled is False
    assert [c.movie_id for c in result] == [1]
