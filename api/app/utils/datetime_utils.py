"""Datetime helpers for the API layer."""

from datetime import date, datetime, timezone


def now_utc() -> datetime:
    """Get the current time in UTC, timezone-aware."""
    return datetime.now(timezone.utc)


def date_to_utc_datetime(day: date) -> datetime:
    """Convert a date to a timezone-aware UTC datetime at midnight."""
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)


def parse_clock_to_seconds(clock: str | None) -> int | None:
    """
    Parse game clock string to seconds remaining.
    
    Accepts formats:
    - "MM:SS" (e.g., "11:45")
    - "MM:SS.x" (e.g., "5:30.0")
    
    Returns None if clock is invalid or None.
    """
    if not clock:
        return None
    try:
        parts = clock.replace(".", ":").split(":")
        if len(parts) >= 2:
            return int(parts[0]) * 60 + int(float(parts[1]))
        return int(float(parts[0]))
    except (ValueError, IndexError):
        return None

