"""Celery app configuration for sports scraper."""

from __future__ import annotations

from datetime import timedelta

from .utils.datetime_utils import now_utc

from celery import Celery, signals
from celery.schedules import crontab

from .config import settings
from .db import db_models, get_session
from .logging import logger

# Canonical queue names — import these instead of using string literals
DEFAULT_QUEUE = "sports-scraper"
SOCIAL_QUEUE = "social-scraper"

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
    "task_default_queue": DEFAULT_QUEUE,
    "task_routes": {
        "run_scrape_job": {"queue": DEFAULT_QUEUE},
        # Social tasks route to dedicated social-scraper worker
        "collect_social_for_league": {"queue": SOCIAL_QUEUE},
        "collect_team_social": {"queue": SOCIAL_QUEUE},
        "map_social_to_games": {"queue": SOCIAL_QUEUE},
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
    "run_scrape_job": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    # Social tasks route to dedicated social-scraper worker for consistent IP/session
    "collect_social_for_league": {"queue": SOCIAL_QUEUE, "routing_key": SOCIAL_QUEUE},
    "collect_team_social": {"queue": SOCIAL_QUEUE, "routing_key": SOCIAL_QUEUE},
    "map_social_to_games": {"queue": SOCIAL_QUEUE, "routing_key": SOCIAL_QUEUE},
    # Social error callback runs on main scraper queue (DB writes only)
    "handle_social_task_failure": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    # Game-state-machine polling tasks
    "update_game_states": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "poll_live_pbp": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "poll_active_odds": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "trigger_flow_for_game": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    "run_daily_sweep": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    # Final-whistle social scrape runs on social-scraper queue (concurrency=1)
    "run_final_whistle_social": {"queue": SOCIAL_QUEUE, "routing_key": SOCIAL_QUEUE},
}
# Daily pipeline schedule (all times US Eastern / UTC during EST):
#
#   3:30 AM EST (08:30 UTC) — Sports ingestion (NBA → NHL → NCAAB sequentially)
#   4:00 AM EST (09:00 UTC) — Daily sweep (truth repair, backfill missing data)
#   4:30 AM EST (09:30 UTC) — NBA flow generation
#   5:00 AM EST (10:00 UTC) — NHL flow generation
#   5:30 AM EST (10:30 UTC) — NCAAB flow generation (capped at 10 games)
#
# Each job is spaced 30 minutes apart. During EDT (March-November) all times
# shift 1 hour later (e.g., ingestion at 4:30 AM EDT).
#
# Odds sync runs every 30 minutes to keep FairBet data fresh for all 3 leagues.
# Always-on tasks (safe in all environments — pure DB, no external APIs)
_always_on_schedule = {
    "game-state-updater-every-3-min": {
        "task": "update_game_states",
        "schedule": crontab(minute="*/3"),
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
}

# Production-only tasks (external APIs, cost, rate limits)
_prod_only_schedule = {
    "daily-sports-ingestion-330am-eastern": {
        "task": "run_scheduled_ingestion",
        "schedule": crontab(minute=30, hour=8),  # 3:30 AM EST = 08:30 UTC
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    "daily-nba-flow-generation-430am-eastern": {
        "task": "run_scheduled_nba_flow_generation",
        "schedule": crontab(minute=30, hour=9),  # 4:30 AM EST = 09:30 UTC (+30 min after sweep)
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    "daily-nhl-flow-generation-5am-eastern": {
        "task": "run_scheduled_nhl_flow_generation",
        "schedule": crontab(minute=0, hour=10),  # 5:00 AM EST = 10:00 UTC (+30 min after NBA flow)
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    "daily-ncaab-flow-generation-530am-eastern": {
        "task": "run_scheduled_ncaab_flow_generation",
        "schedule": crontab(minute=30, hour=10),  # 5:30 AM EST = 10:30 UTC (+30 min after NHL flow)
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    "odds-sync-every-30-minutes": {
        "task": "run_scheduled_odds_sync",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    "live-pbp-poll-every-5-min": {
        "task": "poll_live_pbp",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    "active-odds-poll-every-30-min": {
        "task": "poll_active_odds",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
    },
    # === Daily sweep (truth repair + social scrape #2) ===
    # Runs 30 min after ingestion to catch any gaps
    "daily-sweep-4am-eastern": {
        "task": "run_daily_sweep",
        "schedule": crontab(minute=0, hour=9),  # 4:00 AM EST = 09:00 UTC (+30 min after ingestion)
        "options": {"queue": DEFAULT_QUEUE, "routing_key": DEFAULT_QUEUE},
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
