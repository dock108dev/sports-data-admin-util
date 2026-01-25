"""Live NHL feed helpers (schedule + play-by-play).

Uses the official NHL API (api-web.nhle.com) for schedule and play-by-play data.
This replaces the deprecated statsapi.web.nhl.com endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx

from ..config import settings
from ..logging import logger
from ..models import NormalizedPlay, NormalizedPlayByPlay, TeamIdentity
from ..normalization import normalize_team_name
from ..utils.datetime_utils import now_utc

# New NHL API endpoints (api-web.nhle.com)
NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date}"
NHL_PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"

# Play index multiplier to ensure unique ordering across periods
# Allows up to 10,000 plays per period (sufficient for multi-OT games)
NHL_PERIOD_MULTIPLIER = 10000

# Minimum expected plays for a completed NHL game
NHL_MIN_EXPECTED_PLAYS = 100

# Explicit mapping of NHL event types from typeDescKey
# All recognized event types - unknown types are logged but still stored
NHL_EVENT_TYPE_MAP: dict[str, str] = {
    # Scoring events
    "goal": "GOAL",
    # Shot events
    "shot-on-goal": "SHOT",
    "missed-shot": "MISS",
    "blocked-shot": "BLOCK",
    # Physical play
    "hit": "HIT",
    "giveaway": "GIVEAWAY",
    "takeaway": "TAKEAWAY",
    # Penalties
    "penalty": "PENALTY",
    # Face-offs
    "faceoff": "FACEOFF",
    # Game flow
    "stoppage": "STOPPAGE",
    "period-start": "PERIOD_START",
    "period-end": "PERIOD_END",
    "game-end": "GAME_END",
    "game-official": "GAME_OFFICIAL",
    "shootout-complete": "SHOOTOUT_COMPLETE",
    # Other
    "delayed-penalty": "DELAYED_PENALTY",
    "failed-shot-attempt": "FAILED_SHOT",
}


@dataclass(frozen=True)
class NHLLiveGame:
    """Represents a game from the NHL schedule API."""

    game_id: int
    game_date: datetime
    status: str
    status_text: str | None
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int | None
    away_score: int | None


class NHLLiveFeedClient:
    """Client for NHL live schedule + play-by-play endpoints using api-web.nhle.com."""

    def __init__(self) -> None:
        timeout = settings.scraper_config.request_timeout_seconds
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "sports-data-admin-live/1.0"},
        )

    def fetch_schedule(self, start: date, end: date) -> list[NHLLiveGame]:
        """Fetch NHL schedule for a date range.

        The new NHL API returns schedule by week, so we fetch each date individually.
        """
        logger.info("nhl_schedule_fetch", start=str(start), end=str(end))
        games: list[NHLLiveGame] = []

        current = start
        while current <= end:
            url = NHL_SCHEDULE_URL.format(date=current.strftime("%Y-%m-%d"))
            try:
                response = self.client.get(url)
                if response.status_code != 200:
                    logger.warning(
                        "nhl_schedule_fetch_failed",
                        date=str(current),
                        status=response.status_code,
                        body=response.text[:200],
                    )
                    current = current + _one_day()
                    continue

                payload = response.json()
                games.extend(self._parse_schedule_response(payload, current))

            except Exception as exc:
                logger.warning(
                    "nhl_schedule_fetch_error",
                    date=str(current),
                    error=str(exc),
                )

            current = current + _one_day()

        logger.info("nhl_schedule_parsed", count=len(games), start=str(start), end=str(end))
        return games

    def _parse_schedule_response(self, payload: dict, target_date: date) -> list[NHLLiveGame]:
        """Parse the schedule response from the new NHL API.

        IMPORTANT: Uses the gameWeek date (local date) for game_date, not startTimeUTC.
        This is because our database stores games by local date (e.g., 2026-01-18 for
        a game played on Jan 18 evening local time), but startTimeUTC might be the
        next day in UTC (e.g., 2026-01-19T01:00:00Z for a 6pm MT game).
        """
        games: list[NHLLiveGame] = []

        for week in payload.get("gameWeek", []):
            week_date = week.get("date")
            if week_date != target_date.strftime("%Y-%m-%d"):
                continue

            for game in week.get("games", []):
                game_id = game.get("id")
                if game_id is None:
                    continue

                # Use the gameWeek date (local date) for matching, not startTimeUTC
                # This ensures EDM @ STL on "2026-01-18" matches our DB even though
                # startTimeUTC is "2026-01-19T01:00:00Z"
                game_date = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
                game_state = game.get("gameState", "")
                status = _map_nhl_game_state(game_state)

                home_data = game.get("homeTeam", {})
                away_data = game.get("awayTeam", {})

                home_team = _build_team_identity_from_new_api(home_data)
                away_team = _build_team_identity_from_new_api(away_data)

                games.append(
                    NHLLiveGame(
                        game_id=int(game_id),
                        game_date=game_date,
                        status=status,
                        status_text=game_state,
                        home_team=home_team,
                        away_team=away_team,
                        home_score=_parse_int(home_data.get("score")),
                        away_score=_parse_int(away_data.get("score")),
                    )
                )

        return games

    def fetch_play_by_play(self, game_id: int) -> NormalizedPlayByPlay:
        """Fetch and normalize play-by-play data for a game.

        Args:
            game_id: NHL game ID (e.g., 2025020767)

        Returns:
            NormalizedPlayByPlay with all events normalized to canonical format
        """
        url = NHL_PBP_URL.format(game_id=game_id)
        logger.info("nhl_pbp_fetch", url=url, game_id=game_id)

        try:
            response = self.client.get(url)
        except Exception as exc:
            logger.error("nhl_pbp_fetch_error", game_id=game_id, error=str(exc))
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        if response.status_code == 404:
            logger.warning("nhl_pbp_not_found", game_id=game_id, status=404)
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        if response.status_code != 200:
            logger.warning(
                "nhl_pbp_fetch_failed",
                game_id=game_id,
                status=response.status_code,
                body=response.text[:200] if response.text else "",
            )
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        payload = response.json()
        plays = self._parse_pbp_response(payload, game_id)

        # Validation: warn if low event count for completed game
        game_state = payload.get("gameState", "")
        if game_state == "OFF" and len(plays) < NHL_MIN_EXPECTED_PLAYS:
            logger.warning(
                "nhl_pbp_low_event_count",
                game_id=game_id,
                play_count=len(plays),
                expected_min=NHL_MIN_EXPECTED_PLAYS,
                game_state=game_state,
            )

        # Log first and last event for debugging
        if plays:
            logger.info(
                "nhl_pbp_parsed",
                game_id=game_id,
                count=len(plays),
                first_event=plays[0].play_type,
                first_period=plays[0].quarter,
                last_event=plays[-1].play_type,
                last_period=plays[-1].quarter,
            )
        else:
            logger.info("nhl_pbp_parsed", game_id=game_id, count=0)

        return NormalizedPlayByPlay(source_game_key=str(game_id), plays=plays)

    def _parse_pbp_response(self, payload: dict, game_id: int) -> list[NormalizedPlay]:
        """Parse the play-by-play response from the new NHL API."""
        plays: list[NormalizedPlay] = []
        raw_plays = payload.get("plays", [])

        # Get team info for abbreviation lookup
        home_team_id = payload.get("homeTeam", {}).get("id")
        away_team_id = payload.get("awayTeam", {}).get("id")
        home_abbr = payload.get("homeTeam", {}).get("abbrev")
        away_abbr = payload.get("awayTeam", {}).get("abbrev")

        team_id_to_abbr: dict[int, str] = {}
        if home_team_id and home_abbr:
            team_id_to_abbr[home_team_id] = home_abbr
        if away_team_id and away_abbr:
            team_id_to_abbr[away_team_id] = away_abbr

        # Build player ID to name lookup from rosterSpots
        player_id_to_name: dict[int, str] = {}
        for roster_spot in payload.get("rosterSpots", []):
            player_id = roster_spot.get("playerId")
            first_name = roster_spot.get("firstName", {}).get("default", "")
            last_name = roster_spot.get("lastName", {}).get("default", "")
            if player_id and (first_name or last_name):
                full_name = f"{first_name} {last_name}".strip()
                player_id_to_name[player_id] = full_name

        for play in raw_plays:
            normalized = self._normalize_play(play, team_id_to_abbr, player_id_to_name, game_id)
            if normalized:
                plays.append(normalized)

        # Sort by sortOrder to ensure canonical ordering
        plays.sort(key=lambda p: p.play_index)

        return plays

    def _normalize_play(
        self,
        play: dict[str, Any],
        team_id_to_abbr: dict[int, str],
        player_id_to_name: dict[int, str],
        game_id: int,
    ) -> NormalizedPlay | None:
        """Normalize a single play event from the NHL API.

        Handles the new API format with periodDescriptor, timeInPeriod, etc.
        """
        # Extract period info
        period_desc = play.get("periodDescriptor", {})
        period = _parse_int(period_desc.get("number"))
        period_type = period_desc.get("periodType", "REG")

        # Get sort order as play index (canonical ordering)
        sort_order = _parse_int(play.get("sortOrder"))
        if sort_order is None:
            return None

        # Build play_index: period * multiplier + sort_order for stable ordering
        play_index = (period or 0) * NHL_PERIOD_MULTIPLIER + sort_order

        # Get timing info
        time_in_period = play.get("timeInPeriod")  # e.g., "04:00"
        time_remaining = play.get("timeRemaining")  # e.g., "16:00"

        # Use time_remaining as game_clock (consistent with NBA convention)
        game_clock = time_remaining

        # Get event type
        type_desc_key = play.get("typeDescKey", "")
        play_type = self._map_event_type(type_desc_key, game_id)

        # Extract details
        details = play.get("details", {})

        # Get team abbreviation from eventOwnerTeamId
        event_owner_team_id = _parse_int(details.get("eventOwnerTeamId"))
        team_abbr = team_id_to_abbr.get(event_owner_team_id) if event_owner_team_id else None

        # Get primary player (scorer, shooter, penalty taker, etc.)
        player_id = self._extract_primary_player_id(details, type_desc_key)
        # Resolve player name from roster lookup
        player_name = player_id_to_name.get(player_id) if player_id else None

        # Get scores (only present on goal events)
        home_score = _parse_int(details.get("homeScore"))
        away_score = _parse_int(details.get("awayScore"))

        # Build raw_data with all source-specific details
        raw_data = {
            "event_id": play.get("eventId"),
            "sort_order": sort_order,
            "time_in_period": time_in_period,
            "time_remaining": time_remaining,
            "period_type": period_type,
            "situation_code": play.get("situationCode"),
            "type_code": play.get("typeCode"),
            "type_desc_key": type_desc_key,
            "details": details,
        }

        return NormalizedPlay(
            play_index=play_index,
            quarter=period,  # Using quarter field for period (as NBA does)
            game_clock=game_clock,
            play_type=play_type,
            team_abbreviation=team_abbr,
            player_id=str(player_id) if player_id else None,
            player_name=player_name,
            description=self._build_description(type_desc_key, details),
            home_score=home_score,
            away_score=away_score,
            raw_data=raw_data,
        )

    def _map_event_type(self, type_desc_key: str, game_id: int) -> str:
        """Map NHL typeDescKey to normalized event type.

        Unknown types are logged and stored with original key.
        """
        if not type_desc_key:
            return "UNKNOWN"

        mapped = NHL_EVENT_TYPE_MAP.get(type_desc_key)
        if mapped:
            return mapped

        # Log unknown event type but don't fail
        logger.warning(
            "nhl_pbp_unknown_event_type",
            game_id=game_id,
            type_desc_key=type_desc_key,
        )
        return type_desc_key.upper().replace("-", "_")

    def _extract_primary_player_id(
        self,
        details: dict[str, Any],
        type_desc_key: str,
    ) -> int | None:
        """Extract the primary player ID from event details.

        Different event types have different player ID fields.
        Returns player_id (name is resolved from roster lookup).
        """
        # Priority order for primary player based on event type
        if type_desc_key == "goal":
            return _parse_int(details.get("scoringPlayerId"))
        elif type_desc_key == "shot-on-goal":
            return _parse_int(details.get("shootingPlayerId"))
        elif type_desc_key == "missed-shot":
            return _parse_int(details.get("shootingPlayerId"))
        elif type_desc_key == "blocked-shot":
            return _parse_int(details.get("blockingPlayerId"))
        elif type_desc_key == "hit":
            return _parse_int(details.get("hittingPlayerId"))
        elif type_desc_key == "penalty":
            return _parse_int(details.get("committedByPlayerId"))
        elif type_desc_key == "faceoff":
            return _parse_int(details.get("winningPlayerId"))
        elif type_desc_key == "giveaway":
            return _parse_int(details.get("playerId"))
        elif type_desc_key == "takeaway":
            return _parse_int(details.get("playerId"))

        # Generic fallback - look for any playerId field
        for key in ["playerId", "shootingPlayerId", "scoringPlayerId"]:
            if key in details:
                return _parse_int(details.get(key))

        return None

    def _build_description(self, type_desc_key: str, details: dict[str, Any]) -> str | None:
        """Build a human-readable description from event details."""
        # The new API doesn't provide pre-built descriptions like the old one
        # We build basic descriptions from the details
        if type_desc_key == "goal":
            shot_type = details.get("shotType", "")
            return f"Goal ({shot_type})" if shot_type else "Goal"
        elif type_desc_key == "shot-on-goal":
            shot_type = details.get("shotType", "")
            return f"Shot on goal ({shot_type})" if shot_type else "Shot on goal"
        elif type_desc_key == "missed-shot":
            reason = details.get("reason", "")
            return f"Missed shot ({reason})" if reason else "Missed shot"
        elif type_desc_key == "blocked-shot":
            return "Blocked shot"
        elif type_desc_key == "hit":
            return "Hit"
        elif type_desc_key == "penalty":
            desc_key = details.get("descKey", "")
            duration = details.get("duration", 2)
            return f"Penalty: {desc_key} ({duration} min)" if desc_key else "Penalty"
        elif type_desc_key == "faceoff":
            zone = details.get("zoneCode", "")
            return f"Faceoff ({zone} zone)" if zone else "Faceoff"
        elif type_desc_key == "stoppage":
            reason = details.get("reason", "")
            return f"Stoppage: {reason}" if reason else "Stoppage"

        return type_desc_key.replace("-", " ").title()


def _build_team_identity_from_new_api(team_data: dict) -> TeamIdentity:
    """Build TeamIdentity from the new NHL API team data."""
    abbr = team_data.get("abbrev", "")
    # Get full name from commonName or placeName
    common_name = team_data.get("commonName", {}).get("default", "")
    place_name = team_data.get("placeName", {}).get("default", "")

    # Build full name: "Place Name Common Name" (e.g., "Tampa Bay Lightning")
    full_name = f"{place_name} {common_name}".strip()

    # Normalize through our team name system
    canonical_name, normalized_abbr = normalize_team_name("NHL", full_name)

    return TeamIdentity(
        league_code="NHL",
        name=canonical_name or full_name,
        short_name=common_name or canonical_name,
        abbreviation=normalized_abbr or abbr,
        external_ref=abbr,
    )


def _map_nhl_game_state(state: str) -> str:
    """Map NHL gameState to normalized status."""
    if state in ("OFF", "FINAL"):
        return "final"
    if state in ("LIVE", "CRIT"):
        return "live"
    if state in ("FUT", "PRE"):
        return "scheduled"
    return "scheduled"


def _parse_datetime(value: str | None) -> datetime:
    """Parse ISO datetime string to UTC datetime."""
    if not value:
        return now_utc()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return now_utc()


def _parse_int(value: str | int | None) -> int | None:
    """Safely parse an integer value."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _one_day():
    """Return timedelta of one day."""
    from datetime import timedelta

    return timedelta(days=1)
