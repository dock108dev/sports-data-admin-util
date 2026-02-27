"""Helpers for recording phase-level job runs."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
from typing import Any, Generator

from app.utils.datetime_utils import now_utc as _now_utc

from ..db import db_models, get_session
from ..logging import logger


def start_job_run(
    phase: str,
    leagues: Iterable[str],
    celery_task_id: str | None = None,
) -> int:
    """Create a job run record and return its ID."""
    leagues_list = [league.upper() for league in leagues]
    with get_session() as session:
        run = db_models.SportsJobRun(
            phase=phase,
            leagues=leagues_list,
            status="running",
            started_at=_now_utc(),
            celery_task_id=celery_task_id,
        )
        session.add(run)
        session.flush()
        run_id = int(run.id)
        logger.info("job_run_started", run_id=run_id, phase=phase, leagues=leagues_list)
        return run_id


def complete_job_run(
    run_id: int,
    status: str,
    error_summary: str | None = None,
    summary_data: dict[str, Any] | None = None,
) -> None:
    """Finalize a job run record with status + duration."""
    with get_session() as session:
        run = session.get(db_models.SportsJobRun, run_id)
        if not run:
            logger.error("job_run_missing", run_id=run_id)
            return
        finished_at = _now_utc()
        run.status = status
        run.finished_at = finished_at
        run.duration_seconds = (finished_at - run.started_at).total_seconds()
        run.error_summary = error_summary
        if summary_data is not None:
            run.summary_data = summary_data
        session.flush()
        logger.info("job_run_completed", run_id=run_id, phase=run.phase, status=status)


class JobRunTracker:
    """Mutable tracker for accumulating summary data during a job run."""

    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        self.summary_data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        """Set a summary data key."""
        self.summary_data[key] = value

    def increment(self, key: str, amount: int = 1) -> None:
        """Increment a numeric summary data key."""
        self.summary_data[key] = self.summary_data.get(key, 0) + amount


def _get_current_celery_task_id() -> str | None:
    """Return the current Celery task ID if running inside a Celery worker."""
    try:
        from celery import current_task

        if current_task and current_task.request and current_task.request.id:
            return str(current_task.request.id)
    except Exception:
        pass
    return None


@contextmanager
def track_job_run(
    phase: str,
    leagues: Iterable[str] = (),
) -> Generator[JobRunTracker, None, None]:
    """Context manager that creates a job run on enter and finalizes on exit.

    Usage:
        with track_job_run("poll_live_pbp", ["NBA", "NHL"]) as tracker:
            # ... do work ...
            tracker.set("games_polled", 5)
            tracker.set("api_calls", 12)

    On normal exit: status="success", summary_data from tracker.
    On exception: status="error", error_summary from exception.
    """
    celery_task_id = _get_current_celery_task_id()
    run_id = start_job_run(phase, leagues, celery_task_id=celery_task_id)
    tracker = JobRunTracker(run_id)

    try:
        yield tracker
    except Exception as exc:
        complete_job_run(
            run_id,
            status="error",
            error_summary=str(exc)[:500],
            summary_data=tracker.summary_data or None,
        )
        raise
    else:
        complete_job_run(
            run_id,
            status="success",
            summary_data=tracker.summary_data or None,
        )
