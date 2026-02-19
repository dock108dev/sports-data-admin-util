"""Pure-computation EV annotation helpers for FairBet odds.

Contains the BookOdds model and five stateless helpers that annotate
bets with expected-value data.  These have no dependency on FastAPI,
SQLAlchemy, or the database — they operate entirely on in-memory dicts.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ...services.ev import (
    american_to_implied,
    calculate_ev,
    compute_ev_for_market,
    evaluate_ev_eligibility,
    implied_to_american,
    prob_to_vigged_american,
    remove_vig,
)
from ...services.ev_config import (
    HALF_POINT_LOGIT_SLOPE,
    INCLUDED_BOOKS,
    MAINLINE_DISAGREEMENT_MAX_POINTS,
    MAX_EXTRAPOLATED_PROB_DIVERGENCE,
    MAX_EXTRAPOLATION_HALF_POINTS,
    SHARP_REF_MAX_AGE_SECONDS,
    extrapolation_confidence,
    get_fairbet_debug_game_ids,
)

logger = logging.getLogger(__name__)


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
            # selection_key is index 2, line_value is index 3
            # in the tuple (game_id, market_key, selection_key, line_value)
            if key_a[2] == key_b[2]:
                continue  # Same selection_key — not opposite sides
            # Line values must be compatible to be the same market:
            # Spreads: sum to ~0 (e.g., -3.5 and +3.5)
            # Totals/ML: equal non-negative (e.g., both 200.5 or both 0)
            line_a, line_b = key_a[3], key_b[3]
            lines_sum_to_zero = abs(line_a + line_b) < 0.01
            lines_equal_nonneg = (
                abs(line_a - line_b) < 0.01 and line_a >= 0 and line_b >= 0
            )
            if lines_sum_to_zero or lines_equal_nonneg:
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
        market_key: Raw market key (e.g., "spreads", "alternate_spreads", "totals",
                     "team_totals").

    Returns:
        "spreads", "totals", or "team_totals" for extrapolatable markets,
        None otherwise.
    """
    lower = market_key.lower()
    if "spread" in lower:
        return "spreads"
    # "team_total" check MUST come before "total" since "team_totals" contains "total"
    if "team_total" in lower:
        return "team_totals"
    if "total" in lower:
        return "totals"
    return None


