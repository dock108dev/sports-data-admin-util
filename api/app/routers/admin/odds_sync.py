"""Admin endpoint for on-demand odds synchronization."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ...celery_client import get_celery_app

router = APIRouter()


class OddsSyncResponse(BaseModel):
    status: str
    league: str
    task_id: str


@router.post("/odds/sync", response_model=OddsSyncResponse)
async def trigger_odds_sync(
    league: str | None = Query(None, description="League code (e.g. NBA). Omit for all leagues."),
) -> OddsSyncResponse:
    """Dispatch the unified ``sync_all_odds`` Celery task.

    Accepts an optional league filter so the UI can sync a single league
    on-demand without touching the others.
    """
    celery = get_celery_app()
    result = celery.send_task(
        "sync_all_odds",
        args=[league],
        queue="sports-scraper",
        routing_key="sports-scraper",
    )
    return OddsSyncResponse(
        status="dispatched",
        league=league or "all",
        task_id=result.id,
    )
