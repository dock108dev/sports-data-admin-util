"""
Game Analysis: Timeline partitioning into narrative moments.

This module provides the entry point for analyzing a game timeline.
All narrative logic lives in moments.py.

The output is a simple structure:
- moments: list of all moments (full coverage)
- highlights: list of notable moments (is_notable=True)
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .moments import partition_game, get_highlights

logger = logging.getLogger(__name__)


def build_game_analysis(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyze a game timeline into moments.

    This is the single entry point for game narrative analysis.

    Returns:
        {
            "moments": [Moment.to_dict(), ...],  # Full coverage
            "highlights": [Moment.to_dict(), ...]  # Notable moments only
        }
    """
    moments = partition_game(timeline, summary)
    highlights = get_highlights(moments)

    return {
        "moments": [m.to_dict() for m in moments],
        "highlights": [m.to_dict() for m in highlights],
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
    return build_game_analysis(timeline, summary)
    

# Backwards compatibility aliases
build_nba_game_analysis = build_game_analysis
build_nba_game_analysis_async = build_game_analysis_async
