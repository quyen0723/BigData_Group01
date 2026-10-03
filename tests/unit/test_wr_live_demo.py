# Tests: openspec/changes/live-weighted-popularity/specs/demo-popularity-live "Live demo script".
# The script talks to the API through one function, so here a fake API stands in; it ranks with the real serving.popularity code.
import json
import random
import sys
import uuid
from pathlib import Path

import pytest

from serving.popularity import rank_top

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import wr_live_demo as wr  # noqa: E402

M, C = 1000, 3.5
# movie -> (rating count, rating sum). 1 > 2 > 3 by a hair > 4; 5 is a Planet-Earth-like movie (few ratings, high average).
BASELINE = {
    1: (60_000, 60_000 * 4.40),
    2: (33_000, 33_000 * 4.30),
    3: (12_800, 12_800 * 4.33),
    4: (26_000, 26_000 * 4.27),
    5: (173, 173 * 4.468),
    6: (40_000, 40_000 * 4.20),
}
# seven solid fillers (WR about 4.0) so that the top 10 has a cut-off and a low-support movie can be outside it
BASELINE.update({101 + i: (20_000, 20_000 * (4.00 + 0.01 * i)) for i in range(7)})
TITLES = {mid: f"Movie {mid}" for mid in BASELINE}


class FakeTime:
    """The script sleeps while it waits for streaming; here sleeping just moves a clock."""
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeApi:
    def __init__(self, source="live", never_applies=False, fail_post=None, history=None, poll=60):
        self.poll = poll                 # ratingPollTimeoutSeconds of /debug/system; None = the route is not there
        self.ledger = {}                 # eventId -> (userId, movieId, rating)
        self.posts = []                  # every POST /ratings body, in order
        self.source = source
        self.never_applies = never_applies
        self.fail_post = fail_post or {}     # userId -> list of statuses to answer before 202
        self.history = history or {}         # userId -> interaction_count of other history

    def deltas(self):
        out = {}
        for user, movie, rating in self.ledger.values():
            n, s = out.get(movie, (0, 0.0))
            out[movie] = (n + 1, s + rating)
        return out

    def popularity(self, n, m, deltas):
        new = self.deltas() if deltas else {}
        top = rank_top(BASELINE, new, m=m, c=C, min_support=100, n=n)
        base = {p.movie_id: i + 1 for i, p in enumerate(rank_top(BASELINE, {}, m=m, c=C, min_support=100, n=200))}
        if self.source == "artifact":
            return {"source": "artifact", "m": m, "c": None, "appliedEvents": 0, "items": []}
        return {
            "source": "live", "liveEnabled": True, "preview": m != M, "m": float(m), "c": C, "minSupport": 100,
            "appliedEvents": sum(c for c, _ in new.values()),
            "items": [
                {"rank": i + 1, "movieId": p.movie_id, "title": TITLES[p.movie_id], "genres": "Drama", "avgRating": p.r, "support": p.v,
                 "baseSupport": p.base_v, "newRatings": p.new_ratings, "wr": p.wr, "baseRank": base.get(p.movie_id)}
                for i, p in enumerate(top)
            ],
        }

    def __call__(self, method, path, body=None):
        if method == "GET" and path == "/debug/system":
            return (404, {}) if self.poll is None else (200, {"demo": {"ratingPollTimeoutSeconds": self.poll}})
        if method == "GET" and path.startswith("/debug/popularity"):
            q = dict(kv.split("=") for kv in path.split("?", 1)[1].split("&"))
            return 200, self.popularity(int(q["n"]), float(q.get("m", M)), q.get("deltas") != "false")
        if method == "GET" and path.startswith("/ratings/"):
            eid = path.rsplit("/", 1)[1]
            return 200, {"eventId": eid, "status": "applied" if eid in self.ledger else "pending"}
        if method == "GET" and path.startswith("/debug/users/"):
            user = int(path.rsplit("/", 1)[1])
            return 200, {"userId": user, "interaction_count": self.history.get(user, 0)}
        if method == "POST" and path == "/ratings":
            self.posts.append(body)
            queue = self.fail_post.get(body["userId"], [])
            if queue:
                return queue.pop(0), {"detail": "kafka delivery timed out" if queue is not None else ""}
            if not self.never_applies:
                self.ledger[body["eventId"]] = (body["userId"], body["movieId"], body["rating"])
            return 202, {"eventId": body["eventId"], "status": "accepted"}
        return 404, {"detail": f"{method} {path}"}


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    clock = FakeTime()
    monkeypatch.setattr(wr, "time", clock)
    return clock


def run(argv, api=None):
    return wr.main(argv, http=api or FakeApi())


# ---- pure helpers -------------------------------------------------------------------

def test_ratings_needed_matches_a_brute_force_search():
    rng = random.Random(7)
    for _ in range(200):
        v = rng.randint(100, 70_000)
        total = v * rng.uniform(3.0, 4.6)
        upper = rng.uniform(3.6, 4.5)
        got = wr.ratings_needed(upper, v, total, M, C, 5.0)
        n = 0
        while wr.wr_after(v, total, n, 5.0, M, C) <= upper and n < 200_000:
            n += 1
        assert got == n


