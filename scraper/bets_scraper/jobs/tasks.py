"""Celery tasks for triggering scrape runs."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger
from ..services.ingestion import run_ingestion
from ..services.scheduler import schedule_ingestion_runs
from ..services.timeline_generator import (
    generate_missing_timelines,
    generate_all_needed_timelines,
    SCHEDULED_DAYS_BACK,
)


@shared_task(name="run_scrape_job")
def run_scrape_job(run_id: int, config_payload: dict) -> dict:
    """Run a scrape job.
    
    NOTE: Timeline generation is now DECOUPLED from scraping.
    Use trigger_game_pipelines task or the pipeline API endpoints
    to generate timelines after scraping completes.
    
    For prod auto-chain behavior, call trigger_game_pipelines_task
    separately after this task completes.
    """
    logger.info("scrape_job_started", run_id=run_id)
    result = run_ingestion(run_id, config_payload)
    logger.info("scrape_job_completed", run_id=run_id, result=result)
    
    # NOTE: Timeline generation has been decoupled.
    # The scraper now ONLY handles data ingestion.
    # Timeline/moment generation is triggered separately via:
    # 1. trigger_game_pipelines_task for prod auto-chain
    # 2. Pipeline API endpoints for admin/manual control
    # This allows dev/admin to inspect scraped data before processing.
    
    return result


@shared_task(
    name="trigger_game_pipelines",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def trigger_game_pipelines_task(
    league_code: str,
    days_back: int | None = None,
    max_games: int | None = None,
    auto_chain: bool = True,
) -> dict:
    """Trigger pipeline runs for games missing timeline artifacts.
    
    This is the production task for triggering game pipelines after scraping.
    It finds games with PBP data but no timeline artifacts and starts
    pipeline runs for them.
    
    Args:
        league_code: League to process (required)
        days_back: How many days back to check (None = ALL games)
        max_games: Maximum number of games to process (None = all)
        auto_chain: Whether pipelines should auto-proceed through stages
        
    Returns:
        Summary dict with counts of pipelines started
    """
    import httpx
    from ..config import settings
    from ..db import get_session
    
    logger.info(
        "trigger_game_pipelines_started",
        league=league_code,
        days_back=days_back,
        max_games=max_games,
        auto_chain=auto_chain,
    )
    
    # Find games missing timelines (reuse existing logic)
    from ..services.timeline_generator import find_games_missing_timelines
    
    with get_session() as session:
        games = find_games_missing_timelines(session, league_code, days_back)
    
    if not games:
        logger.info("trigger_game_pipelines_no_games", league=league_code)
        return {
            "games_found": 0,
            "pipelines_started": 0,
            "pipelines_failed": 0,
        }
    
    # Limit games if specified
    games_to_process = games[:max_games] if max_games else games
    
    started = 0
    failed = 0
    
    api_base = settings.api_internal_url
    
    for game_id, game_date, home_team, away_team in games_to_process:
        logger.info(
            "trigger_game_pipeline",
            game_id=game_id,
            game_date=str(game_date),
            matchup=f"{away_team} @ {home_team}",
        )
        
        try:
            # Call the pipeline API to run the full pipeline
            response = httpx.post(
                f"{api_base}/api/admin/sports/pipeline/{game_id}/run-full",
                json={"triggered_by": "prod_auto"},
                timeout=600,  # 10 minute timeout per game
            )
            response.raise_for_status()
            started += 1
            
        except Exception as e:
            logger.error(
                "trigger_game_pipeline_failed",
                game_id=game_id,
                error=str(e),
            )
            failed += 1
    
    summary = {
        "games_found": len(games),
        "pipelines_started": started,
        "pipelines_failed": failed,
    }
    
    logger.info("trigger_game_pipelines_completed", **summary)
    
    return summary


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


@shared_task(
    name="run_scheduled_timeline_generation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_scheduled_timeline_generation() -> dict:
    """
    Scheduled task to generate/regenerate timelines for all games that need them.
    
    This runs after the scheduled ingestion (90 minutes later) and processes:
    - Games that completed and are missing timeline artifacts
    - Games where PBP or social data was updated after timeline was generated
    
    Uses the same lookback window as the scheduler (96 hours / 4 days).
    """
    from ..config_sports import get_scheduled_leagues
    
    leagues = get_scheduled_leagues()
    
    total_summary = {
        "leagues_processed": 0,
        "total_games_found": 0,
        "total_games_missing": 0,
        "total_games_stale": 0,
        "total_games_processed": 0,
        "total_games_successful": 0,
        "total_games_failed": 0,
    }
    
    logger.info(
        "scheduled_timeline_gen_start",
        leagues=list(leagues),
        days_back=SCHEDULED_DAYS_BACK,
    )
    
    for league_code in leagues:
        try:
            summary = generate_all_needed_timelines(
                league_code=league_code,
                days_back=SCHEDULED_DAYS_BACK,
                max_games=None,  # Process all games
            )
            
            total_summary["leagues_processed"] += 1
            total_summary["total_games_found"] += summary.get("games_found", 0)
            total_summary["total_games_missing"] += summary.get("games_missing", 0)
            total_summary["total_games_stale"] += summary.get("games_stale", 0)
            total_summary["total_games_processed"] += summary.get("games_processed", 0)
            total_summary["total_games_successful"] += summary.get("games_successful", 0)
            total_summary["total_games_failed"] += summary.get("games_failed", 0)
            
        except Exception as exc:
            logger.exception(
                "scheduled_timeline_gen_league_failed",
                league=league_code,
                error=str(exc),
            )
    
    logger.info("scheduled_timeline_gen_complete", **total_summary)
    
    return total_summary
