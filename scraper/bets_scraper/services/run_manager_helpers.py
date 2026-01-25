"""Helper queries and ingestion utilities for scrape runs.

This module re-exports functions from specialized modules for backward
compatibility. New code should import directly from:
- game_selection: Game selection queries
- pbp_ingestion: Play-by-play ingestion helpers
"""

from __future__ import annotations

# Re-export game selection functions
from .game_selection import (
    select_games_for_boxscores,
    select_games_for_odds,
    select_games_for_social,
    select_games_for_pbp_sportsref,
)

# Re-export PBP ingestion functions
from .pbp_ingestion import (
    ingest_pbp_via_sportsref,
    select_games_for_pbp_nhl_api,
    ingest_pbp_via_nhl_api,
)

__all__ = [
    # Game selection
    "select_games_for_boxscores",
    "select_games_for_odds",
    "select_games_for_social",
    "select_games_for_pbp_sportsref",
    # PBP ingestion
    "ingest_pbp_via_sportsref",
    "select_games_for_pbp_nhl_api",
    "ingest_pbp_via_nhl_api",
]