def test_ratings_needed_edge_cases():
    assert wr.ratings_needed(3.0, 1000, 1000 * 4.5, M, C) == 0                 # already above
    assert wr.ratings_needed(4.6, 1000, 1000 * 4.0, M, C, stars=4.5) is None    # 4.5 stars cannot reach 4.6


def test_the_seven_samurai_case_needs_about_17_ratings():
    # numbers of the real list: #8 Cuckoo's Nest WR 4.2063, #9 Seven Samurai v 12,776 average 4.2583 (m=1000, C=3.5287)
    assert 15 <= wr.ratings_needed(4.2063, 12_776, 12_776 * 4.2583, 1000, 3.5287) <= 19


def test_the_planet_earth_spam_numbers():
    v, total = 173, 173 * 4.468
    assert wr.wr_after(v, total, 0, 5.0, 1000, 3.5287) == pytest.approx(3.667, abs=1e-3)
    assert wr.wr_after(v, total, 100, 5.0, 1000, 3.5287) == pytest.approx(3.772, abs=1e-3)
    needed = wr.ratings_needed(4.199, v, total, 1000, 3.5287)
    assert 770 <= needed <= 790                                                # "about 780"


def test_event_ids_are_stable_distinct_and_valid_uuids():
    assert wr.event_id(999200001, 2019) == wr.event_id(999200001, 2019)
    assert wr.event_id(999200001, 2019) != wr.event_id(999200002, 2019)
    assert wr.event_id(999200001, 2019) != wr.event_id(999200001, 2020)
    assert str(uuid.UUID(wr.event_id(1, 2))) == wr.event_id(1, 2)


def test_compare_with_artifact():
    items = [{"movieId": 1, "wr": 4.4162}, {"movieId": 2, "wr": 4.3271}]
    artifact = [{"movieId": 1, "score": 4.416}, {"movieId": 2, "score": 4.327}]
    assert wr.compare_with_artifact(items, artifact) == []
    assert any("order differs" in p for p in wr.compare_with_artifact(items[::-1], artifact))
    assert any("differs by" in p for p in wr.compare_with_artifact([{"movieId": 1, "wr": 4.4162}, {"movieId": 2, "wr": 4.35}], artifact))


# ---- commands -----------------------------------------------------------------------

def artifact_file(tmp_path, items):
    path = tmp_path / "popular_movies.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return str(path)


def test_check_passes_when_the_baseline_is_the_artifact(tmp_path, capsys):
    base = FakeApi().popularity(10, M, False)["items"]
    artifact = [{"movieId": i["movieId"], "score": round(i["wr"], 3)} for i in base[:5]]
    assert run(["check", "--artifact", artifact_file(tmp_path, artifact)]) == 0
    assert "PASS" in capsys.readouterr().out


