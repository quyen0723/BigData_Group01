# Tests: openspec/changes/live-weighted-popularity/specs/live-popularity "Baseline statistics from the training split".
# The Spark job itself runs in the spark container (task 2.3); here the pure helpers and the real evidence files.
import datetime as dt
from pathlib import Path

import pytest

from loaders.movie_stats_core import (
    META_ID,
    BaselineMismatch,
    make_meta,
    parse_ledger_since,
    read_recorded_c,
    read_split_stats,
    verify_baseline,
    verify_stored,
)

EVIDENCE = Path(__file__).resolve().parents[2] / "evidence"


def test_reads_the_real_split_files_of_the_offline_run():
    split = read_split_stats((EVIDENCE / "split_stats.csv").read_text(encoding="utf-8"))
    assert split == {"n_train": 22_399_368, "cut_val": 1476348398.0}
    assert read_recorded_c((EVIDENCE / "b3_1_split_baseline.txt").read_text(encoding="utf-8")) == 3.5287


def test_split_stats_needs_exactly_one_data_row():
    header = "n_total,n_train,n_val,n_test,cut_val\n"
    with pytest.raises(ValueError):
        read_split_stats(header)
    with pytest.raises(ValueError):
        read_split_stats(header + "1,2,3,4,5\n1,2,3,4,5\n")


def test_recorded_c_missing_gives_none():
    assert read_recorded_c("no such line") is None


def test_the_offline_split_passes():
    verify_baseline(n_ratings=22_399_368, mean=3.52868, n_train=22_399_368, recorded_c=3.5287)


def test_a_wrong_cutoff_is_refused():
    # a later cutoff lets val ratings in: more ratings than n_train
    with pytest.raises(BaselineMismatch, match="n_train"):
        verify_baseline(n_ratings=24_000_000, mean=3.5287, n_train=22_399_368, recorded_c=3.5287)
    # streamed ratings or a different file: same count would be a coincidence, the mean still has to match
    with pytest.raises(BaselineMismatch, match="C = 3.5287"):
        verify_baseline(n_ratings=22_399_368, mean=3.60, n_train=22_399_368, recorded_c=3.5287)


def test_meta_document_has_everything_the_api_needs():
    now = dt.datetime(2026, 10, 3, 8, 30, tzinfo=dt.timezone.utc)
    meta = make_meta(c=3.52868, recorded_c=3.5287, cutoff=1476348398.0, cutoff_source="split_stats.csv",
                     ratings=22_399_368, movies=36_526, generated_at=now, ledger_since=None)
    assert meta["_id"] == META_ID == "_meta"
    assert meta["C"] == 3.52868 and meta["ratings"] == 22_399_368 and meta["movies"] == 36_526
    assert meta["generatedAt"] == "2026-10-03T08:30:00Z"
    assert meta["ledgerSince"] is None


def test_a_ledger_since_without_an_offset_is_utc_not_the_machines_local_time():
    # the old parsing used .astimezone(utc) on a naive value, which reads it as local time: on a UTC+7 laptop 00:00 became 17:00 the day before
    assert parse_ledger_since("2026-10-03T00:00:00") == dt.datetime(2026, 10, 3, 0, 0)
    assert parse_ledger_since("2026-10-03T00:00:00Z") == dt.datetime(2026, 10, 3, 0, 0)
    assert parse_ledger_since("2026-10-03T07:00:00+07:00") == dt.datetime(2026, 10, 3, 0, 0)
    assert parse_ledger_since("2026-10-02T17:00:00-07:00") == dt.datetime(2026, 10, 3, 0, 0)
    assert parse_ledger_since("  2026-10-03T00:00:00.250Z ") == dt.datetime(2026, 10, 3, 0, 0, 0, 250000)
    assert parse_ledger_since("2026-10-03T00:00:00").tzinfo is None             # what pymongo stores and compares with ingestedAt


def test_what_landed_in_mongo_must_match_what_was_counted():
    verify_stored(stored_ratings=22_399_368, stored_sum=22_399_368 * 3.52868, n_ratings=22_399_368, mean=3.52868)
    with pytest.raises(BaselineMismatch, match="22,399,000"):
        verify_stored(stored_ratings=22_399_000, stored_sum=22_399_000 * 3.52868, n_ratings=22_399_368, mean=3.52868)
    with pytest.raises(BaselineMismatch, match="mean"):
        verify_stored(stored_ratings=100, stored_sum=100 * 3.0, n_ratings=100, mean=3.52868)
