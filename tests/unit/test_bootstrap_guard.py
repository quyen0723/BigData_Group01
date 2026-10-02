# Tests: specs/serving-store/spec.md "Bootstrap does not replace an active pointer".
# Design: address-person1-review-findings D-4.
from loaders.bootstrap_registry import active_pointer_conflict


def pointer(version):
    return {"_id": "active", "modelVersion": version, "previousVersion": None, "artifacts": {}}


def test_another_version_is_active_is_refused_with_a_pointer_to_the_right_tools():
    reason = active_pointer_conflict(pointer("v1.1.0"), "v1.0.0")
    assert reason is not None
    assert "v1.1.0" in reason and "v1.0.0" in reason
    assert "promotion_gate" in reason and "manage_versions" in reason


def test_first_bootstrap_without_a_pointer_is_allowed():
    assert active_pointer_conflict(None, "v1.0.0") is None
    assert active_pointer_conflict({}, "v1.0.0") is None


def test_same_version_again_is_allowed():
    assert active_pointer_conflict(pointer("v1.0.0"), "v1.0.0") is None


def test_pointer_without_a_version_is_not_a_conflict():
    assert active_pointer_conflict({"_id": "active"}, "v1.0.0") is None
