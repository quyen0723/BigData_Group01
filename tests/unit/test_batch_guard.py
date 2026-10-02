# Tests: specs/rating-stream-ingestion/spec.md "Batch guard bound to the checkpoint that wrote it".
# Design: address-person1-review-findings D-2.
import json

from streaming.batch_guard import PROCESS, SKIP, decide_batch_action, read_stream_id

STREAM = "89fe5d54-ae65-46eb-918b-3e33eeed263e"
OTHER = "c044a59b-ed4a-4201-a84e-e76c1276dd6a"


def state(last=43, stream_id=STREAM):
    doc = {"_id": "ratings_stream", "lastBatchId": last}
    if stream_id is not None:
        doc["streamId"] = stream_id
    return doc


def test_no_state_is_processed():
    assert decide_batch_action(None, 0, STREAM).action == PROCESS
    assert decide_batch_action({}, 0, STREAM).action == PROCESS
    assert decide_batch_action({"_id": "ratings_stream"}, 0, STREAM).action == PROCESS


def test_same_stream_and_batch_already_committed_is_skipped():
    decision = decide_batch_action(state(last=43), 43, STREAM)
    assert decision.action == SKIP
    assert "already committed (last=43), skipping" in decision.reason
    assert not decision.warn
    assert decide_batch_action(state(last=43), 12, STREAM).action == SKIP


def test_same_stream_and_new_batch_is_processed():
    decision = decide_batch_action(state(last=43), 44, STREAM)
    assert decision.action == PROCESS and not decision.warn


def test_changed_checkpoint_is_processed_with_a_warning():
    # checkpoint dir lost: Spark counts from 0 again while Mongo still says 43
    for batch_id in (0, 1, 43, 44):
        decision = decide_batch_action(state(last=43), batch_id, OTHER)
        assert decision.action == PROCESS
        assert decision.warn
        assert "checkpoint changed" in decision.reason


def test_unreadable_stream_id_never_skips():
    decision = decide_batch_action(state(last=43), 5, None)
    assert decision.action == PROCESS and decision.warn
    assert "unreadable" in decision.reason


def test_state_written_before_the_change_is_processed_with_a_warning():
    decision = decide_batch_action(state(last=69, stream_id=None), 1, STREAM)
    assert decision.action == PROCESS and decision.warn
    assert "no recorded stream identity" in decision.reason


def test_read_stream_id_reads_the_spark_metadata_file(tmp_path):
    (tmp_path / "metadata").write_text(json.dumps({"id": STREAM}), encoding="utf-8")
    assert read_stream_id(tmp_path) == STREAM


def test_read_stream_id_missing_file_is_none(tmp_path):
    assert read_stream_id(tmp_path) is None
    assert read_stream_id(tmp_path / "does-not-exist") is None


def test_read_stream_id_broken_content_is_none(tmp_path):
    for content in ("", "not json", "[]", "{}", '{"id": 7}', '{"id": ""}'):
        (tmp_path / "metadata").write_text(content, encoding="utf-8")
        assert read_stream_id(tmp_path) is None, content
