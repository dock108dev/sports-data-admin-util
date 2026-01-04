"""API endpoints for tracking last-read game positions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .. import db_models
from ..db import AsyncSession, get_db

router = APIRouter(tags=["reading-position"])


class ReadingPositionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    moment: int = Field(..., ge=0)
    timestamp: float = Field(..., ge=0)
    scroll_hint: str | None = Field(None, alias="scrollHint")


class ReadingPositionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(..., alias="userId")
    game_id: int = Field(..., alias="gameId")
    moment: int = Field(..., ge=0)
    timestamp: float = Field(..., ge=0)
    scroll_hint: str | None = Field(None, alias="scrollHint")


@router.post(
    "/users/{user_id}/games/{game_id}/reading-position",
    response_model=ReadingPositionResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_reading_position(
    user_id: str,
    game_id: int,
    payload: ReadingPositionRequest,
    session: AsyncSession = Depends(get_db),
) -> ReadingPositionResponse:
    """Create or update a user's last-read position for a game."""
    stmt = select(db_models.GameReadingPosition).where(
        db_models.GameReadingPosition.user_id == user_id,
        db_models.GameReadingPosition.game_id == game_id,
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        record = db_models.GameReadingPosition(
            user_id=user_id,
            game_id=game_id,
            moment=payload.moment,
            timestamp=payload.timestamp,
            scroll_hint=payload.scroll_hint,
        )
        session.add(record)
    else:
        record.moment = payload.moment
        record.timestamp = payload.timestamp
        record.scroll_hint = payload.scroll_hint

    await session.flush()

    return ReadingPositionResponse(
        userId=record.user_id,
        gameId=record.game_id,
        moment=record.moment,
        timestamp=record.timestamp,
        scrollHint=record.scroll_hint,
    )


@router.get(
    "/users/{user_id}/games/{game_id}/resume",
    response_model=ReadingPositionResponse,
)
async def get_reading_position(
    user_id: str,
    game_id: int,
    session: AsyncSession = Depends(get_db),
) -> ReadingPositionResponse:
    """Return the last-read position for a user/game pair."""
    stmt = select(db_models.GameReadingPosition).where(
        db_models.GameReadingPosition.user_id == user_id,
        db_models.GameReadingPosition.game_id == game_id,
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading position not found.")

    return ReadingPositionResponse(
        userId=record.user_id,
        gameId=record.game_id,
        moment=record.moment,
        timestamp=record.timestamp,
        scrollHint=record.scroll_hint,
    )
