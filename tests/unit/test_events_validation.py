# Tests: specs/rating-stream-ingestion/spec.md "Validation and quarantine".
from streaming import events
from streaming.schemas import RatingEvent

KNOWN_MOVIES = frozenset({296, 318, 858})
NOW = 1_700_000_000


def make_event(**overrides) -> RatingEvent:
    base = dict(event_id="e-1", user_id=1, movie_id=296, rating=4.5, timestamp=NOW - 1000, source="web")
    base.update(overrides)
    return RatingEvent(**base)


def test_valid_event_passes():
    result = events.validate_event(make_event(), KNOWN_MOVIES, NOW)
    assert result.valid is True
    assert result.reason is None


def test_invalid_rating_value_rejected():
    """spec scenario: 'Invalid rating value' (rating = 7.0)."""
    result = events.validate_event(make_event(rating=7.0), KNOWN_MOVIES, NOW)
    assert result.valid is False
    assert result.reason == events.REASON_BAD_RATING


def test_unknown_movie_rejected():
    """spec scenario: 'Unknown movie'."""
    result = events.validate_event(make_event(movie_id=999999), KNOWN_MOVIES, NOW)
    assert result.valid is False
    assert result.reason == events.REASON_UNKNOWN_MOVIE


def test_empty_event_id_rejected():
    result = events.validate_event(make_event(event_id="  "), KNOWN_MOVIES, NOW)
    assert result.valid is False
    assert result.reason == events.REASON_BAD_EVENT_ID


def test_non_positive_user_id_rejected():
    result = events.validate_event(make_event(user_id=0), KNOWN_MOVIES, NOW)
    assert result.valid is False
    assert result.reason == events.REASON_BAD_USER_ID


def test_non_positive_timestamp_rejected():
    result = events.validate_event(make_event(timestamp=0), KNOWN_MOVIES, NOW)
    assert result.valid is False
    assert result.reason == events.REASON_BAD_TIMESTAMP


def test_timestamp_too_far_in_future_rejected():
    two_days_ahead = NOW + 2 * 86400
    result = events.validate_event(make_event(timestamp=two_days_ahead), KNOWN_MOVIES, NOW, max_future_skew_days=1)
    assert result.valid is False
    assert result.reason == events.REASON_BAD_TIMESTAMP


def test_timestamp_within_future_skew_allowed():
    a_few_hours_ahead = NOW + 3600
    result = events.validate_event(make_event(timestamp=a_few_hours_ahead), KNOWN_MOVIES, NOW, max_future_skew_days=1)
    assert result.valid is True


def test_first_failing_rule_reported_when_multiple_rules_fail():
    """event_id empty AND rating invalid -> event_id check runs first (spec: 'first
    failing rule')."""
    bad = make_event(event_id="", rating=99.0)
    result = events.validate_event(bad, KNOWN_MOVIES, NOW)
    assert result.reason == events.REASON_BAD_EVENT_ID