def test_check_fails_on_a_different_order_or_without_a_baseline(tmp_path, capsys):
    base = FakeApi().popularity(10, M, False)["items"]
    swapped = [{"movieId": i["movieId"], "score": round(i["wr"], 3)} for i in base[:5]]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert run(["check", "--artifact", artifact_file(tmp_path, swapped)]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert run(["check", "--artifact", artifact_file(tmp_path, swapped)], FakeApi(source="artifact")) == 1


def test_plan_names_the_closest_pair_and_suggests_the_command(capsys):
    assert run(["plan"]) == 0
    out = capsys.readouterr().out
    assert "closest pair: #3 Movie 3 needs about" in out          # movie 3 trails movie 2 by a hair
    assert "inject --movie 3 --n" in out


def test_inject_sends_n_ratings_waits_and_shows_the_rank_change(capsys):
    api = FakeApi()
    upper = wr.wr_after(33_000, 33_000 * 4.30, 0, 5.0, M, C)               # movie 2, the one movie 3 has to pass
    n = wr.ratings_needed(upper, 12_800, 12_800 * 4.33, M, C) + 2
    assert 60 < n < 400
    assert run(["inject", "--movie", "3", "--n", str(n)], api) == 0
    out = capsys.readouterr().out
    assert len(api.posts) == n
    assert {p["userId"] for p in api.posts} == set(range(wr.USER_START, wr.USER_START + n))
    assert all(p["movieId"] == 3 and p["rating"] == 5.0 for p in api.posts)
    assert all(p["eventId"] == wr.event_id(p["userId"], 3) for p in api.posts)
    assert f"all {n} applied" in out
    assert "up 1 (was #3" in out                                   # movie 3 passed movie 2
    top = api.popularity(3, M, True)["items"]
    assert [i["movieId"] for i in top] == [1, 3, 2]


def test_running_inject_again_sends_nothing_new(capsys):
    api = FakeApi()
    run(["inject", "--movie", "3", "--n", "25"], api)
    capsys.readouterr()
    assert run(["inject", "--movie", "3", "--n", "25"], api) == 0
    assert len(api.posts) == 25                                      # still the first run's 25
    assert "already exist" in capsys.readouterr().out


def test_dry_run_lists_what_it_would_send_and_sends_nothing(capsys):
    api = FakeApi()
    assert run(["inject", "--movie", "3", "--n", "30", "--dry-run"], api) == 0
    out = capsys.readouterr().out
    assert api.posts == [] and api.ledger == {}
    assert "would send: user 999200001" in out and "--dry-run: nothing sent" in out
    assert "and 25 more" in out


def test_api_and_dry_run_are_accepted_before_or_after_the_command(capsys):
    api = FakeApi()
    assert wr.main(["--api", "http://x:1", "inject", "--movie", "3", "--n", "2", "--dry-run"], http=api) == 0
    assert wr.main(["inject", "--api", "http://x:1", "--movie", "3", "--n", "2", "--dry-run"], http=api) == 0
    assert wr.main(["plan", "--dry-run"], http=api) == 0
    assert wr.main(["check", "--dry-run"], http=api) in (0, 1)
    assert api.posts == []


def test_a_user_with_other_history_is_skipped_not_mixed_in():
    api = FakeApi(history={wr.USER_START + 1: 12})
    run(["inject", "--movie", "3", "--n", "3"], api)
    assert [p["userId"] for p in api.posts] == [wr.USER_START, wr.USER_START + 2, wr.USER_START + 3]


def test_a_503_is_retried_with_the_same_event_id():
    api = FakeApi(fail_post={wr.USER_START: [503, 503]})
    assert run(["inject", "--movie", "3", "--n", "2"], api) == 0
    first_user = [p for p in api.posts if p["userId"] == wr.USER_START]
    assert len(first_user) == 3 and len({p["eventId"] for p in first_user}) == 1


def test_a_refused_rating_stops_with_an_error(capsys):
    api = FakeApi(fail_post={wr.USER_START: [422]})
    assert run(["inject", "--movie", "3", "--n", "2"], api) == 1
    assert "FAILED to send" in capsys.readouterr().out


def test_it_gives_up_when_streaming_never_applies(capsys):
    api = FakeApi(never_applies=True)
    assert run(["inject", "--movie", "3", "--n", "3", "--timeout", "10"], api) == 1
    assert "TIMEOUT: 3 ratings are still pending" in capsys.readouterr().out


def test_spam_prints_the_plan_for_the_lowest_support_high_average_movie(capsys):
    api = FakeApi()
    assert run(["spam", "--n", "0"], api) == 0
    out = capsys.readouterr().out
    assert "Movie 5" in out and "173 ratings" in out
    assert "+ 10 five-star ratings -> WR 3.6" in out and "+100 five-star ratings -> WR 3.7" in out
    assert "(still outside the top 10)" in out
    assert "WR resists, it is not immune" in out
    assert api.posts == []


def test_spam_sends_when_asked_and_the_movie_stays_out_of_the_top(capsys):
    api = FakeApi()
    assert run(["spam", "--n", "100"], api) == 0
    assert len(api.posts) == 100 and all(p["movieId"] == 5 for p in api.posts)
    assert 5 not in [i["movieId"] for i in api.popularity(10, M, True)["items"]]
    out = capsys.readouterr().out
    assert "Movie 5 now: 273 ratings" in out and "still outside the top 10" in out          # the real numbers after the run, next to the plan


def test_arguments_are_checked():
    with pytest.raises(SystemExit):
        run(["inject", "--movie", "3", "--n", "0"])
    with pytest.raises(SystemExit):
        run(["inject", "--movie", "3", "--n", "5", "--stars", "5.3"])
    with pytest.raises(SystemExit):
        run(["spam", "--n", "-1"])


def test_the_wait_follows_the_apis_rating_poll_timeout(fake_clock, capsys):
    api = FakeApi(never_applies=True, poll=45)
    start = fake_clock.now
    assert run(["inject", "--movie", "3", "--n", "3"], api) == 1
    assert 45.6 <= fake_clock.now - start < 45.6 + 4                  # 45 s from the API + 0.2 s per rating, in 2 s steps


def test_the_wait_is_60_seconds_when_the_api_does_not_say(fake_clock):
    api = FakeApi(never_applies=True, poll=None)
    start = fake_clock.now
    assert run(["inject", "--movie", "3", "--n", "3"], api) == 1
    assert 60.6 <= fake_clock.now - start < 60.6 + 4


def test_check_does_not_fail_on_the_exact_rounding_boundary_of_the_artifact():
    # the artifact rounds to 3 decimals, so a correct WR can be 0.0005 away; float noise must not turn that into a FAIL
    assert wr.compare_with_artifact([{"movieId": 1, "wr": 0.8005}], [{"movieId": 1, "score": 0.8}]) == []
    assert wr.compare_with_artifact([{"movieId": 1, "wr": 4.4166}], [{"movieId": 1, "score": 4.416}])      # 0.0006 away is a real difference
