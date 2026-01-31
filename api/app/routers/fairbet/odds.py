"""FairBet odds comparison endpoints.

Provides bet-centric odds views for cross-book comparison.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ... import db_models
from ...db import AsyncSession, get_db

router = APIRouter()


class BookOdds(BaseModel):
    """Odds from a single book for a bet."""

    book: str
    price: float
    observed_at: datetime


class BetDefinition(BaseModel):
    """A unique bet definition with odds from all books."""

    game_id: int
    league_code: str
    home_team: str
    away_team: str
    game_date: datetime
    market_key: str
    selection_key: str
    line_value: float
    books: list[BookOdds]


class FairbetOddsResponse(BaseModel):
    """Response containing all bets with cross-book odds."""

    bets: list[BetDefinition]
    total: int
    books_available: list[str]


@router.get("/odds", response_model=FairbetOddsResponse)
async def get_fairbet_odds(
    session: AsyncSession = Depends(get_db),
    league: str | None = Query(None, description="Filter by league code (NBA, NHL, etc.)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FairbetOddsResponse:
    """Get bet-centric odds for cross-book comparison.

    Returns bets grouped by definition (game + market + selection + line),
    with all available book prices for each bet.

    Only includes non-final games (scheduled, live).
    """
    # Query the fairbet work table with game info
    stmt = (
        select(db_models.FairbetGameOddsWork)
        .join(db_models.SportsGame)
        .options(
            selectinload(db_models.FairbetGameOddsWork.game).selectinload(
                db_models.SportsGame.league
            ),
            selectinload(db_models.FairbetGameOddsWork.game).selectinload(
                db_models.SportsGame.home_team
            ),
            selectinload(db_models.FairbetGameOddsWork.game).selectinload(
                db_models.SportsGame.away_team
            ),
        )
        .where(db_models.SportsGame.status.notin_(["final", "completed"]))
    )

    if league:
        stmt = stmt.where(db_models.SportsGame.league.has(code=league.upper()))

    stmt = stmt.order_by(
        db_models.FairbetGameOddsWork.game_id,
        db_models.FairbetGameOddsWork.market_key,
        db_models.FairbetGameOddsWork.selection_key,
        db_models.FairbetGameOddsWork.line_value,
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()

    # Group by bet definition
    bets_map: dict[tuple, dict[str, Any]] = {}
    all_books: set[str] = set()

    for row in rows:
        game = row.game
        key = (row.game_id, row.market_key, row.selection_key, row.line_value)

        if key not in bets_map:
            bets_map[key] = {
                "game_id": row.game_id,
                "league_code": game.league.code if game.league else "UNKNOWN",
                "home_team": game.home_team.name if game.home_team else "Unknown",
                "away_team": game.away_team.name if game.away_team else "Unknown",
                "game_date": game.start_time,
                "market_key": row.market_key,
                "selection_key": row.selection_key,
                "line_value": row.line_value,
                "books": [],
            }

        bets_map[key]["books"].append(
            BookOdds(
                book=row.book,
                price=row.price,
                observed_at=row.observed_at,
            )
        )
        all_books.add(row.book)

    # Convert to list and apply pagination
    all_bets = list(bets_map.values())
    total = len(all_bets)
    paginated_bets = all_bets[offset : offset + limit]

    # Sort books within each bet by price (best odds first for positive, worst for negative)
    for bet in paginated_bets:
        bet["books"].sort(key=lambda b: -b.price if b.price > 0 else b.price)

    return FairbetOddsResponse(
        bets=[BetDefinition(**bet) for bet in paginated_bets],
        total=total,
        books_available=sorted(all_books),
    )
