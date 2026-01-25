"""Live NBA feed helpers (scoreboard + play-by-play)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import re

import httpx

from ..config import settings
from ..logging import logger
from ..models import NormalizedPlay, NormalizedPlayByPlay
from ..utils.datetime_utils import now_utc

NBA_SCOREBOARD_URL = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_{date}.json"
NBA_PBP_URL = "https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json"
NBA_PERIOD_MULTIPLIER = 10000

_CLOCK_PATTERN = re.compile(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")


@dataclass(frozen=True)
class NBALiveGame:
    game_id: str
    game_date: datetime
    status: str
    status_text: str | None
    home_abbr: str
    away_abbr: str
    home_score: int | None
    away_score: int | None


class NBALiveFeedClient:
    """Client for NBA live scoreboard + play-by-play endpoints."""

    def __init__(self) -> None:
        timeout = settings.scraper_config.request_timeout_seconds
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": "sports-data-admin-live/1.0"})

    def fetch_scoreboard(self, day: date) -> list[NBALiveGame]:
        url = NBA_SCOREBOARD_URL.format(date=day.strftime("%Y%m%d"))
        logger.info("nba_scoreboard_fetch", url=url, date=str(day))
        response = self.client.get(url)
        if response.status_code != 200:
            logger.warning("nba_scoreboard_fetch_failed", status=response.status_code, body=response.text[:200])
            return []

        payload = response.json()
        games = payload.get("scoreboard", {}).get("games", [])
        live_games: list[NBALiveGame] = []
        for game in games:
            game_id = str(game.get("gameId"))
            game_status = game.get("gameStatus")
            status_text = game.get("gameStatusText")
            if game_status == 2:
                status = "live"
            elif game_status == 3:
                status = "final"
            else:
                status = "scheduled"

            game_date = _parse_nba_game_datetime(game.get("gameEt"))
            home_team = game.get("homeTeam", {})
            away_team = game.get("awayTeam", {})
            live_games.append(
                NBALiveGame(
                    game_id=game_id,
                    game_date=game_date,
                    status=status,
                    status_text=status_text,
                    home_abbr=str(home_team.get("teamTricode", "")),
                    away_abbr=str(away_team.get("teamTricode", "")),
                    home_score=_parse_int(home_team.get("score")),
                    away_score=_parse_int(away_team.get("score")),
                )
            )

        logger.info("nba_scoreboard_parsed", count=len(live_games), date=str(day))
        return live_games

    def fetch_play_by_play(self, game_id: str) -> NormalizedPlayByPlay:
        url = NBA_PBP_URL.format(game_id=game_id)
        logger.info("nba_pbp_fetch", url=url, game_id=game_id)
        response = self.client.get(url)
        if response.status_code != 200:
            logger.warning("nba_pbp_fetch_failed", game_id=game_id, status=response.status_code)
            return NormalizedPlayByPlay(source_game_key=game_id, plays=[])

        payload = response.json()
        actions = payload.get("game", {}).get("actions", [])
        plays: list[NormalizedPlay] = []
        for action in actions:
            period = _parse_int(action.get("period"))
            sequence = _parse_int(action.get("actionNumber"))
            if sequence is None:
                continue

            play_index = (period or 0) * NBA_PERIOD_MULTIPLIER + sequence
            clock_value = _parse_nba_clock(action.get("clock"))

            plays.append(
                NormalizedPlay(
                    play_index=play_index,
                    quarter=period,
                    game_clock=clock_value,
                    play_type=str(action.get("actionType")) if action.get("actionType") else None,
                    team_abbreviation=action.get("teamTricode"),
                    player_id=str(action.get("personId")) if action.get("personId") else None,
                    player_name=action.get("playerName"),
                    description=action.get("description"),
                    home_score=_parse_int(action.get("scoreHome")),
                    away_score=_parse_int(action.get("scoreAway")),
                    raw_data={
                        "event_time": action.get("timeActual") or action.get("timeActualUTC"),
                        "clock": action.get("clock"),
                        "period": period,
                        "sequence": sequence,
                    },
                )
            )

        logger.info("nba_pbp_parsed", game_id=game_id, count=len(plays))
        return NormalizedPlayByPlay(source_game_key=game_id, plays=plays)


def _parse_nba_game_datetime(value: str | None) -> datetime:
    if not value:
        return now_utc()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return now_utc()


def _parse_nba_clock(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("PT"):
        match = _CLOCK_PATTERN.match(value)
        if match:
            minutes = int(match.group(1) or 0)
            seconds = float(match.group(2) or 0)
            return f"{minutes}:{int(seconds):02d}"
    return value


def _parse_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
