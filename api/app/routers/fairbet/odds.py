"""FairBet odds comparison endpoints.

Provides bet-centric odds views for cross-book comparison with EV annotation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import selectinload

from ...db import AsyncSession, get_db
from ...db.sports import SportsGame
from ...db.odds import FairbetGameOddsWork
from ...services.ev import SHARP_BOOKS, compute_ev_for_market

router = APIRouter()


class BookOdds(BaseModel):
    """Odds from a single book for a bet."""

    book: str
    price: float
    observed_at: datetime
    ev_percent: float | None = None
    implied_prob: float | None = None
    is_sharp: bool = False


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
    market_category: str | None = None
    player_name: str | None = None
    description: str | None = None
    true_prob: float | None = None
    books: list[BookOdds]


class FairbetOddsResponse(BaseModel):
    """Response containing all bets with cross-book odds."""

    bets: list[BetDefinition]
    total: int
    books_available: list[str]
    market_categories_available: list[str]
    games_available: list[dict[str, Any]]


def _build_base_filters(
    league: str | None,
    market_category: str | None = None,
    game_id: int | None = None,
    book: str | None = None,
    player_name: str | None = None,
) -> tuple:
    """Build common filter conditions for FairBet queries.

    Returns (game_start_expr, filter_conditions) tuple.
    """
    now = datetime.now(timezone.utc)
    live_cutoff = now - timedelta(hours=4)

    # Use COALESCE to get actual start time (tip_time preferred, else game_date)
    game_start = func.coalesce(
        SportsGame.tip_time,
        SportsGame.game_date,
    )

    conditions = [
        SportsGame.status.notin_(["final", "completed"]),
        game_start > live_cutoff,
    ]

    if league:
        conditions.append(SportsGame.league.has(code=league.upper()))

    if market_category:
        conditions.append(FairbetGameOddsWork.market_category == market_category)

    if game_id:
        conditions.append(FairbetGameOddsWork.game_id == game_id)

    if player_name:
        conditions.append(
            func.lower(FairbetGameOddsWork.player_name).contains(player_name.lower())
        )

    return game_start, conditions


def _find_complementary_key(selection_key: str) -> str | None:
    """Find the complementary selection key for two-way market EV calculation.

    total:over <-> total:under
    For team bets, we can't easily derive the complement without more context.
    """
    if selection_key == "total:over":
        return "total:under"
    elif selection_key == "total:under":
        return "total:over"
    # For player props: player:{name}:over <-> player:{name}:under
    if selection_key.startswith("player:") and selection_key.endswith(":over"):
        return selection_key.replace(":over", ":under")
    elif selection_key.startswith("player:") and selection_key.endswith(":under"):
        return selection_key.replace(":under", ":over")
    return None


@router.get("/odds", response_model=FairbetOddsResponse)
async def get_fairbet_odds(
    session: AsyncSession = Depends(get_db),
    league: str | None = Query(None, description="Filter by league code (NBA, NHL, etc.)"),
    market_category: str | None = Query(None, description="Filter by market category (mainline, player_prop, etc.)"),
    game_id: int | None = Query(None, description="Filter to a specific game"),
    book: str | None = Query(None, description="Filter to a specific book"),
    player_name: str | None = Query(None, description="Filter by player name"),
    min_ev: float | None = Query(None, description="Minimum EV% threshold"),
    sort_by: str = Query("ev", description="Sort order: ev, game_time, market"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FairbetOddsResponse:
    """Get bet-centric odds for cross-book comparison with EV annotation.

    Returns bets grouped by definition (game + market + selection + line),
    with all available book prices for each bet, annotated with EV%.

    Only includes upcoming games (start_time in future or within last 4 hours for live games).

    Uses database-level pagination for efficiency.
    """
    _, conditions = _build_base_filters(league, market_category, game_id, book, player_name)

    # Book filter applies at the row level, not the bet definition level
    book_conditions = list(conditions)
    if book:
        book_conditions.append(FairbetGameOddsWork.book == book)

    # Step 1: Count total distinct bet definitions (for pagination metadata)
    count_subq = (
        select(
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
        )
        .distinct()
        .join(SportsGame)
        .where(*conditions)
        .subquery()
    )
    count_stmt = select(func.count()).select_from(count_subq)
    total = (await session.execute(count_stmt)).scalar() or 0

    if total == 0:
        return FairbetOddsResponse(
            bets=[], total=0, books_available=[],
            market_categories_available=[], games_available=[],
        )

    # Step 2: Get paginated bet definitions using CTE
    paginated_bets_cte = (
        select(
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
        )
        .distinct()
        .join(SportsGame)
        .where(*conditions)
        .order_by(
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
        )
        .limit(limit)
        .offset(offset)
    ).cte("paginated_bets")

    # Step 3: Join CTE back to get ALL books for paginated bet definitions
    # (don't filter by book here - we need all books for EV calculation)
    stmt = (
        select(FairbetGameOddsWork)
        .join(
            paginated_bets_cte,
            and_(
                FairbetGameOddsWork.game_id == paginated_bets_cte.c.game_id,
                FairbetGameOddsWork.market_key == paginated_bets_cte.c.market_key,
                FairbetGameOddsWork.selection_key == paginated_bets_cte.c.selection_key,
                FairbetGameOddsWork.line_value == paginated_bets_cte.c.line_value,
            ),
        )
        .join(SportsGame)
        .options(
            selectinload(FairbetGameOddsWork.game).selectinload(
                SportsGame.league
            ),
            selectinload(FairbetGameOddsWork.game).selectinload(
                SportsGame.home_team
            ),
            selectinload(FairbetGameOddsWork.game).selectinload(
                SportsGame.away_team
            ),
        )
        .order_by(
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
        )
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()

    # Step 4: Get available metadata for filter dropdowns
    base_game_conditions = list(conditions)
    books_stmt = (
        select(distinct(FairbetGameOddsWork.book))
        .join(SportsGame)
        .where(*base_game_conditions)
    )
    cats_stmt = (
        select(distinct(FairbetGameOddsWork.market_category))
        .join(SportsGame)
        .where(*base_game_conditions)
    )
    games_stmt = (
        select(
            SportsGame.id,
            SportsGame.game_date,
            SportsGame.tip_time,
        )
        .join(FairbetGameOddsWork, FairbetGameOddsWork.game_id == SportsGame.id)
        .where(*base_game_conditions)
        .distinct()
        .options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
    )

    books_result = await session.execute(books_stmt)
    all_books = sorted([row[0] for row in books_result.all()])

    cats_result = await session.execute(cats_stmt)
    all_cats = sorted([row[0] for row in cats_result.all()])

    # For games_available, fetch game details separately
    games_for_dropdown_stmt = (
        select(SportsGame)
        .join(FairbetGameOddsWork, FairbetGameOddsWork.game_id == SportsGame.id)
        .where(
            SportsGame.status.notin_(["final", "completed"]),
            func.coalesce(SportsGame.tip_time, SportsGame.game_date) > datetime.now(timezone.utc) - timedelta(hours=4),
        )
        .distinct()
        .options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
    )
    games_dropdown_result = await session.execute(games_for_dropdown_stmt)
    games_dropdown = games_dropdown_result.scalars().all()
    games_available = [
        {
            "game_id": g.id,
            "matchup": f"{g.away_team.name if g.away_team else '?'} @ {g.home_team.name if g.home_team else '?'}",
            "game_date": g.start_time.isoformat() if g.start_time else None,
        }
        for g in games_dropdown
    ]

    # Step 5: Group rows by bet definition
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
                "market_category": row.market_category,
                "player_name": row.player_name,
                "books": [],
            }

        bets_map[key]["books"].append(
            {
                "book": row.book,
                "price": row.price,
                "observed_at": row.observed_at,
            }
        )

    # Step 6: EV annotation
    # Group bets by (game_id, market_key, line_value) to find both sides of each market
    market_groups: dict[tuple, list[tuple]] = {}
    for key in bets_map:
        game_id_k, market_key_k, _, line_value_k = key
        group_key = (game_id_k, market_key_k, line_value_k)
        if group_key not in market_groups:
            market_groups[group_key] = []
        market_groups[group_key].append(key)

    for group_key, bet_keys in market_groups.items():
        if len(bet_keys) == 2:
            # Two-way market: compute EV using both sides
            key_a, key_b = bet_keys
            books_a = bets_map[key_a]["books"]
            books_b = bets_map[key_b]["books"]

            annotated_a, annotated_b = compute_ev_for_market(books_a, books_b)

            # Update with annotated data
            bets_map[key_a]["books"] = [
                BookOdds(
                    book=b["book"],
                    price=b["price"],
                    observed_at=b["observed_at"],
                    ev_percent=b.get("ev_percent"),
                    implied_prob=round(b.get("implied_prob", 0), 4) if b.get("implied_prob") else None,
                    is_sharp=b.get("is_sharp", False),
                )
                for b in annotated_a
            ]
            bets_map[key_b]["books"] = [
                BookOdds(
                    book=b["book"],
                    price=b["price"],
                    observed_at=b["observed_at"],
                    ev_percent=b.get("ev_percent"),
                    implied_prob=round(b.get("implied_prob", 0), 4) if b.get("implied_prob") else None,
                    is_sharp=b.get("is_sharp", False),
                )
                for b in annotated_b
            ]

            # Set true_prob on the bet definition
            if annotated_a and annotated_a[0].get("true_prob") is not None:
                bets_map[key_a]["true_prob"] = annotated_a[0]["true_prob"]
            if annotated_b and annotated_b[0].get("true_prob") is not None:
                bets_map[key_b]["true_prob"] = annotated_b[0]["true_prob"]
        else:
            # Single-sided or 3+ way market: just mark sharp books, no EV
            for key in bet_keys:
                bets_map[key]["books"] = [
                    BookOdds(
                        book=b["book"],
                        price=b["price"],
                        observed_at=b["observed_at"],
                        is_sharp=b["book"] in SHARP_BOOKS,
                    )
                    for b in bets_map[key]["books"]
                ]

    # Step 7: Sort
    bets_list = list(bets_map.values())

    if sort_by == "ev":
        # Sort by best EV across books (highest first)
        def best_ev(bet: dict) -> float:
            evs = [b.ev_percent for b in bet["books"] if b.ev_percent is not None]
            return max(evs) if evs else float("-inf")
        bets_list.sort(key=best_ev, reverse=True)
    elif sort_by == "game_time":
        bets_list.sort(key=lambda b: b.get("game_date") or datetime.min.replace(tzinfo=timezone.utc))
    elif sort_by == "market":
        bets_list.sort(key=lambda b: (b.get("market_key", ""), b.get("selection_key", "")))
    else:
        # Default: sort by price (best odds first)
        for bet in bets_list:
            bet["books"].sort(key=lambda b: -b.price)

    # Sort books within each bet by price (best odds first)
    for bet in bets_list:
        bet["books"].sort(key=lambda b: -b.price)

    # Step 8: Apply min_ev filter (post-annotation)
    if min_ev is not None:
        bets_list = [
            bet for bet in bets_list
            if any(
                b.ev_percent is not None and b.ev_percent >= min_ev
                for b in bet["books"]
            )
        ]

    # Step 9: Apply book filter for display (but we needed all books for EV calc)
    if book:
        for bet in bets_list:
            bet["books"] = [b for b in bet["books"] if b.book == book or b.is_sharp]

    return FairbetOddsResponse(
        bets=[BetDefinition(**bet) for bet in bets_list],
        total=total,
        books_available=all_books,
        market_categories_available=all_cats,
        games_available=games_available,
    )
