"""NCAAB live feed helpers (schedule, play-by-play, boxscores).

Uses the College Basketball Data API (api.collegebasketballdata.com) for all NCAAB data.
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
from ..utils.cache import APICache
from ..utils.datetime_utils import now_utc

# College Basketball Data API endpoints
CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_GAMES_URL = f"{CBB_API_BASE}/games"
CBB_GAMES_TEAMS_URL = f"{CBB_API_BASE}/games/teams"
CBB_GAMES_PLAYERS_URL = f"{CBB_API_BASE}/games/players"
CBB_PLAYS_GAME_URL = f"{CBB_API_BASE}/plays/game/{{game_id}}"

# Play index multiplier to ensure unique ordering across periods
# Allows up to 10,000 plays per period (sufficient for overtime games)
NCAAB_PERIOD_MULTIPLIER = 10000

# Minimum expected plays for a completed NCAAB game
NCAAB_MIN_EXPECTED_PLAYS = 100

# Mapping of play types from the CBB API to normalized event types
# Based on actual API responses observed in logs
# Note: API uses inconsistent naming (camelCase, spaces, etc.) so we map all variants
NCAAB_EVENT_TYPE_MAP: dict[str, str] = {
    # Scoring events - shots (various naming conventions)
    "JumpShot": "MADE_SHOT",
    "Layup": "MADE_SHOT",
    "LayUpShot": "MADE_SHOT",
    "Dunk": "MADE_SHOT",
    "DunkShot": "MADE_SHOT",
    "Tip Shot": "MADE_SHOT",
    "TipShot": "MADE_SHOT",
    "Hook Shot": "MADE_SHOT",
    "HookShot": "MADE_SHOT",
    "Three Point Jumper": "MADE_SHOT",
    "ThreePointJumper": "MADE_SHOT",
    "Two Point Jumper": "MADE_SHOT",
    "TwoPointJumper": "MADE_SHOT",
    # Missed shots
    "Missed JumpShot": "MISSED_SHOT",
    "MissedJumpShot": "MISSED_SHOT",
    "Missed Layup": "MISSED_SHOT",
    "MissedLayup": "MISSED_SHOT",
    "MissedLayUpShot": "MISSED_SHOT",
    "Missed Dunk": "MISSED_SHOT",
    "MissedDunk": "MISSED_SHOT",
    "MissedDunkShot": "MISSED_SHOT",
    "Missed Three Point Jumper": "MISSED_SHOT",
    "MissedThreePointJumper": "MISSED_SHOT",
    "Missed Two Point Jumper": "MISSED_SHOT",
    "MissedTwoPointJumper": "MISSED_SHOT",
    "Missed Tip Shot": "MISSED_SHOT",
    "MissedTipShot": "MISSED_SHOT",
    "Missed Hook Shot": "MISSED_SHOT",
    "MissedHookShot": "MISSED_SHOT",
    # Free throws
    "Free Throw Made": "MADE_FREE_THROW",
    "Free Throw Missed": "MISSED_FREE_THROW",
    "MadeFreeThrow": "MADE_FREE_THROW",
    "MissedFreeThrow": "MISSED_FREE_THROW",
    # Rebounds
    "Offensive Rebound": "OFFENSIVE_REBOUND",
    "OffensiveRebound": "OFFENSIVE_REBOUND",
    "Defensive Rebound": "DEFENSIVE_REBOUND",
    "DefensiveRebound": "DEFENSIVE_REBOUND",
    "Rebound": "REBOUND",
    "Team Rebound": "REBOUND",
    "TeamRebound": "REBOUND",
    "Dead Ball Rebound": "REBOUND",
    "DeadBallRebound": "REBOUND",
    # Ball movement - turnovers
    "Turnover": "TURNOVER",
    "Lost Ball Turnover": "TURNOVER",
    "LostBallTurnover": "TURNOVER",
    "Bad Pass Turnover": "TURNOVER",
    "BadPassTurnover": "TURNOVER",
    "Traveling": "TURNOVER",
    "TravelingTurnover": "TURNOVER",
    "Out of Bounds Turnover": "TURNOVER",
    "OutOfBoundsTurnover": "TURNOVER",
    "Shot Clock Violation": "TURNOVER",
    "ShotClockViolation": "TURNOVER",
    "DoublePersonalFoul": "TURNOVER",
    # Other ball movement
    "Steal": "STEAL",
    "Assist": "ASSIST",
    # Fouls (various naming conventions)
    "Foul": "FOUL",
    "Personal Foul": "PERSONAL_FOUL",
    "PersonalFoul": "PERSONAL_FOUL",
    "Shooting Foul": "SHOOTING_FOUL",
    "ShootingFoul": "SHOOTING_FOUL",
    "Offensive Foul": "OFFENSIVE_FOUL",
    "OffensiveFoul": "OFFENSIVE_FOUL",
    "Technical Foul": "TECHNICAL_FOUL",
    "TechnicalFoul": "TECHNICAL_FOUL",
    "Flagrant Foul": "FLAGRANT_FOUL",
    "FlagrantFoul": "FLAGRANT_FOUL",
    "Charging Foul": "OFFENSIVE_FOUL",
    "ChargingFoul": "OFFENSIVE_FOUL",
    # Game flow - timeouts
    "Timeout": "TIMEOUT",
    "TV Timeout": "TIMEOUT",
    "TVTimeout": "TIMEOUT",
    "Team Timeout": "TIMEOUT",
    "TeamTimeout": "TIMEOUT",
    "Official Timeout": "TIMEOUT",
    "OfficialTimeout": "TIMEOUT",
    "OfficialTVTimeOut": "TIMEOUT",
    "ShortTimeOut": "TIMEOUT",
    "FullTimeOut": "TIMEOUT",
    "Media Timeout": "TIMEOUT",
    "MediaTimeout": "TIMEOUT",
    # Other game flow
    "Substitution": "SUBSTITUTION",
    "JumpBall": "JUMP_BALL",
    "Jumpball": "JUMP_BALL",
    "Jump Ball": "JUMP_BALL",
    # Coach's challenge
    "Coach's Challenge (Stands)": "CHALLENGE",
    "Coach's Challenge (Overturned)": "CHALLENGE",
    "CoachsChallenge": "CHALLENGE",
    # Blocks
    "Block": "BLOCK",
    "Block Shot": "BLOCK",
    "BlockShot": "BLOCK",
    "Blocked Shot": "BLOCK",
    "BlockedShot": "BLOCK",
    # Period markers
    "End Period": "END_PERIOD",
    "EndPeriod": "END_PERIOD",
    "End Game": "END_GAME",
    "EndGame": "END_GAME",
    "End of Period": "END_PERIOD",
    "EndOfPeriod": "END_PERIOD",
    "Start Period": "START_PERIOD",
    "StartPeriod": "START_PERIOD",
    "Game Start": "GAME_START",
    "GameStart": "GAME_START",
    "End of Half": "END_PERIOD",
    "EndOfHalf": "END_PERIOD",
    "Start of Half": "START_PERIOD",
    "StartOfHalf": "START_PERIOD",
}


@dataclass(frozen=True)
class NCAABLiveGame:
    """Represents a game from the CBB API schedule."""

    game_id: int
    game_date: datetime
    status: str
    season: int
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    home_score: int | None
    away_score: int | None
    neutral_site: bool


@dataclass
class NCAABBoxscore:
    """Represents boxscore data from the CBB API.

    Contains team and player stats parsed from the games/teams and games/players endpoints.
    """

    game_id: int
    game_date: datetime
    status: str
    season: int
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int
    away_score: int
    team_boxscores: list[NormalizedTeamBoxscore]
    player_boxscores: list[NormalizedPlayerBoxscore]


class NCAABLiveFeedClient:
    """Client for NCAAB data using api.collegebasketballdata.com."""

    def __init__(self) -> None:
        api_key = settings.cbb_stats_api_key
        if not api_key:
            logger.warning("ncaab_api_key_missing", message="CBB_STATS_API_KEY not configured")

        timeout = settings.scraper_config.request_timeout_seconds
        # API uses Bearer token authentication
        headers = {
            "User-Agent": "sports-data-admin-live/1.0",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }
        self.client = httpx.Client(timeout=timeout, headers=headers)
        # Cache of team_id -> displayName (e.g., "Cincinnati Bearcats")
        # Populated lazily on first use
        self._team_names: dict[int, str] = {}
        # API response cache to reduce API calls (1000/day limit)
        self._cache = APICache(settings.scraper_config.html_cache_dir, "cbb")

    def _get_season_for_date(self, game_date: date) -> int:
        """Calculate NCAAB season year from a game date.

        The CBB API uses the ending year of the season (e.g., 2026 for 2025-2026 season).
        NCAAB season runs from November to April:
        - November-December games: season = next year (Nov 2025 -> season 2026)
        - January-April games: season = current year (Jan 2026 -> season 2026)
        """
        if game_date.month >= 11:
            # November-December: season ends next year
            return game_date.year + 1
        else:
            # January-April: season ends this year
            return game_date.year

    def _ensure_team_names(self, season: int) -> None:
        """Fetch and cache team displayNames for matching against Odds API names.

        The teams endpoint returns displayName (e.g., "Cincinnati Bearcats") which
        matches what the Odds API uses, while the games endpoint only returns
        short names (e.g., "Cincinnati").
        """
        if self._team_names:
            return  # Already cached

        try:
            response = self.client.get(
                "https://api.collegebasketballdata.com/teams",
                params={"season": season},
            )
            if response.status_code == 200:
                teams = response.json()
                for team in teams:
                    team_id = team.get("id")
                    display_name = team.get("displayName", "")
                    if team_id and display_name:
                        self._team_names[int(team_id)] = display_name
                logger.info("ncaab_teams_cached", count=len(self._team_names))
        except Exception as exc:
            logger.warning("ncaab_teams_fetch_failed", error=str(exc))

    def _get_team_display_name(self, team_id: int, fallback: str) -> str:
        """Get team displayName from cache, falling back to provided name."""
        return self._team_names.get(team_id, fallback)

    def fetch_games(
        self,
        start: date,
        end: date,
        season: int | None = None,
    ) -> list[NCAABLiveGame]:
        """Fetch NCAAB games for a date range.

        Args:
            start: Start date
            end: End date
            season: Optional season year (calculated from dates if not provided)

        Returns:
            List of NCAABLiveGame objects
        """
        logger.info("ncaab_games_fetch", start=str(start), end=str(end), season=season)

        # Calculate season if not provided
        if season is None:
            season = self._get_season_for_date(start)

        # Ensure team names are cached for proper matching
        self._ensure_team_names(season)

        games: list[NCAABLiveGame] = []

        try:
            # The API takes startDateRange and endDateRange as query params
            params = {
                "season": season,
                "startDateRange": start.strftime("%Y-%m-%d"),
                "endDateRange": end.strftime("%Y-%m-%d"),
            }

            response = self.client.get(CBB_GAMES_URL, params=params)

            if response.status_code == 401:
                logger.error(
                    "ncaab_games_auth_failed",
                    status=response.status_code,
                    message="Invalid or missing API key",
                )
                return []

            if response.status_code != 200:
                logger.warning(
                    "ncaab_games_fetch_failed",
                    status=response.status_code,
                    body=response.text[:200] if response.text else "",
                )
                return []

            data = response.json()
            for game in data:
                parsed = self._parse_game(game, season)
                if parsed:
                    games.append(parsed)

        except Exception as exc:
            logger.warning(
                "ncaab_games_fetch_error",
                start=str(start),
                end=str(end),
                error=str(exc),
            )

        logger.info("ncaab_games_parsed", count=len(games), start=str(start), end=str(end))
        return games

    def _parse_game(self, game: dict, season: int) -> NCAABLiveGame | None:
        """Parse a single game from the API response."""
        game_id = game.get("id")
        if game_id is None:
            return None

        # Parse game date
        start_date_str = game.get("startDate")
        if start_date_str:
            try:
                game_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
            except ValueError:
                game_date = now_utc()
        else:
            game_date = now_utc()

        # Determine status - API returns "final", "scheduled", "cancelled", etc.
        api_status = game.get("status", "scheduled")
        status = api_status if api_status in ("final", "scheduled", "cancelled") else "scheduled"

        # Extract team info - use displayName from teams cache for matching
        home_team_id = game.get("homeTeamId")
        home_team_short = game.get("homeTeam", "")
        home_team_name = self._get_team_display_name(home_team_id, home_team_short) if home_team_id else home_team_short

        away_team_id = game.get("awayTeamId")
        away_team_short = game.get("awayTeam", "")
        away_team_name = self._get_team_display_name(away_team_id, away_team_short) if away_team_id else away_team_short

        # Extract scores
        home_score = _parse_int(game.get("homeScore"))
        away_score = _parse_int(game.get("awayScore"))

        return NCAABLiveGame(
            game_id=int(game_id),
            game_date=game_date,
            status=status,
            season=season,
            home_team_id=home_team_id or 0,
            home_team_name=home_team_name,
            away_team_id=away_team_id or 0,
            away_team_name=away_team_name,
            home_score=home_score,
            away_score=away_score,
            neutral_site=game.get("neutralSite", False),
        )

    def fetch_game_teams_by_date_range(
        self, start_date: date, end_date: date, season: int
    ) -> list[dict]:
        """Fetch team-level boxscore stats for a date range.

        The CBB API ignores the gameId parameter and returns all games (paginated).
        Using date range filtering is more efficient - one API call for many games.
        Results are cached to avoid burning API quota on repeated runs.

        Args:
            start_date: Start of date range
            end_date: End of date range
            season: Season year

        Returns:
            List of team stats dictionaries for all games in the date range
        """
        # Check cache first
        cache_key = f"teams_{start_date}_{end_date}_{season}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info(
                "ncaab_game_teams_using_cache",
                start_date=str(start_date),
                end_date=str(end_date),
                season=season,
                row_count=len(cached) if isinstance(cached, list) else 0,
            )
            return cached

        logger.info(
            "ncaab_game_teams_fetch_by_date",
            start_date=str(start_date),
            end_date=str(end_date),
            season=season,
        )

        try:
            params = {
                "season": season,
                "startDateRange": start_date.strftime("%Y-%m-%d"),
                "endDateRange": end_date.strftime("%Y-%m-%d"),
            }
            response = self.client.get(CBB_GAMES_TEAMS_URL, params=params)

            if response.status_code != 200:
                logger.warning(
                    "ncaab_game_teams_fetch_failed",
                    start_date=str(start_date),
                    end_date=str(end_date),
                    status=response.status_code,
                    body=response.text[:200] if response.text else "",
                )
                return []

            data = response.json()
            logger.info(
                "ncaab_game_teams_fetched",
                start_date=str(start_date),
                end_date=str(end_date),
                row_count=len(data) if isinstance(data, list) else 1,
            )

            # Cache the response
            self._cache.put(cache_key, data)

            return data

        except Exception as exc:
            logger.warning(
                "ncaab_game_teams_fetch_error",
                start_date=str(start_date),
                end_date=str(end_date),
                error=str(exc),
            )
            return []

    def fetch_game_players_by_date_range(
        self, start_date: date, end_date: date, season: int
    ) -> list[dict]:
        """Fetch player-level boxscore stats for a date range.

        The CBB API ignores the gameId parameter and returns all games (paginated).
        Using date range filtering is more efficient - one API call for many games.
        Results are cached to avoid burning API quota on repeated runs.

        Args:
            start_date: Start of date range
            end_date: End of date range
            season: Season year

        Returns:
            List of player stats dictionaries for all games in the date range
        """
        # Check cache first
        cache_key = f"players_{start_date}_{end_date}_{season}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info(
                "ncaab_game_players_using_cache",
                start_date=str(start_date),
                end_date=str(end_date),
                season=season,
                row_count=len(cached) if isinstance(cached, list) else 0,
            )
            return cached

        logger.info(
            "ncaab_game_players_fetch_by_date",
            start_date=str(start_date),
            end_date=str(end_date),
            season=season,
        )

        try:
            params = {
                "season": season,
                "startDateRange": start_date.strftime("%Y-%m-%d"),
                "endDateRange": end_date.strftime("%Y-%m-%d"),
            }
            response = self.client.get(CBB_GAMES_PLAYERS_URL, params=params)

            if response.status_code != 200:
                logger.warning(
                    "ncaab_game_players_fetch_failed",
                    start_date=str(start_date),
                    end_date=str(end_date),
                    status=response.status_code,
                    body=response.text[:200] if response.text else "",
                )
                return []

            data = response.json()
            logger.info(
                "ncaab_game_players_fetched",
                start_date=str(start_date),
                end_date=str(end_date),
                row_count=len(data) if isinstance(data, list) else 1,
            )

            # Cache the response
            self._cache.put(cache_key, data)

            return data

        except Exception as exc:
            logger.warning(
                "ncaab_game_players_fetch_error",
                start_date=str(start_date),
                end_date=str(end_date),
                error=str(exc),
            )
            return []

    def fetch_boxscores_batch(
        self,
        game_ids: list[int],
        start_date: date,
        end_date: date,
        season: int,
        team_names_by_game: dict[int, tuple[str, str]],
    ) -> dict[int, NCAABBoxscore]:
        """Fetch boxscores for multiple games in batch API calls.

        Instead of calling the API once per game (which returns all games anyway),
        this method makes just 2 API calls (teams + players) for the entire date range
        and filters the results to the requested game IDs.

        Args:
            game_ids: List of CBB game IDs to fetch boxscores for
            start_date: Start of date range
            end_date: End of date range
            season: Season year
            team_names_by_game: Dict mapping game_id -> (home_team_name, away_team_name)

        Returns:
            Dict mapping game_id -> NCAABBoxscore for successfully fetched games
        """
        from collections import defaultdict

        logger.info(
            "ncaab_boxscores_batch_fetch",
            game_count=len(game_ids),
            start_date=str(start_date),
            end_date=str(end_date),
            season=season,
        )

        # Convert to set for fast lookup
        game_id_set = set(game_ids)

        # Fetch all team stats for date range (1 API call)
        all_team_stats = self.fetch_game_teams_by_date_range(start_date, end_date, season)

        # Fetch all player stats for date range (1 API call)
        all_player_stats = self.fetch_game_players_by_date_range(start_date, end_date, season)

        # Group team stats by gameId
        team_stats_by_game: dict[int, list[dict]] = defaultdict(list)
        for ts in all_team_stats:
            gid = ts.get("gameId")
            if gid and int(gid) in game_id_set:
                team_stats_by_game[int(gid)].append(ts)

        # Group player stats by gameId
        player_stats_by_game: dict[int, list[dict]] = defaultdict(list)
        for ps in all_player_stats:
            gid = ps.get("gameId")
            if gid and int(gid) in game_id_set:
                player_stats_by_game[int(gid)].append(ps)

        logger.info(
            "ncaab_boxscores_batch_grouped",
            requested_games=len(game_ids),
            games_with_team_stats=len(team_stats_by_game),
            games_with_player_stats=len(player_stats_by_game),
        )

        # Build boxscores for requested game_ids
        results: dict[int, NCAABBoxscore] = {}
        for gid in game_ids:
            team_stats = team_stats_by_game.get(gid, [])
            if not team_stats:
                # No team stats found for this game
                continue

            player_stats = player_stats_by_game.get(gid, [])
            team_names = team_names_by_game.get(gid)
            if not team_names:
                continue

            home_team_name, away_team_name = team_names

            boxscore = self._build_boxscore_from_batch(
                gid, team_stats, player_stats, home_team_name, away_team_name, season
            )
            if boxscore:
                results[gid] = boxscore

        logger.info(
            "ncaab_boxscores_batch_complete",
            requested_games=len(game_ids),
            boxscores_built=len(results),
        )

        return results

    def _build_boxscore_from_batch(
        self,
        game_id: int,
        team_stats: list[dict],
        player_stats: list[dict],
        home_team_name: str,
        away_team_name: str,
        season: int,
    ) -> NCAABBoxscore | None:
        """Build a boxscore from pre-fetched team and player stats.

        Args:
            game_id: CBB game ID
            team_stats: Team stats rows for this game
            player_stats: Player stats rows for this game
            home_team_name: Home team name from DB
            away_team_name: Away team name from DB
            season: Season year

        Returns:
            NCAABBoxscore or None if data is incomplete
        """
        # Parse team stats to determine home/away and extract scores
        home_team_id = None
        away_team_id = None
        home_score = 0
        away_score = 0
        home_team_stats_raw = None
        away_team_stats_raw = None

        for ts in team_stats:
            team_id = ts.get("teamId")
            is_home = ts.get("isHome", False)
            stats = ts.get("teamStats", {}) or {}
            points = _extract_points(stats.get("points"))

            if is_home:
                home_team_id = team_id
                home_score = points
                home_team_stats_raw = ts
            else:
                away_team_id = team_id
                away_score = points
                away_team_stats_raw = ts

        # Build team identities using DB team names
        home_team = _build_team_identity(home_team_name, home_team_id or 0)
        away_team = _build_team_identity(away_team_name, away_team_id or 0)

        # Parse team boxscores
        team_boxscores: list[NormalizedTeamBoxscore] = []
        if home_team_stats_raw:
            team_boxscore = self._parse_team_stats_nested(
                home_team_stats_raw, home_team, True, home_score
            )
            team_boxscores.append(team_boxscore)
        if away_team_stats_raw:
            team_boxscore = self._parse_team_stats_nested(
                away_team_stats_raw, away_team, False, away_score
            )
            team_boxscores.append(team_boxscore)

        # Parse player boxscores from nested "players" array
        player_boxscores: list[NormalizedPlayerBoxscore] = []
        for ps in player_stats:
            team_id = ps.get("teamId")
            is_home = team_id == home_team_id
            team_identity = home_team if is_home else away_team

            players_list = ps.get("players", []) or []
            for player in players_list:
                player_boxscore = self._parse_player_stats(player, team_identity, game_id)
                if player_boxscore:
                    player_boxscores.append(player_boxscore)

        logger.info(
            "ncaab_boxscore_built_from_batch",
            game_id=game_id,
            home_team=home_team_name,
            away_team=away_team_name,
            home_score=home_score,
            away_score=away_score,
            team_stats_count=len(team_boxscores),
            player_stats_count=len(player_boxscores),
        )

        return NCAABBoxscore(
            game_id=game_id,
            game_date=now_utc(),  # Will be overwritten with actual date in ingestion
            status="final",
            season=season,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            team_boxscores=team_boxscores,
            player_boxscores=player_boxscores,
        )

    # Legacy methods kept for backwards compatibility but deprecated
    def fetch_game_teams(self, game_id: int, season: int) -> list[dict]:
        """Fetch team-level boxscore stats for a game.

        DEPRECATED: This method makes an API call that returns ALL games regardless
        of the gameId parameter. Use fetch_boxscores_batch() instead for efficiency.

        Args:
            game_id: CBB game ID (ignored by API)
            season: Season year

        Returns:
            List of team stats dictionaries (for ALL games, not filtered)
        """
        logger.info("ncaab_game_teams_fetch", game_id=game_id, season=season)

        try:
            params = {"gameId": game_id, "season": season}
            response = self.client.get(CBB_GAMES_TEAMS_URL, params=params)

            if response.status_code != 200:
                logger.warning(
                    "ncaab_game_teams_fetch_failed",
                    game_id=game_id,
                    status=response.status_code,
                    body=response.text[:200] if response.text else "",
                )
                return []

            data = response.json()
            # Debug: log sample of response structure
            if data:
                sample = data[0] if isinstance(data, list) else data
                logger.info(
                    "ncaab_game_teams_response_sample",
                    game_id=game_id,
                    row_count=len(data) if isinstance(data, list) else 1,
                    sample_keys=list(sample.keys()) if isinstance(sample, dict) else str(type(sample)),
                )
            return data

        except Exception as exc:
            logger.warning(
                "ncaab_game_teams_fetch_error",
                game_id=game_id,
                error=str(exc),
            )
            return []

    def fetch_game_players(self, game_id: int, season: int) -> list[dict]:
        """Fetch player-level boxscore stats for a game.

        DEPRECATED: This method makes an API call that returns ALL games regardless
        of the gameId parameter. Use fetch_boxscores_batch() instead for efficiency.

        Args:
            game_id: CBB game ID (ignored by API)
            season: Season year

        Returns:
            List of player stats dictionaries (for ALL games, not filtered)
        """
        logger.info("ncaab_game_players_fetch", game_id=game_id, season=season)

        try:
            params = {"gameId": game_id, "season": season}
            response = self.client.get(CBB_GAMES_PLAYERS_URL, params=params)

            if response.status_code != 200:
                logger.warning(
                    "ncaab_game_players_fetch_failed",
                    game_id=game_id,
                    status=response.status_code,
                    body=response.text[:200] if response.text else "",
                )
                return []

            data = response.json()
            # Debug: log sample of response structure
            if data:
                sample = data[0] if isinstance(data, list) else data
                logger.info(
                    "ncaab_game_players_response_sample",
                    game_id=game_id,
                    row_count=len(data) if isinstance(data, list) else 1,
                    sample_keys=list(sample.keys()) if isinstance(sample, dict) else str(type(sample)),
                )
            return data

        except Exception as exc:
            logger.warning(
                "ncaab_game_players_fetch_error",
                game_id=game_id,
                error=str(exc),
            )
            return []

    def fetch_boxscore(self, game: NCAABLiveGame) -> NCAABBoxscore | None:
        """Fetch full boxscore for a game.

        Args:
            game: NCAABLiveGame object with game details

        Returns:
            NCAABBoxscore with team and player stats, or None if fetch failed
        """
        logger.info("ncaab_boxscore_fetch", game_id=game.game_id, season=game.season)

        # Fetch team stats
        team_stats = self.fetch_game_teams(game.game_id, game.season)
        if not team_stats:
            logger.warning(
                "ncaab_boxscore_no_team_stats",
                game_id=game.game_id,
            )
            return None

        # Fetch player stats
        player_stats = self.fetch_game_players(game.game_id, game.season)

        # Build team identities
        home_team = _build_team_identity(game.home_team_name, game.home_team_id)
        away_team = _build_team_identity(game.away_team_name, game.away_team_id)

        # Parse team boxscores
        team_boxscores: list[NormalizedTeamBoxscore] = []
        home_score = game.home_score or 0
        away_score = game.away_score or 0

        for ts in team_stats:
            team_id = ts.get("teamId")
            is_home = team_id == game.home_team_id
            team_identity = home_team if is_home else away_team
            score = home_score if is_home else away_score

            team_boxscore = self._parse_team_stats(ts, team_identity, is_home, score)
            team_boxscores.append(team_boxscore)

        # Parse player boxscores
        player_boxscores: list[NormalizedPlayerBoxscore] = []
        for ps in player_stats:
            team_id = ps.get("teamId")
            is_home = team_id == game.home_team_id
            team_identity = home_team if is_home else away_team

            player_boxscore = self._parse_player_stats(ps, team_identity, game.game_id)
            if player_boxscore:
                player_boxscores.append(player_boxscore)

        logger.info(
            "ncaab_boxscore_parsed",
            game_id=game.game_id,
            status=game.status,
            home_score=home_score,
            away_score=away_score,
            home_players=len([p for p in player_boxscores if p.team.name == home_team.name]),
            away_players=len([p for p in player_boxscores if p.team.name == away_team.name]),
        )

        return NCAABBoxscore(
            game_id=game.game_id,
            game_date=game.game_date,
            status=game.status,
            season=game.season,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            team_boxscores=team_boxscores,
            player_boxscores=player_boxscores,
        )

    def fetch_boxscore_by_id(
        self,
        game_id: int,
        season: int,
        game_date: datetime,
        home_team_name: str,
        away_team_name: str,
    ) -> NCAABBoxscore | None:
        """Fetch boxscore directly by game ID without needing full game info.

        This is useful when we already have the cbb_game_id stored and don't need
        to re-fetch the schedule to get team info.

        Args:
            game_id: CBB game ID
            season: Season year (ending year, e.g., 2026 for 2025-2026)
            game_date: Game date
            home_team_name: Home team name (from DB)
            away_team_name: Away team name (from DB)

        Returns:
            NCAABBoxscore with team and player stats, or None if fetch failed
        """
        logger.info("ncaab_boxscore_fetch_by_id", game_id=game_id, season=season)

        # Fetch team stats - API returns ALL games, we need to filter
        all_team_stats = self.fetch_game_teams(game_id, season)
        if not all_team_stats:
            logger.warning(
                "ncaab_boxscore_no_team_stats",
                game_id=game_id,
            )
            return None

        # Filter to only rows for this specific game (ensure int comparison)
        target_game_id = int(game_id)
        team_stats = [ts for ts in all_team_stats if int(ts.get("gameId", 0)) == target_game_id]

        if not team_stats:
            # Debug: log sample of game IDs in response
            sample_ids = [ts.get("gameId") for ts in all_team_stats[:10]]
            logger.warning(
                "ncaab_boxscore_game_not_in_response",
                game_id=game_id,
                total_rows=len(all_team_stats),
                sample_game_ids=sample_ids,
            )
            return None

        logger.info(
            "ncaab_boxscore_filtered",
            game_id=game_id,
            matched_rows=len(team_stats),
        )

        # Fetch player stats - also returns ALL games
        all_player_stats = self.fetch_game_players(game_id, season)
        player_stats = [ps for ps in all_player_stats if int(ps.get("gameId", 0)) == target_game_id]

        # Each game should have 2 rows in team_stats (one per team)
        # Extract team info from team stats
        home_team_id = None
        away_team_id = None
        home_score = 0
        away_score = 0
        home_team_stats_raw = None
        away_team_stats_raw = None

        for ts in team_stats:
            team_id = ts.get("teamId")
            is_home = ts.get("isHome", False)
            # teamStats is a nested dict with the actual stats
            stats = ts.get("teamStats", {}) or {}
            points = stats.get("points", 0) or 0

            if is_home:
                home_team_id = team_id
                home_score = points
                home_team_stats_raw = ts
            else:
                away_team_id = team_id
                away_score = points
                away_team_stats_raw = ts

        # Build team identities using DB team names
        home_team = _build_team_identity(home_team_name, home_team_id or 0)
        away_team = _build_team_identity(away_team_name, away_team_id or 0)

        # Parse team boxscores (should be exactly 2)
        team_boxscores: list[NormalizedTeamBoxscore] = []
        if home_team_stats_raw:
            team_boxscore = self._parse_team_stats_nested(
                home_team_stats_raw, home_team, True, home_score
            )
            team_boxscores.append(team_boxscore)
        if away_team_stats_raw:
            team_boxscore = self._parse_team_stats_nested(
                away_team_stats_raw, away_team, False, away_score
            )
            team_boxscores.append(team_boxscore)

        # Parse player boxscores from nested "players" array
        player_boxscores: list[NormalizedPlayerBoxscore] = []
        for ps in player_stats:
            team_id = ps.get("teamId")
            is_home = team_id == home_team_id
            team_identity = home_team if is_home else away_team

            # players is a nested array
            players_list = ps.get("players", []) or []
            for player in players_list:
                player_boxscore = self._parse_player_stats(player, team_identity, game_id)
                if player_boxscore:
                    player_boxscores.append(player_boxscore)

        logger.info(
            "ncaab_boxscore_parsed_by_id",
            game_id=game_id,
            home_team=home_team_name,
            away_team=away_team_name,
            home_score=home_score,
            away_score=away_score,
            team_stats_count=len(team_boxscores),
            player_stats_count=len(player_boxscores),
        )

        return NCAABBoxscore(
            game_id=game_id,
            game_date=game_date,
            status="final",  # We only fetch boxscores for completed games
            season=season,
            home_team=home_team,
            away_team=away_team,
            home_score=home_score,
            away_score=away_score,
            team_boxscores=team_boxscores,
            player_boxscores=player_boxscores,
        )

    def _parse_team_stats_nested(
        self,
        ts: dict,
        team_identity: TeamIdentity,
        is_home: bool,
        score: int,
    ) -> NormalizedTeamBoxscore:
        """Parse team-level stats from games/teams endpoint (nested format).

        The API returns stats in a nested 'teamStats' dict.
        """
        stats = ts.get("teamStats", {}) or {}

        return NormalizedTeamBoxscore(
            team=team_identity,
            is_home=is_home,
            points=score,
            rebounds=_parse_int(stats.get("totalRebounds")) or _parse_int(stats.get("rebounds")),
            assists=_parse_int(stats.get("assists")),
            turnovers=_parse_int(stats.get("turnovers")),
            raw_stats=stats,
        )

    def _parse_team_stats(
        self,
        ts: dict,
        team_identity: TeamIdentity,
        is_home: bool,
        score: int,
    ) -> NormalizedTeamBoxscore:
        """Parse team-level stats from games/teams endpoint."""
        # The API provides various stats under different keys
        # We'll extract what's available and store rest in raw_stats
        raw_stats = {k: v for k, v in ts.items() if v is not None}

        return NormalizedTeamBoxscore(
            team=team_identity,
            is_home=is_home,
            points=score,
            rebounds=_parse_int(ts.get("rebounds")) or _parse_int(ts.get("totalRebounds")),
            assists=_parse_int(ts.get("assists")),
            turnovers=_parse_int(ts.get("turnovers")),
            raw_stats=raw_stats,
        )

    def _parse_player_stats(
        self,
        ps: dict,
        team_identity: TeamIdentity,
        game_id: int,
    ) -> NormalizedPlayerBoxscore | None:
        """Parse player-level stats from games/players endpoint."""
        player_id = ps.get("playerId") or ps.get("athleteId")
        if not player_id:
            return None

        player_name = ps.get("player") or ps.get("athleteName") or ""
        if not player_name:
            logger.warning(
                "ncaab_boxscore_player_no_name",
                game_id=game_id,
                player_id=player_id,
            )
            return None

        # Parse minutes (may be "MM:SS" format or just minutes)
        minutes = _parse_minutes(ps.get("minutes"))

        # Build raw stats dict
        raw_stats = {k: v for k, v in ps.items() if v is not None and k not in [
            "playerId", "athleteId", "player", "athleteName", "teamId", "team", "minutes"
        ]}

        return NormalizedPlayerBoxscore(
            player_id=str(player_id),
            player_name=player_name,
            team=team_identity,
            player_role=None,  # NCAAB doesn't have skater/goalie distinction
            position=ps.get("position"),
            sweater_number=None,  # Not typically available
            minutes=minutes,
            points=_parse_int(ps.get("points")),
            rebounds=_parse_int(ps.get("rebounds")) or _parse_int(ps.get("totalRebounds")),
            assists=_parse_int(ps.get("assists")),
            # Basketball-specific stats
            goals=_parse_int(ps.get("fieldGoalsMade")),  # Using goals field for FGM
            shots_on_goal=_parse_int(ps.get("fieldGoalsAttempted")),  # FGA
            blocked_shots=_parse_int(ps.get("blocks")),
            raw_stats=raw_stats,
        )

    def fetch_play_by_play(self, game_id: int) -> NormalizedPlayByPlay:
        """Fetch and normalize play-by-play data for a game.

        Results are cached to avoid burning API quota on repeated runs.

        Args:
            game_id: CBB game ID

        Returns:
            NormalizedPlayByPlay with all events normalized to canonical format
        """
        # Check cache first
        cache_key = f"pbp_{game_id}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("ncaab_pbp_using_cache", game_id=game_id)
            plays = self._parse_pbp_response(cached, game_id)
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=plays)

        url = CBB_PLAYS_GAME_URL.format(game_id=game_id)
        logger.info("ncaab_pbp_fetch", url=url, game_id=game_id)

        try:
            response = self.client.get(url)
        except Exception as exc:
            logger.error("ncaab_pbp_fetch_error", game_id=game_id, error=str(exc))
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        if response.status_code == 404:
            logger.warning("ncaab_pbp_not_found", game_id=game_id, status=404)
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        if response.status_code != 200:
            logger.warning(
                "ncaab_pbp_fetch_failed",
                game_id=game_id,
                status=response.status_code,
                body=response.text[:200] if response.text else "",
            )
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        payload = response.json()

        # Cache the raw response
        self._cache.put(cache_key, payload)

        plays = self._parse_pbp_response(payload, game_id)

        # Log first and last event for debugging
        if plays:
            logger.info(
                "ncaab_pbp_parsed",
                game_id=game_id,
                count=len(plays),
                first_event=plays[0].play_type,
                first_period=plays[0].quarter,
                last_event=plays[-1].play_type,
                last_period=plays[-1].quarter,
            )
        else:
            logger.info("ncaab_pbp_parsed", game_id=game_id, count=0)

        return NormalizedPlayByPlay(source_game_key=str(game_id), plays=plays)

    def _parse_pbp_response(self, payload: list, game_id: int) -> list[NormalizedPlay]:
        """Parse the play-by-play response from the CBB API."""
        plays: list[NormalizedPlay] = []

        for idx, play in enumerate(payload):
            normalized = self._normalize_play(play, idx, game_id)
            if normalized:
                plays.append(normalized)

        # Sort by play_index to ensure canonical ordering
        plays.sort(key=lambda p: p.play_index)

        return plays

    def _normalize_play(
        self,
        play: dict[str, Any],
        index: int,
        game_id: int,
    ) -> NormalizedPlay | None:
        """Normalize a single play event from the CBB API."""
        # Extract period info
        period = _parse_int(play.get("period"))

        # Get sequence number if available, otherwise use index
        sequence = _parse_int(play.get("sequenceNumber")) or index

        # Build play_index: period * multiplier + sequence for stable ordering
        play_index = (period or 0) * NCAAB_PERIOD_MULTIPLIER + sequence

        # Get timing info
        clock = play.get("clock") or play.get("timeRemaining")
        elapsed = play.get("elapsed") or play.get("secondsRemaining")

        # Get event type
        play_type_raw = play.get("playType") or play.get("type") or ""
        play_type = self._map_event_type(play_type_raw, game_id)

        # Extract team info
        team_name = play.get("team") or play.get("teamName")

        # Extract player info
        player_id = play.get("playerId") or play.get("athleteId")
        player_name = play.get("player") or play.get("athleteName")

        # Get scores
        home_score = _parse_int(play.get("homeScore"))
        away_score = _parse_int(play.get("awayScore"))

        # Get description
        description = play.get("description") or play.get("text")

        # Build raw_data with all source-specific details
        raw_data = {
            "sequence": sequence,
            "clock": clock,
            "elapsed": elapsed,
            "play_type_raw": play_type_raw,
        }
        # Add any additional fields from the API
        for key in ["shotType", "shotOutcome", "assistPlayerId", "foulType"]:
            if key in play and play[key] is not None:
                raw_data[key] = play[key]

        return NormalizedPlay(
            play_index=play_index,
            quarter=period,  # Using quarter field for period (NCAA has halves, but API may use periods)
            game_clock=clock,
            play_type=play_type,
            team_abbreviation=team_name,  # Using full name since NCAAB has no standard abbreviations
            player_id=str(player_id) if player_id else None,
            player_name=player_name,
            description=description,
            home_score=home_score,
            away_score=away_score,
            raw_data=raw_data,
        )

    def _map_event_type(self, play_type_raw: str, game_id: int) -> str:
        """Map CBB play type to normalized event type.

        Unknown types are logged and stored with original key.
        """
        if not play_type_raw:
            return "UNKNOWN"

        mapped = NCAAB_EVENT_TYPE_MAP.get(play_type_raw)
        if mapped:
            return mapped

        # Log unknown event type but don't fail
        logger.warning(
            "ncaab_pbp_unknown_event_type",
            game_id=game_id,
            play_type=play_type_raw,
        )
        return play_type_raw.upper().replace(" ", "_")


def _build_team_identity(name: str, team_id: int) -> TeamIdentity:
    """Build TeamIdentity for an NCAAB team.

    NCAAB has hundreds of teams, so we don't have a canonical mapping.
    We store the name as-is and use the API team ID as external_ref.
    """
    return TeamIdentity(
        league_code="NCAAB",
        name=name,
        short_name=name,  # Use full name since abbreviations vary
        abbreviation=None,  # NCAAB teams don't have standard abbreviations
        external_ref=str(team_id),
    )


def _parse_int(value: str | int | float | None) -> int | None:
    """Safely parse an integer value."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_points(value: int | dict | None) -> int:
    """Extract points from API response which may be int or dict.

    The CBB API sometimes returns points as an integer, and sometimes as a dict:
    {"total": 89, "byPeriod": [...], "offTurnovers": 17}

    This handles both formats.
    """
    if value is None:
        return 0
    if isinstance(value, dict):
        # New format: {"total": 89, ...}
        return _parse_int(value.get("total")) or 0
    # Old format: just an integer
    return _parse_int(value) or 0


def _parse_minutes(value: str | int | float | None) -> float | None:
    """Parse minutes value which may be 'MM:SS' or numeric."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # Try parsing "MM:SS" format
        if ":" in value:
            try:
                parts = value.split(":")
                if len(parts) == 2:
                    mins = int(parts[0])
                    secs = int(parts[1])
                    return round(mins + secs / 60, 2)
            except (ValueError, IndexError):
                pass

        # Try parsing as plain number
        try:
            return float(value)
        except ValueError:
            pass

    return None
