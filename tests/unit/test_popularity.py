# Tests: openspec/changes/live-weighted-popularity/specs/live-popularity/spec.md
# "Live popularity is the baseline plus applied ledger events", "Same formula and ordering as the offline artifact".
import datetime as dt
import random

import pytest

from serving.popularity import PopStat, deltas_from_events, rank_top, weighted_rating

M, C = 1000, 3.5287


def textbook(v, r, m=M, c=C):
    """The formula as written in the design (not the rewritten one the code uses)."""
    return v / (v + m) * r + m / (v + m) * c


def test_weighted_rating_is_the_textbook_formula():
    assert weighted_rating(173, 173 * 4.468, M, C) == pytest.approx(textbook(173, 4.468), abs=1e-12)
    assert weighted_rating(73945, 73945 * 4.428, M, C) == pytest.approx(textbook(73945, 4.428), abs=1e-12)


def test_the_numbers_of_the_offline_list():
    """Planet Earth and Shawshank, from the old and new popular_movies.json (3 decimals)."""
    assert round(weighted_rating(173, 173 * 4.468, M, C), 3) == 3.667
    assert round(weighted_rating(73945, 73945 * 4.428, M, C), 3) == 4.416


def test_matches_brute_force_on_random_data():
    rng = random.Random(20261003)
    baseline = {}
    for movie_id in range(1, 400):
        v = rng.randint(1, 60000)
        baseline[movie_id] = (v, v * rng.uniform(1.5, 4.9))
    deltas = {mid: (rng.randint(1, 30), rng.uniform(1, 5) * 30) for mid in rng.sample(range(1, 450), 60)}

    got = rank_top(baseline, deltas, m=M, c=C, min_support=100, n=15)

    reference = []
    for mid in set(baseline) | set(deltas):
        n0, s0 = baseline.get(mid, (0, 0.0))
        dn, ds = deltas.get(mid, (0, 0.0))
        v = n0 + dn
        if v >= 100:
            reference.append((-textbook(v, (s0 + ds) / v), -v, mid))
    reference.sort()
    assert [p.movie_id for p in got] == [mid for _w, _v, mid in reference[:15]]
    for p in got:
        assert p.wr == pytest.approx(textbook(p.v, p.r), abs=1e-9)
        assert p.v == p.base_v + p.new_ratings


def test_ties_break_on_rating_count_then_movie_id():
    # R == C gives WR == C exactly whatever v is, so these three tie on WR
    baseline = {30: (500, 500 * 4.0), 10: (900, 900 * 4.0), 20: (900, 900 * 4.0)}
    got = rank_top(baseline, {}, m=1000, c=4.0, min_support=100, n=3)
    assert [p.movie_id for p in got] == [10, 20, 30]      # larger v first, then smaller movieId


def test_min_support_counts_the_live_ratings():
    baseline = {1: (95, 95 * 4.5)}
    five_more = {1: (5, 25.0)}
    four_more = {1: (4, 20.0)}
    assert [p.movie_id for p in rank_top(baseline, five_more, m=M, c=C, min_support=100, n=5)] == [1]
    assert rank_top(baseline, four_more, m=M, c=C, min_support=100, n=5) == []


def test_a_movie_only_in_the_deltas_starts_from_zero():
    got = rank_top({}, {7: (120, 120 * 4.0)}, m=M, c=C, min_support=100, n=5)
    assert len(got) == 1
    assert got[0] == PopStat(movie_id=7, v=120, r=4.0, wr=pytest.approx(textbook(120, 4.0)), base_v=0, new_ratings=120)


def test_m_zero_is_the_plain_average():
    baseline = {1: (173, 173 * 4.468), 2: (73945, 73945 * 4.428), 3: (132, 132 * 4.345)}
    got = rank_top(baseline, {}, m=0, c=C, min_support=100, n=3)
    assert [p.movie_id for p in got] == [1, 2, 3]          # Planet Earth first, as before WR
    assert got[0].wr == pytest.approx(4.468)
    shrunk = rank_top(baseline, {}, m=1000, c=C, min_support=100, n=3)
    assert [p.movie_id for p in shrunk] == [2, 1, 3]       # Shawshank first once WR shrinks the small ones


