# Tests: openspec/changes/live-weighted-popularity/specs/demo-popularity-live "Cleanup of synthetic ratings".
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import purge_demo_ratings as purge  # noqa: E402


class FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    @staticmethod
    def _match(doc, flt):
        rng = flt["userId"]
        return rng["$gte"] <= doc["userId"] <= rng["$lte"]

    def count_documents(self, flt):
        return sum(1 for d in self.docs if self._match(d, flt))

    def delete_many(self, flt):
        keep = [d for d in self.docs if not self._match(d, flt)]
        deleted = len(self.docs) - len(keep)
        self.docs = keep
        return type("R", (), {"deleted_count": deleted})()


def fake_db():
    users = [1, 127249, 700008, 999100003, 999200001, 999200002, 999200003, 999300001]
    return {
        "rating_events": FakeCollection({"userId": u, "movieId": 296} for u in users + [999200001]),     # one user rated twice
        "user_rated": FakeCollection({"userId": u, "movieId": 296} for u in users),
        "user_history": FakeCollection({"userId": u} for u in users),
    }


def users_left(db, name):
    return sorted(d["userId"] for d in db[name].docs)


def test_the_default_is_a_dry_run_that_only_counts(capsys):
    db = fake_db()
    assert purge.main([], db=db) == 0
    out = capsys.readouterr().out
    assert "dry run: nothing deleted" in out
    assert "rating_events       4 documents" in out and "user_rated          3 documents" in out
    assert len(db["rating_events"].docs) == 9                          # nothing deleted


def test_yes_deletes_only_the_range_in_all_three_collections(capsys):
    db = fake_db()
    assert purge.main(["--yes"], db=db) == 0
    for name in ("user_rated", "user_history"):
        assert users_left(db, name) == [1, 127249, 700008, 999100003, 999300001]
    assert 999200001 not in [d["userId"] for d in db["rating_events"].docs]
    assert "deleted 4, left 0" in capsys.readouterr().out
    assert purge.main(["--yes"], db=db) == 0                              # running again deletes nothing and is fine


def test_all_synthetic_takes_the_whole_reserved_range():
    db = fake_db()
    assert purge.main(["--all-synthetic", "--yes"], db=db) == 0
    assert users_left(db, "user_history") == [1, 127249, 700008]


@pytest.mark.parametrize("low,high", [(1, 999_200_010), (999_200_001, 1_000_000_500), (700_008, 700_008), (999_000_000 - 1, 999_000_005)])
def test_a_range_that_reaches_a_real_user_is_refused_and_nothing_is_deleted(low, high, capsys):
    db = fake_db()
    assert purge.main(["--from", str(low), "--to", str(high), "--yes"], db=db) == 2
    assert "REFUSED" in capsys.readouterr().out
    assert len(db["user_history"].docs) == 8


def test_an_empty_range_is_refused(capsys):
    assert purge.main(["--from", "999300000", "--to", "999200000"], db=fake_db()) == 2


def test_dry_run_flag_wins_over_yes():
    db = fake_db()
    assert purge.main(["--yes", "--dry-run"], db=db) == 0
    assert len(db["user_history"].docs) == 8


def test_the_guard_function_itself():
    purge.validate_range(999_000_000, 999_999_999)
    with pytest.raises(ValueError):
        purge.validate_range(998_999_999, 999_100_000)
    with pytest.raises(ValueError):
        purge.validate_range(999_100_000, 1_000_000_000)


def test_an_overridden_collection_name_is_the_one_that_is_counted_and_purged(capsys):
    names = purge.real_names({"rating_events": "rating_events_v2"})
    assert names == {"rating_events": "rating_events_v2", "user_rated": "user_rated", "user_history": "user_history"}
    db = fake_db()
    db["rating_events_v2"] = db.pop("rating_events")
    result = purge.purge(db, 999_200_000, 999_299_999, True, names)
    assert result["deleted"]["rating_events"] == 4 and result["after"] == {"rating_events": 0, "user_rated": 0, "user_history": 0}
    assert users_left(db, "rating_events_v2") == [1, 127249, 700008, 999100003, 999300001]
    assert "rating_events" not in db                                          # nothing was created or counted under the old name


def test_a_missing_collection_name_is_not_silently_skipped():
    db = fake_db()
    with pytest.raises(KeyError):
        purge.purge(db, 999_200_000, 999_299_999, False, purge.real_names({"rating_events": "typo_collection"}))
