"""Odds event processing for timeline generation.

Transforms SportsGameOdds rows into timeline events (opening/closing
lines and significant line movements).

ODDS CONTRACT
=============
- Odds are PREGAME only: all odds events get phase="pregame"
- OPTIONAL: All code must handle zero odds rows gracefully
- NON-AUTHORITATIVE: Odds contextualize, not drive, narratives
- Two rows per (game, book, market, side): one opening, one closing

Handles:
1. Book selection (preferred book priority)
2. Significant movement detection (open vs close delta)
3. Building odds timeline events

Related modules:
- timeline_generator.py: Main timeline assembly
- social_events.py: Peer module for social event processing
- timeline_events.py: PBP event building and timeline merging
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Sequence

from ..db.odds import SportsGameOdds

logger = logging.getLogger(__name__)

# Preferred book priority (first available wins)
PREFERRED_BOOKS = ["fanduel", "draftkings", "betmgm", "caesars"]

# Movement thresholds
SPREAD_MOVEMENT_THRESHOLD = 1.0  # points
TOTAL_MOVEMENT_THRESHOLD = 1.0  # points
MONEYLINE_MOVEMENT_THRESHOLD = 20  # cents (American odds)


# =============================================================================
# BOOK SELECTION
# =============================================================================


def select_preferred_book(odds: Sequence[SportsGameOdds]) -> str | None:
    """Pick a single book for the timeline.

    Priority: fanduel > draftkings > betmgm > caesars.
    Fallback: book with the most rows.
    Returns None for empty odds.
    """
    if not odds:
        return None

    books_present = {row.book for row in odds}

    for book in PREFERRED_BOOKS:
        if book in books_present:
            return book

    # Fallback: book with most rows
    book_counts = Counter(row.book for row in odds)
    return book_counts.most_common(1)[0][0]


# =============================================================================
# MOVEMENT DETECTION
# =============================================================================


def detect_significant_movements(
    odds_for_book: Sequence[SportsGameOdds],
) -> list[dict[str, Any]]:
    """Compare opening vs closing for each (market_type, side).

    Significant movement thresholds:
    - Spread: >= 1.0 pt
    - Total: >= 1.0 pt
    - Moneyline: >= 20 cents (American odds)

    Returns list of movement dicts with market_type, side,
    opening_line, closing_line, movement.
    """
    # Group by (market_type, side)
    pairs: dict[tuple[str, str | None], dict[str, SportsGameOdds]] = {}
    for row in odds_for_book:
        key = (row.market_type, row.side)
        label = "closing" if row.is_closing_line else "opening"
        pairs.setdefault(key, {})[label] = row

    movements: list[dict[str, Any]] = []
    for (market_type, side), pair in pairs.items():
        opening = pair.get("opening")
        closing = pair.get("closing")
        if not opening or not closing:
            continue
        if opening.line is None or closing.line is None:
            continue

        delta = abs(closing.line - opening.line)

        threshold: float
        if market_type == "spread":
            threshold = SPREAD_MOVEMENT_THRESHOLD
        elif market_type == "total":
            threshold = TOTAL_MOVEMENT_THRESHOLD
        elif market_type == "moneyline":
            threshold = MONEYLINE_MOVEMENT_THRESHOLD
        else:
            continue

        if delta >= threshold:
            movements.append(
                {
                    "market_type": market_type,
                    "side": side,
                    "opening_line": opening.line,
                    "closing_line": closing.line,
                    "movement": round(closing.line - opening.line, 2),
                }
            )

    return movements


# =============================================================================
# EVENT BUILDING
# =============================================================================


def _build_markets_dict(
    rows: Sequence[SportsGameOdds],
) -> dict[str, dict[str, Any]]:
    """Build a markets dict from odds rows grouped by market_type."""
    markets: dict[str, dict[str, Any]] = {}
    for row in rows:
        markets[row.market_type] = {
            "side": row.side,
            "line": row.line,
            "price": row.price,
        }
    return markets


def build_odds_events(
    odds: Sequence[SportsGameOdds],
    game_start: datetime,
    phase_boundaries: dict[str, tuple[datetime, datetime]],
) -> list[tuple[datetime, dict[str, Any]]]:
    """Build odds timeline events (opening line, closing line, movement).

    All odds events are assigned phase="pregame".
    Produces up to 3 events:
    - opening_line: earliest observed_at (fallback: game_start - 2h)
    - closing_line: latest closing observed_at (fallback: game_start - 5min)
    - line_movement: only if significant movements detected, midpoint timestamp

    Args:
        odds: SportsGameOdds rows for this game
        game_start: Authoritative game start time
        phase_boundaries: Pre-computed phase boundaries

    Returns:
        List of (timestamp, event_payload) tuples
    """
    if not odds:
        return []

    book = select_preferred_book(odds)
    if book is None:
        return []

    book_odds = [row for row in odds if row.book == book]
    if not book_odds:
        return []

    opening_rows = [row for row in book_odds if not row.is_closing_line]
    closing_rows = [row for row in book_odds if row.is_closing_line]

    events: list[tuple[datetime, dict[str, Any]]] = []

    # Compute pregame phase start for intra_phase_order
    pregame_start = phase_boundaries.get("pregame", (game_start - timedelta(hours=2), game_start))[0]

    # --- Opening line event ---
    if opening_rows:
        observed_times = [r.observed_at for r in opening_rows if r.observed_at is not None]
        open_ts = min(observed_times) if observed_times else game_start - timedelta(hours=2)
        intra_order = (open_ts - pregame_start).total_seconds()

        events.append((
            open_ts,
            {
                "event_type": "odds",
                "phase": "pregame",
                "odds_type": "opening_line",
                "intra_phase_order": intra_order,
                "book": book,
                "markets": _build_markets_dict(opening_rows),
                "synthetic_timestamp": open_ts.isoformat(),
            },
        ))

    # --- Closing line event ---
    if closing_rows:
        observed_times = [r.observed_at for r in closing_rows if r.observed_at is not None]
        close_ts = max(observed_times) if observed_times else game_start - timedelta(minutes=5)
        intra_order = (close_ts - pregame_start).total_seconds()

        events.append((
            close_ts,
            {
                "event_type": "odds",
                "phase": "pregame",
                "odds_type": "closing_line",
                "intra_phase_order": intra_order,
                "book": book,
                "markets": _build_markets_dict(closing_rows),
                "synthetic_timestamp": close_ts.isoformat(),
            },
        ))

    # --- Line movement event (only if significant) ---
    movements = detect_significant_movements(book_odds)
    if movements:
        # Timestamp = midpoint between open and close
        open_ts = events[0][0] if events else game_start - timedelta(hours=2)
        close_ts = events[-1][0] if len(events) > 1 else game_start - timedelta(minutes=5)
        mid_ts = open_ts + (close_ts - open_ts) / 2
        intra_order = (mid_ts - pregame_start).total_seconds()

        events.append((
            mid_ts,
            {
                "event_type": "odds",
                "phase": "pregame",
                "odds_type": "line_movement",
                "intra_phase_order": intra_order,
                "book": book,
                "markets": _build_markets_dict(book_odds),
                "movements": movements,
                "synthetic_timestamp": mid_ts.isoformat(),
            },
        ))

    logger.info(
        "odds_events_built",
        extra={
            "book": book,
            "odds_events": len(events),
            "movements": len(movements) if movements else 0,
        },
    )

    return events


