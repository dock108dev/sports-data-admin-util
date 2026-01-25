"""Persistence helpers for normalized scraper payloads.

This package provides modular persistence functions organized by domain:
- teams: Team upsert and lookup
- games: Game upsert
- boxscores: Team and player boxscore persistence
- odds: Odds matching and persistence
- admin: Administrative operations (deletion, cache management)
"""

from .admin import clear_odds_cache, delete_game, delete_games_batch
from .boxscores import (
    GamePersistResult,
    PlayerBoxscoreStats,
    persist_game_payload,
    upsert_player_boxscores,
    upsert_team_boxscores,
)
from .games import upsert_game
from .odds import upsert_odds
from .plays import upsert_plays
from .teams import _find_team_by_name, _upsert_team

__all__ = [
    # Admin operations
    "delete_game",
    "delete_games_batch",
    "clear_odds_cache",
    # Game persistence
    "persist_game_payload",
    "GamePersistResult",
    "PlayerBoxscoreStats",
    "upsert_game",
    "upsert_team_boxscores",
    "upsert_player_boxscores",
    "upsert_odds",
    "upsert_plays",
    "_upsert_team",
    "_find_team_by_name",
]
