"""Celery tasks for scrape job execution."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger
from ..services.ingestion import run_ingestion


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
    name="run_scheduled_ingestion",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_scheduled_ingestion() -> dict:
    """Trigger the scheduled ingestion pipeline.

    Runs leagues sequentially with PBP after each:
    1. NBA stats ingestion
    2. NBA PBP ingestion
    3. NHL stats ingestion
    4. NHL PBP ingestion

    This ensures PBP is fetched for newly scraped games.
    """
    from ..services.scheduler import schedule_single_league_and_wait, run_pbp_ingestion_for_league

    results = {}

    # Run NBA stats first and wait for completion
    logger.info("scheduled_ingestion_nba_start")
    nba_result = schedule_single_league_and_wait("NBA")
    results["NBA"] = nba_result
    logger.info("scheduled_ingestion_nba_complete", **nba_result)

    # Run NBA PBP after stats complete
    logger.info("scheduled_ingestion_nba_pbp_start")
    nba_pbp_result = run_pbp_ingestion_for_league("NBA")
    results["NBA_PBP"] = nba_pbp_result
    logger.info("scheduled_ingestion_nba_pbp_complete", **nba_pbp_result)

    # Run NHL stats after NBA PBP
    logger.info("scheduled_ingestion_nhl_start")
    nhl_result = schedule_single_league_and_wait("NHL")
    results["NHL"] = nhl_result
    logger.info("scheduled_ingestion_nhl_complete", **nhl_result)

    # Run NHL PBP after stats complete
    logger.info("scheduled_ingestion_nhl_pbp_start")
    nhl_pbp_result = run_pbp_ingestion_for_league("NHL")
    results["NHL_PBP"] = nhl_pbp_result
    logger.info("scheduled_ingestion_nhl_pbp_complete", **nhl_pbp_result)

    return {
        "leagues": results,
        "total_runs_created": nba_result["runs_created"] + nhl_result["runs_created"],
        "total_pbp_games": nba_pbp_result["pbp_games"] + nhl_pbp_result["pbp_games"],
    }
