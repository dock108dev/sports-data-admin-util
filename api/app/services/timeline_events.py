"""Timeline event building and merging.

Handles PBP event construction and timeline assembly.

SOCIAL DECOUPLING CONTRACT (Phase 2)
====================================
The merge_timeline_events function treats social events as:
- TIME-BASED ONLY: Ordered by phase, then intra_phase_order
- OPTIONAL: Empty social_events list is valid and expected
- NON-COUPLED: No linkage between social events and specific plays

PBP events and social events are merged using PHASE-FIRST ordering.
Social events never modify, explain, or depend on PBP event content.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Sequence

from ..db.sports import SportsGamePlay
from ..utils.datetime_utils import parse_clock_to_seconds
from .timeline_types import (
    NBA_QUARTER_GAME_SECONDS,
    NBA_QUARTER_REAL_SECONDS,
    phase_sort_order,
)
from .timeline_phases import (
    nba_block_for_quarter,
    nba_phase_for_quarter,
    nba_quarter_start,
)


def progress_from_index(index: int, total: int) -> float:
    """
    Calculate progress through the game based on play index.

    Returns 0.0 at start, 1.0 at end.
    """
    if total <= 1:
        return 0.0
    return index / (total - 1)


def build_pbp_events(
    plays: Sequence[SportsGamePlay],
    game_start: datetime,
) -> list[tuple[datetime, dict[str, Any]]]:
    """
    Build PBP events with phase assignment and synthetic timestamps.

    Each event includes:
    - phase: Narrative phase (q1, q2, etc.)
    - intra_phase_order: Sort key within phase (clock-based)
    - synthetic_timestamp: Computed wall-clock time for display
    - team_abbreviation: Team abbreviation (if team_id is present)
    - player_name: Player name (if available)
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
            # Progress through regulation (0.0 to 1.0)
            # For overtime quarters (>4), clamp to 1.0
            raw_progress = (
                quarter - 1 + (1 - clock_seconds / NBA_QUARTER_GAME_SECONDS)
            ) / 4
            progress = min(1.0, max(0.0, raw_progress))

        # Compute synthetic timestamp
        quarter_start = nba_quarter_start(game_start, quarter)
        elapsed_in_quarter = NBA_QUARTER_GAME_SECONDS - (clock_seconds or 0)
        # Scale game time to real time (roughly 1.5x)
        real_elapsed = elapsed_in_quarter * (
            NBA_QUARTER_REAL_SECONDS / NBA_QUARTER_GAME_SECONDS
        )
        synthetic_ts = quarter_start + timedelta(seconds=real_elapsed)

        # Extract team abbreviation from relationship
        team_abbrev = None
        if hasattr(play, "team") and play.team:
            team_abbrev = play.team.abbreviation

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
            "team_abbreviation": team_abbrev,
            "player_name": play.player_name,
            "home_score": play.home_score,
            "away_score": play.away_score,
            "synthetic_timestamp": synthetic_ts.isoformat(),
            "game_progress": round(progress, 3),
        }
        events.append((synthetic_ts, event_payload))

    return events


def merge_timeline_events(
    pbp_events: Sequence[tuple[datetime, dict[str, Any]]],
    social_events: Sequence[tuple[datetime, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Merge PBP and social events using PHASE-FIRST ordering.

    Ordering is determined by:
    1. phase_order (from PHASE_ORDER constant) - PRIMARY
    2. intra_phase_order (clock progress for PBP, seconds for social) - SECONDARY
    3. event_type tiebreaker (pbp before tweet at same position) - TERTIARY

    synthetic_timestamp is NOT used for ordering. It is retained for
    display/debugging purposes only.

    See docs/TIMELINE_ASSEMBLY.md for the canonical assembly recipe.
    """
    merged = list(pbp_events) + list(social_events)

    def sort_key(item: tuple[datetime, dict[str, Any]]) -> tuple[int, float, int, int]:
        _, payload = item

        # Primary: phase order
        phase = payload.get("phase", "unknown")
        phase_order_val = phase_sort_order(phase)

        # Secondary: intra-phase order
        intra_order = payload.get("intra_phase_order", 0)

        # Tertiary: event type (pbp=0, tweet=1) so PBP comes first at ties
        event_type_order = 0 if payload.get("event_type") == "pbp" else 1

        # Quaternary: play_index for PBP stability
        play_index = payload.get("play_index", 0)

        return (phase_order_val, intra_order, event_type_order, play_index)

    sorted_events = sorted(merged, key=sort_key)

    # Extract payloads, keeping intra_phase_order for compact mode
    result = []
    for _, payload in sorted_events:
        result.append(payload)

    return result
