"""Expected Value (EV) calculation engine.

Computes true probabilities by devigging sharp book lines (Pinnacle by default),
then calculates EV% for every book's price on each market.

Sharp book strategy is pluggable: "pinnacle" (single reference) or
"consensus" (future multi-sharp average).
"""

from __future__ import annotations

from typing import Literal

# Default sharp reference book (display name as stored in DB)
SHARP_BOOKS: set[str] = {"Pinnacle"}

# Book keys (API keys) that map to sharp display names
SHARP_BOOK_KEYS: set[str] = {"pinnacle"}

SharpStrategy = Literal["pinnacle", "consensus"]


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
        # Edge case: prices between -100 and +100 shouldn't occur
        # but handle gracefully
        return 0.5


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
        decimal_odds = 2.0  # Fallback

    return (decimal_odds * true_prob - 1.0) * 100.0


def get_reference_prices(
    all_books: list[dict],
    strategy: SharpStrategy = "pinnacle",
) -> list[float] | None:
    """Extract reference sharp book prices for devigging.

    Args:
        all_books: List of dicts with "book" and "price" keys for one side of a market.
        strategy: Which sharp book strategy to use.

    Returns:
        List of American odds prices from the sharp book (one per side),
        or None if no sharp book data is available.
    """
    if strategy == "pinnacle":
        for entry in all_books:
            if entry["book"] in SHARP_BOOKS:
                return [entry["price"]]
        return None
    # Future: "consensus" strategy would average across multiple sharp books
    return None


def compute_ev_for_market(
    side_a_books: list[dict],
    side_b_books: list[dict],
    strategy: SharpStrategy = "pinnacle",
) -> tuple[list[dict], list[dict]]:
    """Compute EV for all books on both sides of a two-way market.

    Finds the sharp book on each side, devigs to get true probabilities,
    then annotates every book's entry with EV%.

    Args:
        side_a_books: List of {"book": str, "price": float, ...} for side A.
        side_b_books: List of {"book": str, "price": float, ...} for side B.
        strategy: Sharp book strategy.

    Returns:
        Tuple of (annotated_side_a, annotated_side_b) with ev_percent,
        implied_prob, and is_sharp fields added.
    """
    # Find Pinnacle prices on each side
    sharp_a_price: float | None = None
    sharp_b_price: float | None = None

    for entry in side_a_books:
        if entry["book"] in SHARP_BOOKS:
            sharp_a_price = entry["price"]
            break

    for entry in side_b_books:
        if entry["book"] in SHARP_BOOKS:
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
        result["is_sharp"] = entry["book"] in SHARP_BOOKS
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
        result["is_sharp"] = entry["book"] in SHARP_BOOKS
        result["implied_prob"] = american_to_implied(entry["price"])
        if true_prob_b is not None:
            result["ev_percent"] = round(calculate_ev(entry["price"], true_prob_b), 2)
            result["true_prob"] = round(true_prob_b, 4)
        else:
            result["ev_percent"] = None
            result["true_prob"] = None
        annotated_b.append(result)

    return annotated_a, annotated_b
