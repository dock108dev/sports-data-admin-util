"""Golf DFS projection endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.golf import GolfDFSProjection

from . import router


@router.get("/dfs/projections")
async def get_dfs_projections(
    tournament_id: int | None = Query(None, description="Filter by tournament ID"),
    site: str | None = Query(None, description="Filter by DFS site (dk, fd)"),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current DFS projections for a golf tournament."""
    stmt = select(GolfDFSProjection).order_by(
        GolfDFSProjection.projected_points.desc()
    ).limit(limit)

    if tournament_id is not None:
        stmt = stmt.where(GolfDFSProjection.tournament_id == tournament_id)
    if site:
        stmt = stmt.where(GolfDFSProjection.site == site)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "projections": [
            {
                "id": p.id,
                "tournament_id": p.tournament_id,
                "dg_id": p.dg_id,
                "player_name": p.player_name,
                "site": p.site,
                "salary": p.salary,
                "projected_points": p.projected_points,
                "projected_ownership": p.projected_ownership,
            }
            for p in rows
        ],
        "count": len(rows),
    }
