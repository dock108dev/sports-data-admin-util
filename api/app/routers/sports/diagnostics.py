"""Diagnostics endpoints for conflicts and missing data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select

from ... import db_models
from ...db import AsyncSession, get_db
from .schemas import GameConflictEntry, MissingPbpEntry

router = APIRouter(prefix="/diagnostics")


@router.get("/missing-pbp", response_model=list[MissingPbpEntry])
async def list_missing_pbp(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    league: str | None = Query(None),
) -> list[MissingPbpEntry]:
    stmt = (
        select(db_models.SportsMissingPbp, db_models.SportsLeague.code)
        .join(db_models.SportsLeague, db_models.SportsMissingPbp.league_id == db_models.SportsLeague.id)
        .order_by(desc(db_models.SportsMissingPbp.updated_at))
        .limit(limit)
    )
    if league:
        stmt = stmt.where(db_models.SportsLeague.code == league.upper())
    results = await session.execute(stmt)
    rows = results.all()
    return [
        MissingPbpEntry(
            game_id=record.game_id,
            league_code=league_code,
            status=record.status,
            reason=record.reason,
            detected_at=record.detected_at,
            updated_at=record.updated_at,
        )
        for record, league_code in rows
    ]


@router.get("/conflicts", response_model=list[GameConflictEntry])
async def list_game_conflicts(
    session: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    league: str | None = Query(None),
) -> list[GameConflictEntry]:
    stmt = (
        select(db_models.SportsGameConflict, db_models.SportsLeague.code)
        .join(db_models.SportsLeague, db_models.SportsGameConflict.league_id == db_models.SportsLeague.id)
        .order_by(desc(db_models.SportsGameConflict.created_at))
        .limit(limit)
    )
    if league:
        stmt = stmt.where(db_models.SportsLeague.code == league.upper())
    results = await session.execute(stmt)
    rows = results.all()
    return [
        GameConflictEntry(
            league_code=league_code,
            game_id=record.game_id,
            conflict_game_id=record.conflict_game_id,
            external_id=record.external_id,
            source=record.source,
            conflict_fields=dict(record.conflict_fields or {}),
            created_at=record.created_at,
            resolved_at=record.resolved_at,
        )
        for record, league_code in rows
    ]
