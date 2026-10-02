# Tests: specs/new-movie-cold-start/spec.md "New-movie candidate source".
# Pure functions (new_items.py) plus the wiring in service.get_recommendations through
# FakeServingRepository. Demo movies live in the reserved id range (>= 9,000,000).
import datetime as dt

from fakes import FakeServingRepository

from serving import new_items, router, service
from serving.config import FusionConfig, NewItemsConfig, RoutingConfig
from serving.models import Candidate, HistorySnapshot

NOW = dt.datetime.now(dt.timezone.utc)
CFG = RoutingConfig(
    threshold_t=10, seeds_per_user=10, recent_cap=50, positive_cap=50,
    fusion=FusionConfig(rrf_k=60, weight_popularity_in_few=0.3, weight_content_in_enough=0.3),
)
NEW_CFG = NewItemsConfig(enabled=True, slots=1, position=3, window_days=30, id_range_start=9_000_000)

POPULAR = [
    {"movieId": 900 + i, "title": f"Pop {i}", "genres": "Comedy", "rank": i + 1, "score": 4.5 - i / 10, "support": 1000 - i}
    for i in range(6)
]
MOVIES = {
    **{900 + i: {"title": f"Pop {i}", "genres": "Comedy"} for i in range(6)},
    100: {"title": "Seed", "genres": "Crime|Drama"},
    200: {"title": "Similar A", "genres": "Crime|Drama"},
    201: {"title": "Similar B", "genres": "Crime|Drama"},
}
FEW = {5: HistorySnapshot(3, recent_movie_ids=(100,), positive_movie_ids=(100,), last_updated=1)}
SIMILAR = {(100, "v1.0.0"): [{"movieId": 200, "score": 0.9, "rank": 1}, {"movieId": 201, "score": 0.8, "rank": 2}]}


def demo_movie(title, genres, days_old=1):
    return {"title": title, "genres": genres, "support": 0, "addedAt": NOW - dt.timedelta(days=days_old)}


def make_repo(extra_movies=None, histories=None, rated=None):
    return FakeServingRepository(
        histories=FEW if histories is None else histories,
        similar=SIMILAR,
        popular={"v1.0.0": POPULAR},
        rated=rated,
        movies={**MOVIES, **(extra_movies or {})},
    )


def rec(repo, user_id=5, k=5, cfg=NEW_CFG):
    return service.get_recommendations(user_id, k, repo, CFG, cfg)


# ---- pure functions ---------------------------------------------------------

def test_genre_profile_shares_sum_to_one():
    profile = new_items.genre_profile(["Crime|Drama", "Drama"])
    assert profile == {"Crime": 1 / 3, "Drama": 2 / 3}


def test_genre_profile_ignores_no_genres_marker_and_empty_seed():
    assert new_items.genre_profile(["(no genres listed)"]) == {}
    assert new_items.genre_profile([]) == {}


def test_score_new_movies_orders_by_score_then_newest_then_id():
    profile = {"Crime": 0.5, "Drama": 0.5}
    movies = [
        {"_id": 9000003, "genres": "Crime", "addedAt": NOW - dt.timedelta(days=5)},
        {"_id": 9000002, "genres": "Crime|Drama", "addedAt": NOW - dt.timedelta(days=9)},
        {"_id": 9000001, "genres": "Drama", "addedAt": NOW - dt.timedelta(days=1)},
        {"_id": 9000004, "genres": "Western", "addedAt": NOW},
    ]
    ordered = [mid for mid, _ in new_items.score_new_movies(profile, movies)]
    assert ordered == [9000002, 9000001, 9000003]  # Western has no overlap and is dropped


def test_place_new_items_inserts_at_position_and_keeps_k():
    final = [Candidate(movie_id=i, rank=i, score=1.0 - i / 10) for i in range(1, 6)]
    placed = new_items.place_new_items(final, [9000001], slots=1, position=3, k=5)
    assert [c.movie_id for c in placed] == [1, 2, 9000001, 3, 4]
    scores = [c.score for c in placed]
    assert scores == sorted(scores, reverse=True)


def test_place_new_items_appends_when_list_is_shorter_than_position():
    final = [Candidate(movie_id=1, rank=1, score=0.5)]
    placed = new_items.place_new_items(final, [9000001], slots=1, position=3, k=5)
    assert [c.movie_id for c in placed] == [1, 9000001]


def _scores(candidates):
    return [c.score for c in candidates]


