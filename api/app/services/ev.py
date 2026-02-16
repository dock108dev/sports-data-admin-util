"""Expected Value (EV) calculation engine.

Computes true probabilities by devigging sharp book lines (Pinnacle by default),
then calculates EV% for every book's price on each market.

Uses the eligibility gate from ev_config to determine whether EV can be computed
for a given (league, market_category) pair.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .ev_config import (
    EXCLUDED_BOOKS,
    EVStrategyConfig,
    EligibilityResult,
    get_strategy,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EVComputeResult:
    """Structured return from compute_ev_for_market()."""

    annotated_a: list[dict] = field(default_factory=list)
    annotated_b: list[dict] = field(default_factory=list)
    true_prob_a: float | None = None
    true_prob_b: float | None = None
    reference_price_a: float | None = None
    reference_price_b: float | None = None
    ev_method: str | None = None
    confidence_tier: str | None = None
    fair_odds_suspect: bool = False


def american_to_implied(price: float) -> float:
    """Convert American odds to implied probability (0-1 range).

    Args:
        price: American odds (e.g., -110, +150)

    Returns:
        Implied probability as a float between 0 and 1.
    """
    if price >= 100:
        return 100.0 / (price + 100.0)
    elif price <= -100:
        return abs(price) / (abs(price) + 100.0)
    else:
        raise ValueError(
            f"Invalid American odds: {price} (must be <= -100 or >= +100)"
        )


def implied_to_american(prob: float) -> float:
    """Convert implied probability (0-1) to American odds.

    Args:
        prob: Implied probability as a float between 0 and 1.

    Returns:
        American odds (e.g., -300, +300). Returns 0.0 for degenerate inputs.
    """
    if prob <= 0 or prob >= 1:
        return 0.0
    if prob >= 0.5:
        return -(prob / (1 - prob)) * 100.0
    else:
        return ((1 - prob) / prob) * 100.0


def remove_vig(implied_probs: list[float]) -> list[float]:
    """Remove vig from implied probabilities using additive normalization.

    The sum of implied probabilities from a bookmaker exceeds 1.0 by the vig.
    This function normalizes them to sum to 1.0, giving true probabilities.

    Args:
        implied_probs: List of implied probabilities for all outcomes in a market.

    Returns:
        List of true (no-vig) probabilities summing to 1.0.
    """
    total = sum(implied_probs)
    if total <= 0:
        return implied_probs
    return [p / total for p in implied_probs]


def calculate_ev(book_price: float, true_prob: float) -> float:
    """Calculate expected value percentage for a bet.

    EV% = (true_prob * net_profit) - ((1 - true_prob) * stake)
    Simplified: EV% = (decimal_odds * true_prob) - 1

    Args:
        book_price: American odds offered by the book.
        true_prob: True probability of the outcome (0-1).

    Returns:
        EV as a percentage (e.g., 3.5 means +3.5% EV).
    """
    # Convert to decimal odds
    if book_price >= 100:
        decimal_odds = (book_price / 100.0) + 1.0
    elif book_price <= -100:
        decimal_odds = (100.0 / abs(book_price)) + 1.0
    else:
        raise ValueError(
            f"Invalid American odds: {book_price}. "
            "Must be >= +100 or <= -100."
        )

    return (decimal_odds * true_prob - 1.0) * 100.0


def _find_sharp_entry(
    books: list[dict],
    eligible_sharp_books: tuple[str, ...],
) -> dict | None:
    """Find the first sharp book entry in a list of book dicts.

    Args:
        books: List of {"book": str, "price": float, "observed_at": datetime, ...}.
        eligible_sharp_books: Tuple of eligible sharp book display names.

    Returns:
        The first matching book dict, or None.
    """
    for entry in books:
        if entry["book"] in eligible_sharp_books:
            return entry
    return None


def evaluate_ev_eligibility(
    league_code: str,
    market_category: str,
    side_a_books: list[dict],
    side_b_books: list[dict],
    now: datetime | None = None,
) -> EligibilityResult:
    """Evaluate whether EV can be computed for a two-way market.

    Checks (in order):
    1. Strategy exists for (league, market_category)
    2. Sharp book present on both sides
    3. Sharp book observed_at within max_reference_staleness_seconds of now
    4. >= min_qualifying_books non-excluded books per side

    Args:
        league_code: League code (e.g., "NBA").
        market_category: Market category (e.g., "mainline").
        side_a_books: Book entries for side A.
        side_b_books: Book entries for side B.
        now: Current time (defaults to utcnow, injectable for testing).

    Returns:
        EligibilityResult with eligible=True or disabled_reason explaining why not.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # 1. Strategy exists?
    config = get_strategy(league_code, market_category)
    if config is None:
        return EligibilityResult(
            eligible=False,
            strategy_config=None,
            disabled_reason="no_strategy",
            ev_method=None,
            confidence_tier=None,
        )

    # 2. Sharp book present on both sides?
    sharp_a = _find_sharp_entry(side_a_books, config.eligible_sharp_books)
    sharp_b = _find_sharp_entry(side_b_books, config.eligible_sharp_books)

    if sharp_a is None or sharp_b is None:
        return EligibilityResult(
            eligible=False,
            strategy_config=config,
            disabled_reason="reference_missing",
            ev_method=config.strategy_name,
            confidence_tier=config.confidence_tier.value,
        )

    # 3. Freshness check
    sharp_a_observed = sharp_a.get("observed_at")
    sharp_b_observed = sharp_b.get("observed_at")

    if sharp_a_observed is not None and sharp_b_observed is not None:
        # Use the older of the two timestamps
        oldest = min(sharp_a_observed, sharp_b_observed)
        age_seconds = (now - oldest).total_seconds()
        if age_seconds > config.max_reference_staleness_seconds:
            return EligibilityResult(
                eligible=False,
                strategy_config=config,
                disabled_reason="reference_stale",
                ev_method=config.strategy_name,
                confidence_tier=config.confidence_tier.value,
            )

    # 4. Minimum qualifying books per side (non-excluded)
    qualifying_a = sum(
        1 for b in side_a_books if b["book"] not in EXCLUDED_BOOKS
    )
    qualifying_b = sum(
        1 for b in side_b_books if b["book"] not in EXCLUDED_BOOKS
    )

    if qualifying_a < config.min_qualifying_books or qualifying_b < config.min_qualifying_books:
        return EligibilityResult(
            eligible=False,
            strategy_config=config,
            disabled_reason="insufficient_books",
            ev_method=config.strategy_name,
            confidence_tier=config.confidence_tier.value,
        )

    return EligibilityResult(
        eligible=True,
        strategy_config=config,
        disabled_reason=None,
        ev_method=config.strategy_name,
        confidence_tier=config.confidence_tier.value,
    )


