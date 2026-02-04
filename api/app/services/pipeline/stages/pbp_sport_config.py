"""Sport-specific timing constants and phase mapping functions.

This module contains pure functions and constants for PBP normalization.
No database or external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# =============================================================================
# NBA Constants
# =============================================================================
NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_OT_GAME_SECONDS = 5 * 60
NBA_OT_REAL_SECONDS = 10 * 60

# =============================================================================
# NCAAB Constants (20-minute halves)
# =============================================================================
NCAAB_REGULATION_REAL_SECONDS = 75 * 60
NCAAB_HALFTIME_REAL_SECONDS = 20 * 60
NCAAB_HALF_REAL_SECONDS = NCAAB_REGULATION_REAL_SECONDS // 2
NCAAB_HALF_GAME_SECONDS = 20 * 60
NCAAB_OT_GAME_SECONDS = 5 * 60
NCAAB_OT_REAL_SECONDS = 10 * 60

# =============================================================================
# NHL Constants (20-minute periods)
# =============================================================================
NHL_REGULATION_REAL_SECONDS = 90 * 60
NHL_INTERMISSION_REAL_SECONDS = 18 * 60
NHL_PERIOD_REAL_SECONDS = NHL_REGULATION_REAL_SECONDS // 3
NHL_PERIOD_GAME_SECONDS = 20 * 60
NHL_OT_GAME_SECONDS = 5 * 60
NHL_OT_REAL_SECONDS = 10 * 60
NHL_PLAYOFF_OT_GAME_SECONDS = 20 * 60

# =============================================================================
# Social post time windows
# =============================================================================
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60


# =============================================================================
# Phase Mapping Functions
# =============================================================================


def nba_phase_for_quarter(quarter: int | None) -> str:
    """Map NBA quarter number to narrative phase."""
    if quarter is None:
        return "unknown"
    if quarter == 1:
        return "q1"
    if quarter == 2:
        return "q2"
    if quarter == 3:
        return "q3"
    if quarter == 4:
        return "q4"
    return f"ot{quarter - 4}" if quarter > 4 else "unknown"


def nba_block_for_quarter(quarter: int | None) -> str:
    """Map NBA quarter to game block (first_half, second_half, overtime)."""
    if quarter is None:
        return "unknown"
    if quarter <= 2:
        return "first_half"
    if quarter <= 4:
        return "second_half"
    return "overtime"


def ncaab_phase_for_period(period: int | None) -> str:
    """Map NCAAB period to narrative phase (h1, h2, ot1, etc.)."""
    if period is None:
        return "unknown"
    if period == 1:
        return "h1"
    if period == 2:
        return "h2"
    return f"ot{period - 2}" if period > 2 else "unknown"


def ncaab_block_for_period(period: int | None) -> str:
    """Map NCAAB period to game block."""
    if period is None:
        return "unknown"
    if period == 1:
        return "first_half"
    if period == 2:
        return "second_half"
    return "overtime"


def nhl_phase_for_period(period: int | None) -> str:
    """Map NHL period to narrative phase (p1, p2, p3, ot, shootout)."""
    if period is None:
        return "unknown"
    if period == 1:
        return "p1"
    if period == 2:
        return "p2"
    if period == 3:
        return "p3"
    if period == 4:
        return "ot"
    if period == 5:
        return "shootout"
    return f"ot{period - 3}"


def nhl_block_for_period(period: int | None) -> str:
    """Map NHL period to game block."""
    if period is None:
        return "unknown"
    if period <= 3:
        return "regulation"
    if period == 4:
        return "overtime"
    return "shootout" if period == 5 else "overtime"


# =============================================================================
# Period Start Time Functions
# =============================================================================


def nba_quarter_start(game_start: datetime, quarter: int) -> datetime:
    """Calculate when an NBA quarter starts in real time."""
    if quarter == 1:
        return game_start
    if quarter == 2:
        return game_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    if quarter == 3:
        return game_start + timedelta(
            seconds=2 * NBA_QUARTER_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS
        )
    if quarter == 4:
        return game_start + timedelta(
            seconds=3 * NBA_QUARTER_REAL_SECONDS + NBA_HALFTIME_REAL_SECONDS
        )
    ot_num = quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_num * 15 * 60
    )


def ncaab_period_start(game_start: datetime, period: int) -> datetime:
    """Calculate when a NCAAB period starts in real time."""
    if period == 1:
        return game_start
    if period == 2:
        return game_start + timedelta(
            seconds=NCAAB_HALF_REAL_SECONDS + NCAAB_HALFTIME_REAL_SECONDS
        )
    ot_num = period - 2
    return game_start + timedelta(
        seconds=NCAAB_REGULATION_REAL_SECONDS + ot_num * 10 * 60
    )


def nhl_period_start(game_start: datetime, period: int) -> datetime:
    """Calculate when an NHL period starts in real time."""
    if period == 1:
        return game_start
    if period == 2:
        return game_start + timedelta(
            seconds=NHL_PERIOD_REAL_SECONDS + NHL_INTERMISSION_REAL_SECONDS
        )
    if period == 3:
        return game_start + timedelta(
            seconds=2 * NHL_PERIOD_REAL_SECONDS + 2 * NHL_INTERMISSION_REAL_SECONDS
        )
    ot_num = period - 3
    return game_start + timedelta(
        seconds=NHL_REGULATION_REAL_SECONDS + ot_num * 10 * 60
    )
