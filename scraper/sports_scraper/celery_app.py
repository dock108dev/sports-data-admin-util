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
}
# Daily sports ingestion at 4 AM US Eastern (9:00 UTC during EST, 8:00 UTC during EDT)
# Using 9:00 UTC to align with 4 AM during Eastern Standard Time (November-March).
# During Eastern Daylight Time (March-November), this will run at 5 AM EDT.
#
# Ingestion runs leagues sequentially: NBA -> NHL (15 min later) -> NCAAB (15 min later)
#
# Timeline generation runs 90 minutes after ingestion to allow scraping to complete.
# It processes:
# - Games missing timelines (newly completed games with PBP data)
# - Games needing regeneration (PBP or social updated after timeline was generated)
#
# Story generation runs 15 minutes after timeline generation to allow timelines to complete.
# It generates AI stories for all games in the last 3 days that have PBP data.
app.conf.beat_schedule = {
    "daily-sports-ingestion-4am-eastern": {
        "task": "run_scheduled_ingestion",
        "schedule": crontab(minute=0, hour=9),  # 4 AM EST = 9:00 UTC
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "daily-timeline-generation-530am-eastern": {
        "task": "run_scheduled_timeline_generation",
        "schedule": crontab(minute=30, hour=10),  # 5:30 AM EST = 10:30 UTC (90 min after ingestion)
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
    "daily-story-generation-545am-eastern": {
        "task": "run_scheduled_story_generation",
        "schedule": crontab(minute=45, hour=10),  # 5:45 AM EST = 10:45 UTC (15 min after timeline gen)
        "options": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    },
}


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
