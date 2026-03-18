"""Shared profile-loading and rolling-profile-building logic.

Extracted from ``MLBPADatasetBuilder`` to eliminate duplication across
the pitch and batted ball dataset builders.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.tasks._training_helpers import stats_to_metrics

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Each rolling-window game ≈ 1.5 calendar days on average (off-days,
# travel days, rainouts).  Multiplying the game window by this factor
# gives a conservative calendar-day lookback so the SQL query loads
# enough history without scanning the entire table.
_CALENDAR_DAYS_PER_GAME = 2


class ProfileMixin:
    """Mixin providing profile history loading and rolling profile assembly.

    Subclasses must set ``self._db: AsyncSession`` before calling these
    methods.
    """

    _db: AsyncSession

    async def _load_profile_histories(
        self,
        dt_start: datetime | None,
        dt_end: datetime | None,
        rolling_window: int,
    ) -> tuple[
        dict[str, list[tuple[str, Any]]],
        dict[str, list[tuple[str, Any]]],
        dict[int, list[tuple[str, Any]]],
    ]:
        """Pre-load batter, pitcher, and team history for profile assembly.

        Queries are bounded by ``dt_end`` (upper) and a computed floor
        derived from ``dt_start`` and ``rolling_window`` (lower).  The
        floor ensures we load enough history to build a full rolling
        profile for the earliest game in the date range, without
        scanning all rows back to the beginning of time.
        """
        from sqlalchemy import select

        from app.db.mlb_advanced import (
            MLBGameAdvancedStats,
            MLBPitcherGameStats,
            MLBPlayerAdvancedStats,
        )
        from app.db.sports import SportsGame

        db = self._db

        # Lower bound: enough history before the earliest target game
        # to fill a full rolling window.
        dt_floor = None
        if dt_start:
            lookback_days = rolling_window * _CALENDAR_DAYS_PER_GAME
            dt_floor = dt_start - timedelta(days=lookback_days)

        def _apply_date_bounds(stmt):  # type: ignore[no-untyped-def]
            if dt_floor:
                stmt = stmt.where(SportsGame.game_date >= dt_floor)
            if dt_end:
                stmt = stmt.where(SportsGame.game_date <= dt_end)
            return stmt

        # Batter history from MLBPlayerAdvancedStats
        batter_stmt = _apply_date_bounds(
            select(MLBPlayerAdvancedStats, SportsGame.game_date)
            .join(SportsGame, SportsGame.id == MLBPlayerAdvancedStats.game_id)
            .where(SportsGame.status.in_(["final", "archived"]))
            .order_by(SportsGame.game_date.asc())
        )
        batter_result = await db.execute(batter_stmt)

        batter_history: dict[str, list[tuple[str, Any]]] = defaultdict(list)
        for stats_row, game_date in batter_result:
            batter_history[stats_row.player_external_ref].append(
                (str(game_date), stats_row)
            )

        # Pitcher history from MLBPitcherGameStats
        pitcher_stmt = _apply_date_bounds(
            select(MLBPitcherGameStats, SportsGame.game_date)
            .join(SportsGame, SportsGame.id == MLBPitcherGameStats.game_id)
            .where(SportsGame.status.in_(["final", "archived"]))
            .order_by(SportsGame.game_date.asc())
        )
        pitcher_result = await db.execute(pitcher_stmt)

        pitcher_history: dict[str, list[tuple[str, Any]]] = defaultdict(list)
        for stats_row, game_date in pitcher_result:
            pitcher_history[stats_row.player_external_ref].append(
                (str(game_date), stats_row)
            )

        # Team history for fallback pitcher profiles
        team_stmt = _apply_date_bounds(
            select(MLBGameAdvancedStats, SportsGame.game_date)
            .join(SportsGame, SportsGame.id == MLBGameAdvancedStats.game_id)
            .where(SportsGame.status.in_(["final", "archived"]))
            .order_by(SportsGame.game_date.asc())
        )
        team_result = await db.execute(team_stmt)

        team_history: dict[int, list[tuple[str, Any]]] = defaultdict(list)
        for stats_row, game_date in team_result:
            team_history[stats_row.team_id].append((str(game_date), stats_row))

        return batter_history, pitcher_history, team_history

    @staticmethod
    def _build_player_profile(
        player_ref: str,
        history: dict[str, list[tuple[str, Any]]],
        before_date: str,
        window: int,
        min_games: int,
    ) -> dict[str, float] | None:
        """Build a player rolling profile from pre-loaded history."""
        player_games = history.get(player_ref, [])
        prior = [s for d, s in player_games if d < before_date]
        if len(prior) < min_games:
            return None
        recent = prior[-window:]
        metrics_list = [stats_to_metrics(s) for s in recent]
        aggregated: dict[str, float] = {}
        for key in metrics_list[0]:
            vals = [m[key] for m in metrics_list if key in m]
            if vals:
                aggregated[key] = round(sum(vals) / len(vals), 4)
        return aggregated

    @staticmethod
    def _build_pitcher_profile(
        pitcher_ref: str,
        history: dict[str, list[tuple[str, Any]]],
        before_date: str,
        window: int,
        min_games: int,
    ) -> dict[str, float] | None:
        """Build a pitcher rolling profile from pitcher game stats history."""
        from app.analytics.datasets.mlb_pa_dataset import _pitcher_stats_to_metrics

        pitcher_games = history.get(pitcher_ref, [])
        prior = [s for d, s in pitcher_games if d < before_date]
        if len(prior) < min_games:
            return None
        recent = prior[-window:]
        metrics_list = [_pitcher_stats_to_metrics(s) for s in recent]
        if not metrics_list:
            return None
        aggregated: dict[str, float] = {}
        for key in metrics_list[0]:
            vals = [m[key] for m in metrics_list if key in m]
            if vals:
                aggregated[key] = round(sum(vals) / len(vals), 4)
        return aggregated