def _median(sorted_values: list[float]) -> float:
    """Return the median of an already-sorted list of floats."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return sorted_values[mid]
    return (sorted_values[mid - 1] + sorted_values[mid]) / 2.0


def compute_ev_for_market(
    side_a_books: list[dict],
    side_b_books: list[dict],
    strategy_config: EVStrategyConfig,
) -> EVComputeResult:
    """Compute EV for all books on both sides of a two-way market.

    Finds the sharp book on each side, devigs to get true probabilities,
    then annotates every book's entry with EV%.

    Args:
        side_a_books: List of {"book": str, "price": float, ...} for side A.
        side_b_books: List of {"book": str, "price": float, ...} for side B.
        strategy_config: The strategy configuration to use.

    Returns:
        EVComputeResult with annotated sides and metadata.
    """
    sharp_books = set(strategy_config.eligible_sharp_books)

    # Find sharp prices on each side
    sharp_a_price: float | None = None
    sharp_b_price: float | None = None

    for entry in side_a_books:
        if entry["book"] in sharp_books:
            sharp_a_price = entry["price"]
            break

    for entry in side_b_books:
        if entry["book"] in sharp_books:
            sharp_b_price = entry["price"]
            break

    # Compute true probabilities if we have both sides from sharp book
    true_prob_a: float | None = None
    true_prob_b: float | None = None

    if sharp_a_price is not None and sharp_b_price is not None:
        implied_a = american_to_implied(sharp_a_price)
        implied_b = american_to_implied(sharp_b_price)
        true_probs = remove_vig([implied_a, implied_b])
        true_prob_a = true_probs[0]
        true_prob_b = true_probs[1]

    # Annotate side A
    annotated_a = []
    for entry in side_a_books:
        result = {**entry}
        result["is_sharp"] = entry["book"] in sharp_books
        result["implied_prob"] = american_to_implied(entry["price"])
        if true_prob_a is not None:
            result["ev_percent"] = round(calculate_ev(entry["price"], true_prob_a), 2)
            result["true_prob"] = round(true_prob_a, 4)
        else:
            result["ev_percent"] = None
            result["true_prob"] = None
        annotated_a.append(result)

    # Annotate side B
    annotated_b = []
    for entry in side_b_books:
        result = {**entry}
        result["is_sharp"] = entry["book"] in sharp_books
        result["implied_prob"] = american_to_implied(entry["price"])
        if true_prob_b is not None:
            result["ev_percent"] = round(calculate_ev(entry["price"], true_prob_b), 2)
            result["true_prob"] = round(true_prob_b, 4)
        else:
            result["ev_percent"] = None
            result["true_prob"] = None
        annotated_b.append(result)

    # Sanity check: compare devigged fair odds against median book price
    fair_odds_suspect = False
    if true_prob_a is not None and true_prob_b is not None:
        fair_american_a = implied_to_american(true_prob_a)
        fair_american_b = implied_to_american(true_prob_b)

        # Compute median price for each side from all books
        prices_a = sorted(entry["price"] for entry in side_a_books)
        prices_b = sorted(entry["price"] for entry in side_b_books)

        if prices_a and prices_b:
            median_a = _median(prices_a)
            median_b = _median(prices_b)

            divergence = max(
                abs(fair_american_a - median_a),
                abs(fair_american_b - median_b),
            )
            if divergence > strategy_config.max_fair_odds_divergence:
                fair_odds_suspect = True

    return EVComputeResult(
        annotated_a=annotated_a,
        annotated_b=annotated_b,
        true_prob_a=true_prob_a,
        true_prob_b=true_prob_b,
        reference_price_a=sharp_a_price,
        reference_price_b=sharp_b_price,
        ev_method=strategy_config.strategy_name,
        confidence_tier=strategy_config.confidence_tier.value,
        fair_odds_suspect=fair_odds_suspect,
    )
