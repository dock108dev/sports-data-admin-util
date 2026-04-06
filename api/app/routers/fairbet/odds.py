"""FairBet odds comparison endpoints.

Provides bet-centric odds views for cross-book comparison with EV annotation.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, select, tuple_
from sqlalchemy.orm import selectinload

from ...config import settings
from ...db import AsyncSession, get_db
from ...db.odds import FairbetGameOddsWork
from ...db.sports import SportsGame
from ...services.ev import american_to_implied
from ...services.ev_config import (
    INCLUDED_BOOKS,
    SHARP_REF_MAX_AGE_SECONDS,
    get_fairbet_debug_game_ids,
    get_strategy,
)
from ...services.fairbet_display import (
    book_abbreviation,
    build_explanation_steps,
    confidence_display_label,
    ev_method_display_name,
    ev_method_explanation,
    fair_american_odds,
    market_display_name,
    selection_display,
)
from ...services.fairbet_runtime import (
    build_query_hash,
    create_snapshot,
    decode_cursor,
    encode_cursor,
    get_cached_response,
    get_snapshot,
    normalize_query_dict,
    set_cached_response,
)
from .ev_annotation import (
    BookOdds,
    _annotate_pair_ev,
    _pair_opposite_sides,
    derive_entity_key,
)
from .ev_extrapolation import _build_sharp_reference, _try_extrapolated_ev

logger = logging.getLogger(__name__)

# Minimum number of books required for a bet to appear in FairBet results.
# Bets with fewer books lack sufficient market coverage for meaningful comparison.
MIN_BOOKS_FOR_FAIRBET = 3

router = APIRouter()


class ExplanationDetailRow(BaseModel):
    """A single key-value row in an explanation step."""

    label: str
    value: str
    is_highlight: bool = False  # Client can bold/accent highlighted rows


class ExplanationStep(BaseModel):
    """One step in the math walkthrough explaining how fair odds were derived."""

    step_number: int
    title: str
    description: str
    detail_rows: list[ExplanationDetailRow] = []


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
    estimated_sharp_price: float | None = None
    extrapolation_ref_line: float | None = None
    extrapolation_distance: float | None = None
    consensus_book_count: int | None = None
    consensus_iqr: float | None = None
    per_book_fair_probs: dict[str, float] | None = None
    confidence: float | None = None
    confidence_flags: list[str] = []
    fair_american_odds: int | None = None
    selection_display: str | None = None
    market_display_name: str | None = None
    best_book: str | None = None
    best_ev_percent: float | None = None
    is_reliably_positive: bool | None = None
    confidence_display_label: str | None = None
    ev_method_display_name: str | None = None
    ev_method_explanation: str | None = None
    explanation_steps: list[ExplanationStep] | None = None


class FairbetOddsResponse(BaseModel):
    """Response containing all bets with cross-book odds."""

    bets: list[BetDefinition]
    # New paging contract fields (additive; bets preserved for compatibility).
    items: list[BetDefinition] = []
    nextCursor: str | None = None
    hasMore: bool = False
    total: int | None = None
    generatedAt: datetime | None = None
    snapshotId: str | None = None
    requestId: str | None = None
    pageLatencyMs: int | None = None
    partial: bool = False
    warnings: list[str] = []
    books_available: list[str] = []
    market_categories_available: list[str] = []
    games_available: list[dict[str, Any]] = []
    ev_diagnostics: dict[str, int] = {}
    ev_config: dict[str, Any] | None = None


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
    now = datetime.now(UTC)

    game_start = SportsGame.game_date

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
    request: Request = None,
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
    sort_by: str | None = Query(None, description="Sort order: ev, game_time, market"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    cursor: str | None = Query(None, description="Cursor token for stable pagination"),
    snapshot_id: str | None = Query(None, alias="snapshotId"),
    include_meta: bool = Query(
        False,
        description="Include books/categories/games metadata; disabled by default for performance.",
    ),
) -> FairbetOddsResponse:
    """Get FairBet odds with light (DB) and snapshot (EV) pagination modes."""
    t0 = time.perf_counter()
    db_ms = 0.0
    warnings: list[str] = []
    request_id: str | None = None
    if request is not None:
        request_id = request.headers.get("x-request-id")
        if not request_id:
            scope_state = request.scope.get("state", {})
            if isinstance(scope_state, dict):
                request_id = scope_state.get("request_id")

    sort_resolved = sort_by
    if not sort_resolved:
        sort_resolved = "game_time" if settings.fairbet_light_default_enabled else "ev"

    if cursor and not settings.fairbet_cursor_enabled:
        raise HTTPException(status_code=400, detail="Cursor pagination is disabled.")
    if cursor and offset > 0:
        raise HTTPException(status_code=400, detail="Use cursor or offset, not both.")

    async def _exec(stmt):
        nonlocal db_ms
        s = time.perf_counter()
        result = await session.execute(stmt)
        db_ms += (time.perf_counter() - s) * 1000
        return result

    def _cursor_payload_from_key(
        sort_key: str,
        game_date: datetime,
        game_id: int,
        market_key: str,
        selection_key: str,
        line_value: float,
        index: int | None = None,
    ) -> dict[str, Any]:
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

    def _apply_keyset_where(stmt, sort_key: str, cursor_values: list[Any]):
        if sort_key == "game_time":
            dt = datetime.fromisoformat(str(cursor_values[0]))
            return stmt.where(
                tuple_(
                    SportsGame.game_date,
                    FairbetGameOddsWork.game_id,
                    FairbetGameOddsWork.market_key,
                    FairbetGameOddsWork.selection_key,
                    FairbetGameOddsWork.line_value,
                )
                > tuple_(
                    dt,
                    int(cursor_values[1]),
                    str(cursor_values[2]),
                    str(cursor_values[3]),
                    float(cursor_values[4]),
                )
            )
        if sort_key == "market":
            dt = datetime.fromisoformat(str(cursor_values[2]))
            return stmt.where(
                tuple_(
                    FairbetGameOddsWork.market_key,
                    FairbetGameOddsWork.selection_key,
                    SportsGame.game_date,
                    FairbetGameOddsWork.game_id,
                    FairbetGameOddsWork.line_value,
                )
                > tuple_(
                    str(cursor_values[0]),
                    str(cursor_values[1]),
                    dt,
                    int(cursor_values[3]),
                    float(cursor_values[4]),
                )
            )
        return stmt.where(
            tuple_(
                FairbetGameOddsWork.game_id,
                FairbetGameOddsWork.market_key,
                FairbetGameOddsWork.selection_key,
                FairbetGameOddsWork.line_value,
            )
            > tuple_(
                int(cursor_values[0]),
                str(cursor_values[1]),
                str(cursor_values[2]),
                float(cursor_values[3]),
            )
        )

    def _sort_order(sort_key: str):
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

    def _empty_response() -> FairbetOddsResponse:
        generated = datetime.now(UTC)
        latency = int((time.perf_counter() - t0) * 1000)
        return FairbetOddsResponse(
            bets=[],
            items=[],
            total=0,
            hasMore=False,
            nextCursor=None,
            generatedAt=generated,
            requestId=request_id,
            pageLatencyMs=latency,
            partial=False,
            warnings=warnings,
            books_available=[],
            market_categories_available=[],
            games_available=[],
        )

    _, conditions = _build_base_filters(
        league,
        market_category,
        game_id,
        book,
        player_name,
        included_books=INCLUDED_BOOKS,
        exclude_categories=exclude_categories,
    )

    # Cache keying includes query semantics and pagination inputs.
    cache_params = normalize_query_dict({
        "league": league,
        "market_category": market_category,
        "exclude_categories": exclude_categories,
        "game_id": game_id,
        "book": book,
        "player_name": player_name,
        "min_ev": min_ev,
        "has_fair": has_fair,
        "sort_by": sort_resolved,
        "limit": limit,
        "offset": offset,
        "cursor": cursor,
        "snapshot_id": snapshot_id,
        "include_meta": include_meta,
    })
    query_hash = build_query_hash(cache_params)
    version_result = await _exec(select(func.max(FairbetGameOddsWork.updated_at)))
    max_updated = version_result.scalar()
    content_version = (
        max_updated.replace(microsecond=0).isoformat() if max_updated else "none"
    )

    # Cache only for non-EV requests; EV is snapshot-cached separately.
    if sort_resolved != "ev":
        cached = get_cached_response(query_hash, content_version)
        if cached:
            logger.info(
                "fairbet_odds_cache_hit",
                extra={"query_hash": query_hash, "sort_by": sort_resolved},
            )
            return FairbetOddsResponse(**cached)

    async def _load_metadata() -> tuple[list[str], list[str], list[dict[str, Any]]]:
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
            .options(
                selectinload(SportsGame.home_team),
                selectinload(SportsGame.away_team),
            )
        )
        books_result = await _exec(books_stmt)
        cats_result = await _exec(cats_stmt)
        games_result = await _exec(games_stmt)
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

    def _enrich_and_finalize(rows: list[FairbetGameOddsWork], sort_key: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
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
                    "game_date": game.game_date,
                    "market_key": row.market_key,
                    "selection_key": row.selection_key,
                    "line_value": row.line_value,
                    "market_category": row.market_category,
                    "player_name": row.player_name,
                    "entity_key": derive_entity_key(
                        row.selection_key, row.market_key, row.player_name
                    ),
                    "books": [],
                }

            bets_map[key]["books"].append(
                {"book": row.book, "price": row.price, "observed_at": row.observed_at}
            )

        from .ev_staleness import filter_stale_books

        bets_map = filter_stale_books(bets_map, sharp_books={"Pinnacle"})
        bets_map = {
            k: b for k, b in bets_map.items() if len(b.get("books", [])) >= MIN_BOOKS_FOR_FAIRBET
        }

        market_groups: dict[tuple, list[tuple]] = {}
        for key in bets_map:
            game_id_k, market_key_k, _, line_value_k = key
            entity_key = bets_map[key]["entity_key"]
            group_key = (game_id_k, market_key_k, entity_key, abs(line_value_k))
            market_groups.setdefault(group_key, []).append(key)

        ev_diagnostics: dict[str, int] = {"total_pairs": 0, "total_unpaired": 0}
        sharp_refs = _build_sharp_reference(
            bets_map, {"Pinnacle"}, max_age_seconds=SHARP_REF_MAX_AGE_SECONDS
        )

        for _, bet_keys in market_groups.items():
            pairs, unpaired = _pair_opposite_sides(bet_keys)
            for key_a, key_b in pairs:
                ev_diagnostics["total_pairs"] += 1
                reason = _annotate_pair_ev(key_a, key_b, bets_map)
                if reason == "entity_mismatch":
                    _debug_ids = get_fairbet_debug_game_ids()
                    if key_a[0] in _debug_ids:
                        logger.info(
                            "entity_pair_blocked",
                            extra={
                                "game_id": key_a[0],
                                "entity_a": bets_map[key_a].get("entity_key"),
                                "entity_b": bets_map[key_b].get("entity_key"),
                                "market_key": key_a[1],
                                "line_value": key_a[3],
                            },
                        )
                if reason == "reference_missing":
                    extrap_reason = _try_extrapolated_ev(key_a, key_b, bets_map, sharp_refs)
                    if extrap_reason is None:
                        ev_diagnostics["extrapolated"] = ev_diagnostics.get("extrapolated", 0) + 1
                        reason = None
                    else:
                        reason = extrap_reason
                bucket = reason or "passed"
                ev_diagnostics[bucket] = ev_diagnostics.get(bucket, 0) + 1

            for key in unpaired:
                ev_diagnostics["total_unpaired"] += 1
                ev_diagnostics["no_pair"] = ev_diagnostics.get("no_pair", 0) + 1
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

        bets_list = list(bets_map.values())
        if sort_key == "ev":
            def best_ev(bet: dict) -> float:
                evs = [b.display_ev for b in bet["books"] if b.display_ev is not None]
                if evs:
                    return max(evs)
                raw = [b.ev_percent for b in bet["books"] if b.ev_percent is not None]
                return max(raw) if raw else float("-inf")
            bets_list.sort(key=best_ev, reverse=True)
        elif sort_key == "game_time":
            bets_list.sort(
                key=lambda b: (
                    b.get("game_date") or datetime.min.replace(tzinfo=UTC),
                    b.get("game_id", 0),
                    b.get("market_key", ""),
                    b.get("selection_key", ""),
                    b.get("line_value", 0),
                )
            )
        elif sort_key == "market":
            bets_list.sort(
                key=lambda b: (
                    b.get("market_key", ""),
                    b.get("selection_key", ""),
                    b.get("game_date") or datetime.min.replace(tzinfo=UTC),
                    b.get("game_id", 0),
                    b.get("line_value", 0),
                )
            )
        else:
            bets_list.sort(
                key=lambda b: (
                    b.get("game_id", 0),
                    b.get("market_key", ""),
                    b.get("selection_key", ""),
                    b.get("line_value", 0),
                )
            )

        for bet in bets_list:
            bet["books"].sort(key=lambda b: -b.price)

        if has_fair is not None:
            bets_list = [b for b in bets_list if b.get("has_fair", False) == has_fair]
        if min_ev is not None:
            bets_list = [
                bet
                for bet in bets_list
                if any(
                    (b.display_ev is not None and b.display_ev >= min_ev)
                    or (
                        b.display_ev is None
                        and b.ev_percent is not None
                        and b.ev_percent >= min_ev
                    )
                    for b in bet["books"]
                )
            ]

        if book:
            for bet in bets_list:
                bet["books"] = [b for b in bet["books"] if b.book == book or b.is_sharp]

        for bet in bets_list:
            bet["fair_american_odds"] = fair_american_odds(bet.get("true_prob"))
            bet["selection_display"] = selection_display(
                bet.get("selection_key", ""),
                bet.get("market_key", ""),
                home_team=bet.get("home_team"),
                away_team=bet.get("away_team"),
                player_name=bet.get("player_name"),
                line_value=bet.get("line_value"),
            )
            bet["market_display_name"] = market_display_name(bet.get("market_key", ""))
            bet["confidence_display_label"] = confidence_display_label(
                bet.get("ev_confidence_tier")
            )
            bet["ev_method_display_name"] = ev_method_display_name(bet.get("ev_method"))
            bet["ev_method_explanation"] = ev_method_explanation(bet.get("ev_method"))

            best_ev_val: float | None = None
            best_book_name: str | None = None
            for b in bet["books"]:
                ev_val = b.display_ev if b.display_ev is not None else b.ev_percent
                if ev_val is not None and (best_ev_val is None or ev_val > best_ev_val):
                    best_ev_val = ev_val
                    best_book_name = b.book
            bet["best_book"] = best_book_name
            bet["best_ev_percent"] = round(best_ev_val, 2) if best_ev_val is not None else None
            bet["is_reliably_positive"] = (
                best_ev_val is not None and best_ev_val > 0 and (bet.get("confidence") or 0) >= 0.7
            )

            best_book_price: float | None = None
            if best_book_name:
                for b in bet["books"]:
                    if b.book == best_book_name:
                        best_book_price = b.price
                        break

            bet["explanation_steps"] = build_explanation_steps(
                ev_method=bet.get("ev_method"),
                ev_disabled_reason=bet.get("ev_disabled_reason"),
                true_prob=bet.get("true_prob"),
                reference_price=bet.get("reference_price"),
                opposite_reference_price=bet.get("opposite_reference_price"),
                fair_odds=bet["fair_american_odds"],
                best_book=best_book_name,
                best_book_price=best_book_price,
                best_ev_percent=bet["best_ev_percent"],
                estimated_sharp_price=bet.get("estimated_sharp_price"),
                extrapolation_ref_line=bet.get("extrapolation_ref_line"),
                extrapolation_distance=bet.get("extrapolation_distance"),
                per_book_fair_probs=bet.get("per_book_fair_probs"),
                consensus_iqr=bet.get("consensus_iqr"),
            )

            enriched_books: list[BookOdds] = []
            for b in bet["books"]:
                abbr = book_abbreviation(b.book)
                price_dec: float | None = None
                try:
                    imp = american_to_implied(b.price)
                    price_dec = round(1.0 / imp, 3) if imp > 0 else None
                except (ValueError, ZeroDivisionError):
                    logger.debug("skipped_invalid_odds_conversion", extra={"price": b.price})
                ev_tier: str | None = None
                ev_val = b.display_ev if b.display_ev is not None else b.ev_percent
                if ev_val is not None:
                    if ev_val >= 5.0:
                        ev_tier = "strong_positive"
                    elif ev_val >= 0.0:
                        ev_tier = "positive"
                    else:
                        ev_tier = "negative"
                elif b.is_sharp:
                    ev_tier = "neutral"
                enriched_books.append(
                    b.model_copy(
                        update={
                            "book_abbr": abbr,
                            "price_decimal": price_dec,
                            "ev_tier": ev_tier,
                        }
                    )
                )
            bet["books"] = enriched_books
        return bets_list, ev_diagnostics

    # EV mode: require snapshot semantics for cursor paging.
    if sort_resolved == "ev":
        books_available, cats_available, games_available = await _load_metadata()
        if snapshot_id:
            snapshot = get_snapshot(snapshot_id)
            if not snapshot:
                raise HTTPException(status_code=410, detail="Snapshot expired or not found.")
            if snapshot.get("query_hash") != query_hash:
                raise HTTPException(status_code=400, detail="Snapshot does not match query.")
            all_items = snapshot.get("items", [])
            total = int(snapshot.get("total", len(all_items)))
            generated_at = datetime.fromisoformat(snapshot["generated_at"])
            start_idx = 0
            if cursor:
                payload = decode_cursor(cursor)
                if payload.get("sort") != "ev":
                    raise HTTPException(status_code=400, detail="Invalid cursor for EV snapshot.")
                start_idx = int(payload.get("i", 0))
            page = all_items[start_idx : start_idx + limit]
            has_more = start_idx + limit < total
            next_cursor = (
                encode_cursor({"sort": "ev", "i": start_idx + limit}) if has_more else None
            )
            latency = int((time.perf_counter() - t0) * 1000)
            response = FairbetOddsResponse(
                bets=[BetDefinition(**b) for b in page],
                items=[BetDefinition(**b) for b in page],
                total=total,
                nextCursor=next_cursor,
                hasMore=has_more,
                generatedAt=generated_at,
                snapshotId=snapshot_id,
                requestId=request_id,
                pageLatencyMs=latency,
                partial=False,
                warnings=warnings,
                books_available=books_available,
                market_categories_available=cats_available,
                games_available=games_available,
                ev_diagnostics={},
                ev_config={
                    "min_books_for_display": MIN_BOOKS_FOR_FAIRBET,
                    "ev_color_thresholds": {"strong_positive": 5.0, "positive": 0.0},
                },
            )
            return response

        # First EV page: compute once, then snapshot for stable paging.
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
        total_stmt = select(func.count()).select_from(count_subq)
        total = (await _exec(total_stmt)).scalar() or 0
        if total == 0:
            return _empty_response()

        full_keys_stmt = (
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
        keys = (await _exec(full_keys_stmt)).all()
        if not keys:
            return _empty_response()
        key_tuples = [(k[0], k[1], k[2], float(k[3])) for k in keys]
        rows_stmt = (
            select(FairbetGameOddsWork)
            .join(SportsGame)
            .where(
                FairbetGameOddsWork.book.in_(INCLUDED_BOOKS),
                tuple_(
                    FairbetGameOddsWork.game_id,
                    FairbetGameOddsWork.market_key,
                    FairbetGameOddsWork.selection_key,
                    FairbetGameOddsWork.line_value,
                ).in_(key_tuples),
            )
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
        rows = (await _exec(rows_stmt)).scalars().all()
        bets_all, ev_diagnostics = _enrich_and_finalize(rows, "ev")
        total = len(bets_all)
        sid, generated = create_snapshot(query_hash, bets_all, total)
        page = bets_all[:limit]
        has_more = total > limit
        next_cursor = encode_cursor({"sort": "ev", "i": limit}) if has_more else None
        latency = int((time.perf_counter() - t0) * 1000)
        return FairbetOddsResponse(
            bets=[BetDefinition(**b) for b in page],
            items=[BetDefinition(**b) for b in page],
            total=total,
            nextCursor=next_cursor,
            hasMore=has_more,
            generatedAt=generated,
            snapshotId=sid,
            requestId=request_id,
            pageLatencyMs=latency,
            partial=False,
            warnings=warnings,
            books_available=books_available,
            market_categories_available=cats_available,
            games_available=games_available,
            ev_diagnostics=ev_diagnostics,
            ev_config={
                "min_books_for_display": MIN_BOOKS_FOR_FAIRBET,
                "ev_color_thresholds": {"strong_positive": 5.0, "positive": 0.0},
            },
        )

    # Light/default mode: deterministic keyset + DB pagination.
    order_cols = _sort_order(sort_resolved)
    keys_stmt = (
        select(
            FairbetGameOddsWork.game_id,
            FairbetGameOddsWork.market_key,
            FairbetGameOddsWork.selection_key,
            FairbetGameOddsWork.line_value,
            SportsGame.game_date,
        )
        .distinct()
        .join(SportsGame)
        .where(*conditions)
        .order_by(*order_cols)
    )
    if cursor:
        payload = decode_cursor(cursor)
        cursor_sort = str(payload.get("sort"))
        if cursor_sort != sort_resolved:
            raise HTTPException(status_code=400, detail="Cursor sort does not match sort_by.")
        keys_stmt = _apply_keyset_where(keys_stmt, sort_resolved, payload.get("v", []))
    elif offset:
        # Keep offset support for backward compatibility.
        keys_stmt = keys_stmt.offset(offset)
    keys_stmt = keys_stmt.limit(limit + 1)

    key_rows = (await _exec(keys_stmt)).all()
    has_more = len(key_rows) > limit
    page_keys = key_rows[:limit]
    if not page_keys:
        return _empty_response()

    next_cursor: str | None = None
    if has_more:
        last = page_keys[-1]
        next_cursor = encode_cursor(
            _cursor_payload_from_key(
                sort_resolved,
                last[4],
                int(last[0]),
                str(last[1]),
                str(last[2]),
                float(last[3]),
            )
        )

    key_tuples = [(int(k[0]), str(k[1]), str(k[2]), float(k[3])) for k in page_keys]
    rows_stmt = (
        select(FairbetGameOddsWork)
        .join(SportsGame)
        .where(
            FairbetGameOddsWork.book.in_(INCLUDED_BOOKS),
            tuple_(
                FairbetGameOddsWork.game_id,
                FairbetGameOddsWork.market_key,
                FairbetGameOddsWork.selection_key,
                FairbetGameOddsWork.line_value,
            ).in_(key_tuples),
        )
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
    rows = (await _exec(rows_stmt)).scalars().all()
    bets_list, ev_diagnostics = _enrich_and_finalize(rows, sort_resolved)

    total_stmt = select(func.count()).select_from(
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
    total = (await _exec(total_stmt)).scalar() or len(bets_list)
    books_available, cats_available, games_available = await _load_metadata()

    generated_at = datetime.now(UTC)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    response = FairbetOddsResponse(
        bets=[BetDefinition(**b) for b in bets_list],
        items=[BetDefinition(**b) for b in bets_list],
        nextCursor=next_cursor,
        hasMore=has_more,
        total=total,
        generatedAt=generated_at,
        requestId=request_id,
        pageLatencyMs=latency_ms,
        partial=False,
        warnings=warnings,
        books_available=books_available,
        market_categories_available=cats_available,
        games_available=games_available,
        ev_diagnostics=ev_diagnostics,
        ev_config={
            "min_books_for_display": MIN_BOOKS_FOR_FAIRBET,
            "ev_color_thresholds": {"strong_positive": 5.0, "positive": 0.0},
        },
    )
    if sort_resolved != "ev":
        set_cached_response(
            query_hash=query_hash,
            content_version=content_version,
            payload=response.model_dump(mode="json"),
        )
    logger.info(
        "fairbet_odds_served",
        extra={
            "sort_by": sort_resolved,
            "db_ms": round(db_ms, 1),
            "handler_ms": latency_ms,
            "rows_returned": len(bets_list),
            "has_more": has_more,
        },
    )
    return response


@router.get("/odds/meta")
async def get_fairbet_odds_meta(
    session: AsyncSession = Depends(get_db),
    league: str | None = Query(None),
    market_category: str | None = Query(None),
    exclude_categories: list[str] | None = Query(None),
    game_id: int | None = Query(None),
    book: str | None = Query(None),
    player_name: str | None = Query(None),
) -> dict[str, Any]:
    """Lightweight metadata endpoint for filter dropdowns."""
    _, conditions = _build_base_filters(
        league,
        market_category,
        game_id,
        book,
        player_name,
        included_books=INCLUDED_BOOKS,
        exclude_categories=exclude_categories,
    )
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
        .options(
            selectinload(SportsGame.home_team),
            selectinload(SportsGame.away_team),
        )
    )
    books = sorted([row[0] for row in (await session.execute(books_stmt)).all()])
    cats = sorted([row[0] for row in (await session.execute(cats_stmt)).all()])
    games = (await session.execute(games_stmt)).scalars().all()
    return {
        "books_available": books,
        "market_categories_available": cats,
        "games_available": [
            {
                "game_id": g.id,
                "matchup": (
                    f"{g.away_team.name if g.away_team else '?'} @ "
                    f"{g.home_team.name if g.home_team else '?'}"
                ),
                "game_date": g.game_date.isoformat() if g.game_date else None,
            }
            for g in games
        ],
    }
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
            SportsGame.game_date > datetime.now(UTC),
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
            "game_date": g.game_date.isoformat() if g.game_date else None,
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
                "game_date": game.game_date,
                "market_key": row.market_key,
                "selection_key": row.selection_key,
                "line_value": row.line_value,
                "market_category": row.market_category,
                "player_name": row.player_name,
                "entity_key": derive_entity_key(row.selection_key, row.market_key, row.player_name),
                "books": [],
            }

        bets_map[key]["books"].append(
            {
                "book": row.book,
                "price": row.price,
                "observed_at": row.observed_at,
            }
        )

    # Step 5a: Drop non-sharp books with stale observed_at (>2 min behind sharp book)
    from .ev_staleness import filter_stale_books

    bets_map = filter_stale_books(bets_map, sharp_books={"Pinnacle"})

    # Step 5b: Drop bets with insufficient book coverage
    pre_filter_count = len(bets_map)
    bets_map = {
        key: bet for key, bet in bets_map.items()
        if len(bet["books"]) >= MIN_BOOKS_FOR_FAIRBET
    }
    if pre_filter_count > len(bets_map):
        logger.info(
            "min_books_filter",
            extra={
                "dropped": pre_filter_count - len(bets_map),
                "remaining": len(bets_map),
                "threshold": MIN_BOOKS_FOR_FAIRBET,
            },
        )

    # Step 6: EV annotation with eligibility gate
    # Group bets by (game_id, market_key, entity_key, abs(line_value)) to find candidate pairs
    # entity_key prevents cross-entity pairing (different players, different team totals)
    market_groups: dict[tuple, list[tuple]] = {}
    for key in bets_map:
        game_id_k, market_key_k, _, line_value_k = key
        entity_key = bets_map[key]["entity_key"]
        group_key = (game_id_k, market_key_k, entity_key, abs(line_value_k))
        if group_key not in market_groups:
            market_groups[group_key] = []
        market_groups[group_key].append(key)

    ev_diagnostics: dict[str, int] = {"total_pairs": 0, "total_unpaired": 0}
    sharp_refs = _build_sharp_reference(
        bets_map, {"Pinnacle"}, max_age_seconds=SHARP_REF_MAX_AGE_SECONDS
    )

    for group_key, bet_keys in market_groups.items():
        # Find valid pairs: entries with different selection_keys
        pairs, unpaired = _pair_opposite_sides(bet_keys)

        for key_a, key_b in pairs:
            ev_diagnostics["total_pairs"] += 1
            reason = _annotate_pair_ev(key_a, key_b, bets_map)
            if reason == "entity_mismatch":
                _debug_ids = get_fairbet_debug_game_ids()
                if key_a[0] in _debug_ids:
                    logger.info(
                        "entity_pair_blocked",
                        extra={
                            "game_id": key_a[0],
                            "entity_a": bets_map[key_a].get("entity_key"),
                            "entity_b": bets_map[key_b].get("entity_key"),
                            "market_key": key_a[1],
                            "line_value": key_a[3],
                        },
                    )
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
        # Sort by best display_ev (confidence-weighted) across books (highest first)
        def best_ev(bet: dict) -> float:
            evs = [b.display_ev for b in bet["books"] if b.display_ev is not None]
            if evs:
                return max(evs)
            # Fall back to raw ev_percent if display_ev not set
            raw = [b.ev_percent for b in bet["books"] if b.ev_percent is not None]
            return max(raw) if raw else float("-inf")

        bets_list.sort(key=best_ev, reverse=True)
    elif sort_by == "game_time":
        bets_list.sort(
            key=lambda b: b.get("game_date")
            or datetime.min.replace(tzinfo=UTC)
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
                (b.display_ev is not None and b.display_ev >= min_ev)
                or (b.display_ev is None and b.ev_percent is not None and b.ev_percent >= min_ev)
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

    # Enrich bets with display fields
    for bet in bets_list:
        # BetDefinition-level display fields
        bet["fair_american_odds"] = fair_american_odds(bet.get("true_prob"))
        bet["selection_display"] = selection_display(
            bet.get("selection_key", ""),
            bet.get("market_key", ""),
            home_team=bet.get("home_team"),
            away_team=bet.get("away_team"),
            player_name=bet.get("player_name"),
            line_value=bet.get("line_value"),
        )
        bet["market_display_name"] = market_display_name(bet.get("market_key", ""))
        bet["confidence_display_label"] = confidence_display_label(
            bet.get("ev_confidence_tier")
        )
        bet["ev_method_display_name"] = ev_method_display_name(bet.get("ev_method"))
        bet["ev_method_explanation"] = ev_method_explanation(bet.get("ev_method"))

        # Best book + best EV
        best_ev_val: float | None = None
        best_book_name: str | None = None
        for b in bet["books"]:
            ev_val = b.display_ev if b.display_ev is not None else b.ev_percent
            if ev_val is not None and (best_ev_val is None or ev_val > best_ev_val):
                best_ev_val = ev_val
                best_book_name = b.book
        bet["best_book"] = best_book_name
        bet["best_ev_percent"] = round(best_ev_val, 2) if best_ev_val is not None else None
        bet["is_reliably_positive"] = (
            best_ev_val is not None
            and best_ev_val > 0
            and (bet.get("confidence") or 0) >= 0.7
        )

        # Explanation steps
        best_book_price: float | None = None
        if best_book_name:
            for b in bet["books"]:
                if b.book == best_book_name:
                    best_book_price = b.price
                    break

        bet["explanation_steps"] = build_explanation_steps(
            ev_method=bet.get("ev_method"),
            ev_disabled_reason=bet.get("ev_disabled_reason"),
            true_prob=bet.get("true_prob"),
            reference_price=bet.get("reference_price"),
            opposite_reference_price=bet.get("opposite_reference_price"),
            fair_odds=bet["fair_american_odds"],
            best_book=best_book_name,
            best_book_price=best_book_price,
            best_ev_percent=bet["best_ev_percent"],
            estimated_sharp_price=bet.get("estimated_sharp_price"),
            extrapolation_ref_line=bet.get("extrapolation_ref_line"),
            extrapolation_distance=bet.get("extrapolation_distance"),
            per_book_fair_probs=bet.get("per_book_fair_probs"),
            consensus_iqr=bet.get("consensus_iqr"),
        )

        # BookOdds-level display fields
        enriched_books: list[BookOdds] = []
        for b in bet["books"]:
            abbr = book_abbreviation(b.book)
            # Convert American to decimal: decimal = 1 + |100/price| or 1 + price/100
            price_dec: float | None = None
            try:
                imp = american_to_implied(b.price)
                price_dec = round(1.0 / imp, 3) if imp > 0 else None
            except (ValueError, ZeroDivisionError):
                logger.debug("skipped_invalid_odds_conversion", extra={"price": b.price})
            # EV tier per book
            ev_tier: str | None = None
            ev_val = b.display_ev if b.display_ev is not None else b.ev_percent
            if ev_val is not None:
                if ev_val >= 5.0:
                    ev_tier = "strong_positive"
                elif ev_val >= 0.0:
                    ev_tier = "positive"
                else:
                    ev_tier = "negative"
            elif b.is_sharp:
                ev_tier = "neutral"
            enriched_books.append(
                b.model_copy(update={
                    "book_abbr": abbr,
                    "price_decimal": price_dec,
                    "ev_tier": ev_tier,
                })
            )
        bet["books"] = enriched_books

    return FairbetOddsResponse(
        bets=[BetDefinition(**bet) for bet in bets_list],
        total=total,
        books_available=all_books,
        market_categories_available=all_cats,
        games_available=games_available,
        ev_diagnostics=ev_diagnostics,
        ev_config={
            "min_books_for_display": MIN_BOOKS_FOR_FAIRBET,
            "ev_color_thresholds": {"strong_positive": 5.0, "positive": 0.0},
        },
    )
