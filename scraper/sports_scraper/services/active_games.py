"""ActiveGamesResolver: query games by lifecycle window state.

Computes window_state at query time (never stored) so results are always fresh.
Window states:
- PRE:  scheduled/pregame game within pregame_window_hours of tip_time
- IN:   live game
- POST: final game within postgame_window_hours of end_time
- NONE: game outside any active window
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from sqlalchemy import case, literal_column, or_
from sqlalchemy.orm import Session

from ..config_sports import get_league_config, LEAGUE_CONFIG
from ..db import db_models
from ..logging import logger
from ..utils.datetime_utils import now_utc

WindowState = Literal["PRE", "IN", "POST", "NONE"]

# Default windows used when no league-specific config is available
_DEFAULT_PREGAME_HOURS = 6
_DEFAULT_POSTGAME_HOURS = 3
_DEFAULT_PBP_STALE_MINUTES = 4


class ActiveGamesResolver:
    """Resolves which games need attention right now.

    All queries compute window_state inline via SQL CASE so results
    are never stale. Designed for indexed scans over ~50-100 active games.
    """

    def __init__(
        self,
        pregame_hours: int = _DEFAULT_PREGAME_HOURS,
        postgame_hours: int = _DEFAULT_POSTGAME_HOURS,
        pbp_stale_minutes: int = _DEFAULT_PBP_STALE_MINUTES,
    ) -> None:
        self.pregame_hours = pregame_hours
        self.postgame_hours = postgame_hours
        self.pbp_stale_minutes = pbp_stale_minutes

    @staticmethod
    def _window_state_expression(
        pregame_hours: int = _DEFAULT_PREGAME_HOURS,
        postgame_hours: int = _DEFAULT_POSTGAME_HOURS,
    ):
        """Build a SQL CASE expression that computes window_state inline."""
        now = now_utc()
        return case(
            # POST: final game with end_time within postgame window
            (
                (db_models.SportsGame.status == db_models.GameStatus.final.value)
                & (db_models.SportsGame.end_time.isnot(None))
                & (db_models.SportsGame.end_time > now - timedelta(hours=postgame_hours)),
                literal_column("'POST'"),
            ),
            # IN: currently live
            (
                db_models.SportsGame.status == db_models.GameStatus.live.value,
                literal_column("'IN'"),
            ),
            # PRE: scheduled or pregame within pregame window
            (
                (
                    db_models.SportsGame.status.in_([
                        db_models.GameStatus.scheduled.value,
                        db_models.GameStatus.pregame.value,
                    ])
                )
                & (db_models.SportsGame.tip_time.isnot(None))
                & (db_models.SportsGame.tip_time < now + timedelta(hours=pregame_hours)),
                literal_column("'PRE'"),
            ),
            else_=literal_column("'NONE'"),
        )

    def get_active_games(
        self,
        session: Session,
        league_code: str | None = None,
    ) -> list[tuple[db_models.SportsGame, str]]:
        """Return games in any active window with their computed window_state.

        Args:
            session: DB session
            league_code: Optional filter by league

        Returns:
            List of (game, window_state) tuples where window_state is PRE/IN/POST
        """
        ws = self._window_state_expression(self.pregame_hours, self.postgame_hours)
        query = (
            session.query(db_models.SportsGame, ws.label("window_state"))
            .filter(
                db_models.SportsGame.status.in_([
                    db_models.GameStatus.scheduled.value,
                    db_models.GameStatus.pregame.value,
                    db_models.GameStatus.live.value,
                    db_models.GameStatus.final.value,
                ])
            )
        )

        if league_code:
            league_id = (
                session.query(db_models.SportsLeague.id)
                .filter(db_models.SportsLeague.code == league_code)
                .scalar()
            )
            if league_id:
                query = query.filter(db_models.SportsGame.league_id == league_id)

        # Filter out NONE window states — we only want active games
        results = query.all()
        return [(game, ws_val) for game, ws_val in results if ws_val != "NONE"]

    def get_games_needing_pbp(
        self,
        session: Session,
    ) -> list[db_models.SportsGame]:
        """Return pregame/live games where PBP data is stale.

        Only includes leagues with live_pbp_enabled=True.
        A game needs PBP if last_pbp_at is NULL or older than pbp_stale_minutes.
        """
        now = now_utc()
        stale_threshold = now - timedelta(minutes=self.pbp_stale_minutes)

        # Get league IDs where live PBP is enabled
        enabled_leagues = [
            code for code, cfg in LEAGUE_CONFIG.items() if cfg.live_pbp_enabled
        ]
        if not enabled_leagues:
            return []

        league_ids = (
            session.query(db_models.SportsLeague.id)
            .filter(db_models.SportsLeague.code.in_(enabled_leagues))
            .all()
        )
        league_id_list = [lid for (lid,) in league_ids]
        if not league_id_list:
            return []

        games = (
            session.query(db_models.SportsGame)
            .filter(
                db_models.SportsGame.league_id.in_(league_id_list),
                db_models.SportsGame.status.in_([
                    db_models.GameStatus.pregame.value,
                    db_models.GameStatus.live.value,
                ]),
                or_(
                    db_models.SportsGame.last_pbp_at.is_(None),
                    db_models.SportsGame.last_pbp_at < stale_threshold,
                ),
            )
            .order_by(db_models.SportsGame.tip_time.asc().nullslast())
            .all()
        )

        logger.debug("games_needing_pbp", count=len(games))
        return games

    def get_games_needing_social(
        self,
        session: Session,
    ) -> list[tuple[int, int]]:
        """Return (game_id, team_id) pairs for games in active windows.

        Returns unique team IDs across all active games so social collection
        can be dispatched per-team without duplicates.
        """
        active = self.get_active_games(session)
        seen_teams: set[int] = set()
        pairs: list[tuple[int, int]] = []

        for game, _ws in active:
            for team_id in (game.home_team_id, game.away_team_id):
                if team_id not in seen_teams:
                    seen_teams.add(team_id)
                    pairs.append((game.id, team_id))

        logger.debug("games_needing_social", pairs=len(pairs), unique_teams=len(seen_teams))
        return pairs

    def get_games_needing_odds(
        self,
        session: Session,
    ) -> list[db_models.SportsGame]:
        """Return games that need odds updates.

        Includes:
        - pregame/live games (active odds)
        - recently-final games within 2 hours (closing line capture)
        """
        now = now_utc()
        closing_line_cutoff = now - timedelta(hours=2)

        games = (
            session.query(db_models.SportsGame)
            .filter(
                or_(
                    # Active games need live odds
                    db_models.SportsGame.status.in_([
                        db_models.GameStatus.pregame.value,
                        db_models.GameStatus.live.value,
                    ]),
                    # Recently-final games need closing line
                    (
                        (db_models.SportsGame.status == db_models.GameStatus.final.value)
                        & (db_models.SportsGame.end_time.isnot(None))
                        & (db_models.SportsGame.end_time > closing_line_cutoff)
                    ),
                )
            )
            .order_by(db_models.SportsGame.tip_time.asc().nullslast())
            .all()
        )

        logger.debug("games_needing_odds", count=len(games))
        return games
