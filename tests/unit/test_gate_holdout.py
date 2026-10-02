# Tests: specs/model-refresh-orchestration/spec.md "Promotion gate fails closed without a holdout cut".
# Design: address-person1-review-findings D-5.
from orchestration.gate_holdout import MISSING_CUT_TEST, resolve_cut_test

CUT = 1573258563.0


def card(cut=None, **extra):
    return {"split": {"cut_test": cut, **extra}} if cut is not None else {"split": extra}


def test_both_cards_without_cut_gives_none():
    assert resolve_cut_test({}, {}) is None
    assert resolve_cut_test(None, None) is None
    assert resolve_cut_test(card(), card(method="global_temporal")) is None
    assert resolve_cut_test({"split": None}, {"split": "oops"}) is None


def test_only_active_card_has_the_cut():
    assert resolve_cut_test({}, card(CUT)) == CUT


def test_only_candidate_card_has_the_cut():
    assert resolve_cut_test(card(CUT), {}) == CUT


def test_candidate_cut_wins_over_active():
    assert resolve_cut_test(card(2.0), card(1.0)) == 2.0


def test_zero_is_a_value_not_a_missing_cut():
    assert resolve_cut_test(card(0), card(CUT)) == 0.0


def test_string_number_is_converted():
    assert resolve_cut_test(card("1573258563"), {}) == CUT


def test_unparseable_cut_counts_as_missing_instead_of_raising():
    for bad in ("n/a", "", [1, 2], {"v": 1}):
        assert resolve_cut_test(card(bad), {}) is None, bad
    assert resolve_cut_test(card("n/a"), card(CUT)) == CUT      # falls back to the other card


def test_failure_message_names_the_missing_cut():
    assert "cut_test" in MISSING_CUT_TEST
    assert "full curated ratings" in MISSING_CUT_TEST
