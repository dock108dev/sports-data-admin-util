"""Phase utilities for timeline generation.

Handles quarter-to-phase mapping, timing calculations, and phase boundaries.

PHASE 3: TIME-BASED TWEET CLASSIFICATION
========================================
This module provides league-aware, time-based phase classification for tweets.
NO PBP DATA is used for classification - only time relative to game_start.

Key principles:
- game_start is authoritative
- estimated_game_end is heuristic (imprecision is expected)
- OT detection may be approximate (false positives acceptable)
- Classification is deterministic and repeatable

🚫 Do not use PBP data for phase classification
🚫 Do not infer game state from tweet content
🚫 Do not attempt clock alignment
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from ..db.sports import SportsGamePlay
from .timeline_types import (
    NBA_HALFTIME_REAL_SECONDS,
    NBA_OVERTIME_REAL_SECONDS,
    NBA_QUARTER_REAL_SECONDS,
    NBA_REGULATION_REAL_SECONDS,
    SOCIAL_POSTGAME_WINDOW_SECONDS,
    SOCIAL_PREGAME_WINDOW_SECONDS,
    # Phase 3 constants
    NCAAB_REGULATION_REAL_MINUTES,
    NCAAB_OT_BUFFER_MINUTES,
    NBA_REGULATION_REAL_MINUTES,
    NBA_OT_BUFFER_MINUTES,
    NHL_REGULATION_REAL_MINUTES,
    NHL_OT_BUFFER_MINUTES,
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


def nba_game_end(
    game_start: datetime, plays: Sequence[SportsGamePlay]
) -> datetime:
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
# PHASE 3: TIME-BASED TWEET CLASSIFICATION (Tasks 3.1 & 3.2)
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


def classify_tweet_phase(
    tweet_time: datetime,
    game_start: datetime,
    league_code: str,
    has_overtime: bool = False,
) -> str:
    """Classify a tweet into pregame, in-game, or postgame.

    Task 3.1: Time-based phase classification.

    Classification rules:
    - Pregame: tweet_time < game_start
    - In-game: game_start <= tweet_time <= estimated_game_end + OT_buffer
    - Postgame: tweet_time > estimated_game_end + OT_buffer AND
                tweet_time <= estimated_game_end + 4 hours

    Tweets beyond postgame window return "postgame" but may be deprioritized.

    Args:
        tweet_time: When the tweet was posted
        game_start: Authoritative game start time
        league_code: League code for timing heuristics
        has_overtime: Whether OT is detected

    Returns:
        Phase string: "pregame", "in_game", or "postgame"
    """
    if tweet_time < game_start:
        return "pregame"

    estimated_end = estimate_game_end(game_start, league_code, has_overtime)

    if tweet_time <= estimated_end:
        return "in_game"

    # Everything after game end is postgame
    return "postgame"


def map_tweet_to_segment(
    tweet_time: datetime,
    game_start: datetime,
    league_code: str,
    has_overtime: bool = False,
) -> str:
    """Map an in-game tweet to a specific game segment.

    Task 3.2: Segment mapping using elapsed ratio.

    Computes elapsed_ratio = (tweet_time - game_start) / estimated_game_duration
    Maps ratio to league-appropriate segment (quarter/half/period).

    Segment boundaries are approximate - minor misplacements are acceptable.

    Args:
        tweet_time: When the tweet was posted
        game_start: Authoritative game start time
        league_code: League code for segment mapping
        has_overtime: Whether OT is detected

    Returns:
        Segment string (e.g., "q1", "first_half", "p2")
    """
    league_upper = (league_code or "").upper()

    # Get estimated game duration
    regulation_mins, ot_buffer_mins = get_league_timing(league_code)
    estimated_duration_mins = regulation_mins
    if has_overtime:
        estimated_duration_mins += ot_buffer_mins

    # Calculate elapsed ratio (clamped to [0, 1])
    elapsed = (tweet_time - game_start).total_seconds()
    duration_seconds = estimated_duration_mins * 60

    if duration_seconds <= 0:
        elapsed_ratio = 0.0
    else:
        elapsed_ratio = max(0.0, min(1.0, elapsed / duration_seconds))

    # Map ratio to segment based on league
    if league_upper == "NCAAB":
        return _map_ncaab_segment(elapsed_ratio)
    elif league_upper == "NHL":
        return _map_nhl_segment(elapsed_ratio, has_overtime)
    else:
        # Default to NBA
        return _map_nba_segment(elapsed_ratio)


def _map_ncaab_segment(elapsed_ratio: float) -> str:
    """Map elapsed ratio to NCAAB segment (halves).

    NCAAB has two 20-minute halves with halftime.
    Approximate split: first_half (0-0.45), halftime (0.45-0.55), second_half (0.55-1.0)
    """
    if elapsed_ratio < 0.45:
        return "first_half"
    elif elapsed_ratio < 0.55:
        return "halftime"
    else:
        return "second_half"


def _map_nba_segment(elapsed_ratio: float) -> str:
    """Map elapsed ratio to NBA segment (quarters).

    NBA has four 12-minute quarters with halftime after Q2.
    Approximate splits with halftime buffer.
    """
    if elapsed_ratio < 0.20:
        return "q1"
    elif elapsed_ratio < 0.40:
        return "q2"
    elif elapsed_ratio < 0.50:
        return "halftime"
    elif elapsed_ratio < 0.70:
        return "q3"
    else:
        return "q4"


def _map_nhl_segment(elapsed_ratio: float, has_overtime: bool) -> str:
    """Map elapsed ratio to NHL segment (periods).

    NHL has three 20-minute periods.
    Approximate split: p1 (0-0.33), p2 (0.33-0.66), p3 (0.66-1.0)
    OT/shootout handled separately.
    """
    if has_overtime and elapsed_ratio > 0.95:
        return "ot"

    if elapsed_ratio < 0.33:
        return "p1"
    elif elapsed_ratio < 0.66:
        return "p2"
    else:
        return "p3"


def assign_tweet_phase_and_segment(
    tweet_time: datetime,
    game_start: datetime,
    league_code: str,
    has_overtime: bool = False,
) -> tuple[str, str | None]:
    """Classify tweet and assign segment in one call.

    Combines Task 3.1 (phase classification) and Task 3.2 (segment mapping).

    Args:
        tweet_time: When the tweet was posted
        game_start: Authoritative game start time
        league_code: League code
        has_overtime: Whether OT is detected

    Returns:
        Tuple of (phase, segment) where:
        - phase: "pregame", "in_game", or "postgame"
        - segment: Specific segment for in-game tweets, None for others
    """
    phase = classify_tweet_phase(tweet_time, game_start, league_code, has_overtime)

    if phase == "in_game":
        segment = map_tweet_to_segment(
            tweet_time, game_start, league_code, has_overtime
        )
        return phase, segment

    return phase, None


def compute_league_phase_boundaries(
    game_start: datetime,
    league_code: str,
    has_overtime: bool = False,
) -> dict[str, tuple[datetime, datetime]]:
    """Compute phase boundaries for any league (time-based only).

    Phase 3: League-aware phase boundaries using heuristic timing.
    No PBP data is used.

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
