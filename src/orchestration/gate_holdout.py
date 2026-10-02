# gate_holdout.py — which holdout the promotion gate evaluates on (pure; no pyspark import).
# Spec: specs/model-refresh-orchestration/spec.md "Promotion gate fails closed without a holdout cut".
# Design: address-person1-review-findings D-5.
#
# G1-G3 compare RMSE on the held-out part of the curated ratings, `timestamp >= split.cut_test`.
# The cut lives in the model cards. Without it the filter used to be dropped, which silently evaluated
# both models on the whole dataset, training rows included. A gate that is meant to fail closed
# must not do that, so a missing cut is reported as a failed check instead.
from __future__ import annotations

MISSING_CUT_TEST = (
    "no split.cut_test in either model card; refusing to evaluate on the full curated ratings"
)


def _cut_of(card: dict | None) -> float | None:
    split = (card or {}).get("split")
    value = split.get("cut_test") if isinstance(split, dict) else None
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None      # an unusable cut counts as missing, so the gate still fails closed and writes its report


def resolve_cut_test(candidate_card: dict | None, active_card: dict | None) -> float | None:
    """The candidate's cut wins, then the active model's; None when neither card has one.
    A value of 0 is a value, not 'missing' (no `or` chaining)."""
    cut = _cut_of(candidate_card)
    return cut if cut is not None else _cut_of(active_card)
