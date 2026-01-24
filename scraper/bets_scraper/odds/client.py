"""Odds API client for pulling mainline closing prices.

Supports both live odds (upcoming games) and historical odds (past games).
Uses The Odds API: https://the-odds-api.com/liveapi/guides/v4/

Includes local JSON caching to avoid repeat API calls and save credits.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..config import settings
from ..logging import logger
from ..models import NormalizedOddsSnapshot, TeamIdentity
from ..normalization import normalize_team_name

# US sports use Eastern Time for game dates
US_EASTERN = ZoneInfo("America/New_York")


SPORT_KEY_MAP = {
    "NBA": "basketball_nba",
    "NCAAB": "basketball_ncaab",
    "NFL": "americanfootball_nfl",
    "NCAAF": "americanfootball_ncaaf",
    "MLB": "baseball_mlb",
    "NHL": "icehockey_nhl",
}

MARKET_TYPES = {
    "spreads": "spread",
    "totals": "total",
    "h2h": "moneyline",
}

# NHL uses "spreads" for puck lines; keep the canonical "spread" market type.

# Default snapshot times for closing lines (in UTC)
# Evening games typically close around these times
CLOSING_LINE_HOURS = {
    "NBA": 23,      # ~7 PM ET = 23:00 UTC (winter) / 11 PM UTC
    "NCAAB": 23,
    "NFL": 17,      # ~1 PM ET = 17:00 UTC (Sunday games)
    "NCAAF": 17,
    "MLB": 23,      # ~7 PM ET
    "NHL": 23,
}


class OddsAPIClient:
    def __init__(self) -> None:
        if not settings.odds_api_key:
            logger.warning("odds_api_key_missing", message="ODDS_API_KEY not configured; odds sync disabled.")
        self.client = httpx.Client(
            base_url=settings.odds_config.base_url,
            headers={"User-Agent": "dock108-odds-sync/1.0"},
            timeout=settings.odds_config.request_timeout_seconds,
        )
        # Cache directory for odds responses
        self._cache_dir = Path(settings.scraper_config.html_cache_dir) / "odds"

    def _truncate_body(self, body: str | None, limit: int = 500) -> str | None:
        if not body:
            return None
        if len(body) <= limit:
            return body
        return f"{body[:limit]}..."

    # -------------------------------------------------------------------------
    # Cache helpers
    # -------------------------------------------------------------------------
    def _get_cache_path(self, league: str, game_date: date, is_historical: bool) -> Path:
        """Get cache file path for an odds response."""
        prefix = "historical" if is_historical else "live"
        return self._cache_dir / league / f"{game_date}_{prefix}.json"

    def _read_cache(self, cache_path: Path) -> dict | None:
        """Read cached JSON response if it exists."""
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text())
                logger.debug("odds_cache_hit", path=str(cache_path))
                return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("odds_cache_read_error", path=str(cache_path), error=str(e))
        return None

    def _write_cache(self, cache_path: Path, data: Any) -> None:
        """Write API response to cache."""
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data, indent=2, default=str))
            logger.debug("odds_cache_written", path=str(cache_path))
        except IOError as e:
            logger.warning("odds_cache_write_error", path=str(cache_path), error=str(e))

    # -------------------------------------------------------------------------
    # API methods
    # -------------------------------------------------------------------------
    def _sport_key(self, league_code: str) -> str | None:
        return SPORT_KEY_MAP.get(league_code.upper())

    def fetch_mainlines(
        self,
        league_code: str,
        start_date: date,
        end_date: date,
        books: list[str] | None = None,
    ) -> list[NormalizedOddsSnapshot]:
        """Fetch live odds for upcoming games.
        
        Uses the standard /sports/{sport}/odds endpoint.
        """
        if not settings.odds_api_key:
            return []

        sport_key = self._sport_key(league_code)
        if not sport_key:
            logger.warning("unsupported_league_for_odds", league=league_code)
            return []

        # Check cache first (use start_date as key for live odds)
        cache_path = self._get_cache_path(league_code, start_date, is_historical=False)
        cached = self._read_cache(cache_path)
        if cached is not None:
            logger.info("odds_using_cache", league=league_code, date=str(start_date), type="live")
            return self._parse_odds_events(league_code, cached, books)

        start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        
        params = {
            "apiKey": settings.odds_api_key,
            "regions": "us",
            "markets": ",".join(MARKET_TYPES.keys()),
            "oddsFormat": "american",
            "commenceTimeFrom": start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commenceTimeTo": end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if books:
            params["bookmakers"] = ",".join(books)

        response = self.client.get(f"/sports/{sport_key}/odds", params=params)
        if response.status_code != 200:
            logger.error(
                "odds_api_error",
                status=response.status_code,
                body=self._truncate_body(response.text),
            )
            return []

        payload = response.json()
        logger.info(
            "odds_api_response",
            league=league_code,
            event_count=len(payload) if isinstance(payload, list) else 0,
            remaining=response.headers.get("x-requests-remaining"),
        )
        
        # Cache the response
        self._write_cache(cache_path, payload)
        
        return self._parse_odds_events(league_code, payload, books)

    def fetch_historical_odds(
        self,
        league_code: str,
        game_date: date,
        books: list[str] | None = None,
    ) -> list[NormalizedOddsSnapshot]:
        """Fetch historical odds for a specific date using the historical API.
        
        Uses /historical/sports/{sport}/odds endpoint.
        Cost: 30 credits per call (3 markets x 1 region).
        
        Args:
            league_code: League code (NBA, NFL, etc.)
            game_date: The date to fetch odds for
            books: Optional list of bookmaker keys to filter
            
        Returns:
            List of normalized odds snapshots for all games on that date
        """
        if not settings.odds_api_key:
            logger.warning("odds_api_key_missing", message="ODDS_API_KEY not configured")
            return []

        sport_key = self._sport_key(league_code)
        if not sport_key:
            logger.warning("unsupported_league_for_odds", league=league_code)
            return []

        # Check cache first
        cache_path = self._get_cache_path(league_code, game_date, is_historical=True)
        cached = self._read_cache(cache_path)
        if cached is not None:
            logger.info("odds_using_cache", league=league_code, date=str(game_date), type="historical")
            # Cached data is the full API response, extract events
            events = cached.get("data", []) if isinstance(cached, dict) else cached
            return self._parse_odds_events(league_code, events, books)

        # Build snapshot time - use closing line hour for this sport
        closing_hour = CLOSING_LINE_HOURS.get(league_code.upper(), 23)
        snapshot_dt = datetime.combine(game_date, time(closing_hour, 0), tzinfo=timezone.utc)
        date_param = snapshot_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "apiKey": settings.odds_api_key,
            "regions": "us",
            "markets": ",".join(MARKET_TYPES.keys()),
            "oddsFormat": "american",
            "date": date_param,
        }
        if books:
            params["bookmakers"] = ",".join(books)

        logger.info(
            "fetching_historical_odds",
            league=league_code,
            date=str(game_date),
            snapshot=date_param,
        )

        # FIX: Use /historical/sports/... not /v4/historical/sports/...
        # (base_url already includes /v4)
        response = self.client.get(f"/historical/sports/{sport_key}/odds", params=params)
        if response.status_code != 200:
            logger.error(
                "historical_odds_api_error",
                status=response.status_code,
                body=self._truncate_body(response.text),
            )
            return []

        result = response.json()
        
        # Log quota usage from headers
        remaining = response.headers.get("x-requests-remaining", "?")
        used = response.headers.get("x-requests-used", "?")
        cost = response.headers.get("x-requests-last", "?")
        logger.info(
            "historical_odds_quota",
            remaining=remaining,
            used=used,
            cost=cost,
        )

        # Cache the full response
        self._write_cache(cache_path, result)

        # Historical endpoint wraps data in a "data" field
        events = result.get("data", [])
        if not events:
            logger.info("no_historical_odds", league=league_code, date=str(game_date))
            return []

        logger.info(
            "historical_odds_response",
            league=league_code,
            date=str(game_date),
            event_count=len(events),
            snapshot_timestamp=result.get("timestamp"),
        )

        return self._parse_odds_events(league_code, events, books)

    def _parse_odds_events(
        self,
        league_code: str,
        events: list,
        books: list[str] | None = None,
    ) -> list[NormalizedOddsSnapshot]:
        """Parse events list into normalized odds snapshots.
        
        Shared logic for both live and historical endpoints.
        """
        snapshots: list[NormalizedOddsSnapshot] = []
        
        for event in events:
            # Parse commence_time as UTC
            commence_utc = datetime.fromisoformat(event["commence_time"].replace("Z", "+00:00"))
            # Convert to Eastern Time for date extraction (US sports use ET dates)
            # This ensures games at 7pm ET on Jan 22 are stored as Jan 22, not Jan 23 UTC
            commence_et = commence_utc.astimezone(US_EASTERN)
            # Create game_date at midnight ET, then convert back to UTC for storage
            game_date_et = datetime.combine(commence_et.date(), datetime.min.time(), tzinfo=US_EASTERN)
            game_date = game_date_et.astimezone(timezone.utc)
            
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
                                tip_time=commence_utc,  # Actual start time in UTC
                                source_key=market.get("key"),
                                is_closing_line=True,
                                raw_payload=outcome,
                            )
                        )
        
        return snapshots
