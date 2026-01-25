"""Helpers for recording phase-level job runs."""

from __future__ import annotations

from app.utils.datetime_utils import now_utc as _now_utc
from typing import Iterable

from ..db import db_models, get_session
from ..logging import logger


def start_job_run(phase: str, leagues: Iterable[str]) -> int:
    """Create a job run record and return its ID."""
    leagues_list = [league.upper() for league in leagues]
    with get_session() as session:
        run = db_models.SportsJobRun(
            phase=phase,
            leagues=leagues_list,
            status="running",
            started_at=_now_utc(),
        )
        session.add(run)
        session.flush()
        run_id = int(run.id)
        logger.info("job_run_started", run_id=run_id, phase=phase, leagues=leagues_list)
        return run_id


def complete_job_run(run_id: int, status: str, error_summary: str | None = None) -> None:
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
        session.flush()
        logger.info("job_run_completed", run_id=run_id, phase=run.phase, status=status)
