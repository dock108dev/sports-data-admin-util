"""Celery app configuration for sports scraper."""

from __future__ import annotations

from datetime import timedelta

from .utils.datetime_utils import now_utc

from celery import Celery, signals
from celery.schedules import crontab

from .config import settings
from .db import db_models, get_session
from .logging import logger

celery_config = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "worker_prefetch_multiplier": 1,
    "task_time_limit": 43200,       # 12 hours hard limit
    "task_soft_time_limit": 42600,  # 11h 50m soft limit
    "task_default_queue": "sports-scraper",
    "task_routes": {
        "run_scrape_job": {"queue": "sports-scraper"},
        # Social tasks route to dedicated social-scraper worker
        "collect_social_for_league": {"queue": "social-scraper"},
        "collect_team_social": {"queue": "social-scraper"},
        "map_social_to_games": {"queue": "social-scraper"},
    },
}

app = Celery(
    "sports-data-scraper",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["sports_scraper.jobs.tasks"],
)
app.conf.update(**celery_config)
app.conf.task_routes = {
    "run_scrape_job": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    # Social tasks route to dedicated social-scraper worker for consistent IP/session
    "collect_social_for_league": {"queue": "social-scraper", "routing_key": "social-scraper"},
    "collect_team_social": {"queue": "social-scraper", "routing_key": "social-scraper"},
    "map_social_to_games": {"queue": "social-scraper", "routing_key": "social-scraper"},
    # Game-state-machine polling tasks
    "update_game_states": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    "poll_live_pbp": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    "poll_active_odds": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    "trigger_flow_for_game": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    "run_daily_sweep": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    # Final-whistle social scrape runs on social-scraper queue (concurrency=1)
    "run_final_whistle_social": {"queue": "social-scraper", "routing_key": "social-scraper"},
}
# Daily sports ingestion at 5:00 AM US Eastern (10:00 UTC during EST, 09:00 UTC during EDT)
# Using 10:00 UTC to align with 5:00 AM during Eastern Standard Time (November-March).
# During Eastern Daylight Time (March-November), this will run at 6:00 AM EDT.
#
# Ingestion runs leagues sequentially: NBA -> NHL -> NCAAB
#
# Flow generation runs 90 minutes after ingestion to allow scraping to complete.
# Each league runs in sequence, 15 minutes apart:
#   6:30 AM EST - NBA flow generation
#   6:45 AM EST - NHL flow generation
#   7:00 AM EST - NCAAB flow generation (capped at 10 games per run)
# Each generates AI flows for games in the last 72 hours. Skips existing flows.
#
# Odds sync runs every 30 minutes to keep FairBet data fresh for all 3 leagues.
# Always-on tasks (safe in all environments — pure DB, no external APIs)
_always_on_schedule = {
    "game-state-updater-every-3-min": {
        "task": "update_game_states",
        "schedule": crontab(minute="*/3"),
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
}

# Production-only tasks (external APIs, cost, rate limits)
_prod_only_schedule = {
    "daily-sports-ingestion-5am-eastern": {
        "task": "run_scheduled_ingestion",
        "schedule": crontab(minute=0, hour=10),  # 5:00 AM EST = 10:00 UTC
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "daily-nba-flow-generation-630am-eastern": {
        "task": "run_scheduled_nba_flow_generation",
        "schedule": crontab(minute=30, hour=11),  # 6:30 AM EST = 11:30 UTC (90 min after ingestion)
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "daily-nhl-flow-generation-645am-eastern": {
        "task": "run_scheduled_nhl_flow_generation",
        "schedule": crontab(minute=45, hour=11),  # 6:45 AM EST = 11:45 UTC (15 min after NBA flow)
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "daily-ncaab-flow-generation-7am-eastern": {
        "task": "run_scheduled_ncaab_flow_generation",
        "schedule": crontab(minute=0, hour=12),  # 7:00 AM EST = 12:00 UTC (15 min after NHL flow)
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "odds-sync-every-30-minutes": {
        "task": "run_scheduled_odds_sync",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "live-pbp-poll-every-5-min": {
        "task": "poll_live_pbp",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "active-odds-poll-every-30-min": {
        "task": "poll_active_odds",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    # === Daily sweep (truth repair + social scrape #2) ===
    "daily-sweep-5am-eastern": {
        "task": "run_daily_sweep",
        "schedule": crontab(minute=0, hour=10),  # 5:00 AM EST = 10:00 UTC
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
}

if settings.environment == "production":
    app.conf.beat_schedule = {**_always_on_schedule, **_prod_only_schedule}
    logger.info(
        "beat_schedule_production",
        task_count=len(_always_on_schedule) + len(_prod_only_schedule),
    )
else:
    app.conf.beat_schedule = _always_on_schedule
    logger.info(
        "beat_schedule_non_production",
        environment=settings.environment,
        task_count=len(_always_on_schedule),
    )


def mark_stale_runs_interrupted():
    """
    Mark any runs that are stuck in 'running' status as 'interrupted'.
    
    This handles cases where the Docker container was killed or the worker
    crashed, leaving runs in a 'running' state that will never complete.
    """
    try:
        with get_session() as session:
            # Find runs that have been running for more than 1 hour
            # (reasonable threshold - if a run is truly running, it should complete or fail)
            stale_threshold = now_utc() - timedelta(hours=1)
            
            stale_runs = session.query(db_models.SportsScrapeRun).filter(
                db_models.SportsScrapeRun.status == "running",
                db_models.SportsScrapeRun.started_at.isnot(None),
                db_models.SportsScrapeRun.started_at < stale_threshold,
            ).all()
            
            if stale_runs:
                for run in stale_runs:
                    run.status = "interrupted"
                    run.finished_at = now_utc()
                    run.error_details = "Run was interrupted (worker shutdown or container killed)"
                    logger.warning(
                        "marking_stale_run_interrupted",
                        run_id=run.id,
                        started_at=str(run.started_at),
                        hours_running=(now_utc() - run.started_at).total_seconds() / 3600,
                    )
                
                session.commit()
                logger.info("stale_runs_marked_interrupted", count=len(stale_runs))
            else:
                logger.debug("no_stale_runs_found")
    except Exception as exc:
        logger.exception("failed_to_mark_stale_runs", error=str(exc))


@signals.worker_ready.connect
def on_worker_ready(sender=None, **kwargs):
    """Called when Celery worker is ready. Mark any stale runs as interrupted."""
    # sender is the worker Consumer object with .hostname attribute
    worker_name = getattr(sender, "hostname", None) or str(sender) if sender else "unknown"
    logger.info("celery_worker_ready", worker=worker_name)
    mark_stale_runs_interrupted()


@signals.worker_shutting_down.connect
def on_worker_shutting_down(sender=None, **kwargs):
    """Called when Celery worker is shutting down. Mark currently running tasks as interrupted."""
    # sender for this signal is a string (the worker hostname), not an object
    worker_name = str(sender) if sender else "unknown"
    logger.info("celery_worker_shutting_down", worker=worker_name)
    try:
        with get_session() as session:
            # Mark any runs that are currently running as interrupted
            running_runs = session.query(db_models.SportsScrapeRun).filter(
                db_models.SportsScrapeRun.status == "running",
            ).all()
            
            if running_runs:
                for run in running_runs:
                    run.status = "interrupted"
                    run.finished_at = now_utc()
                    run.error_details = "Run was interrupted (worker shutdown)"
                    logger.warning(
                        "marking_run_interrupted_on_shutdown",
                        run_id=run.id,
                        started_at=str(run.started_at),
                    )
                
                session.commit()
                logger.info("runs_marked_interrupted_on_shutdown", count=len(running_runs))
    except Exception as exc:
        logger.exception("failed_to_mark_runs_on_shutdown", error=str(exc))
