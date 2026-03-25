"""NBA data transforms: raw stats to simulation-ready models.

Converts raw box score and play-by-play data from the existing
ingestion pipeline into structured inputs for the analytics and
simulation engines.

This module bridges the gap between the scraper's raw data format
and the analytics framework's expected input format.
"""

from __future__ import annotations

from typing import Any


def transform_game_stats(raw_stats: dict[str, Any]) -> dict[str, Any]:
    """Transform raw game-level stats into analytics-ready format.

    Args:
        raw_stats: Raw game stats from the ingestion pipeline.

    Returns:
        Normalized dict suitable for analytics engines.
    """
    return {}


def transform_player_stats(raw_stats: dict[str, Any]) -> dict[str, Any]:
    """Transform raw player stats into analytics-ready format.

    Args:
        raw_stats: Raw player boxscore/advanced stats.

    Returns:
        Normalized dict suitable for metrics computation.
    """
    return {}
