"""Boxscore ingestion via official APIs.

This module re-exports boxscore ingestion functions for NHL and NCAAB
from their respective modules for backward compatibility.

NHL: api-web.nhle.com
NCAAB: api.collegebasketballdata.com

Benefits:
- Single data source per league (schedule, PBP, and boxscores)
- Faster ingestion - REST API vs web scraping
- More reliable - official API less likely to break than HTML scraping
- No Sports Reference rate limiting
"""

from __future__ import annotations

# Re-export shared dependencies for test patching
from ..persistence import persist_game_payload  # noqa: F401
from .pbp_ingestion import _populate_nhl_game_ids  # noqa: F401

# Re-export NHL functions
from .nhl_boxscore_ingestion import (
    select_games_for_boxscores_nhl_api,
    ingest_boxscores_via_nhl_api,
    season_from_date as _season_from_date,  # noqa: F401
    convert_nhl_boxscore_to_normalized_game as _convert_boxscore_to_normalized_game,  # noqa: F401
)

# Re-export NCAAB functions
from .ncaab_boxscore_ingestion import (
    normalize_team_name as _normalize_team_name,  # noqa: F401
    populate_ncaab_game_ids as _populate_ncaab_game_ids,  # noqa: F401
    select_games_for_boxscores_ncaab_api,
    ingest_boxscores_via_ncaab_api,
    convert_ncaab_boxscore_to_normalized_game as _convert_ncaab_boxscore_to_normalized_game,  # noqa: F401
)

# Public API
__all__ = [
    # NHL
    "select_games_for_boxscores_nhl_api",
    "ingest_boxscores_via_nhl_api",
    # NCAAB
    "select_games_for_boxscores_ncaab_api",
    "ingest_boxscores_via_ncaab_api",
]
