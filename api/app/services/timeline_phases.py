"""Phase utilities for timeline generation.

Handles quarter-to-phase mapping, timing calculations, and phase boundaries.
Provides league-aware, time-based phase classification for tweets.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from ..db.sports import SportsGamePlay
from .timeline_types import (
    NBA_HALFTIME_REAL_SECONDS,
    NBA_OT_BUFFER_MINUTES,
    NBA_OVERTIME_REAL_SECONDS,
    NBA_QUARTER_REAL_SECONDS,
    NBA_REGULATION_REAL_MINUTES,
    NBA_REGULATION_REAL_SECONDS,
    NCAAB_HALF_REAL_SECONDS,
    NCAAB_HALFTIME_REAL_SECONDS,
    NCAAB_OT_BUFFER_MINUTES,
    NCAAB_REGULATION_REAL_MINUTES,
    NCAAB_REGULATION_REAL_SECONDS,
    NHL_INTERMISSION_REAL_SECONDS,
    NHL_OT_BUFFER_MINUTES,
    NHL_PERIOD_REAL_SECONDS,
    NHL_REGULATION_REAL_MINUTES,
    NHL_REGULATION_REAL_SECONDS,
    SOCIAL_POSTGAME_WINDOW_SECONDS,
    SOCIAL_PREGAME_WINDOW_SECONDS,
)


def nba_phase_for_quarter(quarter: int | None) -> str:
    """Map quarter number to narrative phase."""
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
    if quarter == 5:
        return "ot1"
    if quarter == 6:
        return "ot2"
    if quarter == 7:
        return "ot3"
    if quarter == 8:
        return "ot4"
    return f"ot{quarter - 4}" if quarter > 4 else "unknown"


def nba_block_for_quarter(quarter: int | None) -> str:
    """Map quarter to game block (first_half, second_half, overtime)."""
    if quarter is None:
        return "unknown"
    if quarter <= 2:
        return "first_half"
    if quarter <= 4:
        return "second_half"
    return "overtime"


# =============================================================================
# NCAAB Phase Mapping Functions
# =============================================================================


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


# =============================================================================
# NHL Phase Mapping Functions
# =============================================================================


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
    """Calculate when a quarter starts in real time."""
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
    # Overtime quarters: OT1 (quarter 5) starts at regulation end
    ot_num = quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + (ot_num - 1) * NBA_OVERTIME_REAL_SECONDS
    )


def nba_regulation_end(game_start: datetime) -> datetime:
    """Calculate when regulation ends."""
    return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)


def nba_game_end(game_start: datetime, plays: Sequence[SportsGamePlay]) -> datetime:
    """Calculate actual game end time based on plays."""
    max_quarter = 4
    for play in plays:
        if play.quarter and play.quarter > max_quarter:
            max_quarter = play.quarter

    if max_quarter <= 4:
        return nba_regulation_end(game_start)

    # Has overtime - game ends at the end of the last OT period
    ot_count = max_quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_count * NBA_OVERTIME_REAL_SECONDS
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


def compute_phase_boundaries(
    game_start: datetime, has_overtime: bool = False
) -> dict[str, tuple[datetime, datetime]]:
    """
    Compute start/end times for each narrative phase.

    These boundaries are used to assign social posts to phases.
    The pregame and postgame phases extend beyond the game itself.
    """
    boundaries: dict[str, tuple[datetime, datetime]] = {}

    # Pregame: 2 hours before to game start
    pregame_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
    boundaries["pregame"] = (pregame_start, game_start)

    # Q1
    q1_start = game_start
    q1_end = game_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q1"] = (q1_start, q1_end)

    # Q2
    q2_start = q1_end
    q2_end = q2_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q2"] = (q2_start, q2_end)

    # Halftime
    halftime_start = q2_end
    halftime_end = halftime_start + timedelta(seconds=NBA_HALFTIME_REAL_SECONDS)
    boundaries["halftime"] = (halftime_start, halftime_end)

    # Q3
    q3_start = halftime_end
    q3_end = q3_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q3"] = (q3_start, q3_end)

    # Q4
    q4_start = q3_end
    q4_end = q4_start + timedelta(seconds=NBA_QUARTER_REAL_SECONDS)
    boundaries["q4"] = (q4_start, q4_end)

    # Overtime periods (if applicable)
    if has_overtime:
        ot_start = q4_end
        for i in range(1, 5):  # Up to 4 OT periods
            ot_end = ot_start + timedelta(seconds=NBA_OVERTIME_REAL_SECONDS)
            boundaries[f"ot{i}"] = (ot_start, ot_end)
            ot_start = ot_end
        boundaries["postgame"] = (
            ot_start,
            ot_start + timedelta(seconds=SOCIAL_POSTGAME_WINDOW_SECONDS),
        )
    else:
        boundaries["postgame"] = (
            q4_end,
            q4_end + timedelta(seconds=SOCIAL_POSTGAME_WINDOW_SECONDS),
        )

    return boundaries


# =============================================================================
# LEAGUE-AWARE TIMING
# =============================================================================


def get_league_timing(league_code: str) -> tuple[int, int]:
    """Get regulation duration and OT buffer for a league.

    Args:
        league_code: League code (NBA, NCAAB, NHL)

    Returns:
        Tuple of (regulation_minutes, ot_buffer_minutes)
    """
    league_upper = (league_code or "").upper()

    if league_upper == "NCAAB":
        return NCAAB_REGULATION_REAL_MINUTES, NCAAB_OT_BUFFER_MINUTES
    elif league_upper == "NHL":
        return NHL_REGULATION_REAL_MINUTES, NHL_OT_BUFFER_MINUTES
    else:
        # Default to NBA timing
        return NBA_REGULATION_REAL_MINUTES, NBA_OT_BUFFER_MINUTES


def estimate_game_end(
    game_start: datetime,
    league_code: str,
    has_overtime: bool = False,
) -> datetime:
    """Estimate game end time based on league and overtime status.

    This is a HEURISTIC estimate - imprecision is expected and acceptable.
    No PBP data is used.

    Args:
        game_start: Authoritative game start time
        league_code: League code (NBA, NCAAB, NHL)
        has_overtime: Whether OT is detected (approximate)

    Returns:
        Estimated game end datetime
    """
    regulation_mins, ot_buffer_mins = get_league_timing(league_code)

    estimated_end = game_start + timedelta(minutes=regulation_mins)

    if has_overtime:
        estimated_end += timedelta(minutes=ot_buffer_mins)

    return estimated_end


def compute_league_phase_boundaries(
    game_start: datetime,
    league_code: str,
    has_overtime: bool = False,
) -> dict[str, tuple[datetime, datetime]]:
    """Compute phase boundaries for any league (time-based only).

    League-aware phase boundaries using heuristic timing.

    Args:
        game_start: Authoritative game start time
        league_code: League code (NBA, NCAAB, NHL)
        has_overtime: Whether OT is detected

    Returns:
        Dict mapping phase names to (start, end) datetime tuples
    """
    league_upper = (league_code or "").upper()
    boundaries: dict[str, tuple[datetime, datetime]] = {}

    regulation_mins, ot_buffer_mins = get_league_timing(league_code)

    # Pregame: 2 hours before to game start
    pregame_start = game_start - timedelta(seconds=SOCIAL_PREGAME_WINDOW_SECONDS)
    boundaries["pregame"] = (pregame_start, game_start)

    if league_upper == "NCAAB":
        # Two halves with halftime
        half_duration = regulation_mins / 2
        halftime_duration = 20  # ~20 minute halftime in college

        first_half_end = game_start + timedelta(minutes=half_duration)
        boundaries["first_half"] = (game_start, first_half_end)

        halftime_end = first_half_end + timedelta(minutes=halftime_duration)
        boundaries["halftime"] = (first_half_end, halftime_end)

        second_half_end = halftime_end + timedelta(minutes=half_duration)
        boundaries["second_half"] = (halftime_end, second_half_end)

        game_end = second_half_end
        if has_overtime:
            ot_end = game_end + timedelta(minutes=ot_buffer_mins)
            boundaries["ot"] = (game_end, ot_end)
            game_end = ot_end

    elif league_upper == "NHL":
        # Three periods
        period_duration = regulation_mins / 3
        intermission = 18  # ~18 minute intermissions

        p1_end = game_start + timedelta(minutes=period_duration)
        boundaries["p1"] = (game_start, p1_end)

        p2_start = p1_end + timedelta(minutes=intermission)
        p2_end = p2_start + timedelta(minutes=period_duration)
        boundaries["p2"] = (p1_end, p2_end)

        p3_start = p2_end + timedelta(minutes=intermission)
        p3_end = p3_start + timedelta(minutes=period_duration)
        boundaries["p3"] = (p2_end, p3_end)

        game_end = p3_end
        if has_overtime:
            ot_end = game_end + timedelta(minutes=ot_buffer_mins)
            boundaries["ot"] = (game_end, ot_end)
            game_end = ot_end

    else:
        # Default to NBA: four quarters with halftime
        quarter_duration = regulation_mins / 4
        halftime_duration = 15  # ~15 minute halftime

        q1_end = game_start + timedelta(minutes=quarter_duration)
        boundaries["q1"] = (game_start, q1_end)

        q2_end = q1_end + timedelta(minutes=quarter_duration)
        boundaries["q2"] = (q1_end, q2_end)

        halftime_end = q2_end + timedelta(minutes=halftime_duration)
        boundaries["halftime"] = (q2_end, halftime_end)

        q3_end = halftime_end + timedelta(minutes=quarter_duration)
        boundaries["q3"] = (halftime_end, q3_end)

        q4_end = q3_end + timedelta(minutes=quarter_duration)
        boundaries["q4"] = (q3_end, q4_end)

        game_end = q4_end
        if has_overtime:
            ot_end = game_end + timedelta(minutes=ot_buffer_mins)
            boundaries["ot1"] = (game_end, ot_end)
            game_end = ot_end

    # Postgame
    postgame_end = game_end + timedelta(seconds=SOCIAL_POSTGAME_WINDOW_SECONDS)
    boundaries["postgame"] = (game_end, postgame_end)

    return boundaries