def _build_sharp_reference(
    bets_map: dict[tuple, dict[str, Any]],
    sharp_book_names: set[str],
    max_age_seconds: int | None = None,
) -> dict[tuple[int, str], list[dict[str, Any]]]:
    """Pre-compute sharp reference index from all bets that have Pinnacle.

    Scans bets_map for entries where a sharp book is present. Groups by
    (game_id, market_base, abs(line_value)). For each group with two different
    selection_keys (both sides), devigs the sharp book's prices.

    Args:
        bets_map: The full bets map keyed by (game_id, market_key, selection_key, line_value).
        sharp_book_names: Set of sharp book display names (e.g., {"Pinnacle"}).
        max_age_seconds: If set, discard sharp entries whose observed_at is
            older than ``now - max_age_seconds``.

    Returns:
        Dict keyed by (game_id, market_base) → list of reference lines sorted by
        mainline preference. Each entry has abs_line, is_mainline, probs, prices,
        observed_at.
    """
    from datetime import timezone as _tz

    now = datetime.now(_tz.utc)

    # Step 1: Collect sharp book entries grouped by (game_id, market_base, abs_line)
    # Each group entry: (selection_key, sharp_price, market_key, signed_line_value, observed_at)
    sharp_groups: dict[
        tuple[int, str, float], list[tuple[str, float, str, float, datetime]]
    ] = {}

    for key, bet in bets_map.items():
        game_id_k, market_key_k, selection_key_k, line_value_k = key
        mbase = _market_base(market_key_k)
        if mbase is None:
            continue

        # Find sharp book entry
        books = bet["books"]
        sharp_price = None
        sharp_observed_at = None
        for b in books:
            book_name = b["book"] if isinstance(b, dict) else b.book
            if book_name in sharp_book_names:
                sharp_price = b["price"] if isinstance(b, dict) else b.price
                sharp_observed_at = (
                    b["observed_at"] if isinstance(b, dict) else b.observed_at
                )
                break
        if sharp_price is None:
            continue

        # Staleness check
        if max_age_seconds is not None and sharp_observed_at is not None:
            age = (now - sharp_observed_at).total_seconds()
            if age > max_age_seconds:
                continue

        group_key = (game_id_k, mbase, abs(line_value_k))
        if group_key not in sharp_groups:
            sharp_groups[group_key] = []
        sharp_groups[group_key].append(
            (selection_key_k, sharp_price, market_key_k, line_value_k, sharp_observed_at)
        )

    # Step 2: For each group, find valid pairs (compatible line values) and devig
    refs: dict[tuple[int, str], list[dict[str, Any]]] = {}

    for (game_id, mbase, abs_line), entries in sharp_groups.items():
        # Pair entries with compatible line values using the same logic as
        # _pair_opposite_sides: different selection_key AND lines sum to ~0 or equal
        used: set[int] = set()
        valid_pairs: list[tuple[int, int]] = []
        for i in range(len(entries)):
            if i in used:
                continue
            for j_idx in range(i + 1, len(entries)):
                if j_idx in used:
                    continue
                sel_i, _, _, line_i, _ = entries[i]
                sel_j, _, _, line_j, _ = entries[j_idx]
                if sel_i == sel_j:
                    continue
                lines_sum_zero = abs(line_i + line_j) < 0.01
                lines_eq_nonneg = (
                    abs(line_i - line_j) < 0.01 and line_i >= 0 and line_j >= 0
                )
                if lines_sum_zero or lines_eq_nonneg:
                    valid_pairs.append((i, j_idx))
                    used.add(i)
                    used.add(j_idx)
                    break

        for idx_a, idx_b in valid_pairs:
            sel_a, price_a, mkey_a, line_a, obs_at_a = entries[idx_a]
            sel_b, price_b, mkey_b, line_b, _ = entries[idx_b]

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
                "probs": {sel_a: true_probs[0], sel_b: true_probs[1]},
                "prices": {sel_a: price_a, sel_b: price_b},
                "signed_lines": {sel_a: line_a, sel_b: line_b},
                "observed_at": obs_at_a,
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
        if distance < 1e-9:
            continue
        if distance < best_distance or (
            distance == best_distance and ref["is_mainline"] and best_ref and not best_ref["is_mainline"]
        ):
            best_ref = ref
            best_distance = distance

    if best_ref is None:
        return "reference_missing"

    # 4b. MAINLINE DISAGREEMENT CHECK: If both the target bet and the
    # reference are mainlines, this is cross-book line disagreement (e.g.,
    # Pinnacle 148.5 vs FanDuel 142.5), NOT an alternate relationship.
    # Extrapolation is invalid here — reject it.
    bet_is_mainline = not market_key.lower().startswith("alternate")
    if (
        bet_is_mainline
        and best_ref["is_mainline"]
        and best_distance > MAINLINE_DISAGREEMENT_MAX_POINTS
    ):
        logger.warning(
            "mainline_line_disagreement",
            extra={
                "game_id": game_id,
                "market_key": market_key,
                "target_line": target_abs_line,
                "ref_line": best_ref["abs_line"],
                "distance_points": round(best_distance, 1),
            },
        )
        return "mainline_line_disagreement"

    # 5. Match selection_keys between reference and target
    sel_a = key_a[2]  # selection_key
    sel_b = key_b[2]
    if sel_a not in best_ref["probs"] or sel_b not in best_ref["probs"]:
        return "reference_missing"

    # 6. Compute SIGNED half-point shift.
    #
    # The direction of the logit shift depends on which side sel_a is:
    #   Spreads: positive line (getting points) → prob increases with higher line
    #            negative line (giving points)  → prob decreases with higher line
    #   Totals:  "under" → prob increases with higher line
    #            "over"  → prob decreases with higher line
    #
    # Using signed line values (for spreads) or over/under semantics (for totals)
    # ensures the shift direction is always correct regardless of pairing order.
    if mbase == "spreads":
        ref_signed_line_a = best_ref["signed_lines"][sel_a]
        target_signed_line_a = key_a[3]
        n_half_points = (target_signed_line_a - ref_signed_line_a) / 0.5
    else:  # totals — both sides share the same positive line value
        abs_shift = (target_abs_line - best_ref["abs_line"]) / 0.5
        # Over: prob decreases with higher line → negate shift
        # Under: prob increases with higher line → keep shift
        if "under" in sel_a.lower():
            n_half_points = abs_shift
        else:
            n_half_points = -abs_shift

    hp_map = MAX_EXTRAPOLATION_HALF_POINTS.get(league_code)
    if hp_map is None:
        return "reference_missing"
    max_hp = hp_map.get(mbase)
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

    # Clamp to avoid log(0) — shouldn't happen from devig but be safe
    base_prob_a = max(0.001, min(0.999, base_prob_a))

    base_logit_a = math.log(base_prob_a / (1 - base_prob_a))

    # n_half_points is now signed so that positive always means "sel_a prob
    # should increase" and negative means "sel_a prob should decrease".
    new_logit_a = base_logit_a + (n_half_points * slope)
    extrap_prob_a = 1.0 / (1.0 + math.exp(-new_logit_a))
    extrap_prob_b = 1.0 - extrap_prob_a  # By construction, sums to 1.0

    # 8b. SANITY CHECK: If Pinnacle is present on the target line,
    # the extrapolated true prob must NOT exceed Pinnacle's vigged implied prob.
    # If it does, the extrapolation overshot — reject it.
    for key, extrap_prob in [(key_a, extrap_prob_a), (key_b, extrap_prob_b)]:
        bet = bets_map[key]
        for b in bet["books"]:
            book_name = b["book"] if isinstance(b, dict) else b.book
            price = b["price"] if isinstance(b, dict) else b.price
            if book_name == "Pinnacle":
                try:
                    pinnacle_implied = american_to_implied(price)
                    if extrap_prob > pinnacle_implied:
                        # Our "no-vig" prob exceeds Pinnacle's vigged prob — impossible
                        return "extrapolation_exceeds_pinnacle"
                except ValueError:
                    pass

    # 8c. DIVERGENCE CHECK: Compare extrapolated fair prob against median
    # implied prob across non-sharp books.  Catches phantom EV from
    # long-distance extrapolation drift (e.g., fair 80% vs market 53%).
    for key, extrap_prob in [(key_a, extrap_prob_a), (key_b, extrap_prob_b)]:
        bet = bets_map[key]
        non_sharp_implieds: list[float] = []
        for b in bet["books"]:
            book_name = b["book"] if isinstance(b, dict) else b.book
            price = b["price"] if isinstance(b, dict) else b.price
            if book_name == "Pinnacle":
                continue
            if book_name not in INCLUDED_BOOKS:
                continue
            try:
                non_sharp_implieds.append(american_to_implied(price))
            except ValueError:
                continue
        if non_sharp_implieds:
            non_sharp_implieds.sort()
            n = len(non_sharp_implieds)
            mid = n // 2
            median_implied = (
                non_sharp_implieds[mid]
                if n % 2 == 1
                else (non_sharp_implieds[mid - 1] + non_sharp_implieds[mid]) / 2.0
            )
            if abs(extrap_prob - median_implied) > MAX_EXTRAPOLATED_PROB_DIVERGENCE:
                logger.warning(
                    "extrapolation_fair_divergence",
                    extra={
                        "game_id": game_id,
                        "market_key": market_key,
                        "extrap_prob": round(extrap_prob, 4),
                        "median_implied": round(median_implied, 4),
                        "divergence": round(abs(extrap_prob - median_implied), 4),
                        "n_half_points": round(n_half_points, 1),
                        "ref_line": best_ref["abs_line"],
                        "target_line": target_abs_line,
                    },
                )
                return "extrapolation_fair_divergence"

    # 8d. TARGETED DEBUG LOGGING (game-ID toggle)
    _debug_ids = get_fairbet_debug_game_ids()
    if game_id in _debug_ids:
        _book_prices_a = [
            (b["book"] if isinstance(b, dict) else b.book,
             b["price"] if isinstance(b, dict) else b.price)
            for b in bets_map[key_a]["books"]
        ]
        logger.info(
            "fairbet_extrapolation_debug",
            extra={
                "game_id": game_id,
                "market_key": market_key,
                "selection_key_a": sel_a,
                "line_value_a": key_a[3],
                "ref_line": best_ref["abs_line"],
                "ref_is_mainline": best_ref["is_mainline"],
                "ref_observed_at": str(best_ref.get("observed_at")),
                "distance_points": round(best_distance, 2),
                "n_half_points": round(n_half_points, 1),
                "base_prob_a": round(base_prob_a, 4),
                "extrap_prob_a": round(extrap_prob_a, 4),
                "extrap_prob_b": round(extrap_prob_b, 4),
                "book_prices_a": _book_prices_a,
                "block_reason": None,
            },
        )

    # 9. Confidence tier
    confidence = extrapolation_confidence(n_half_points)

    # 10. Reference prices from the chosen ref (for display)
    ref_price_a = best_ref["prices"].get(sel_a)
    ref_price_b = best_ref["prices"].get(sel_b)

    # 10b. Estimated Pinnacle prices at the target line
    est_price_a = round(prob_to_vigged_american(extrap_prob_a))
    est_price_b = round(prob_to_vigged_american(extrap_prob_b))

    # 11. Annotate books on both sides
    for key, true_prob, ref_price, opp_ref_price, est_price in [
        (key_a, extrap_prob_a, ref_price_a, ref_price_b, est_price_a),
        (key_b, extrap_prob_b, ref_price_b, ref_price_a, est_price_b),
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
        bet["estimated_sharp_price"] = est_price
        bet["extrapolation_ref_line"] = best_ref["abs_line"]
        bet["extrapolation_distance"] = round(abs(n_half_points), 1)

    return None
