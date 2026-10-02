# Tests: specs/recommendation-api/spec.md "Exact already-rated exclusion".
from serving import exclusion
from serving.models import Candidate


def test_exclude_rated_removes_matching_candidates():
    candidates = [
        Candidate(movie_id=1, rank=1),
        Candidate(movie_id=2, rank=2),
        Candidate(movie_id=3, rank=3),
    ]
    result = exclusion.exclude_rated(candidates, frozenset({2}))
    assert [c.movie_id for c in result] == [1, 3]


def test_exclude_rated_preserves_order_and_no_match_is_noop():
    candidates = [Candidate(movie_id=5, rank=1), Candidate(movie_id=1, rank=2)]
    result = exclusion.exclude_rated(candidates, frozenset({999}))
    assert [c.movie_id for c in result] == [5, 1]


def test_exclude_rated_ids_for_plain_id_lists():
    seeds = [10, 20, 30]
    result = exclusion.exclude_rated_ids(seeds, frozenset({20}))
    assert result == [10, 30]
