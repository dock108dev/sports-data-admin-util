"""Parsing helpers for Odds API responses.

Extracts normalized odds snapshots from raw API event data.
Split from client.py for maintainability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..logging import logger
from ..models import NormalizedOddsSnapshot, TeamIdentity, classify_market
from ..normalization import normalize_team_name

# US sports use Eastern Time for game dates
US_EASTERN = ZoneInfo("America/New_York")

# Books in scope for odds ingestion — only these are persisted.
# Matches INCLUDED_BOOKS in api/app/services/ev_config.py.
ALLOWED_BOOKS: frozenset[str] = frozenset(
    {
        # US sportsbooks
        "BetMGM",
        "BetRivers",
        "Caesars",
        "DraftKings",
        "FanDuel",
        # EU / sharp
        "Pinnacle",
        "888sport",
        "William Hill",
        # UK sportsbooks
        "Betfair Exchange",
        "Betfair Sportsbook",
        "Ladbrokes",
        "Paddy Power",
        "William Hill (UK)",
    }
)

# Market type mapping (needed for filtering in parse_odds_events)
MARKET_TYPES = {
    "spreads": "spread",
    "totals": "total",
    "h2h": "moneyline",
}


def parse_odds_events(
    league_code: str,
    events: list,
    books: list[str] | None = None,
) -> list[NormalizedOddsSnapshot]:
    """Parse events list into normalized odds snapshots.

    Shared logic for both live and historical endpoints.
    """
    snapshots: list[NormalizedOddsSnapshot] = []

    for event in events:
        # Store event ID for downstream prop fetching
        event_id = event.get("id")

        # Parse commence_time as UTC
        commence_utc = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
        # Convert to Eastern Time for date extraction (US sports use ET dates)
        # This ensures games at 7pm ET on Jan 22 are stored as Jan 22, not Jan 23 UTC
        commence_et = commence_utc.astimezone(US_EASTERN)
        # Create game_date at midnight ET, then convert back to UTC for storage
        game_date_et = datetime.combine(commence_et.date(), datetime.min.time(), tzinfo=US_EASTERN)
        game_date = game_date_et.astimezone(UTC)

        # Normalize team names to canonical form
        raw_home_name = event["home_team"]
        raw_away_name = event["away_team"]
        home_canonical, home_abbr = normalize_team_name(league_code, raw_home_name)
        away_canonical, away_abbr = normalize_team_name(league_code, raw_away_name)

        # Log normalization - always log to help debug matching issues
        logger.debug(
            "odds_team_normalization",
            league=league_code,
            raw_home=raw_home_name,
            normalized_home=home_canonical,
            home_abbr=home_abbr,
            raw_away=raw_away_name,
            normalized_away=away_canonical,
            away_abbr=away_abbr,
            was_normalized=(raw_home_name != home_canonical or raw_away_name != away_canonical),
        )

        # Warn if normalization fell back to generating abbreviation
        # (indicates team name not in mappings)
        # Skip this check for NCAAB since abbreviations are None
        if league_code != "NCAAB" and (
            (home_abbr and len(home_abbr) > 3) or (away_abbr and len(away_abbr) > 3)
        ):
            logger.warning(
                "odds_team_abbreviation_generated",
                league=league_code,
                raw_home=raw_home_name,
                generated_home_abbr=home_abbr,
                raw_away=raw_away_name,
                generated_away_abbr=away_abbr,
                message="Team names not found in mappings - using generated abbreviations",
            )

        home_team = TeamIdentity(
            league_code=league_code,
            name=home_canonical,
            short_name=home_canonical,
            abbreviation=home_abbr,
        )
        away_team = TeamIdentity(
            league_code=league_code,
            name=away_canonical,
            short_name=away_canonical,
            abbreviation=away_abbr,
        )

        for bookmaker in event.get("bookmakers", []):
            if books and bookmaker["key"] not in books:
                continue
            if bookmaker.get("title") not in ALLOWED_BOOKS:
                continue
            for market in bookmaker.get("markets", []):
                market_type = MARKET_TYPES.get(market["key"])
                if not market_type:
                    continue
                for outcome in market.get("outcomes", []):
                    side = outcome.get("name")
                    price = outcome.get("price")
                    line = outcome.get("point")
                    if not side or price is None:
                        logger.debug(
                            "odds_outcome_skipped",
                            league=league_code,
                            book=bookmaker.get("title"),
                            market=market.get("key"),
                            reason="missing_side_or_price",
                        )
                        continue
                    if market_type in ("spread", "total") and line is None:
                        logger.debug(
                            "odds_outcome_skipped",
                            league=league_code,
                            book=bookmaker.get("title"),
                            market=market.get("key"),
                            side=side,
                            reason="missing_line",
                        )
                        continue
                    snapshots.append(
                        NormalizedOddsSnapshot(
                            league_code=league_code,
                            book=bookmaker["title"],
                            market_type=market_type,  # type: ignore[arg-type]
                            side=side,
                            line=line,
                            price=price,
                            observed_at=datetime.fromisoformat(
                                bookmaker["last_update"].replace("Z", "+00:00")
                            ),
                            home_team=home_team,
                            away_team=away_team,
                            game_date=game_date,
                            source_key=market.get("key"),
                            is_closing_line=True,
                            raw_payload=outcome,
                            event_id=event_id,
                        )
                    )

    return snapshots


def parse_prop_event(
    league_code: str,
    event_data: dict,
) -> list[NormalizedOddsSnapshot]:
    """Parse a single event's prop odds into normalized snapshots."""
    snapshots: list[NormalizedOddsSnapshot] = []

    event_id = event_data.get("id")
    commence_str = event_data.get("commence_time")
    if not commence_str:
        return []

    commence_utc = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
    commence_et = commence_utc.astimezone(US_EASTERN)
    game_date_et = datetime.combine(commence_et.date(), datetime.min.time(), tzinfo=US_EASTERN)
    game_date = game_date_et.astimezone(UTC)

    raw_home_name = event_data.get("home_team", "")
    raw_away_name = event_data.get("away_team", "")
    home_canonical, home_abbr = normalize_team_name(league_code, raw_home_name)
    away_canonical, away_abbr = normalize_team_name(league_code, raw_away_name)

    home_team = TeamIdentity(
        league_code=league_code,
        name=home_canonical,
        short_name=home_canonical,
        abbreviation=home_abbr,
    )
    away_team = TeamIdentity(
        league_code=league_code,
        name=away_canonical,
        short_name=away_canonical,
        abbreviation=away_abbr,
    )

    for bookmaker in event_data.get("bookmakers", []):
        if bookmaker.get("title") not in ALLOWED_BOOKS:
            continue
        for market in bookmaker.get("markets", []):
            market_key = market.get("key", "")
            market_category = classify_market(market_key)

            for outcome in market.get("outcomes", []):
                side = outcome.get("name")
                price = outcome.get("price")
                line = outcome.get("point")
                description = outcome.get("description")

                if not side or price is None:
                    continue

                # Extract player name from description field (props use this)
                player_name = description if market_category == "player_prop" else None

                # last_update lives on market in event-level API
                last_update_str = market.get("last_update") or bookmaker.get("last_update", "")
                observed_at = (
                    datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
                    if last_update_str
                    else commence_utc
                )

                snapshots.append(
                    NormalizedOddsSnapshot(
                        league_code=league_code,
                        book=bookmaker["title"],
                        market_type=market_key,
                        side=side,
                        line=line,
                        price=price,
                        observed_at=observed_at,
                        home_team=home_team,
                        away_team=away_team,
                        game_date=game_date,
                        source_key=market_key,
                        is_closing_line=True,
                        raw_payload=outcome,
                        event_id=event_id,
                        market_category=market_category,
                        player_name=player_name,
                        description=description,
                    )
                )

    return snapshots
