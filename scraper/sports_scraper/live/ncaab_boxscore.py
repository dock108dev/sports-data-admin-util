"""NCAAB boxscore fetching and parsing.

Handles boxscore data from the CBB API games/teams and games/players endpoints.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import TYPE_CHECKING

import httpx

from ..logging import logger
from ..models import (
    NormalizedPlayerBoxscore,
    NormalizedTeamBoxscore,
    TeamIdentity,
)
from ..utils.cache import APICache
from ..utils.datetime_utils import now_utc
from ..utils.parsing import parse_int
from .ncaab_constants import CBB_GAMES_PLAYERS_URL, CBB_GAMES_TEAMS_URL
from .ncaab_helpers import build_team_identity, extract_points, parse_minutes
from .ncaab_models import NCAABBoxscore, NCAABLiveGame

if TYPE_CHECKING:
    pass


class NCAABBoxscoreFetcher:
    """Fetches and parses boxscore data from the CBB API."""

    def __init__(self, client: httpx.Client, cache: APICache) -> None:
        """Initialize the boxscore fetcher.

        Args:
            client: HTTP client for API requests
            cache: Cache for storing API responses
        """
        self.client = client
        self._cache = cache

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
        """Build a boxscore from pre-fetched team and player stats."""
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
            points = extract_points(stats.get("points"))

            if is_home:
                home_team_id = team_id
                home_score = points
                home_team_stats_raw = ts
            else:
                away_team_id = team_id
                away_score = points
                away_team_stats_raw = ts

        # Build team identities using DB team names
        home_team = build_team_identity(home_team_name, home_team_id or 0)
        away_team = build_team_identity(away_team_name, away_team_id or 0)

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

    def fetch_game_teams(self, game_id: int, season: int) -> list[dict]:
        """Fetch team-level boxscore stats for a game.

        Note: The API returns all games in the response regardless of gameId filter.
        For bulk operations, prefer fetch_boxscores_batch() for efficiency.
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

        Note: The API returns all games in the response regardless of gameId filter.
        For bulk operations, prefer fetch_boxscores_batch() for efficiency.
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
        """Fetch full boxscore for a game."""
        logger.info("ncaab_boxscore_fetch", game_id=game.game_id, season=game.season)

        # Fetch team stats
        team_stats = self.fetch_game_teams(game.game_id, game.season)
        if not team_stats:
            logger.warning("ncaab_boxscore_no_team_stats", game_id=game.game_id)
            return None

        # Fetch player stats
        player_stats = self.fetch_game_players(game.game_id, game.season)

        # Build team identities
        home_team = build_team_identity(game.home_team_name, game.home_team_id)
        away_team = build_team_identity(game.away_team_name, game.away_team_id)

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
        """Fetch boxscore directly by game ID without needing full game info."""
        logger.info("ncaab_boxscore_fetch_by_id", game_id=game_id, season=season)

        # Fetch team stats - API returns ALL games, we need to filter
        all_team_stats = self.fetch_game_teams(game_id, season)
        if not all_team_stats:
            logger.warning("ncaab_boxscore_no_team_stats", game_id=game_id)
            return None

        # Filter to only rows for this specific game
        target_game_id = int(game_id)
        team_stats = [ts for ts in all_team_stats if int(ts.get("gameId", 0)) == target_game_id]

        if not team_stats:
            sample_ids = [ts.get("gameId") for ts in all_team_stats[:10]]
            logger.warning(
                "ncaab_boxscore_game_not_in_response",
                game_id=game_id,
                total_rows=len(all_team_stats),
                sample_game_ids=sample_ids,
            )
            return None

        logger.info("ncaab_boxscore_filtered", game_id=game_id, matched_rows=len(team_stats))

        # Fetch player stats - also returns ALL games
        all_player_stats = self.fetch_game_players(game_id, season)
        player_stats = [ps for ps in all_player_stats if int(ps.get("gameId", 0)) == target_game_id]

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
        home_team = build_team_identity(home_team_name, home_team_id or 0)
        away_team = build_team_identity(away_team_name, away_team_id or 0)

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
            status="final",
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
        """Parse team-level stats from games/teams endpoint (nested format)."""
        stats = ts.get("teamStats", {}) or {}

        return NormalizedTeamBoxscore(
            team=team_identity,
            is_home=is_home,
            points=score,
            rebounds=parse_int(stats.get("totalRebounds")) or parse_int(stats.get("rebounds")),
            assists=parse_int(stats.get("assists")),
            turnovers=parse_int(stats.get("turnovers")),
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
        raw_stats = {k: v for k, v in ts.items() if v is not None}

        return NormalizedTeamBoxscore(
            team=team_identity,
            is_home=is_home,
            points=score,
            rebounds=parse_int(ts.get("rebounds")) or parse_int(ts.get("totalRebounds")),
            assists=parse_int(ts.get("assists")),
            turnovers=parse_int(ts.get("turnovers")),
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

        player_name = ps.get("name") or ps.get("player") or ps.get("athleteName") or ""
        if not player_name:
            logger.warning(
                "ncaab_boxscore_player_no_name",
                game_id=game_id,
                player_id=player_id,
            )
            return None

        minutes = parse_minutes(ps.get("minutes"))

        raw_stats = {k: v for k, v in ps.items() if v is not None and k not in [
            "playerId", "athleteId", "player", "athleteName", "name", "teamId", "team", "minutes"
        ]}

        return NormalizedPlayerBoxscore(
            player_id=str(player_id),
            player_name=player_name,
            team=team_identity,
            player_role=None,
            position=ps.get("position"),
            sweater_number=None,
            minutes=minutes,
            points=parse_int(ps.get("points")),
            rebounds=parse_int(ps.get("rebounds")) or parse_int(ps.get("totalRebounds")),
            assists=parse_int(ps.get("assists")),
            goals=parse_int(ps.get("fieldGoalsMade")),
            shots_on_goal=parse_int(ps.get("fieldGoalsAttempted")),
            blocked_shots=parse_int(ps.get("blocks")),
            raw_stats=raw_stats,
        )
