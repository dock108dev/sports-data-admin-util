"""
PBP event building for timeline generation.

Transforms raw play-by-play data into timeline events with phase
assignment and synthetic timestamps.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from ... import db_models
from .phase_utils import (
    NBA_QUARTER_GAME_SECONDS,
    NBA_QUARTER_REAL_SECONDS,
    NBA_REGULATION_REAL_SECONDS,
    nba_phase_for_quarter,
    nba_block_for_quarter,
    nba_quarter_start,
    parse_clock_to_seconds,
    progress_from_index,
)


def nba_game_end(
    game_start: datetime, plays: Sequence[db_models.SportsGamePlay]
) -> datetime:
    """Calculate actual game end time based on plays."""
    max_quarter = 4
    for play in plays:
        if play.quarter and play.quarter > max_quarter:
            max_quarter = play.quarter

    if max_quarter <= 4:
        return game_start + timedelta(seconds=NBA_REGULATION_REAL_SECONDS)

    # Has overtime
    ot_count = max_quarter - 4
    return game_start + timedelta(
        seconds=NBA_REGULATION_REAL_SECONDS + ot_count * 15 * 60
    )


def build_pbp_events(
    plays: Sequence[db_models.SportsGamePlay],
    game_start: datetime,
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build PBP events with phase assignment and synthetic timestamps.

    Each event includes:
    - phase: Narrative phase (q1, q2, etc.)
    - intra_phase_order: Sort key within phase (clock-based)
    - synthetic_timestamp: Computed wall-clock time for display
    """
    events: list[tuple[datetime, dict[str, Any]]] = []
    total_plays = len(plays)

    for play in plays:
        quarter = play.quarter or 1
        phase = nba_phase_for_quarter(quarter)
        block = nba_block_for_quarter(quarter)

        # Parse game clock
        clock_seconds = parse_clock_to_seconds(play.game_clock)
        if clock_seconds is None:
            # Fallback: use play index for ordering
            intra_phase_order = play.play_index
            progress = progress_from_index(play.play_index, total_plays)
        else:
            # Invert clock: 12:00 (720s) -> 0, 0:00 -> 720
            # So earlier in quarter has lower order (comes first)
            intra_phase_order = NBA_QUARTER_GAME_SECONDS - clock_seconds
            progress = (quarter - 1 + (1 - clock_seconds / 720)) / 4

        # Compute synthetic timestamp
        quarter_start = nba_quarter_start(game_start, quarter)
        elapsed_in_quarter = NBA_QUARTER_GAME_SECONDS - (clock_seconds or 0)
        # Scale game time to real time (roughly 1.5x)
        real_elapsed = elapsed_in_quarter * (NBA_QUARTER_REAL_SECONDS / NBA_QUARTER_GAME_SECONDS)
        synthetic_ts = quarter_start + timedelta(seconds=real_elapsed)

        event_payload = {
            "event_type": "pbp",
            "phase": phase,
            "intra_phase_order": intra_phase_order,
            "play_index": play.play_index,
            "quarter": quarter,
            "block": block,
            "game_clock": play.game_clock,
            "description": play.description,
            "play_type": play.play_type,
            "home_score": play.home_score,
            "away_score": play.away_score,
            "synthetic_timestamp": synthetic_ts.isoformat(),
            "game_progress": round(progress, 3),
        }
        events.append((synthetic_ts, event_payload))

    return events
