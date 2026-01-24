"""Celery tasks for triggering scrape runs."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger
from ..services.ingestion import run_ingestion
from ..services.timeline_generator import (
    generate_missing_timelines,
    generate_all_needed_timelines,
    SCHEDULED_DAYS_BACK,
)


@shared_task(name="run_scrape_job")
def run_scrape_job(run_id: int, config_payload: dict) -> dict:
    """Run a scrape job (data ingestion only).

    Timeline generation is decoupled - call trigger_game_pipelines_task
    after this completes, or use Pipeline API endpoints for manual control.
    """
    logger.info("scrape_job_started", run_id=run_id)
    result = run_ingestion(run_id, config_payload)
    logger.info("scrape_job_completed", run_id=run_id, result=result)
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
    """Trigger the scheduled ingestion pipeline.

    Runs leagues sequentially: NBA first, waits for completion, then NHL.
    This ensures NHL runs immediately after NBA completes.
    """
    from ..services.scheduler import schedule_single_league_and_wait

    results = {}

    # Run NBA first and wait for completion
    logger.info("scheduled_ingestion_nba_start")
    nba_result = schedule_single_league_and_wait("NBA")
    results["NBA"] = nba_result
    logger.info("scheduled_ingestion_nba_complete", **nba_result)

    # Run NHL immediately after NBA completes
    logger.info("scheduled_ingestion_nhl_start")
    nhl_result = schedule_single_league_and_wait("NHL")
    results["NHL"] = nhl_result
    logger.info("scheduled_ingestion_nhl_complete", **nhl_result)

    return {
        "leagues": results,
        "total_runs_created": nba_result["runs_created"] + nhl_result["runs_created"],
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


@shared_task(
    name="run_scheduled_story_generation",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def run_scheduled_story_generation() -> dict:
    """
    Scheduled task to generate stories for games in the last 3 days.

    This runs after timeline generation completes and generates stories for all
    games with PBP data that haven't had stories generated yet.

    Uses a 3-day window: today, yesterday, and 2 days ago.
    For example, if run on 1/23, generates stories for 1/21, 1/22, and 1/23.
    """
    import httpx
    import time
    from datetime import date, timedelta
    from ..config import settings
    from ..config_sports import get_scheduled_leagues

    # Calculate 3-day window: 2 days ago through today
    today = date.today()
    start_date = today - timedelta(days=2)
    end_date = today

    leagues = list(get_scheduled_leagues())

    logger.info(
        "scheduled_story_gen_start",
        start_date=str(start_date),
        end_date=str(end_date),
        leagues=leagues,
    )

    api_base = settings.api_internal_url

    try:
        # Start the bulk generation job
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{api_base}/api/admin/sports/games/bulk-generate-async",
                json={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "leagues": leagues,
                    "force": False,  # Don't regenerate existing stories
                },
            )
            response.raise_for_status()
            job_data = response.json()

        job_id = job_data["job_id"]
        logger.info("scheduled_story_gen_job_started", job_id=job_id)

        # Poll for completion (max 30 minutes, check every 30 seconds)
        max_polls = 60
        poll_interval = 30

        for poll_num in range(max_polls):
            time.sleep(poll_interval)

            with httpx.Client(timeout=30.0) as client:
                status_response = client.get(
                    f"{api_base}/api/admin/sports/games/bulk-generate-status/{job_id}"
                )
                status_response.raise_for_status()
                status = status_response.json()

            state = status.get("state", "UNKNOWN")

            if state == "PROGRESS":
                logger.info(
                    "scheduled_story_gen_progress",
                    job_id=job_id,
                    current=status.get("current"),
                    total=status.get("total"),
                    successful=status.get("successful"),
                    failed=status.get("failed"),
                    skipped=status.get("skipped"),
                )
            elif state == "SUCCESS":
                result = status.get("result", {})
                logger.info(
                    "scheduled_story_gen_complete",
                    job_id=job_id,
                    total_games=result.get("total_games", 0),
                    successful=result.get("successful", 0),
                    failed=result.get("failed", 0),
                    skipped=result.get("skipped", 0),
                    generated=result.get("generated", 0),
                )
                return {
                    "job_id": job_id,
                    "state": "SUCCESS",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "leagues": leagues,
                    **result,
                }
            elif state == "FAILURE":
                logger.error(
                    "scheduled_story_gen_failed",
                    job_id=job_id,
                    status=status.get("status"),
                )
                return {
                    "job_id": job_id,
                    "state": "FAILURE",
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                    "leagues": leagues,
                    "error": status.get("status"),
                }

        # Timed out waiting for completion
        logger.warning(
            "scheduled_story_gen_timeout",
            job_id=job_id,
            max_wait_minutes=max_polls * poll_interval / 60,
        )
        return {
            "job_id": job_id,
            "state": "TIMEOUT",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "leagues": leagues,
            "error": "Timed out waiting for job completion",
        }

    except httpx.HTTPStatusError as exc:
        logger.error(
            "scheduled_story_gen_http_error",
            status_code=exc.response.status_code,
            error=exc.response.text,
        )
        return {
            "state": "ERROR",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "leagues": leagues,
            "error": f"HTTP {exc.response.status_code}: {exc.response.text}",
        }
    except Exception as exc:
        logger.exception(
            "scheduled_story_gen_error",
            error=str(exc),
        )
        raise  # Let Celery retry


@shared_task(name="clear_scraper_cache")
def clear_scraper_cache_task(league_code: str, days: int = 7) -> dict:
    """Clear cached scoreboard HTML files for the last N days.
    
    This allows manually refreshing recent data before a scrape run.
    Only clears scoreboard pages (not boxscores or PBP which are immutable).
    
    Args:
        league_code: League to clear cache for (e.g., "NBA", "NHL")
        days: Number of days back to clear (default 7)
        
    Returns:
        Summary dict with count of deleted files
    """
    from ..config import settings
    from ..utils.cache import HTMLCache
    
    logger.info(
        "clear_cache_started",
        league=league_code,
        days=days,
    )
    
    cache = HTMLCache(
        settings.scraper_config.html_cache_dir,
        league_code,
    )
    
    result = cache.clear_recent_scoreboards(days=days)
    
    logger.info(
        "clear_cache_completed",
        league=league_code,
        days=days,
        deleted_count=result["deleted_count"],
    )
    
    return {
        "league": league_code,
        "days": days,
        **result,
    }
