"""Datetime helpers."""

from datetime import date, datetime, timezone


def now_utc() -> datetime:
    """Get the current time in UTC, timezone-aware."""
    return datetime.now(timezone.utc)


def date_to_utc_datetime(day: date) -> datetime:
    """Convert a date to a timezone-aware UTC datetime at midnight."""
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)