def test_many_ratings_make_wr_approach_the_average():
    huge = rank_top({1: (10_000_000, 10_000_000 * 4.2)}, {}, m=M, c=C, min_support=100, n=1)[0]
    assert huge.wr == pytest.approx(4.2, abs=1e-3)


def test_one_new_five_star_rating_moves_the_statistics():
    n0, r0 = 12776, 4.258                                   # Seven Samurai in the offline list
    got = rank_top({1: (n0, n0 * r0)}, {1: (1, 5.0)}, m=M, c=C, min_support=100, n=1)[0]
    assert got.v == 12777
    assert got.r == pytest.approx((n0 * r0 + 5) / 12777)
    assert got.new_ratings == 1 and got.base_v == n0


def test_a_low_support_movie_stays_low_after_100_spam_ratings():
    base = (173, 173 * 4.468)                               # Planet Earth
    spam = (100, 500.0)
    got = rank_top({1: base}, {1: spam}, m=M, c=C, min_support=100, n=1)[0]
    assert got.wr == pytest.approx(3.772, abs=1e-3)
    assert got.wr < 4.199                                    # the offline top-10 cut-off


def test_n_larger_than_eligible_returns_all_and_inputs_are_not_changed():
    baseline = {1: (200, 800.0), 2: (300, 1500.0)}
    deltas = {1: (1, 5.0)}
    before = (dict(baseline), dict(deltas))
    got = rank_top(baseline, deltas, m=M, c=C, min_support=100, n=50)
    assert len(got) == 2
    assert (baseline, deltas) == before
    assert got == rank_top(baseline, deltas, m=M, c=C, min_support=100, n=50)      # deterministic


# ---- deltas_from_events -------------------------------------------------------------

T0 = dt.datetime(2026, 10, 2, 12, 0, 0)


def event(eid, user, movie, rating, ts, ingested):
    return {"_id": eid, "userId": user, "movieId": movie, "rating": rating, "timestamp": ts, "ingestedAt": ingested}


def test_one_rating_per_user_and_movie_the_latest_wins():
    events = [
        event("a", 1, 296, 3.0, 1000, T0),
        event("b", 1, 296, 5.0, 2000, T0),               # same pair, later timestamp
        event("c", 2, 296, 4.0, 1500, T0),
    ]
    assert deltas_from_events(events) == {296: (2, 9.0)}


def test_equal_timestamps_fall_back_to_ingestion_time_then_id():
    early, late = T0, T0 + dt.timedelta(seconds=5)
    events = [event("a", 1, 5, 2.0, 1000, late), event("b", 1, 5, 4.0, 1000, early)]
    assert deltas_from_events(events) == {5: (1, 2.0)}
    same = [event("a", 1, 5, 2.0, 1000, T0), event("b", 1, 5, 4.0, 1000, T0)]
    assert deltas_from_events(same) == {5: (1, 4.0)}      # larger _id last


def test_events_inside_the_baseline_are_ignored():
    since = T0
    events = [
        event("old", 1, 10, 5.0, 1, T0 - dt.timedelta(seconds=1)),
        event("edge", 2, 10, 5.0, 1, T0),                 # not strictly after
        event("new", 3, 10, 4.0, 1, T0 + dt.timedelta(seconds=1)),
        {"_id": "none", "userId": 4, "movieId": 10, "rating": 1.0, "timestamp": 1},   # no ingestedAt
    ]
    assert deltas_from_events(events, since) == {10: (1, 4.0)}
    assert deltas_from_events(events) == {10: (4, 15.0)}     # without a mark everything counts


def test_aware_and_naive_datetimes_compare_as_utc():
    aware = T0.replace(tzinfo=dt.timezone.utc)
    events = [event("a", 1, 3, 5.0, 1, T0 + dt.timedelta(seconds=1))]
    assert deltas_from_events(events, aware) == {3: (1, 5.0)}


def test_no_events_no_deltas():
    assert deltas_from_events([]) == {}