def test_place_new_items_two_slots_keeps_scores_non_increasing():
    """review finding 9 / spec "Placed new movies keep scores non-increasing": with slots > 1 every placed
    item takes the score of the first item it displaces, so no score is larger than the one before it."""
    final = [Candidate(movie_id=1, rank=1, score=0.9), Candidate(movie_id=2, rank=2, score=0.8),
             Candidate(movie_id=3, rank=3, score=0.7)]
    placed = new_items.place_new_items(final, [9000001, 9000002], slots=2, position=2, k=5)
    assert [c.movie_id for c in placed] == [1, 9000001, 9000002, 2, 3]
    assert _scores(placed) == [0.9, 0.8, 0.8, 0.8, 0.7]
    assert _scores(placed) == sorted(_scores(placed), reverse=True)


def test_place_new_items_at_the_end_takes_the_last_score_and_stays_ordered():
    final = [Candidate(movie_id=1, rank=1, score=0.9), Candidate(movie_id=2, rank=2, score=0.6)]
    placed = new_items.place_new_items(final, [9000001, 9000002], slots=2, position=5, k=5)
    assert [c.movie_id for c in placed] == [1, 2, 9000001, 9000002]
    assert _scores(placed) == [0.9, 0.6, 0.6, 0.6]


def test_place_new_items_one_slot_matches_the_previous_behaviour():
    final = [Candidate(movie_id=i, rank=i, score=1.0 - i / 10) for i in range(1, 6)]
    placed = new_items.place_new_items(final, [9000001], slots=1, position=3, k=5)
    assert [c.movie_id for c in placed] == [1, 2, 9000001, 3, 4]
    assert placed[2].score == final[2].score


def test_place_new_items_into_an_empty_list():
    placed = new_items.place_new_items([], [9000001], slots=1, position=3, k=5)
    assert [c.movie_id for c in placed] == [9000001]


# ---- service wiring ----------------------------------------------------------

def test_matching_new_movie_appears_at_reserved_rank_with_new_source():
    repo = make_repo({9000000: demo_movie("Demo Crime Story", "Crime|Drama")})
    resp = rec(repo)
    ids = [item.movie_id for item in resp.recommendations]
    assert ids[2] == 9000000
    assert resp.recommendations[2].source == "new"
    assert resp.recommendations[2].title == "Demo Crime Story"
    assert len(resp.recommendations) == 5


def test_non_matching_new_movie_is_not_shown():
    repo = make_repo({9000000: demo_movie("Demo Western", "Western")})
    assert 9000000 not in [item.movie_id for item in rec(repo).recommendations]


def test_zero_history_user_gets_pure_popularity_even_with_demo_movies():
    repo = make_repo({9000000: demo_movie("Demo Crime Story", "Crime|Drama")}, histories={})
    resp = rec(repo, user_id=77)
    assert resp.tier == router.TIER_0
    assert 9000000 not in [item.movie_id for item in resp.recommendations]


def test_already_rated_demo_movie_is_excluded():
    repo = make_repo({9000000: demo_movie("Demo Crime Story", "Crime|Drama")}, rated={5: frozenset({9000000})})
    assert 9000000 not in [item.movie_id for item in rec(repo).recommendations]


def test_movie_outside_window_is_not_new():
    repo = make_repo({9000000: demo_movie("Old Demo", "Crime|Drama", days_old=45)})
    assert 9000000 not in [item.movie_id for item in rec(repo).recommendations]


def test_disabled_flag_gives_identical_output_to_no_config():
    repo = make_repo({9000000: demo_movie("Demo Crime Story", "Crime|Drama")})
    off = rec(repo, cfg=NewItemsConfig(enabled=False))
    baseline = service.get_recommendations(5, 5, repo, CFG)
    assert [(i.movie_id, i.source, i.rank) for i in off.recommendations] == [
        (i.movie_id, i.source, i.rank) for i in baseline.recommendations
    ]


def test_slots_limit_how_many_new_movies_are_placed():
    repo = make_repo({
        9000000: demo_movie("Demo A", "Crime|Drama"),
        9000001: demo_movie("Demo B", "Crime|Drama"),
    })
    one = [i.movie_id for i in rec(repo).recommendations if i.source == "new"]
    two = [i.movie_id for i in rec(repo, cfg=NewItemsConfig(True, 2, 3, 30, 9_000_000)).recommendations if i.source == "new"]
    assert len(one) == 1 and len(two) == 2
