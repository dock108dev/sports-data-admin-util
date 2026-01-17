"""
Game Analysis: Timeline partitioning into narrative moments.

This module provides the entry point for analyzing a game timeline.
All narrative logic lives in moments.py.

The output is a simple structure:
- moments: list of all moments (full coverage)
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .moments import partition_game

logger = logging.getLogger(__name__)


# Sport-specific Lead Ladder thresholds
# These define the point margins that represent meaningful lead tiers
SPORT_THRESHOLDS: dict[str, list[int]] = {
    "NBA": [3, 6, 10, 16],      # NBA: 3-pt game, 6-pt (2 poss), 10+ comfortable, 16+ blowout
    "NCAAB": [3, 6, 10, 16],    # College basketball similar to NBA
    "NHL": [1, 2, 3],           # Hockey: 1 goal, 2 goals, 3+ goals
    "NFL": [3, 7, 14, 21],      # Football: FG, TD, 2 TDs, 3 TDs
    "MLB": [1, 2, 4],           # Baseball: 1 run, 2 runs, 4+ runs
}

DEFAULT_THRESHOLDS = [3, 6, 10, 16]  # Default to NBA-style


def get_thresholds_for_sport(sport: str) -> list[int]:
    """Get Lead Ladder thresholds for a sport."""
    return SPORT_THRESHOLDS.get(sport.upper(), DEFAULT_THRESHOLDS)


def build_game_analysis(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Analyze a game timeline into moments.

    This is the single entry point for game narrative analysis.

    Args:
        timeline: Full timeline events (PBP + social)
        summary: Game summary metadata
        sport: Sport code (NBA, NHL, NFL, etc.) for threshold selection

    Returns:
        {
            "moments": [Moment.to_dict(), ...],  # Full coverage
        }
    """
    thresholds = get_thresholds_for_sport(sport)
    moments = partition_game(timeline, summary, thresholds=thresholds)

    return {
        "moments": [m.to_dict() for m in moments],
    }


async def build_game_analysis_async(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    game_id: int,
    sport: str = "NBA",
) -> dict[str, Any]:
    """
    Analyze a game timeline into moments (async version).
    
    Currently identical to sync version. Async signature retained
    for future AI enrichment if needed.
    """
    return build_game_analysis(timeline, summary, sport=sport)
