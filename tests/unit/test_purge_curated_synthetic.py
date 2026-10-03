# Tests: loaders/purge_curated_synthetic.py, only the parts that run before Spark starts (guards and recovery messages).
import pytest

from loaders import purge_curated_synthetic as job


def run(tmp_path, *args):
    return job.main(["--path", str(tmp_path), "--year", "2026", *args])


def test_a_range_that_reaches_a_real_user_is_refused_before_anything_happens(tmp_path, capsys):
    (tmp_path / "year=2026").mkdir()
    assert run(tmp_path, "--from", "700000", "--to", "999999999") == 2
    assert "REFUSED" in capsys.readouterr().out


def test_apply_needs_the_streaming_service_to_be_stopped(tmp_path, capsys):
    (tmp_path / "year=2026").mkdir()
    assert run(tmp_path, "--all-synthetic", "--apply") == 2
    assert "--streaming-stopped" in capsys.readouterr().out


def test_no_partition_and_no_leftovers_is_nothing_to_do(tmp_path, capsys):
    assert run(tmp_path, "--all-synthetic") == 0
    assert "nothing to do" in capsys.readouterr().out


def test_an_interrupted_swap_is_recognised_and_the_recovery_commands_are_printed(tmp_path, capsys):
    (tmp_path / "_purge_tmp_year=2026").mkdir()
    (tmp_path / "_purge_old_year=2026").mkdir()                              # year=2026 itself is missing: killed between the two renames
    assert run(tmp_path, "--all-synthetic") == 2
    out = capsys.readouterr().out
    assert "MISSING" in out and "roll forward" in out and "roll back" in out
    assert f"mv {tmp_path / '_purge_old_year=2026'} {tmp_path / 'year=2026'}" in out
    assert f"mv {tmp_path / '_purge_tmp_year=2026'} {tmp_path / 'year=2026'}" in out
