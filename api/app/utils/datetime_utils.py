"""Datetime helpers for the API layer.

DATE CONVENTION:
All date parameters in the API use Eastern Time (America/New_York).
This represents "game day" as fans understand it - a 10pm ET game
on Jan 22 is a "Jan 22 game", regardless of UTC date.

All datetime fields in responses are UTC (ISO 8601).
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Eastern timezone for game date interpretation
EASTERN = ZoneInfo("America/New_York")


def now_utc() -> datetime:
    """Get the current time in UTC, timezone-aware."""
    return datetime.now(timezone.utc)


def today_utc() -> date:
    """Return the current date in UTC timezone."""
    return now_utc().date()


def today_eastern() -> date:
    """Return the current date in Eastern timezone."""
    return datetime.now(EASTERN).date()


def date_to_utc_datetime(day: date) -> datetime:
    """Convert a date to a timezone-aware UTC datetime at midnight."""
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)


def eastern_date_to_utc_range(game_date: date) -> tuple[datetime, datetime]:
    """Convert an Eastern Time date to UTC datetime range.

    A game on "Jan 22 Eastern" spans from midnight Jan 22 ET
    to just before midnight Jan 23 ET.

    Args:
        game_date: A date in Eastern Time (America/New_York)

    Returns:
        Tuple of (start_utc, end_utc) where end is exclusive.
        The range covers the full 24-hour period in Eastern Time.

    Example:
        Jan 22, 2026 (EST) -> (2026-01-22 05:00:00 UTC, 2026-01-23 05:00:00 UTC)
        Jul 15, 2026 (EDT) -> (2026-07-15 04:00:00 UTC, 2026-07-16 04:00:00 UTC)
    """
    eastern_start = datetime.combine(game_date, time.min, tzinfo=EASTERN)
    eastern_end = datetime.combine(
        game_date + timedelta(days=1), time.min, tzinfo=EASTERN
    )
    return eastern_start.astimezone(timezone.utc), eastern_end.astimezone(timezone.utc)


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
