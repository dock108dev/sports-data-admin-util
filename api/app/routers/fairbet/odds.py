"""FairBet odds comparison endpoints.

Provides bet-centric odds views for cross-book comparison with EV annotation.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import selectinload

from ...db import AsyncSession, get_db
from ...db.sports import SportsGame
from ...db.odds import FairbetGameOddsWork
from ...services.ev import (
    american_to_implied,
    calculate_ev,
    compute_ev_for_market,
    evaluate_ev_eligibility,
    implied_to_american,
    remove_vig,
)
from ...services.ev_config import (
    EXCLUDED_BOOKS,
    HALF_POINT_LOGIT_SLOPE,
    MAX_EXTRAPOLATION_HALF_POINTS,
    extrapolation_confidence,
    get_strategy,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class BookOdds(BaseModel):
    """Odds from a single book for a bet."""

    book: str
    price: float
    observed_at: datetime
    ev_percent: float | None = None
    implied_prob: float | None = None
    is_sharp: bool = False
    ev_method: str | None = None
    ev_confidence_tier: str | None = None


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


def _pair_opposite_sides(
    bet_keys: list[tuple],
) -> tuple[list[tuple[tuple, tuple]], list[tuple]]:
    """Pair bet keys that represent opposite sides of a two-way market.

    Two keys are opposite sides when they share (game_id, market_key, abs(line_value))
    but have different selection_keys.

    Returns:
        (pairs, unpaired) — list of (key_a, key_b) pairs + list of unmatched keys.
    """
    pairs: list[tuple[tuple, tuple]] = []
    used: set[int] = set()

    for i, key_a in enumerate(bet_keys):
        if i in used:
            continue
        for j in range(i + 1, len(bet_keys)):
            if j in used:
                continue
            key_b = bet_keys[j]
            # selection_key is index 2 in the tuple (game_id, market_key, selection_key, line_value)
            if key_a[2] != key_b[2]:
                pairs.append((key_a, key_b))
                used.add(i)
                used.add(j)
                break

    unpaired = [bet_keys[i] for i in range(len(bet_keys)) if i not in used]
    return pairs, unpaired


def _annotate_pair_ev(
    key_a: tuple,
    key_b: tuple,
    bets_map: dict[tuple, dict[str, Any]],
) -> str | None:
    """Compute and annotate EV for a single market pair in-place.

    Returns the disabled_reason string if EV was not computed, or None on success.
    """
    books_a = bets_map[key_a]["books"]
    books_b = bets_map[key_b]["books"]
    league_code = bets_map[key_a].get("league_code", "UNKNOWN")
    market_cat = bets_map[key_a].get("market_category", "mainline")

    eligibility = evaluate_ev_eligibility(
        league_code,
        market_cat,
        books_a,
        books_b,
    )

    logger.info(
        "ev_eligibility_result",
        extra={
            "league": league_code,
            "market_category": market_cat,
            "market_key": bets_map[key_a]["market_key"],
            "eligible": eligibility.eligible,
            "disabled_reason": eligibility.disabled_reason,
            "confidence_tier": eligibility.confidence_tier,
            "books_a_count": len(books_a),
            "books_b_count": len(books_b),
            "books_a_names": [b["book"] for b in books_a],
        },
    )

    if eligibility.eligible and eligibility.strategy_config is not None:
        ev_result = compute_ev_for_market(
            books_a,
            books_b,
            eligibility.strategy_config,
        )

        if ev_result.fair_odds_suspect:
            logger.warning(
                "fair_odds_outlier",
                extra={
                    "league": league_code,
                    "market_category": market_cat,
                    "market_key": bets_map[key_a]["market_key"],
                },
            )
            # Devig produced implausible fair odds — skip EV annotation
            sharp = set(eligibility.strategy_config.eligible_sharp_books)
            for key in (key_a, key_b):
                bets_map[key]["ev_disabled_reason"] = "fair_odds_outlier"
                bets_map[key]["ev_confidence_tier"] = ev_result.confidence_tier
                bets_map[key]["ev_method"] = ev_result.ev_method
                bets_map[key]["books"] = [
                    BookOdds(
                        book=b["book"],
                        price=b["price"],
                        observed_at=b["observed_at"],
                        is_sharp=b["book"] in sharp,
                    )
                    for b in bets_map[key]["books"]
                ]
            return "fair_odds_outlier"

        # Update with annotated data
        bets_map[key_a]["books"] = [
            BookOdds(
                book=b["book"],
                price=b["price"],
                observed_at=b["observed_at"],
                ev_percent=b.get("ev_percent"),
                implied_prob=round(b.get("implied_prob", 0), 4)
                if b.get("implied_prob")
                else None,
                is_sharp=b.get("is_sharp", False),
                ev_method=ev_result.ev_method,
                ev_confidence_tier=ev_result.confidence_tier,
            )
            for b in ev_result.annotated_a
        ]
        bets_map[key_b]["books"] = [
            BookOdds(
                book=b["book"],
                price=b["price"],
                observed_at=b["observed_at"],
                ev_percent=b.get("ev_percent"),
                implied_prob=round(b.get("implied_prob", 0), 4)
                if b.get("implied_prob")
                else None,
                is_sharp=b.get("is_sharp", False),
                ev_method=ev_result.ev_method,
                ev_confidence_tier=ev_result.confidence_tier,
            )
            for b in ev_result.annotated_b
        ]

        # Set true_prob and EV metadata on the bet definition
        if (
            ev_result.annotated_a
            and ev_result.annotated_a[0].get("true_prob") is not None
        ):
            bets_map[key_a]["true_prob"] = ev_result.annotated_a[0]["true_prob"]
        if (
            ev_result.annotated_b
            and ev_result.annotated_b[0].get("true_prob") is not None
        ):
            bets_map[key_b]["true_prob"] = ev_result.annotated_b[0]["true_prob"]

        bets_map[key_a]["reference_price"] = ev_result.reference_price_a
        bets_map[key_a]["opposite_reference_price"] = ev_result.reference_price_b
        bets_map[key_b]["reference_price"] = ev_result.reference_price_b
        bets_map[key_b]["opposite_reference_price"] = ev_result.reference_price_a

        bets_map[key_a]["ev_method"] = ev_result.ev_method
        bets_map[key_a]["ev_confidence_tier"] = ev_result.confidence_tier
        bets_map[key_b]["ev_method"] = ev_result.ev_method
        bets_map[key_b]["ev_confidence_tier"] = ev_result.confidence_tier

        bets_map[key_a]["has_fair"] = True
        bets_map[key_b]["has_fair"] = True
        return None
    else:
        # Not eligible: attach disabled metadata, convert books to BookOdds
        sharp = (
            set(eligibility.strategy_config.eligible_sharp_books)
            if eligibility.strategy_config
            else set()
        )
        for key in (key_a, key_b):
            bets_map[key]["ev_disabled_reason"] = eligibility.disabled_reason
            bets_map[key]["ev_confidence_tier"] = eligibility.confidence_tier
            bets_map[key]["ev_method"] = eligibility.ev_method
            bets_map[key]["books"] = [
                BookOdds(
                    book=b["book"],
                    price=b["price"],
                    observed_at=b["observed_at"],
                    is_sharp=b["book"] in sharp,
                )
                for b in bets_map[key]["books"]
            ]
        return eligibility.disabled_reason


def _market_base(market_key: str) -> str | None:
    """Normalize market_key to base type for extrapolation.

    Args:
        market_key: Raw market key (e.g., "spreads", "alternate_spreads", "totals").

    Returns:
        "spreads" or "totals" for extrapolatable markets, None otherwise.
    """
    lower = market_key.lower()
    if "spread" in lower:
        return "spreads"
    if "total" in lower:
        return "totals"
    return None


def _build_sharp_reference(
    bets_map: dict[tuple, dict[str, Any]],
    sharp_book_names: set[str],
) -> dict[tuple[int, str], list[dict[str, Any]]]:
    """Pre-compute sharp reference index from all bets that have Pinnacle.

    Scans bets_map for entries where a sharp book is present. Groups by
    (game_id, market_base, abs(line_value)). For each group with two different
    selection_keys (both sides), devigs the sharp book's prices.

    Args:
        bets_map: The full bets map keyed by (game_id, market_key, selection_key, line_value).
        sharp_book_names: Set of sharp book display names (e.g., {"Pinnacle"}).

    Returns:
        Dict keyed by (game_id, market_base) → list of reference lines sorted by
        mainline preference. Each entry has abs_line, is_mainline, probs, prices.
    """
    # Step 1: Collect sharp book entries grouped by (game_id, market_base, abs_line)
    # Each group entry: (selection_key, sharp_price, market_key)
    sharp_groups: dict[tuple[int, str, float], list[tuple[str, float, str]]] = {}

    for key, bet in bets_map.items():
        game_id_k, market_key_k, selection_key_k, line_value_k = key
        mbase = _market_base(market_key_k)
        if mbase is None:
            continue

        # Find sharp book entry
        books = bet["books"]
        sharp_price = None
        for b in books:
            book_name = b["book"] if isinstance(b, dict) else b.book
            if book_name in sharp_book_names:
                sharp_price = b["price"] if isinstance(b, dict) else b.price
                break
        if sharp_price is None:
            continue

        group_key = (game_id_k, mbase, abs(line_value_k))
        if group_key not in sharp_groups:
            sharp_groups[group_key] = []
        sharp_groups[group_key].append((selection_key_k, sharp_price, market_key_k))

    # Step 2: For each group with two sides, devig and store
    refs: dict[tuple[int, str], list[dict[str, Any]]] = {}

    for (game_id, mbase, abs_line), entries in sharp_groups.items():
        # Need exactly two different selection_keys
        by_selection: dict[str, tuple[float, str]] = {}
        for sel_key, price, mkey in entries:
            if sel_key not in by_selection:
                by_selection[sel_key] = (price, mkey)

        if len(by_selection) != 2:
            continue

        selections = list(by_selection.keys())
        price_a, mkey_a = by_selection[selections[0]]
        price_b, mkey_b = by_selection[selections[1]]

        try:
            implied_a = american_to_implied(price_a)
            implied_b = american_to_implied(price_b)
            true_probs = remove_vig([implied_a, implied_b])
        except ValueError:
            continue

        # Determine if this is a mainline market_key (not "alternate_*")
        is_mainline = not mkey_a.lower().startswith("alternate")

        ref_entry: dict[str, Any] = {
            "abs_line": abs_line,
            "is_mainline": is_mainline,
            "probs": {selections[0]: true_probs[0], selections[1]: true_probs[1]},
            "prices": {selections[0]: price_a, selections[1]: price_b},
        }

        ref_key = (game_id, mbase)
        if ref_key not in refs:
            refs[ref_key] = []
        refs[ref_key].append(ref_entry)

    # Step 3: Sort each list — mainline first, then by abs_line
    for ref_key in refs:
        refs[ref_key].sort(key=lambda r: (not r["is_mainline"], r["abs_line"]))

    return refs


def _try_extrapolated_ev(
    key_a: tuple,
    key_b: tuple,
    bets_map: dict[tuple, dict[str, Any]],
    sharp_refs: dict[tuple[int, str], list[dict[str, Any]]],
) -> str | None:
    """Attempt to compute EV via logit-space extrapolation from a sharp reference.

    Called as a fallback when _annotate_pair_ev returns "reference_missing".
    Uses the closest available Pinnacle reference line and extrapolates
    true probabilities to the target line using logit-space shifts.

    Args:
        key_a: Bet key tuple for side A.
        key_b: Bet key tuple for side B.
        bets_map: The full bets map (mutated in-place).
        sharp_refs: Pre-computed sharp reference index.

    Returns:
        None on success (EV annotated), or a disabled_reason string.
    """
    game_id = key_a[0]
    market_key = bets_map[key_a]["market_key"]
    league_code = bets_map[key_a].get("league_code", "UNKNOWN")

    # 1. Get market base — skip non-extrapolatable markets
    mbase = _market_base(market_key)
    if mbase is None:
        return "reference_missing"

    # 2. Look up sharp references for this game + market type
    ref_key = (game_id, mbase)
    ref_list = sharp_refs.get(ref_key)
    if not ref_list:
        return "reference_missing"

    # 3. Get target abs line
    target_abs_line = abs(key_a[3])  # line_value from key tuple

    # 4. Find closest reference line; break ties by preferring mainline
    best_ref = None
    best_distance = float("inf")
    for ref in ref_list:
        distance = abs(ref["abs_line"] - target_abs_line)
        # Skip if this IS the exact same line (should have been handled by direct devig)
        if distance == 0:
            continue
        if distance < best_distance or (
            distance == best_distance and ref["is_mainline"] and best_ref and not best_ref["is_mainline"]
        ):
            best_ref = ref
            best_distance = distance

    if best_ref is None:
        return "reference_missing"

    # 5. Match selection_keys between reference and target
    sel_a = key_a[2]  # selection_key
    sel_b = key_b[2]
    if sel_a not in best_ref["probs"] or sel_b not in best_ref["probs"]:
        return "reference_missing"

    # 6. Compute half-point distance and check max
    n_half_points = (target_abs_line - best_ref["abs_line"]) / 0.5

    max_hp = MAX_EXTRAPOLATION_HALF_POINTS.get(league_code)
    if max_hp is None:
        return "reference_missing"
    if abs(n_half_points) > max_hp:
        return "extrapolation_out_of_range"

    # 7. Get logit slope for this sport + market
    sport_slopes = HALF_POINT_LOGIT_SLOPE.get(league_code)
    if sport_slopes is None:
        return "reference_missing"
    slope = sport_slopes.get(mbase)
    if slope is None:
        return "reference_missing"

    # 8. Logit-space extrapolation
    base_prob_a = best_ref["probs"][sel_a]
    base_prob_b = best_ref["probs"][sel_b]

    # Clamp base probs to avoid log(0) — shouldn't happen from devig but be safe
    base_prob_a = max(0.001, min(0.999, base_prob_a))
    base_prob_b = max(0.001, min(0.999, base_prob_b))

    base_logit_a = math.log(base_prob_a / (1 - base_prob_a))

    # For spreads: wider line (higher abs) means the favorite is LESS likely to cover.
    # sel_a is the favorite side (negative line_value) → logit decreases with positive n_half_points.
    # For totals: higher line means LESS likely to go over → same direction.
    # This sign convention works because n_half_points is positive when target > ref,
    # meaning the line moved away from the favorite/over.
    new_logit_a = base_logit_a - (n_half_points * slope)
    extrap_prob_a = 1.0 / (1.0 + math.exp(-new_logit_a))
    extrap_prob_b = 1.0 - extrap_prob_a  # By construction, sums to 1.0

    # 9. Confidence tier
    confidence = extrapolation_confidence(n_half_points)

    # 10. Reference prices from the chosen ref (for display)
    ref_price_a = best_ref["prices"].get(sel_a)
    ref_price_b = best_ref["prices"].get(sel_b)

    # 11. Annotate books on both sides
    for key, true_prob, ref_price, opp_ref_price in [
        (key_a, extrap_prob_a, ref_price_a, ref_price_b),
        (key_b, extrap_prob_b, ref_price_b, ref_price_a),
    ]:
        bet = bets_map[key]
        new_books: list[BookOdds] = []
        for b in bet["books"]:
            # Handle both dict and BookOdds (already converted by _annotate_pair_ev)
            if isinstance(b, dict):
                book_name = b["book"]
                price = b["price"]
                observed_at = b["observed_at"]
            else:
                book_name = b.book
                price = b.price
                observed_at = b.observed_at

            try:
                ev_pct = round(calculate_ev(price, true_prob), 2)
                impl_prob = round(american_to_implied(price), 4)
            except ValueError:
                ev_pct = None
                impl_prob = None

            new_books.append(
                BookOdds(
                    book=book_name,
                    price=price,
                    observed_at=observed_at,
                    ev_percent=ev_pct,
                    implied_prob=impl_prob,
                    is_sharp=book_name == "Pinnacle",
                    ev_method="pinnacle_extrapolated",
                    ev_confidence_tier=confidence,
                )
            )

        bet["books"] = new_books
        bet["true_prob"] = round(true_prob, 4)
        bet["reference_price"] = ref_price
        bet["opposite_reference_price"] = opp_ref_price
        bet["ev_method"] = "pinnacle_extrapolated"
        bet["ev_confidence_tier"] = confidence
        bet["has_fair"] = True
        bet["ev_disabled_reason"] = None

    return None


def _build_base_filters(
    league: str | None,
    market_category: str | None = None,
    game_id: int | None = None,
    book: str | None = None,
    player_name: str | None = None,
    excluded_books: frozenset[str] | None = None,
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

    if excluded_books:
        conditions.append(FairbetGameOddsWork.book.notin_(excluded_books))

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
        excluded_books=EXCLUDED_BOOKS,
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

    # When post-annotation filters are active (has_fair, min_ev), we must fetch
    # ALL bet definitions, annotate, filter, then paginate in Python.  Otherwise
    # DB-level pagination would silently drop matching bets from other pages and
    # report a total that doesn't reflect the filter.
    needs_post_filter = has_fair is not None or min_ev is not None

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
    if not needs_post_filter:
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
        .where(FairbetGameOddsWork.book.notin_(EXCLUDED_BOOKS))
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

    if needs_post_filter:
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
