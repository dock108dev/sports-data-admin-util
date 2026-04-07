"""MLB forecast endpoints — read-only, API-key accessible.

Serves pre-computed hourly predictions from the ``mlb_daily_forecasts``
work table. No admin role required.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.mlb_forecast import MlbDailyForecast

router = APIRouter()


def _serialize_forecast(row: MlbDailyForecast) -> dict[str, Any]:
    """Convert a forecast row to the API response shape."""
    line_analysis: dict[str, Any] | None = None
    if row.market_home_ml is not None:
        line_analysis = {
            "market_home_ml": row.market_home_ml,
            "market_away_ml": row.market_away_ml,
            "market_home_wp": row.market_home_wp,
            "market_away_wp": row.market_away_wp,
            "home_edge": row.home_edge,
            "away_edge": row.away_edge,
            "model_home_line": row.model_home_line,
            "model_away_line": row.model_away_line,
            "home_ev_pct": row.home_ev_pct,
            "away_ev_pct": row.away_ev_pct,
            "provider": row.line_provider,
            "line_type": row.line_type,
        }

    return {
        "game_id": row.game_id,
        "game_date": row.game_date,
        "home_team": row.home_team,
        "away_team": row.away_team,
        "home_win_prob": row.home_win_prob,
        "away_win_prob": row.away_win_prob,
        "predicted_home_score": row.predicted_home_score,
        "predicted_away_score": row.predicted_away_score,
        "probability_source": row.probability_source,
        "line_analysis": line_analysis,
        "sim_meta": {
            "iterations": row.sim_iterations,
            "wp_std_dev": row.sim_wp_std_dev,
            "profile_games_home": row.profile_games_home,
            "profile_games_away": row.profile_games_away,
            "model_id": row.model_id,
        },
        "refreshed_at": row.refreshed_at.isoformat() if row.refreshed_at else None,
    }


@router.get("/forecasts/mlb")
async def get_mlb_forecasts(
    date: str | None = Query(
        default=None,
        description="Game date YYYY-MM-DD (default: today ET)",
    ),
    game_id: int | None = Query(default=None, description="Filter to specific game"),
    min_edge: float | None = Query(
        default=None,
        description="Min absolute edge on either side to include",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return pre-computed MLB forecasts for upcoming games.

    Refreshed hourly by the ``refresh_mlb_forecasts`` Celery task.
    Includes simulation results and current market line analysis.
    """
    from app.utils.datetime_utils import today_et

    target_date = date or today_et().isoformat()

    stmt = (
        select(MlbDailyForecast)
        .where(MlbDailyForecast.game_date == target_date)
        .order_by(MlbDailyForecast.game_id)
    )

    if game_id is not None:
        stmt = stmt.where(MlbDailyForecast.game_id == game_id)

    if min_edge is not None:
        abs_edge = abs(min_edge)
        stmt = stmt.where(
            (MlbDailyForecast.home_edge > abs_edge)
            | (MlbDailyForecast.away_edge > abs_edge)
        )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    forecasts = [_serialize_forecast(row) for row in rows]

    # Latest refresh timestamp across all returned rows
    last_refreshed = None
    if rows:
        max_stmt = select(func.max(MlbDailyForecast.refreshed_at)).where(
            MlbDailyForecast.game_date == target_date
        )
        max_result = await db.execute(max_stmt)
        max_ts = max_result.scalar()
        last_refreshed = max_ts.isoformat() if max_ts else None

    return {
        "forecasts": forecasts,
        "date": target_date,
        "count": len(forecasts),
        "last_refreshed": last_refreshed,
    }
