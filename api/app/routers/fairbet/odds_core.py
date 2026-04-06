"""Core query helpers for FairBet odds pagination and metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import distinct, func, select, tuple_
from sqlalchemy.orm import selectinload

from ...db.odds import FairbetGameOddsWork
from ...db.sports import SportsGame, SportsLeague


def _safe_game_meta_options() -> tuple[Any, ...]:
    """Return metadata eager-load options, tolerating partial mapper state in tests."""
    try:
        return (
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
    except Exception:
        return ()


def build_base_filters(
    league: str | None,
    market_category: str | None = None,
    game_id: int | None = None,
    player_name: str | None = None,
    included_books: frozenset[str] | None = None,
    exclude_categories: list[str] | None = None,
) -> tuple[Any, list[Any]]:
    """Build common SQLAlchemy conditions for FairBet queries."""
    now = datetime.now(UTC)
    game_start = SportsGame.game_date
    conditions: list[Any] = [
        SportsGame.status.notin_(["final", "completed"]),
        game_start > now,
    ]
    if league:
        league_code = league.upper()
        conditions.append(
            SportsGame.league_id.in_(
                select(SportsLeague.id).where(func.upper(SportsLeague.code) == league_code)
            )
        )
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


def cursor_payload_from_key(
    sort_key: str,
    game_date: datetime,
    game_id: int,
    market_key: str,
    selection_key: str,
    line_value: float,
    index: int | None = None,
) -> dict[str, Any]:
    """Encode cursor payload for a terminal row in a page."""
    if sort_key == "game_time":
        return {
            "sort": sort_key,
            "v": [game_date.isoformat(), game_id, market_key, selection_key, line_value],
        }
    if sort_key == "market":
        return {
            "sort": sort_key,
            "v": [market_key, selection_key, game_date.isoformat(), game_id, line_value],
        }
    if sort_key == "ev":
        return {"sort": sort_key, "i": index or 0}
    return {"sort": "key", "v": [game_id, market_key, selection_key, line_value]}


def apply_keyset_where(stmt: Any, sort_key: str, cursor_values: list[Any]) -> Any:
    """Apply keyset continuation predicate for cursor pagination."""
    if sort_key == "game_time":
        dt = datetime.fromisoformat(str(cursor_values[0]))
        lhs = tuple_(
            SportsGame.game_date,
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
        )
        rhs = tuple_(
            dt,
            int(cursor_values[1]),
            str(cursor_values[2]),
            str(cursor_values[3]),
            float(cursor_values[4]),
        )
        return stmt.where(lhs > rhs)
    if sort_key == "market":
        dt = datetime.fromisoformat(str(cursor_values[2]))
        lhs = tuple_(
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            SportsGame.game_date,
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.line_value,
        )
        rhs = tuple_(
            str(cursor_values[0]),
            str(cursor_values[1]),
            dt,
            int(cursor_values[3]),
            float(cursor_values[4]),
        )
        return stmt.where(lhs > rhs)
    lhs = tuple_(
        FairbetGameOddsWork.game_id,
        FairbetGameOddsWork.market_key,
        FairbetGameOddsWork.selection_key,
        FairbetGameOddsWork.line_value,
    )
    rhs = tuple_(
        int(cursor_values[0]),
        str(cursor_values[1]),
        str(cursor_values[2]),
        float(cursor_values[3]),
    )
    return stmt.where(lhs > rhs)


def sort_order(sort_key: str) -> tuple[Any, ...]:
    """Return deterministic SQL order columns for sort_key."""
    if sort_key == "game_time":
        return (
            SportsGame.game_date,
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
        )
    if sort_key == "market":
        return (
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            SportsGame.game_date,
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.line_value,
        )
    return (
        FairbetGameOddsWork.game_id,
        FairbetGameOddsWork.market_key,
        FairbetGameOddsWork.selection_key,
        FairbetGameOddsWork.line_value,
    )


async def load_metadata(
    conditions: list[Any],
    include_meta: bool,
    exec_fn,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Load dropdown metadata arrays when requested by the client."""
    if not include_meta:
        return [], [], []

    books_stmt = (
        select(distinct(FairbetGameOddsWork.book))
        .join(SportsGame)
        .where(*conditions)
    )
    cats_stmt = (
        select(distinct(FairbetGameOddsWork.market_category))
        .join(SportsGame)
        .where(*conditions)
    )
    games_stmt = (
        select(SportsGame)
        .join(FairbetGameOddsWork, FairbetGameOddsWork.game_id == SportsGame.id)
        .where(*conditions)
        .distinct()
        .options(*_safe_game_meta_options())
    )
    books_result = await exec_fn(books_stmt)
    cats_result = await exec_fn(cats_stmt)
    games_result = await exec_fn(games_stmt)

    books_available = sorted([row[0] for row in books_result.all()])
    market_categories_available = sorted([row[0] for row in cats_result.all()])
    games_available = [
        {
            "game_id": g.id,
            "matchup": (
                f"{g.away_team.name if g.away_team else '?'} @ "
                f"{g.home_team.name if g.home_team else '?'}"
            ),
            "game_date": g.game_date.isoformat() if g.game_date else None,
        }
        for g in games_result.scalars().all()
    ]
    return books_available, market_categories_available, games_available
