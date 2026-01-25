"""Phase utilities for timeline generation.

Handles NBA quarter-to-phase mapping, timing calculations, and phase boundaries.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from .. import db_models
from .timeline_types import (
    NBA_HALFTIME_REAL_SECONDS,
    NBA_OVERTIME_REAL_SECONDS,
    NBA_QUARTER_REAL_SECONDS,
    NBA_REGULATION_REAL_SECONDS,
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
    game_start: datetime, plays: Sequence[db_models.SportsGamePlay]
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
