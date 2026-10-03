# Tests: scripts/demo_wr_explain.py (read-only explanation of WR on the system's own numbers). The two lists are written to a temp dir,
# so the test does not depend on the 1.7 GB data bundle that is not in git.
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import demo_wr_explain as explain  # noqa: E402

OLD = [   # the list before WR: plain average, ordered by it
    {"movieId": 1, "title": "Planet Earth (2006)", "genres": "Documentary", "rank": 1, "score": 4.468, "support": 173},
    {"movieId": 2, "title": "Shawshank Redemption, The (1994)", "genres": "Drama", "rank": 2, "score": 4.428, "support": 73945},
    {"movieId": 3, "title": "The Blue Planet (2001)", "genres": "Documentary", "rank": 3, "score": 4.345, "support": 132},
    {"movieId": 4, "title": "Godfather, The (1972)", "genres": "Crime", "rank": 4, "score": 4.344, "support": 47709},
]
NEW = [
    {"movieId": 2, "title": "Shawshank Redemption, The (1994)", "genres": "Drama", "rank": 1, "score": 4.416, "support": 73945},
    {"movieId": 4, "title": "Godfather, The (1972)", "genres": "Crime", "rank": 2, "score": 4.327, "support": 47709},
    {"movieId": 5, "title": "Casablanca (1942)", "genres": "Drama", "rank": 3, "score": 4.199, "support": 26335},
]


@pytest.fixture()
def files(tmp_path, monkeypatch):
    for name, items in (("old.json", OLD), ("new.json", NEW)):
        (tmp_path / name).write_text(json.dumps({"items": items}), encoding="utf-8")
    monkeypatch.setattr(explain, "OLD", tmp_path / "old.json")
    monkeypatch.setattr(explain, "NEW", tmp_path / "new.json")


def run(capsys, *argv):
    monkey = sys.argv
    try:
        sys.argv = ["demo_wr_explain.py", *argv]
        assert explain.main() == 0
    finally:
        sys.argv = monkey
    return capsys.readouterr().out


def test_wr_pulls_the_small_movies_down_and_the_big_ones_stay(files, capsys):
    out = run(capsys)
    assert "Planet Earth (2006)" in out and "#1  -> #3" in out                      # was first, now third of these four
    assert "Shawshank Redemption, The (1994)   73945  4.428    98.7%     4.416   #2  -> #1" in out
    assert "left the top 10: Planet Earth (2006), The Blue Planet (2001)" in out
    assert "entered the top 10: Casablanca (1942)" in out


def test_the_step_by_step_uses_the_formula_with_the_systems_numbers(files, capsys):
    out = run(capsys)
    assert "w = 173/(173+1000) = 0.147   (14.7% own average, 85.3% pulled to the global mean)" in out
    assert "WR = 0.147 x 4.468 + 0.853 x 3.5287 = 3.667" in out


def test_m_zero_gives_the_plain_average_back(files, capsys):
    out = run(capsys, "--m", "0")
    assert "#1  -> #1" in out and "100.0%" in out
    assert "sections 1-3 show what-if numbers" in out
