"""FairBet odds comparison endpoints.

Provides bet-centric odds views for cross-book comparison.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, select
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


def _build_base_filters(
    league: str | None,
) -> tuple:
    """Build common filter conditions for FairBet queries.

    Returns (game_start_expr, filter_conditions) tuple.
    """
    now = datetime.now(timezone.utc)
    live_cutoff = now - timedelta(hours=4)

    # Use COALESCE to get actual start time (tip_time preferred, else game_date)
    game_start = func.coalesce(
        db_models.SportsGame.tip_time,
        db_models.SportsGame.game_date,
    )

    conditions = [
        db_models.SportsGame.status.notin_(["final", "completed"]),
        game_start > live_cutoff,
    ]

    if league:
        conditions.append(db_models.SportsGame.league.has(code=league.upper()))

    return game_start, conditions


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

    Only includes upcoming games (start_time in future or within last 4 hours for live games).

    Uses database-level pagination for efficiency.
    """
    _, conditions = _build_base_filters(league)

    # Step 1: Count total distinct bet definitions (for pagination metadata)
    count_subq = (
        select(
            db_models.FairbetGameOddsWork.game_id,
            db_models.FairbetGameOddsWork.market_key,
            db_models.FairbetGameOddsWork.selection_key,
            db_models.FairbetGameOddsWork.line_value,
        )
        .distinct()
        .join(db_models.SportsGame)
        .where(*conditions)
        .subquery()
    )
    count_stmt = select(func.count()).select_from(count_subq)
    total = (await session.execute(count_stmt)).scalar() or 0

    if total == 0:
        return FairbetOddsResponse(bets=[], total=0, books_available=[])

    # Step 2: Get paginated bet definitions using CTE
    # This applies LIMIT/OFFSET at the database level
    paginated_bets_cte = (
        select(
            db_models.FairbetGameOddsWork.game_id,
            db_models.FairbetGameOddsWork.market_key,
            db_models.FairbetGameOddsWork.selection_key,
            db_models.FairbetGameOddsWork.line_value,
        )
        .distinct()
        .join(db_models.SportsGame)
        .where(*conditions)
        .order_by(
            db_models.FairbetGameOddsWork.game_id,
            db_models.FairbetGameOddsWork.market_key,
            db_models.FairbetGameOddsWork.selection_key,
            db_models.FairbetGameOddsWork.line_value,
        )
        .limit(limit)
        .offset(offset)
    ).cte("paginated_bets")

    # Step 3: Join CTE back to get all books for paginated bet definitions only
    stmt = (
        select(db_models.FairbetGameOddsWork)
        .join(
            paginated_bets_cte,
            and_(
                db_models.FairbetGameOddsWork.game_id == paginated_bets_cte.c.game_id,
                db_models.FairbetGameOddsWork.market_key == paginated_bets_cte.c.market_key,
                db_models.FairbetGameOddsWork.selection_key == paginated_bets_cte.c.selection_key,
                db_models.FairbetGameOddsWork.line_value == paginated_bets_cte.c.line_value,
            ),
        )
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
        .order_by(
            db_models.FairbetGameOddsWork.game_id,
            db_models.FairbetGameOddsWork.market_key,
            db_models.FairbetGameOddsWork.selection_key,
            db_models.FairbetGameOddsWork.line_value,
        )
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()

    # Step 4: Get available books (all books across filtered games, not just paginated)
    books_stmt = (
        select(distinct(db_models.FairbetGameOddsWork.book))
        .join(db_models.SportsGame)
        .where(*conditions)
    )
    books_result = await session.execute(books_stmt)
    all_books = sorted([row[0] for row in books_result.all()])

    # Step 5: Group rows by bet definition (only paginated rows now)
    bets_map: dict[tuple, dict[str, Any]] = {}

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

    # Sort books within each bet by price (best odds first)
    # For American odds, higher values are always better: +150 > +120, -105 > -110
    for bet in bets_map.values():
        bet["books"].sort(key=lambda b: -b.price)

    return FairbetOddsResponse(
        bets=[BetDefinition(**bet) for bet in bets_map.values()],
        total=total,
        books_available=all_books,
    )
