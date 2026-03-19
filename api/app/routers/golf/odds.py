"""Golf odds endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.golf import GolfTournamentOdds

from . import router


@router.get("/odds/outrights")
async def get_outright_odds(
    tournament_id: int | None = Query(None, description="Filter by tournament ID"),
    market: str | None = Query(None, description="Filter by market (e.g. win, top_5)"),
    book: str | None = Query(None, description="Filter by sportsbook"),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current outright odds for golf tournaments."""
    stmt = select(GolfTournamentOdds).order_by(
        GolfTournamentOdds.odds.asc()
    ).limit(limit)

    if tournament_id is not None:
        stmt = stmt.where(GolfTournamentOdds.tournament_id == tournament_id)
    if market:
        stmt = stmt.where(GolfTournamentOdds.market == market)
    if book:
        stmt = stmt.where(GolfTournamentOdds.book == book)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "odds": [
            {
                "id": o.id,
                "tournament_id": o.tournament_id,
                "dg_id": o.dg_id,
                "player_name": o.player_name,
                "book": o.book,
                "market": o.market,
                "odds": o.odds,
                "implied_prob": o.implied_prob,
                "dg_prob": o.dg_prob,
                "observed_at": o.observed_at.isoformat() if o.observed_at else None,
            }
            for o in rows
        ],
        "count": len(rows),
    }


@router.get("/odds/matchups")
async def get_matchup_odds() -> dict[str, Any]:
    """Get matchup odds (placeholder)."""
    return {"matchups": [], "count": 0}
