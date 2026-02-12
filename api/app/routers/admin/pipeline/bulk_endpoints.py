"""Bulk generation endpoints for pipeline management."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ....db import AsyncSession, get_db
from ....db.pipeline import BulkStoryGenerationJob

from .models import (
    BulkGenerateAsyncResponse,
    BulkGenerateRequest,
    BulkGenerateStatusResponse,
)

router = APIRouter()


@router.post(
    "/pipeline/bulk-generate-async",
    response_model=BulkGenerateAsyncResponse,
    summary="Start bulk game flow generation",
    description="Start an async job to generate game flows for multiple games.",
)
async def bulk_generate_async(
    request: BulkGenerateRequest,
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateAsyncResponse:
    """Start bulk game flow generation as a Celery background job.

    Job state is persisted in the database for consistency across workers.
    The job runs in the api-worker container and survives restarts.
    """
    from ....celery_app import celery_app

    # Parse date strings to datetime
    start_dt = datetime.strptime(request.start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(request.end_date, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59
    )

    # Create job record in database
    job = BulkStoryGenerationJob(
        status="pending",
        start_date=start_dt,
        end_date=end_dt,
        leagues=request.leagues,
        force_regenerate=request.force,
        max_games=request.max_games,
        triggered_by="admin",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    job_uuid = str(job.job_uuid)

    # Send task to Celery worker
    celery_app.send_task("run_bulk_story_generation", args=[job.id])

    return BulkGenerateAsyncResponse(
        job_id=job_uuid,
        message="Bulk game flow generation job started",
        status_url=f"/api/admin/sports/pipeline/bulk-generate-status/{job_uuid}",
    )


@router.get(
    "/pipeline/bulk-generate-status/{job_id}",
    response_model=BulkGenerateStatusResponse,
    summary="Get bulk generation status",
    description="Get the status of a bulk generation job.",
)
async def get_bulk_generate_status(
    job_id: str,
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateStatusResponse:
    """Get the status of a bulk generation job from the database."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job ID format: {job_id}",
        )

    result = await session.execute(
        select(BulkStoryGenerationJob).where(
            BulkStoryGenerationJob.job_uuid == job_uuid
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    # Map DB status to state for API response
    state_map = {
        "pending": "PENDING",
        "running": "PROGRESS",
        "completed": "SUCCESS",
        "failed": "FAILURE",
    }

    # Build result dict if job is complete
    result_dict = None
    if job.status in ("completed", "failed"):
        result_dict = {
            "total": job.total_games,
            "successful": job.successful,
            "failed": job.failed,
            "skipped": job.skipped,
            "errors": job.errors_json or [],
        }

    return BulkGenerateStatusResponse(
        job_id=str(job.job_uuid),
        state=state_map.get(job.status, "PENDING"),
        current=job.current_game,
        total=job.total_games,
        successful=job.successful,
        failed=job.failed,
        skipped=job.skipped,
        result=result_dict,
    )
