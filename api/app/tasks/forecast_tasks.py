"""Hourly MLB forecast refresh.

Runs every hour via Celery beat. Simulates all MLB games in the next
24 hours using the active model and upserts results into the
``mlb_daily_forecasts`` work table. Downstream apps query this table
for pre-computed predictions with betting edge analysis.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="refresh_mlb_forecasts", bind=True, max_retries=1)
def refresh_mlb_forecasts(self) -> dict:
    """Entry point: refresh MLB daily forecasts."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run_forecast_refresh(self.request.id))
    finally:
        loop.close()


async def _run_forecast_refresh(celery_task_id: str | None = None) -> dict:
    """Async implementation of the hourly forecast refresh."""
    from app.tasks._task_infra import _complete_job_run, _start_job_run, _task_db
    from app.tasks.batch_sim_tasks import _execute_batch_sim
    from app.utils.datetime_utils import today_et

    async with _task_db() as sf:
        run_id = await _start_job_run(sf, "mlb_forecast_refresh", celery_task_id)

        try:
            # Determine active model
            model_id = _get_active_model_id()

            # Date window: today through tomorrow (ET)
            et_today = today_et()
            et_tomorrow = et_today + timedelta(days=1)
            date_start = et_today.isoformat()
            date_end = et_tomorrow.isoformat()

            # Run simulations via existing batch orchestrator
            result = await _execute_batch_sim(
                sf=sf,
                sport="mlb",
                probability_mode="ml",
                iterations=5000,
                rolling_window=30,
                date_start=date_start,
                date_end=date_end,
                model_id=model_id,
            )

            # Handle no-games gracefully (off-day)
            game_results = result.get("results") or []
            games_by_id = result.get("_games_by_id") or {}
            game_count = len(game_results)

            if game_count > 0:
                await _upsert_forecasts(sf, game_results, games_by_id, model_id)

            # Clean up stale rows (>1 day old)
            await _cleanup_stale(sf, et_today)

            summary = {"game_count": game_count, "model_id": model_id}
            await _complete_job_run(sf, run_id, "success", summary_data=summary)
            logger.info("mlb_forecast_refresh_complete", extra=summary)
            return summary

        except Exception as exc:
            logger.exception("mlb_forecast_refresh_failed")
            await _complete_job_run(sf, run_id, "error", str(exc)[:500])
            return {"error": str(exc)}


def _get_active_model_id() -> str | None:
    """Return the active MLB PA model ID, or None for rule-based fallback."""
    try:
        from app.analytics.models.core.model_registry import ModelRegistry

        registry = ModelRegistry()
        model = registry.get_active_model("mlb", "plate_appearance")
        return model["model_id"] if model else None
    except Exception:
        logger.debug("no_active_mlb_model", exc_info=True)
        return None


async def _upsert_forecasts(
    sf,
    game_results: list[dict],
    games_by_id: dict,
    model_id: str | None,
) -> None:
    """Upsert simulation results into mlb_daily_forecasts."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.db.mlb_forecast import MlbDailyForecast
    from app.utils.datetime_utils import to_et_date

    now = datetime.now(UTC)

    async with sf() as db:
        for game_result in game_results:
            game_id = game_result.get("game_id")
            if not game_id:
                continue

            line = game_result.get("line_analysis") or {}
            game_obj = games_by_id.get(game_id)
            game_date_str = game_result.get("game_date", "")
            if game_obj and hasattr(game_obj, "game_date") and game_obj.game_date:
                game_date_str = to_et_date(game_obj.game_date).isoformat()

            row = {
                "game_id": game_id,
                "game_date": game_date_str,
                "home_team": game_result.get("home_team", ""),
                "away_team": game_result.get("away_team", ""),
                "home_team_id": game_result.get("home_team_id", 0),
                "away_team_id": game_result.get("away_team_id", 0),
                "home_win_prob": game_result.get("home_win_probability", 0.5),
                "away_win_prob": game_result.get("away_win_probability", 0.5),
                "predicted_home_score": game_result.get("average_home_score"),
                "predicted_away_score": game_result.get("average_away_score"),
                "probability_source": game_result.get("probability_source"),
                "sim_iterations": game_result.get("iterations", 5000),
                "sim_wp_std_dev": game_result.get("home_wp_std_dev"),
                "score_std_home": game_result.get("score_std_home"),
                "score_std_away": game_result.get("score_std_away"),
                "profile_games_home": game_result.get("profile_games_home"),
                "profile_games_away": game_result.get("profile_games_away"),
                # Line analysis
                "market_home_ml": line.get("market_home_ml"),
                "market_away_ml": line.get("market_away_ml"),
                "market_home_wp": line.get("market_home_wp"),
                "market_away_wp": line.get("market_away_wp"),
                "home_edge": line.get("home_edge"),
                "away_edge": line.get("away_edge"),
                "model_home_line": line.get("model_home_line"),
                "model_away_line": line.get("model_away_line"),
                "home_ev_pct": line.get("home_ev_pct"),
                "away_ev_pct": line.get("away_ev_pct"),
                "line_provider": line.get("provider"),
                "line_type": line.get("line_type"),
                # Metadata
                "model_id": model_id,
                "event_summary": game_result.get("event_summary"),
                "feature_snapshot": game_result.get("feature_snapshot"),
                "refreshed_at": now,
            }

            stmt = pg_insert(MlbDailyForecast).values(row)
            update_cols = {
                k: stmt.excluded[k] for k in row if k not in ("game_id", "created_at")
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["game_id"],
                set_=update_cols,
            )
            await db.execute(stmt)

        await db.commit()


async def _cleanup_stale(sf, today) -> None:
    """Remove forecast rows for games older than yesterday."""
    from sqlalchemy import delete

    from app.db.mlb_forecast import MlbDailyForecast

    cutoff = (today - timedelta(days=1)).isoformat()
    async with sf() as db:
        await db.execute(
            delete(MlbDailyForecast).where(MlbDailyForecast.game_date < cutoff)
        )
        await db.commit()
