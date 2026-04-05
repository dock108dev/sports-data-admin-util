"""SSOT per-game processing functions for all leagues.

Each function takes a session + SportsGame ORM object, fetches data from the
shared API client, calls shared persistence functions, and returns a
GameProcessResult. Functions do NOT handle game selection, rate limiting,
jitter, or locking -- those are caller-side concerns.

Both the live polling path (polling_helpers.py) and the manual/scheduled
ingestion path (pbp_*.py, *_boxscore_ingestion.py) call these same functions,
ensuring identical processing regardless of trigger.

Per-league implementations live in game_processors_{league}.py modules.
This file provides the shared dataclass, helpers, dispatchers, and
public re-exports.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..logging import logger


@dataclass
class GameProcessResult:
    """Result of processing a single game."""

    api_calls: int = 0
    events_inserted: int = 0
    boxscore_updated: bool = False
    transition: dict | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def has_game_action(plays: list) -> bool:
    """Check whether any plays represent actual game action (period >= 1).

    Pre-game events (lineup announcements, status changes, etc.) have
    ``quarter=None`` or ``quarter=0``.  Only plays with ``quarter >= 1``
    indicate the game has started.  Used to guard the pregame → live
    status promotion so pre-game API events don't prematurely flip games
    to live status.
    """
    return any(
        getattr(p, "quarter", None) is not None and getattr(p, "quarter", 0) >= 1
        for p in plays
    )


def try_promote_to_live(
    game,
    plays: list,
    result: GameProcessResult,
    league: str,
    *,
    db_models=None,
    now_utc_fn=None,
) -> None:
    """Promote a pregame game to live if plays contain actual game action.

    Mutates ``game.status`` and populates ``result.transition`` if
    promotion occurs.  No-op if the game is not in pregame status or
    if the plays are only pre-game events.
    """
    if db_models is None:
        from ..db import db_models as _dbm
        db_models = _dbm
    if now_utc_fn is None:
        from ..utils.datetime_utils import now_utc
        now_utc_fn = now_utc

    if game.status != db_models.GameStatus.pregame.value:
        return
    if not has_game_action(plays):
        return

    game.status = db_models.GameStatus.live.value
    game.updated_at = now_utc_fn()
    result.transition = {
        "game_id": game.id,
        "from": "pregame",
        "to": "live",
    }
    logger.info(
        "poll_pbp_inferred_live",
        game_id=game.id,
        league=league,
        reason="pbp_game_action_found",
        play_count=len(plays),
    )


# ---------------------------------------------------------------------------
# Re-exports — canonical import path for all callers
# ---------------------------------------------------------------------------

from .game_processors_mlb import (  # noqa: E402, F401
    check_game_status_mlb,
    process_game_boxscore_mlb,
    process_game_pbp_mlb,
)
from .game_processors_nba import (  # noqa: E402, F401
    check_game_status_nba,
    process_game_boxscore_nba,
    process_game_pbp_nba,
)
from .game_processors_ncaab import (  # noqa: E402, F401
    process_game_boxscore_ncaab,
    process_game_boxscores_ncaab_batch,
    process_game_pbp_ncaab,
)
from .game_processors_nfl import (  # noqa: E402, F401
    check_game_status_nfl,
    process_game_boxscore_nfl,
    process_game_pbp_nfl,
)
from .game_processors_nhl import (  # noqa: E402, F401
    check_game_status_nhl,
    process_game_boxscore_nhl,
    process_game_pbp_nhl,
)

# ---------------------------------------------------------------------------
# Dispatchers (route by league_code)
# ---------------------------------------------------------------------------


def process_game_pbp(session, game, league_code: str) -> GameProcessResult:
    """Dispatch PBP processing to the appropriate league handler."""
    if league_code == "NBA":
        return process_game_pbp_nba(session, game)
    elif league_code == "NHL":
        return process_game_pbp_nhl(session, game)
    elif league_code == "MLB":
        return process_game_pbp_mlb(session, game)
    elif league_code == "NCAAB":
        return process_game_pbp_ncaab(session, game)
    elif league_code == "NFL":
        return process_game_pbp_nfl(session, game)
    return GameProcessResult()


def process_game_boxscore(session, game, league_code: str) -> GameProcessResult:
    """Dispatch boxscore processing to the appropriate league handler."""
    if league_code == "NBA":
        return process_game_boxscore_nba(session, game)
    elif league_code == "NHL":
        return process_game_boxscore_nhl(session, game)
    elif league_code == "MLB":
        return process_game_boxscore_mlb(session, game)
    elif league_code == "NCAAB":
        return process_game_boxscore_ncaab(session, game)
    elif league_code == "NFL":
        return process_game_boxscore_nfl(session, game)
    return GameProcessResult()
