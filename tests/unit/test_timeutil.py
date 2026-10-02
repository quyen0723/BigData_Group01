# Design: address-person1-review-findings D-7 "Đổi datetime sang epoch".
# pymongo returns BSON dates as naive datetimes; they are UTC, so the epoch must not depend on the host's time zone.
import calendar
import datetime as dt

from serving.timeutil import as_utc, to_epoch

UTC = dt.timezone.utc
NAIVE = dt.datetime(2026, 10, 2, 9, 30, 15)
EXPECTED = calendar.timegm(NAIVE.timetuple())          # the UTC reading, computed without any local-time rule


def test_naive_datetime_is_read_as_utc_regardless_of_the_host_zone():
    assert to_epoch(NAIVE) == EXPECTED


def test_aware_utc_datetime_gives_the_same_epoch():
    assert to_epoch(NAIVE.replace(tzinfo=UTC)) == EXPECTED


def test_aware_datetime_in_another_zone_is_converted():
    plus_seven = dt.timezone(dt.timedelta(hours=7))
    assert to_epoch(dt.datetime(2026, 10, 2, 16, 30, 15, tzinfo=plus_seven)) == EXPECTED


def test_to_epoch_returns_whole_seconds():
    assert to_epoch(NAIVE.replace(microsecond=999_999)) == EXPECTED
    assert isinstance(to_epoch(NAIVE), int)


def test_as_utc_labels_naive_and_converts_aware():
    assert as_utc(NAIVE) == NAIVE.replace(tzinfo=UTC)
    plus_seven = dt.timezone(dt.timedelta(hours=7))
    converted = as_utc(dt.datetime(2026, 10, 2, 16, 30, 15, tzinfo=plus_seven))
    assert converted == NAIVE.replace(tzinfo=UTC) and converted.utcoffset() == dt.timedelta(0)
