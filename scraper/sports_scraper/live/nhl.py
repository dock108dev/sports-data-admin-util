"""Live NHL feed helpers (schedule, play-by-play, boxscores).

Uses the official NHL API (api-web.nhle.com) for all NHL data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import httpx

from ..config import settings
from ..logging import logger
from ..models import (
    NormalizedPlay,
    NormalizedPlayByPlay,
    NormalizedPlayerBoxscore,
    NormalizedTeamBoxscore,
    TeamIdentity,
)
from ..normalization import normalize_team_name
from ..utils.cache import APICache
from ..utils.datetime_utils import now_utc
from ..utils.parsing import parse_int

# New NHL API endpoints (api-web.nhle.com)
NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date}"
NHL_PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
NHL_BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"

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


@dataclass
class NHLBoxscore:
    """Represents boxscore data from the NHL API.

    Contains team and player stats parsed from the boxscore endpoint.
    """

    game_id: int
    game_date: datetime
    status: str
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int
    away_score: int
    team_boxscores: list  # List of NormalizedTeamBoxscore
    player_boxscores: list  # List of NormalizedPlayerBoxscore


class NHLLiveFeedClient:
    """Client for NHL live schedule + play-by-play endpoints using api-web.nhle.com."""

    def __init__(self) -> None:
        timeout = settings.scraper_config.request_timeout_seconds
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "sports-data-admin-live/1.0"},
        )
        # API response cache to reduce redundant API calls
        self._cache = APICache(settings.scraper_config.html_cache_dir, "nhl")

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
                        home_score=parse_int(home_data.get("score")),
                        away_score=parse_int(away_data.get("score")),
                    )
                )

        return games

    def fetch_play_by_play(self, game_id: int) -> NormalizedPlayByPlay:
        """Fetch and normalize play-by-play data for a game.

        Results are cached to avoid redundant API calls.

        Args:
            game_id: NHL game ID (e.g., 2025020767)

        Returns:
            NormalizedPlayByPlay with all events normalized to canonical format
        """
        # Check cache first
        cache_key = f"pbp_{game_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("nhl_pbp_using_cache", game_id=game_id)
            plays = self._parse_pbp_response(cached, game_id)
            # Validation for cached data
            game_state = cached.get("gameState", "")
            if game_state == "OFF" and len(plays) < NHL_MIN_EXPECTED_PLAYS:
                logger.warning(
                    "nhl_pbp_low_event_count",
                    game_id=game_id,
                    play_count=len(plays),
                    expected_min=NHL_MIN_EXPECTED_PLAYS,
                    game_state=game_state,
                    source="cache",
                )
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=plays)

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

        # Cache the raw response
        self._cache.put(cache_key, payload)

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

        # Warn if no roster data found - player names won't be resolved
        if not player_id_to_name:
            logger.warning(
                "nhl_pbp_no_roster_data",
                game_id=game_id,
                message="rosterSpots is empty or missing - player names will not be resolved",
            )

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
        period = parse_int(period_desc.get("number"))
        period_type = period_desc.get("periodType", "REG")

        # Get sort order as play index (canonical ordering)
        sort_order = parse_int(play.get("sortOrder"))
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
        event_owner_team_id = parse_int(details.get("eventOwnerTeamId"))
        team_abbr = team_id_to_abbr.get(event_owner_team_id) if event_owner_team_id else None

        # Get primary player (scorer, shooter, penalty taker, etc.)
        player_id = self._extract_primary_player_id(details, type_desc_key)
        # Resolve player name from roster lookup
        player_name = player_id_to_name.get(player_id) if player_id else None

        # Get scores (only present on goal events)
        home_score = parse_int(details.get("homeScore"))
        away_score = parse_int(details.get("awayScore"))

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
            return parse_int(details.get("scoringPlayerId"))
        elif type_desc_key == "shot-on-goal":
            return parse_int(details.get("shootingPlayerId"))
        elif type_desc_key == "missed-shot":
            return parse_int(details.get("shootingPlayerId"))
        elif type_desc_key == "blocked-shot":
            return parse_int(details.get("blockingPlayerId"))
        elif type_desc_key == "hit":
            return parse_int(details.get("hittingPlayerId"))
        elif type_desc_key == "penalty":
            return parse_int(details.get("committedByPlayerId"))
        elif type_desc_key == "faceoff":
            return parse_int(details.get("winningPlayerId"))
        elif type_desc_key == "giveaway":
            return parse_int(details.get("playerId"))
        elif type_desc_key == "takeaway":
            return parse_int(details.get("playerId"))

        # Generic fallback - look for any playerId field
        for key in ["playerId", "shootingPlayerId", "scoringPlayerId"]:
            if key in details:
                return parse_int(details.get(key))

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

    def fetch_boxscore(self, game_id: int) -> NHLBoxscore | None:
        """Fetch boxscore from NHL API.

        Results are cached to avoid redundant API calls.

        Args:
            game_id: NHL game ID (e.g., 2025020767)

        Returns:
            NHLBoxscore with team and player stats, or None if fetch failed
        """
        # Check cache first
        cache_key = f"boxscore_{game_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("nhl_boxscore_using_cache", game_id=game_id)
            return self._parse_boxscore_response(cached, game_id)

        url = NHL_BOXSCORE_URL.format(game_id=game_id)
        logger.info("nhl_boxscore_fetch", url=url, game_id=game_id)

        try:
            response = self.client.get(url)
        except Exception as exc:
            logger.error("nhl_boxscore_fetch_error", game_id=game_id, error=str(exc))
            return None

        if response.status_code == 404:
            logger.warning("nhl_boxscore_not_found", game_id=game_id, status=404)
            return None

        if response.status_code != 200:
            logger.warning(
                "nhl_boxscore_fetch_failed",
                game_id=game_id,
                status=response.status_code,
                body=response.text[:200] if response.text else "",
            )
            return None

        payload = response.json()

        # Cache the raw response
        self._cache.put(cache_key, payload)

        return self._parse_boxscore_response(payload, game_id)

    def _parse_boxscore_response(self, payload: dict, game_id: int) -> NHLBoxscore:
        """Parse boxscore JSON into normalized structure."""
        # Extract game info
        game_date_str = payload.get("gameDate", "")
        game_date = _parse_datetime(game_date_str + "T00:00:00Z")
        game_state = payload.get("gameState", "")
        status = _map_nhl_game_state(game_state)

        # Extract team info
        home_team_data = payload.get("homeTeam", {})
        away_team_data = payload.get("awayTeam", {})

        home_team = _build_team_identity_from_new_api(home_team_data)
        away_team = _build_team_identity_from_new_api(away_team_data)

        home_score = parse_int(home_team_data.get("score")) or 0
        away_score = parse_int(away_team_data.get("score")) or 0

        # Extract team-level stats from boxscore summary
        team_boxscores: list[NormalizedTeamBoxscore] = []
        player_boxscores: list[NormalizedPlayerBoxscore] = []

        # Parse player stats for each team
        player_by_game_stats = payload.get("playerByGameStats", {})

        # Home team players
        home_players_data = player_by_game_stats.get("homeTeam", {})
        home_players = self._parse_team_players(home_players_data, home_team, game_id)
        player_boxscores.extend(home_players)

        # Away team players
        away_players_data = player_by_game_stats.get("awayTeam", {})
        away_players = self._parse_team_players(away_players_data, away_team, game_id)
        player_boxscores.extend(away_players)

        # Build team boxscores from aggregated player stats
        home_team_boxscore = self._build_team_boxscore_from_players(
            home_team, is_home=True, score=home_score, players=home_players
        )
        away_team_boxscore = self._build_team_boxscore_from_players(
            away_team, is_home=False, score=away_score, players=away_players
        )
        team_boxscores = [away_team_boxscore, home_team_boxscore]

        logger.info(
            "nhl_boxscore_parsed",
            game_id=game_id,
            status=status,
            home_score=home_score,
            away_score=away_score,
            home_players=len([p for p in player_boxscores if p.team.abbreviation == home_team.abbreviation]),
            away_players=len([p for p in player_boxscores if p.team.abbreviation == away_team.abbreviation]),
        )

        return NHLBoxscore(
            game_id=game_id,
            game_date=game_date,
            status=status,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            team_boxscores=team_boxscores,
            player_boxscores=player_boxscores,
        )

    def _parse_team_players(
        self,
        team_data: dict,
        team_identity: TeamIdentity,
        game_id: int,
    ) -> list[NormalizedPlayerBoxscore]:
        """Parse all players for a team from playerByGameStats."""
        players: list[NormalizedPlayerBoxscore] = []

        # Parse forwards
        for player_data in team_data.get("forwards", []):
            player = self._parse_skater_stats(player_data, team_identity, game_id)
            if player:
                players.append(player)

        # Parse defense
        for player_data in team_data.get("defense", []):
            player = self._parse_skater_stats(player_data, team_identity, game_id)
            if player:
                players.append(player)

        # Parse goalies
        for player_data in team_data.get("goalies", []):
            player = self._parse_goalie_stats(player_data, team_identity, game_id)
            if player:
                players.append(player)

        return players

    def _parse_skater_stats(
        self,
        player_data: dict,
        team_identity: TeamIdentity,
        game_id: int,
    ) -> NormalizedPlayerBoxscore | None:
        """Parse skater stats (forwards/defense) from NHL API.

        NHL API field mappings:
        - playerId -> player_id
        - sweaterNumber -> sweater_number
        - name.default -> player_name
        - position -> position
        - toi ("12:34") -> minutes (12.57)
        - goals, assists, points -> same
        - sog -> shots_on_goal
        - plusMinus -> plus_minus
        - pim -> penalties
        - hits -> hits
        - blockedShots -> blocked_shots
        - shifts -> shifts
        - giveaways -> giveaways
        - takeaways -> takeaways
        - faceoffWinningPctg -> faceoff_pct
        """
        player_id = player_data.get("playerId")
        if not player_id:
            return None

        # Get player name
        name_data = player_data.get("name", {})
        player_name = name_data.get("default", "")
        if not player_name:
            logger.warning(
                "nhl_boxscore_player_no_name",
                game_id=game_id,
                player_id=player_id,
            )
            return None

        # Parse time on ice (format: "12:34")
        toi = player_data.get("toi", "")
        minutes = _parse_toi_to_minutes(toi)

        # Parse faceoff percentage (comes as decimal like 0.55)
        faceoff_pct = player_data.get("faceoffWinningPctg")
        if faceoff_pct is not None:
            faceoff_pct = round(float(faceoff_pct) * 100, 1) if faceoff_pct else None

        # Build raw stats dict for power play/shorthanded goals
        raw_stats = {
            "powerPlayGoals": player_data.get("powerPlayGoals"),
            "shorthandedGoals": player_data.get("shorthandedGoals"),
        }
        # Remove None values
        raw_stats = {k: v for k, v in raw_stats.items() if v is not None}

        return NormalizedPlayerBoxscore(
            player_id=str(player_id),
            player_name=player_name,
            team=team_identity,
            player_role="skater",
            position=player_data.get("position"),
            sweater_number=parse_int(player_data.get("sweaterNumber")),
            minutes=minutes,
            goals=parse_int(player_data.get("goals")),
            assists=parse_int(player_data.get("assists")),
            points=parse_int(player_data.get("points")),
            shots_on_goal=parse_int(player_data.get("sog")),
            penalties=parse_int(player_data.get("pim")),
            plus_minus=parse_int(player_data.get("plusMinus")),
            hits=parse_int(player_data.get("hits")),
            blocked_shots=parse_int(player_data.get("blockedShots")),
            shifts=parse_int(player_data.get("shifts")),
            giveaways=parse_int(player_data.get("giveaways")),
            takeaways=parse_int(player_data.get("takeaways")),
            faceoff_pct=faceoff_pct,
            # Goalie stats remain None for skaters
            saves=None,
            goals_against=None,
            shots_against=None,
            save_percentage=None,
            raw_stats=raw_stats,
        )

    def _parse_goalie_stats(
        self,
        player_data: dict,
        team_identity: TeamIdentity,
        game_id: int,
    ) -> NormalizedPlayerBoxscore | None:
        """Parse goalie stats from NHL API.

        NHL API field mappings:
        - playerId -> player_id
        - sweaterNumber -> sweater_number
        - name.default -> player_name
        - toi ("45:00") -> minutes (45.0)
        - saveShotsAgainst ("25/27") -> saves, shots_against
        - goalsAgainst -> goals_against
        - savePctg -> save_percentage
        """
        player_id = player_data.get("playerId")
        if not player_id:
            return None

        # Get player name
        name_data = player_data.get("name", {})
        player_name = name_data.get("default", "")
        if not player_name:
            logger.warning(
                "nhl_boxscore_goalie_no_name",
                game_id=game_id,
                player_id=player_id,
            )
            return None

        # Parse time on ice (format: "45:00")
        toi = player_data.get("toi", "")
        minutes = _parse_toi_to_minutes(toi)

        # Parse saveShotsAgainst (format: "25/27" -> saves=25, shots_against=27)
        save_shots = player_data.get("saveShotsAgainst", "")
        saves, shots_against = _parse_save_shots(save_shots)

        # Get goals against
        goals_against = parse_int(player_data.get("goalsAgainst"))

        # Get save percentage (comes as decimal like 0.926)
        save_pctg = player_data.get("savePctg")
        save_percentage = round(float(save_pctg) * 100, 1) if save_pctg is not None else None

        # Build raw stats dict for additional fields
        raw_stats = {
            "evenStrengthShotsAgainst": player_data.get("evenStrengthShotsAgainst"),
            "powerPlayShotsAgainst": player_data.get("powerPlayShotsAgainst"),
            "shorthandedShotsAgainst": player_data.get("shorthandedShotsAgainst"),
        }
        # Remove None values
        raw_stats = {k: v for k, v in raw_stats.items() if v is not None}

        return NormalizedPlayerBoxscore(
            player_id=str(player_id),
            player_name=player_name,
            team=team_identity,
            player_role="goalie",
            position="G",
            sweater_number=parse_int(player_data.get("sweaterNumber")),
            minutes=minutes,
            # Goalie stats
            saves=saves,
            goals_against=goals_against,
            shots_against=shots_against,
            save_percentage=save_percentage,
            # Skater stats remain None for goalies
            goals=None,
            assists=None,
            points=None,
            shots_on_goal=None,
            penalties=parse_int(player_data.get("pim")),
            plus_minus=None,
            hits=None,
            blocked_shots=None,
            shifts=None,
            giveaways=None,
            takeaways=None,
            faceoff_pct=None,
            raw_stats=raw_stats,
        )

    def _build_team_boxscore_from_players(
        self,
        team_identity: TeamIdentity,
        is_home: bool,
        score: int,
        players: list[NormalizedPlayerBoxscore],
    ) -> NormalizedTeamBoxscore:
        """Build team boxscore by aggregating player stats."""
        # Aggregate skater stats
        skaters = [p for p in players if p.player_role == "skater"]

        total_shots = sum(p.shots_on_goal or 0 for p in skaters)
        total_pim = sum(p.penalties or 0 for p in skaters)
        total_assists = sum(p.assists or 0 for p in skaters)

        return NormalizedTeamBoxscore(
            team=team_identity,
            is_home=is_home,
            points=score,
            shots_on_goal=total_shots if total_shots > 0 else None,
            penalty_minutes=total_pim if total_pim > 0 else None,
            assists=total_assists if total_assists > 0 else None,
            raw_stats={},
        )


def _parse_toi_to_minutes(toi: str) -> float | None:
    """Parse time on ice string (e.g., '12:34') to decimal minutes (12.57)."""
    if not toi:
        return None
    try:
        parts = toi.split(":")
        if len(parts) == 2:
            mins = int(parts[0])
            secs = int(parts[1])
            return round(mins + secs / 60, 2)
    except (ValueError, IndexError):
        pass
    return None


def _parse_save_shots(save_shots: str) -> tuple[int | None, int | None]:
    """Parse saveShotsAgainst string (e.g., '25/27') to (saves, shots_against)."""
    if not save_shots:
        return None, None
    try:
        parts = save_shots.split("/")
        if len(parts) == 2:
            saves = int(parts[0])
            shots_against = int(parts[1])
            return saves, shots_against
    except (ValueError, IndexError):
        pass
    return None, None


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


def _one_day():
    """Return timedelta of one day."""
    from datetime import timedelta

    return timedelta(days=1)
