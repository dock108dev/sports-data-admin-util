"""Backfill endpoints for pipeline management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ....db import AsyncSession, get_db
from .models import BackfillEmbeddedTweetsResponse

router = APIRouter()


@router.post(
    "/pipeline/backfill-embedded-tweets",
    response_model=BackfillEmbeddedTweetsResponse,
    summary="Backfill embedded tweets",
    description="Retroactively attach embedded tweets to flows that have all-NULL embedded_social_post_id.",
)
async def backfill_embedded_tweets(
    game_id: int | None = Query(default=None, description="Single game ID to backfill"),
    lookback_days: int = Query(default=7, ge=1, le=30, description="Days to look back for bulk scan"),
    session: AsyncSession = Depends(get_db),
) -> BackfillEmbeddedTweetsResponse:
    """Backfill embedded tweets for flows missing social data.

    If game_id is provided, backfills only that game.
    Otherwise, scans all flows from the last lookback_days.
    """
    from ....services.pipeline.backfill_embedded_tweets import (
        backfill_embedded_tweets_for_game,
        find_and_backfill_all,
    )

    try:
        if game_id is not None:
            result = await backfill_embedded_tweets_for_game(session, game_id)
            await session.commit()
            backfilled = 1 if result.get("status") == "backfilled" else 0
            return BackfillEmbeddedTweetsResponse(
                total_checked=1,
                total_backfilled=backfilled,
                results=[result],
                message=f"Game {game_id}: {result.get('status')}",
            )
        else:
            bulk_result = await find_and_backfill_all(session, lookback_days)
            await session.commit()
            return BackfillEmbeddedTweetsResponse(
                total_checked=bulk_result["total_checked"],
                total_backfilled=bulk_result["total_backfilled"],
                results=bulk_result["results"],
                message=(
                    f"Checked {bulk_result['total_checked']} flows, "
                    f"backfilled {bulk_result['total_backfilled']}"
                ),
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backfill failed: {e}",
        )
