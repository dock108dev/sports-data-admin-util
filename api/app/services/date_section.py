"""Date section classification for game list grouping.

Computes "Today"/"Yesterday"/"Tomorrow"/"Earlier"/"Upcoming" in US Eastern
so clients don't need timezone-aware date classification logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def classify_date_section(
    game_time: datetime | None,
    *,
    now: datetime | None = None,
) -> str | None:
    """Classify a game's start time into a display section.

    Args:
        game_time: The game's start time (timezone-aware or naive UTC).
        now: Current time for testing; defaults to now in ET.

    Returns:
        One of "Today", "Yesterday", "Tomorrow", "Earlier", "Upcoming",
        or None if game_time is None.
    """
    if game_time is None:
        return None

    if now is None:
        now = datetime.now(_ET)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_ET)
    else:
        now = now.astimezone(_ET)

    if game_time.tzinfo is None:
        # Assume UTC for naive datetimes
        from zoneinfo import ZoneInfo as ZI
        game_time = game_time.replace(tzinfo=ZI("UTC"))

    game_et = game_time.astimezone(_ET)
    today = now.date()
    game_date = game_et.date()

    if game_date == today:
        return "Today"
    if game_date == today - timedelta(days=1):
        return "Yesterday"
    if game_date == today + timedelta(days=1):
        return "Tomorrow"
    if game_date < today:
        return "Earlier"
    return "Upcoming"
