"""Administrative persistence operations.

Provides functions for data cleanup and cache management.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger
from .odds_matching import cache_clear, cache_invalidate_game


def delete_game(session: Session, game_id: int, clear_cache: bool = True) -> dict:
    """Delete a game and all related data, with optional cache invalidation.

    Deletes the game and relies on CASCADE to remove:
    - sports_team_boxscores
    - sports_player_boxscores
    - sports_game_odds
    - sports_plays

    Args:
        session: Database session
        game_id: ID of the game to delete
        clear_cache: If True, invalidates cache entries for this game

    Returns:
        Dict with deletion details including game_id and whether it was found
    """
    game = session.get(db_models.SportsGame, game_id)
    if not game:
        logger.warning("delete_game_not_found", game_id=game_id)
        return {"game_id": game_id, "found": False, "deleted": False}

    # Capture game info before deletion for logging
    game_info = {
        "game_id": game_id,
        "home_team_id": game.home_team_id,
        "away_team_id": game.away_team_id,
        "game_date": str(game.game_date.date()) if game.game_date else None,
        "source_game_key": game.source_game_key,
    }

    # Delete the game (CASCADE handles related tables)
    session.delete(game)
    session.flush()

    # Invalidate cache entry for this game
    cache_entries_cleared = 0
    if clear_cache:
        cache_entries_cleared = cache_invalidate_game(game_id)

    logger.info(
        "game_deleted",
        game_id=game_id,
        game_date=game_info["game_date"],
        source_game_key=game_info["source_game_key"],
        cache_entries_cleared=cache_entries_cleared,
    )

    return {
        "game_id": game_id,
        "found": True,
        "deleted": True,
        "game_info": game_info,
        "cache_entries_cleared": cache_entries_cleared,
    }


def delete_games_batch(
    session: Session,
    game_ids: list[int],
    clear_all_cache: bool = True,
) -> dict:
    """Delete multiple games and optionally clear the entire cache.

    For bulk deletions, it's more efficient to clear the entire cache
    rather than invalidating individual entries.

    Args:
        session: Database session
        game_ids: List of game IDs to delete
        clear_all_cache: If True, clears entire cache after deletion

    Returns:
        Dict with deletion summary
    """
    deleted = []
    not_found = []

    for game_id in game_ids:
        result = delete_game(session, game_id, clear_cache=False)
        if result["deleted"]:
            deleted.append(game_id)
        else:
            not_found.append(game_id)

    # Clear entire cache after batch deletion
    cache_entries_cleared = 0
    if clear_all_cache and deleted:
        cache_entries_cleared = cache_clear()

    logger.info(
        "games_batch_deleted",
        deleted_count=len(deleted),
        not_found_count=len(not_found),
        cache_entries_cleared=cache_entries_cleared,
    )

    return {
        "deleted": deleted,
        "not_found": not_found,
        "cache_entries_cleared": cache_entries_cleared,
    }


def clear_odds_cache() -> int:
    """Clear the entire odds matching cache.

    Use this after any manual database changes to game data.
    Returns number of entries cleared.
    """
    return cache_clear()
