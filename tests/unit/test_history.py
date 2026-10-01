# Tests: specs/rating-stream-ingestion/spec.md "Immediate serving-state update",
#        specs/serving-store/spec.md "User history aggregation".
from serving import history
from serving.models import RatedMovie


def test_recompute_history_empty_user():
    snap = history.recompute_history([], recent_cap=50, positive_cap=50)
    assert snap.interaction_count == 0
    assert snap.recent_movie_ids == ()
    assert snap.positive_movie_ids == ()
    assert snap.last_updated is None


def test_recompute_history_orders_by_recency_then_movie_id():
    rated = [
        RatedMovie(movie_id=1, rating=5.0, rating_ts=100),
        RatedMovie(movie_id=2, rating=3.0, rating_ts=200),
        RatedMovie(movie_id=3, rating=4.5, rating_ts=200),  # tie ts with movie 2
    ]
    snap = history.recompute_history(rated, recent_cap=50, positive_cap=50)
    assert snap.interaction_count == 3
    # ts=200 first (movie 2 before movie 3 by movie_id asc tie-break), then ts=100
    assert snap.recent_movie_ids == (2, 3, 1)
    assert snap.last_updated == 200


def test_recompute_history_positive_filters_by_threshold():
    rated = [
        RatedMovie(movie_id=1, rating=3.5, rating_ts=100),   # below threshold
        RatedMovie(movie_id=2, rating=4.0, rating_ts=200),   # at threshold, positive
        RatedMovie(movie_id=3, rating=5.0, rating_ts=300),   # positive
    ]
    snap = history.recompute_history(rated, recent_cap=50, positive_cap=50, positive_threshold=4.0)
    assert snap.positive_movie_ids == (3, 2)  # most recent first


def test_recompute_history_respects_caps():
    rated = [RatedMovie(movie_id=i, rating=5.0, rating_ts=i) for i in range(1, 21)]
    snap = history.recompute_history(rated, recent_cap=5, positive_cap=3)
    assert len(snap.recent_movie_ids) == 5
    assert len(snap.positive_movie_ids) == 3
    assert snap.interaction_count == 20  # count is NOT capped, only the arrays are


def test_apply_rating_adds_new_movie():
    updated = history.apply_rating([], new_movie_id=10, new_rating=4.0, new_rating_ts=100)
    assert updated == [RatedMovie(movie_id=10, rating=4.0, rating_ts=100)]


def test_apply_rating_updates_existing_when_newer():
    existing = [RatedMovie(movie_id=10, rating=3.0, rating_ts=100)]
    updated = history.apply_rating(existing, new_movie_id=10, new_rating=5.0, new_rating_ts=200)
    assert updated == [RatedMovie(movie_id=10, rating=5.0, rating_ts=200)]


def test_apply_rating_keeps_existing_when_incoming_is_older():
    """Out-of-order delivery: an older event must not overwrite a newer one."""
    existing = [RatedMovie(movie_id=10, rating=5.0, rating_ts=200)]
    updated = history.apply_rating(existing, new_movie_id=10, new_rating=1.0, new_rating_ts=50)
    assert updated == [RatedMovie(movie_id=10, rating=5.0, rating_ts=200)]


def test_apply_rating_replay_is_idempotent():
    """spec: 'Batch replay after crash' — applying the same event twice must leave
    the resulting rated-set identical to applying it once."""
    existing = [RatedMovie(movie_id=10, rating=3.0, rating_ts=100)]
    once = history.apply_rating(existing, new_movie_id=20, new_rating=4.5, new_rating_ts=150)
    twice = history.apply_rating(once, new_movie_id=20, new_rating=4.5, new_rating_ts=150)
    assert once == twice


def test_apply_rating_does_not_duplicate_movie_id():
    existing = [RatedMovie(movie_id=10, rating=3.0, rating_ts=100)]
    updated = history.apply_rating(existing, new_movie_id=10, new_rating=4.0, new_rating_ts=150)
    assert len(updated) == 1
