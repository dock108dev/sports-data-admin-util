"""FairBet odds comparison endpoints.

Provides bet-centric odds views for cross-book comparison with EV annotation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import selectinload

from ...db import AsyncSession, get_db
from ...db.sports import SportsGame
from ...db.odds import FairbetGameOddsWork
from ...services.ev_config import (
    INCLUDED_BOOKS,
    get_strategy,
)
from .ev_annotation import (
    BookOdds,
    _annotate_pair_ev,
    _build_sharp_reference,
    _market_base,
    _pair_opposite_sides,
    _try_extrapolated_ev,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    reference_price: float | None = None
    opposite_reference_price: float | None = None
    books: list[BookOdds]
    ev_confidence_tier: str | None = None
    ev_disabled_reason: str | None = None
    ev_method: str | None = None
    has_fair: bool = False


class FairbetOddsResponse(BaseModel):
    """Response containing all bets with cross-book odds."""

    bets: list[BetDefinition]
    total: int
    books_available: list[str]
    market_categories_available: list[str]
    games_available: list[dict[str, Any]]
    ev_diagnostics: dict[str, int] = {}


def _build_base_filters(
    league: str | None,
    market_category: str | None = None,
    game_id: int | None = None,
    book: str | None = None,
    player_name: str | None = None,
    included_books: frozenset[str] | None = None,
    exclude_categories: list[str] | None = None,
) -> tuple:
    """Build common filter conditions for FairBet queries.

    Returns (game_start_expr, filter_conditions) tuple.
    """
    now = datetime.now(timezone.utc)

    # Use COALESCE to get actual start time (tip_time preferred, else game_date)
    game_start = func.coalesce(
        SportsGame.tip_time,
        SportsGame.game_date,
    )

    conditions = [
        SportsGame.status.notin_(["final", "completed"]),
        game_start > now,
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

    if included_books:
        conditions.append(FairbetGameOddsWork.book.in_(included_books))

    if exclude_categories:
        conditions.append(FairbetGameOddsWork.market_category.notin_(exclude_categories))

    return game_start, conditions


@router.get("/odds", response_model=FairbetOddsResponse)
async def get_fairbet_odds(
    session: AsyncSession = Depends(get_db),
    league: str | None = Query(
        None, description="Filter by league code (NBA, NHL, etc.)"
    ),
    market_category: str | None = Query(
        None, description="Filter by market category (mainline, player_prop, etc.)"
    ),
    exclude_categories: list[str] | None = Query(
        None, description="Exclude market categories (e.g. alternate)"
    ),
    game_id: int | None = Query(None, description="Filter to a specific game"),
    book: str | None = Query(None, description="Filter to a specific book"),
    player_name: str | None = Query(None, description="Filter by player name"),
    min_ev: float | None = Query(None, description="Minimum EV% threshold"),
    has_fair: bool | None = Query(
        None, description="Filter to bets with (true) or without (false) fair odds"
    ),
    sort_by: str = Query("ev", description="Sort order: ev, game_time, market"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> FairbetOddsResponse:
    """Get bet-centric odds for cross-book comparison with EV annotation.

    Returns bets grouped by definition (game + market + selection + line),
    with all available book prices for each bet, annotated with EV%.

    Only includes pregame games (start_time in future).
    Excludes junk/offshore books from results and EV calculations.

    Uses database-level pagination for efficiency.
    """
    _, conditions = _build_base_filters(
        league,
        market_category,
        game_id,
        book,
        player_name,
        included_books=INCLUDED_BOOKS,
        exclude_categories=exclude_categories,
    )

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
            bets=[],
            total=0,
            books_available=[],
            market_categories_available=[],
            games_available=[],
        )

    # When post-annotation filters or EV sort are active, we must fetch ALL bet
    # definitions, annotate, then paginate in Python.  Otherwise DB-level
    # pagination would silently drop matching bets (for filters) or only sort
    # the current page (for EV sort).
    needs_full_fetch = has_fair is not None or min_ev is not None or sort_by == "ev"

    # Step 2: Get bet definitions using CTE (skip DB pagination when post-filtering)
    paginated_bets_q = (
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
    )
    if not needs_full_fetch:
        paginated_bets_q = paginated_bets_q.limit(limit).offset(offset)

    paginated_bets_cte = paginated_bets_q.cte("paginated_bets")

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
        .where(FairbetGameOddsWork.book.in_(INCLUDED_BOOKS))
        .options(
            selectinload(FairbetGameOddsWork.game).selectinload(SportsGame.league),
            selectinload(FairbetGameOddsWork.game).selectinload(SportsGame.home_team),
            selectinload(FairbetGameOddsWork.game).selectinload(SportsGame.away_team),
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
            func.coalesce(SportsGame.tip_time, SportsGame.game_date)
            > datetime.now(timezone.utc),
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

    # Step 6: EV annotation with eligibility gate
    # Group bets by (game_id, market_key, abs(line_value)) to find candidate pairs
    market_groups: dict[tuple, list[tuple]] = {}
    for key in bets_map:
        game_id_k, market_key_k, _, line_value_k = key
        group_key = (game_id_k, market_key_k, abs(line_value_k))
        if group_key not in market_groups:
            market_groups[group_key] = []
        market_groups[group_key].append(key)

    ev_diagnostics: dict[str, int] = {"total_pairs": 0, "total_unpaired": 0}
    sharp_refs = _build_sharp_reference(bets_map, {"Pinnacle"})

    for group_key, bet_keys in market_groups.items():
        # Find valid pairs: entries with different selection_keys
        pairs, unpaired = _pair_opposite_sides(bet_keys)

        for key_a, key_b in pairs:
            ev_diagnostics["total_pairs"] += 1
            reason = _annotate_pair_ev(key_a, key_b, bets_map)
            if reason == "reference_missing":
                extrap_reason = _try_extrapolated_ev(
                    key_a, key_b, bets_map, sharp_refs
                )
                if extrap_reason is None:
                    ev_diagnostics["extrapolated"] = (
                        ev_diagnostics.get("extrapolated", 0) + 1
                    )
                    reason = None  # Mark as passed
                else:
                    reason = extrap_reason
            bucket = reason or "passed"
            ev_diagnostics[bucket] = ev_diagnostics.get(bucket, 0) + 1

        for key in unpaired:
            ev_diagnostics["total_unpaired"] += 1
            ev_diagnostics["no_pair"] = ev_diagnostics.get("no_pair", 0) + 1
            # Look up sharp books so is_sharp is set even without EV
            sample_league = bets_map[key].get("league_code", "UNKNOWN")
            sample_cat = bets_map[key].get("market_category", "mainline")
            cfg = get_strategy(sample_league, sample_cat)
            sharp = set(cfg.eligible_sharp_books) if cfg else set()
            bets_map[key]["ev_disabled_reason"] = "no_pair"
            bets_map[key]["books"] = [
                BookOdds(
                    book=b["book"],
                    price=b["price"],
                    observed_at=b["observed_at"],
                    is_sharp=b["book"] in sharp,
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
        bets_list.sort(
            key=lambda b: b.get("game_date")
            or datetime.min.replace(tzinfo=timezone.utc)
        )
    elif sort_by == "market":
        bets_list.sort(
            key=lambda b: (b.get("market_key", ""), b.get("selection_key", ""))
        )
    # Sort books within each bet by price (best odds first)
    for bet in bets_list:
        bet["books"].sort(key=lambda b: -b.price)

    # Step 8: Apply post-annotation filters and recalculate total/pagination
    if has_fair is not None:
        bets_list = [bet for bet in bets_list if bet.get("has_fair", False) == has_fair]

    if min_ev is not None:
        bets_list = [
            bet
            for bet in bets_list
            if any(
                b.ev_percent is not None and b.ev_percent >= min_ev
                for b in bet["books"]
            )
        ]

    if needs_full_fetch:
        total = len(bets_list)
        bets_list = bets_list[offset : offset + limit]

    # Step 9: Apply book filter for display (but we needed all books for EV calc).
    # Sharp books are always retained even when filtering by a specific book so
    # the UI can show the reference line that anchors the EV calculation.
    if book:
        for bet in bets_list:
            bet["books"] = [b for b in bet["books"] if b.book == book or b.is_sharp]

    return FairbetOddsResponse(
        bets=[BetDefinition(**bet) for bet in bets_list],
        total=total,
        books_available=all_books,
        market_categories_available=all_cats,
        games_available=games_available,
        ev_diagnostics=ev_diagnostics,
    )
