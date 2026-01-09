"""Celery tasks for triggering scrape runs."""

from __future__ import annotations

from celery import shared_task

from ..logging import logger
from ..services.ingestion import run_ingestion
from ..services.scheduler import schedule_ingestion_runs


@shared_task(name="run_scrape_job")
def run_scrape_job(run_id: int, config_payload: dict) -> dict:
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
    """Trigger the scheduled ingestion pipeline (manual debug entry point)."""
    summary = schedule_ingestion_runs()
    return {
        "runs_created": summary.runs_created,
        "runs_skipped": summary.runs_skipped,
        "run_failures": summary.run_failures,
        "enqueue_failures": summary.enqueue_failures,
        "last_run_at": summary.last_run_at.isoformat(),
    }
