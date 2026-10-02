# timeutil.py — datetime helpers shared by serving and orchestration (pure).
# pymongo returns BSON dates as naive datetimes (tz_aware=False); every naive value read
# from Mongo in this project is UTC, so it is labelled as such before any conversion.
# A bare `.timestamp()` on a naive datetime would read it as the host's local time.
from __future__ import annotations

import datetime as dt


def as_utc(value: dt.datetime) -> dt.datetime:
    """Naive datetimes are taken as UTC; aware ones are converted to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc)


def to_epoch(value: dt.datetime) -> int:
    """Whole epoch seconds of `value`, naive values taken as UTC."""
    return int(as_utc(value).timestamp())
