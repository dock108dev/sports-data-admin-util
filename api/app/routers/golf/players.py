"""Golf player endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.golf import GolfPlayer, GolfPlayerStats

from . import router


@router.get("/players")
async def search_players(
    q: str | None = Query(None, description="Name search query"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Search golf players by name."""
    stmt = select(GolfPlayer).order_by(GolfPlayer.player_name).limit(limit)

    if q:
        stmt = stmt.where(GolfPlayer.player_name.ilike(f"%{q}%"))

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "players": [
            {
                "id": p.id,
                "dg_id": p.dg_id,
                "player_name": p.player_name,
                "country": p.country,
                "country_code": p.country_code,
                "amateur": p.amateur,
            }
            for p in rows
        ],
        "count": len(rows),
    }


@router.get("/players/{dg_id}")
async def get_player(
    dg_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a golf player profile by DataGolf ID."""
    stmt = select(GolfPlayer).where(GolfPlayer.dg_id == dg_id)
    result = await db.execute(stmt)
    p = result.scalar_one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "id": p.id,
        "dg_id": p.dg_id,
        "player_name": p.player_name,
        "country": p.country,
        "country_code": p.country_code,
        "amateur": p.amateur,
        "dk_id": p.dk_id,
        "fd_id": p.fd_id,
        "yahoo_id": p.yahoo_id,
    }


@router.get("/players/{dg_id}/stats")
async def get_player_stats(
    dg_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get stats for a golf player by DataGolf ID."""
    stmt = select(GolfPlayerStats).where(GolfPlayerStats.dg_id == dg_id)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Player stats not found")
    return {
        "dg_id": dg_id,
        "stats": [
            {
                "period": s.period,
                "sg_total": s.sg_total,
                "sg_ott": s.sg_ott,
                "sg_app": s.sg_app,
                "sg_arg": s.sg_arg,
                "sg_putt": s.sg_putt,
                "driving_dist": s.driving_dist,
                "driving_acc": s.driving_acc,
                "dg_rank": s.dg_rank,
                "owgr": s.owgr,
                "sample_size": s.sample_size,
            }
            for s in rows
        ],
    }
