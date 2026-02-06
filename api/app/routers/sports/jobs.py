"""Job run monitoring endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from ...db.scraper import SportsJobRun
from ...db import AsyncSession, get_db
from .schemas import JobRunResponse

router = APIRouter()


@router.get("/jobs", response_model=list[JobRunResponse])
async def list_job_runs(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    phase: str | None = Query(None),
) -> list[JobRunResponse]:
    stmt = select(SportsJobRun)
    if phase:
        stmt = stmt.where(SportsJobRun.phase == phase)
    stmt = stmt.order_by(desc(SportsJobRun.started_at)).limit(limit)
    results = await session.execute(stmt)
    runs = results.scalars().all()
    return [
        JobRunResponse(
            id=run.id,
            phase=run.phase,
            leagues=list(run.leagues or []),
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            duration_seconds=run.duration_seconds,
            error_summary=run.error_summary,
            created_at=run.created_at,
        )
        for run in runs
    ]
