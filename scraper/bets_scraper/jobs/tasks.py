"""Celery tasks for triggering scrape runs."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger
from ..services.ingestion import run_ingestion
from ..services.scheduler import schedule_ingestion_runs
from ..services.timeline_generator import generate_missing_timelines


@shared_task(name="run_scrape_job")
def run_scrape_job(run_id: int, config_payload: dict) -> dict:
    from ..config_sports import validate_league_code, is_timeline_enabled
    
    logger.info("scrape_job_started", run_id=run_id)
    result = run_ingestion(run_id, config_payload)
    logger.info("scrape_job_completed", run_id=run_id, result=result)
    
    # After scrape completes, trigger timeline generation for any games now ready
    league_code = config_payload.get("league_code")
    if not league_code:
        logger.error("scrape_job_missing_league_code", run_id=run_id)
        return result
    
    try:
        validate_league_code(league_code)
    except ValueError as exc:
        logger.error("scrape_job_invalid_league_code", run_id=run_id, error=str(exc))
        return result
    
    # Only trigger timeline generation if enabled for this league
    if is_timeline_enabled(league_code):
        _trigger_timeline_generation_after_scrape(league_code)
    else:
        logger.info("timeline_generation_not_enabled_for_league", league=league_code)
    
    return result


def _trigger_timeline_generation_after_scrape(league_code: str) -> None:
    """Trigger timeline generation for ALL games missing moments/highlights."""
    from ..config import settings
    from ..celery_app import app as celery_app
    
    if not settings.timeline_config.enable_timeline_generation:
        logger.info("timeline_generation_disabled_skipping_post_scrape")
        return
    
    try:
        # days_back=None means find ALL games missing timelines (no date limit)
        # This is important for backfill scenarios
        async_result = celery_app.send_task(
            "generate_missing_timelines",
            kwargs={
                "league_code": league_code,
                "days_back": None,  # ALL games, not limited by date
                "max_games": settings.timeline_config.timeline_generation_max_games,
            },
            queue="bets-scraper",
            routing_key="bets-scraper",
        )
        logger.info(
            "timeline_generation_triggered_post_scrape",
            league=league_code,
            job_id=async_result.id,
            days_back="ALL",
        )
    except Exception as exc:
        logger.error(
            "timeline_generation_trigger_failed",
            league=league_code,
            error=str(exc),
        )


@shared_task(
    name="run_scheduled_ingestion",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_scheduled_ingestion() -> dict:
    """Trigger the scheduled ingestion pipeline (manual debug entry point)."""
    summary = schedule_ingestion_runs()
    return {
        "runs_created": summary.runs_created,
        "runs_skipped": summary.runs_skipped,
        "run_failures": summary.run_failures,
        "enqueue_failures": summary.enqueue_failures,
        "last_run_at": summary.last_run_at.isoformat(),
    }


@shared_task(
    name="generate_missing_timelines",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def generate_missing_timelines_task(
    league_code: str,
    days_back: int | None = None,
    max_games: int | None = None,
) -> dict:
    """
    Generate timeline artifacts for games missing them.
    
    This task finds completed games with play-by-play data but no timeline
    artifacts, and triggers timeline generation for each one.
    
    Args:
        league_code: League to process (required)
        days_back: How many days back to check (None = ALL games)
        max_games: Maximum number of games to process (None = all)
        
    Returns:
        Summary dict with counts of processed/successful/failed games
    """
    logger.info(
        "timeline_gen_task_started",
        league=league_code,
        days_back=days_back,
        max_games=max_games,
    )
    
    summary = generate_missing_timelines(
        league_code=league_code,
        days_back=days_back,
        max_games=max_games,
    )
    
    logger.info("timeline_gen_task_completed", **summary)
    
    return summary


@shared_task(
    name="regenerate_timeline",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def regenerate_timeline_task(
    game_id: int,
    reason: str = "manual",
) -> dict:
    """
    Regenerate timeline artifact for a specific game.
    
    This task calls the API endpoint to regenerate the timeline for a single game.
    Used by auto-regeneration after social backfill or manual regeneration requests.
    
    Args:
        game_id: Game ID to regenerate timeline for
        reason: Reason for regeneration (e.g., "social_backfill", "manual")
        
    Returns:
        Result dict with success/failure status
    """
    import httpx
    from ..config import settings
    
    logger.info(
        "timeline_regen_task_started",
        game_id=game_id,
        reason=reason,
    )
    
    api_url = f"{settings.api_internal_url}/api/admin/sports/timelines/generate/{game_id}"
    
    try:
        response = httpx.post(
            api_url,
            json={"timeline_version": "v1"},
            timeout=600,  # 10 minute timeout for large games
        )
        response.raise_for_status()
        result = response.json()
        
        logger.info(
            "timeline_regen_task_completed",
            game_id=game_id,
            reason=reason,
            success=True,
        )
        
        return {
            "game_id": game_id,
            "success": True,
            "reason": reason,
            "result": result,
        }
        
    except httpx.HTTPStatusError as exc:
        logger.error(
            "timeline_regen_task_failed",
            game_id=game_id,
            reason=reason,
            status_code=exc.response.status_code,
            error=exc.response.text,
        )
        return {
            "game_id": game_id,
            "success": False,
            "reason": reason,
            "error": f"HTTP {exc.response.status_code}: {exc.response.text}",
        }
        
    except Exception as exc:
        logger.error(
            "timeline_regen_task_failed",
            game_id=game_id,
            reason=reason,
            error=str(exc),
        )
        return {
            "game_id": game_id,
            "success": False,
            "reason": reason,
            "error": str(exc),
        }
