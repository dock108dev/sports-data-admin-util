"""
Phase and time utilities for timeline generation.

Provides phase boundary calculations, synthetic timestamp logic,
and progress calculations for NBA games.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# =============================================================================
# CONSTANTS
# =============================================================================

NBA_REGULATION_REAL_SECONDS = 75 * 60
NBA_HALFTIME_REAL_SECONDS = 15 * 60
NBA_QUARTER_REAL_SECONDS = NBA_REGULATION_REAL_SECONDS // 4
NBA_QUARTER_GAME_SECONDS = 12 * 60
NBA_PREGAME_REAL_SECONDS = 10 * 60
NBA_OVERTIME_PADDING_SECONDS = 30 * 60

# Social post time windows
SOCIAL_PREGAME_WINDOW_SECONDS = 2 * 60 * 60   # 2 hours before game start
SOCIAL_POSTGAME_WINDOW_SECONDS = 2 * 60 * 60  # 2 hours after game end

# Canonical phase ordering - source of truth for timeline order
PHASE_ORDER: dict[str, int] = {
    "pregame": 0,
    "q1": 1,
    "q2": 2,
    "halftime": 3,
    "q3": 4,
    "q4": 5,
    "ot1": 6,
    "ot2": 7,
    "ot3": 8,
    "ot4": 9,
    "postgame": 99,
}


# =============================================================================
# PHASE UTILITIES
# =============================================================================


def phase_sort_order(phase: str | None) -> int:
    """Get sort order for a phase. Unknown phases sort after postgame."""
    if phase is None:
        return 100
    return PHASE_ORDER.get(phase, 100)


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
    # Overtime quarters
    ot_num = quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_num * 15 * 60
    )


def nba_regulation_end(game_start: datetime) -> datetime:
    """Calculate when regulation ends."""
    return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)


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
            ot_end = ot_start + timedelta(seconds=15 * 60)
            boundaries[f"ot{i}"] = (ot_start, ot_end)
            ot_start = ot_end
        boundaries["postgame"] = (ot_start, ot_start + timedelta(hours=2))
    else:
        boundaries["postgame"] = (q4_end, q4_end + timedelta(hours=2))

    return boundaries


# =============================================================================
# CLOCK PARSING
# =============================================================================


def parse_clock_to_seconds(clock: str | None) -> int | None:
    """
    Parse game clock string (e.g. "11:45", "5:30.0") to seconds remaining.

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


def progress_from_index(index: int, total: int) -> float:
    """
    Calculate progress through the game based on play index.

    Returns 0.0 at start, 1.0 at end.
    """
    if total <= 1:
        return 0.0
    return index / (total - 1)
