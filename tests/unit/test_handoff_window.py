# Tests: specs/model-refresh-orchestration/spec.md "Handoff window bounded by committed events".
# Design: address-person1-review-findings D-1.
import datetime as dt

from orchestration.handoff_window import committed_up_to, in_window, window_query

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 2, 9, 0, 0, tzinfo=UTC)
EPOCH = dt.datetime(1970, 1, 1, tzinfo=UTC)


def at(seconds: float) -> dt.datetime:
    return T0 + dt.timedelta(seconds=seconds)


def handoff(events: list[dict], since: dt.datetime, stream_state: dict | None):
    """What retrain_trigger does, with the Mongo query replaced by `in_window`:
    returns (exported event ids, new watermark)."""
    upper = committed_up_to(stream_state)
    if upper is None:
        return [], since
    exported = [e["_id"] for e in events if in_window(e["ingestedAt"], since, upper)]
    return exported, upper


def test_batch_ingested_after_last_commit_is_not_exported():
    # batch 1 committed at T0 (ingestedAt T0-1); batch 2 stamped T0+5 and written after the handoff read lastRunAt
    events = [{"_id": "a", "ingestedAt": at(-1)}, {"_id": "b", "ingestedAt": at(5)}]
    exported, watermark = handoff(events, EPOCH, {"lastRunAt": at(0)})
    assert exported == ["a"]
    assert watermark == at(0)


def test_partially_inserted_batch_is_not_exported_and_not_lost_by_the_new_watermark():
    # batch 2 (stamped T0+5) has inserted only "b1" when the handoff runs; "b2" lands after
    first, watermark = handoff(
        [{"_id": "a", "ingestedAt": at(-1)}, {"_id": "b1", "ingestedAt": at(5)}], EPOCH, {"lastRunAt": at(0)})
    assert first == ["a"]

    all_events = [{"_id": "a", "ingestedAt": at(-1)}, {"_id": "b1", "ingestedAt": at(5)}, {"_id": "b2", "ingestedAt": at(5)}]
    second, _ = handoff(all_events, watermark, {"lastRunAt": at(6)})
    assert sorted(second) == ["b1", "b2"]


def test_event_exactly_at_last_run_at_is_exported():
    exported, _ = handoff([{"_id": "a", "ingestedAt": at(0)}], EPOCH, {"lastRunAt": at(0)})
    assert exported == ["a"]


def test_event_exactly_at_the_watermark_is_not_exported_twice():
    exported, _ = handoff([{"_id": "a", "ingestedAt": at(0)}], at(0), {"lastRunAt": at(10)})
    assert exported == []


def test_two_handoffs_in_a_row_export_every_committed_event_exactly_once():
    events = [{"_id": f"e{i}", "ingestedAt": at(i)} for i in range(1, 11)]   # ingested at T0+1 .. T0+10
    # first handoff while batches up to T0+4 are committed, the rest are still arriving
    first, watermark = handoff(events, EPOCH, {"lastRunAt": at(4)})
    second, watermark = handoff(events, watermark, {"lastRunAt": at(10)})
    third, _ = handoff(events, watermark, {"lastRunAt": at(10)})

    assert sorted(first + second) == sorted(e["_id"] for e in events)
    assert len(first + second) == len(set(first + second))
    assert third == []


def test_no_ratings_stream_state_means_nothing_to_hand_off():
    assert committed_up_to(None) is None
    assert committed_up_to({}) is None
    assert committed_up_to({"lastBatchId": 3}) is None          # state without lastRunAt
    exported, watermark = handoff([{"_id": "a", "ingestedAt": at(0)}], EPOCH, None)
    assert exported == [] and watermark == EPOCH


def test_naive_datetimes_from_pymongo_are_taken_as_utc():
    naive_last_run = dt.datetime(2026, 10, 2, 9, 0, 0)               # what pymongo returns
    assert committed_up_to({"lastRunAt": naive_last_run}) == at(0)
    assert in_window(dt.datetime(2026, 10, 2, 8, 59, 59), EPOCH, at(0))
    assert not in_window(dt.datetime(2026, 10, 2, 9, 0, 1), EPOCH, at(0))


def test_window_query_is_exclusive_below_and_inclusive_above():
    query = window_query(at(-10), at(0))
    assert query == {"ingestedAt": {"$gt": at(-10), "$lte": at(0)}}
