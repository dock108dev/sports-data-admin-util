"""FairBet odds work table utilities.

This module provides:
1. selection_key generation for book-agnostic bet identification
2. Upsert logic for the fairbet_game_odds_work table

Selection Key Format
--------------------
{entity_type}:{entity_slug}

The selection_key identifies WHAT is being bet on (team or total direction),
while market_key identifies the bet TYPE (h2h, spreads, totals).

Examples:
- team:los_angeles_lakers (bet on Lakers - used for both moneyline and spread)
- total:over (game total over)
- total:under (game total under)

The same selection_key can appear with different market_keys:
- game_id=1, market_key="h2h", selection_key="team:lakers" (moneyline)
- game_id=1, market_key="spreads", selection_key="team:lakers" (spread)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ..models import NormalizedOddsSnapshot


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug.

    Examples:
        "Los Angeles Lakers" -> "los_angeles_lakers"
        "Over" -> "over"
        "LeBron James" -> "lebron_james"
    """
    if not text:
        return ""
    # Lowercase
    slug = text.lower()
    # Replace spaces and hyphens with underscores
    slug = re.sub(r"[\s\-]+", "_", slug)
    # Remove non-alphanumeric except underscores
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug)
    # Strip leading/trailing underscores
    slug = slug.strip("_")
    return slug


def build_selection_key(
    market_type: str,
    side: str | None,
    home_team_name: str,
    away_team_name: str,
    player_name: str | None = None,
    market_category: str = "mainline",
) -> str:
    """Build a deterministic, book-agnostic selection key.

    Args:
        market_type: Canonical market type (moneyline, spread, total, or prop key)
        side: The side/outcome (team name, "Over", "Under", etc.)
        home_team_name: Home team name for context
        away_team_name: Away team name for context
        player_name: Player name for player props
        market_category: Market category (mainline, player_prop, etc.)

    Returns:
        A selection key like "team:lakers", "total:over", or "player:lebron_james:over"
    """
    if not side:
        return "unknown"

    side_lower = side.lower()
    side_slug = slugify(side)

    # Player prop bets: player:{player_slug}:over/under
    if market_category == "player_prop" and player_name:
        player_slug = slugify(player_name)
        if "over" in side_lower:
            return f"player:{player_slug}:over"
        elif "under" in side_lower:
            return f"player:{player_slug}:under"
        else:
            return f"player:{player_slug}:{side_slug}"

    # Total bets (mainline or team_prop): Over/Under
    if market_type == "total" or market_category == "team_prop" or market_type.startswith("team_total"):
        if "over" in side_lower:
            return "total:over"
        elif "under" in side_lower:
            return "total:under"
        else:
            return f"total:{side_slug}"

    # Team bets: Moneyline/Spread
    # Try to match side to home or away team
    home_slug = slugify(home_team_name)
    away_slug = slugify(away_team_name)

    # Check if side matches either team
    if side_slug == home_slug or home_team_name.lower() in side_lower or side_lower in home_team_name.lower():
        return f"team:{home_slug}"
    elif side_slug == away_slug or away_team_name.lower() in side_lower or side_lower in away_team_name.lower():
        return f"team:{away_slug}"
    else:
        # Fallback: use side directly
        return f"team:{side_slug}"


def upsert_fairbet_odds(
    session: "Session",
    game_id: int,
    game_status: str,
    snapshot: "NormalizedOddsSnapshot",
) -> bool:
    """Upsert odds into the FairBet work table.

    Only inserts for non-completed games (scheduled, live).

    Args:
        session: Database session
        game_id: The matched game ID
        game_status: Current game status
        snapshot: The normalized odds snapshot

    Returns:
        True if upserted, False if skipped (game completed)
    """
    # Import dependencies at runtime to avoid circular imports
    # and allow pure functions to be tested without DB setup
    from sqlalchemy.dialects.postgresql import insert

    from ..db import db_models
    from ..logging import logger
    from ..utils.datetime_utils import now_utc

    # Only insert for non-completed games
    if game_status in ("final", "completed"):
        return False

    # Look up game's actual teams from DB (not the Odds API snapshot)
    # This prevents wrong team names from bleeding into fairbet_game_odds_work
    # when a game is mis-matched by fuzzy name matching.
    game = session.get(db_models.SportsGame, game_id)
    if not game:
        logger.warning("fairbet_skip_game_not_found", game_id=game_id)
        return False
    home_team = session.get(db_models.SportsTeam, game.home_team_id)
    away_team = session.get(db_models.SportsTeam, game.away_team_id)
    if not home_team or not away_team:
        logger.warning(
            "fairbet_skip_team_not_found",
            game_id=game_id,
            home_team_id=game.home_team_id,
            away_team_id=game.away_team_id,
        )
        return False

    # Build selection key using DB team names for consistent keys
    selection_key = build_selection_key(
        market_type=snapshot.market_type,
        side=snapshot.side,
        home_team_name=home_team.name,
        away_team_name=away_team.name,
        player_name=snapshot.player_name,
        market_category=snapshot.market_category,
    )

    # Validation guard: for team bets (moneyline/spread), if the selection key
    # fell through to the fallback path (side didn't match either DB team),
    # it means the snapshot's team doesn't belong to this game — skip it.
    is_team_bet = snapshot.market_type in ("moneyline", "spread") or (
        snapshot.market_category == "mainline"
        and snapshot.market_type not in ("total",)
        and snapshot.source_key in ("h2h", "spreads")
    )
    if is_team_bet and selection_key.startswith("team:"):
        home_slug = slugify(home_team.name)
        away_slug = slugify(away_team.name)
        key_slug = selection_key.removeprefix("team:")
        if key_slug != home_slug and key_slug != away_slug:
            logger.warning(
                "fairbet_skip_team_mismatch",
                game_id=game_id,
                selection_key=selection_key,
                home_team=home_team.name,
                away_team=away_team.name,
                snapshot_side=snapshot.side,
            )
            return False

    # Use source_key as market_key (e.g., "h2h", "spreads", "totals")
    # Fall back to market_type if source_key not available
    market_key = snapshot.source_key or snapshot.market_type

    # Use 0 as sentinel for NULL line (moneyline)
    line_value = snapshot.line if snapshot.line is not None else 0.0

    # Price must be present
    if snapshot.price is None:
        logger.debug(
            "fairbet_skip_no_price",
            game_id=game_id,
            market_key=market_key,
            selection_key=selection_key,
        )
        return False

    stmt = (
        insert(db_models.FairbetGameOddsWork)
        .values(
            game_id=game_id,
            market_key=market_key,
            selection_key=selection_key,
            line_value=line_value,
            book=snapshot.book,
            price=snapshot.price,
            observed_at=snapshot.observed_at,
            market_category=snapshot.market_category,
            player_name=snapshot.player_name,
            updated_at=now_utc(),
        )
        .on_conflict_do_update(
            index_elements=["game_id", "market_key", "selection_key", "line_value", "book"],
            set_={
                "price": snapshot.price,
                "observed_at": snapshot.observed_at,
                "market_category": snapshot.market_category,
                "player_name": snapshot.player_name,
                "updated_at": now_utc(),
            },
        )
    )

    session.execute(stmt)
    return True
