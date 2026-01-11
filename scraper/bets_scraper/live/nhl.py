"""Live NHL feed helpers (schedule + play-by-play)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from ..config import settings
from ..logging import logger
from ..models import NormalizedPlay, NormalizedPlayByPlay, TeamIdentity
from ..normalization import normalize_team_name
from ..utils.datetime_utils import now_utc

NHL_SCHEDULE_URL = "https://statsapi.web.nhl.com/api/v1/schedule"
NHL_PBP_URL = "https://statsapi.web.nhl.com/api/v1/game/{game_id}/feed/live"
NHL_PERIOD_MULTIPLIER = 10000


@dataclass(frozen=True)
class NHLLiveGame:
    game_id: int
    game_date: datetime
    status: str
    status_text: str | None
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int | None
    away_score: int | None


class NHLLiveFeedClient:
    """Client for NHL live schedule + play-by-play endpoints."""

    def __init__(self) -> None:
        timeout = settings.scraper_config.request_timeout_seconds
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": "sports-data-admin-live/1.0"})

    def fetch_schedule(self, start: date, end: date) -> list[NHLLiveGame]:
        logger.info("nhl_schedule_fetch", start=str(start), end=str(end))
        response = self.client.get(
            NHL_SCHEDULE_URL,
            params={"startDate": start.strftime("%Y-%m-%d"), "endDate": end.strftime("%Y-%m-%d")},
        )
        if response.status_code != 200:
            logger.warning("nhl_schedule_fetch_failed", status=response.status_code, body=response.text[:200])
            return []

        payload = response.json()
        games: list[NHLLiveGame] = []
        for date_block in payload.get("dates", []):
            for game in date_block.get("games", []):
                game_id = game.get("gamePk")
                if game_id is None:
                    continue
                game_date = _parse_datetime(game.get("gameDate"))
                status_info = game.get("status", {})
                status_text = status_info.get("detailedState")
                status = _map_nhl_status(status_info.get("abstractGameState"), status_text)

                home_team = _build_team_identity(game.get("teams", {}).get("home", {}).get("team", {}))
                away_team = _build_team_identity(game.get("teams", {}).get("away", {}).get("team", {}))

                home_score = _parse_int(game.get("teams", {}).get("home", {}).get("score"))
                away_score = _parse_int(game.get("teams", {}).get("away", {}).get("score"))

                games.append(
                    NHLLiveGame(
                        game_id=int(game_id),
                        game_date=game_date,
                        status=status,
                        status_text=status_text,
                        home_team=home_team,
                        away_team=away_team,
                        home_score=home_score,
                        away_score=away_score,
                    )
                )

        logger.info("nhl_schedule_parsed", count=len(games), start=str(start), end=str(end))
        return games

    def fetch_play_by_play(self, game_id: int) -> NormalizedPlayByPlay:
        url = NHL_PBP_URL.format(game_id=game_id)
        logger.info("nhl_pbp_fetch", url=url, game_id=game_id)
        response = self.client.get(url)
        if response.status_code != 200:
            logger.warning("nhl_pbp_fetch_failed", game_id=game_id, status=response.status_code)
            return NormalizedPlayByPlay(source_game_key=str(game_id), plays=[])

        payload = response.json()
        plays: list[NormalizedPlay] = []
        for play in payload.get("liveData", {}).get("plays", {}).get("allPlays", []):
            about = play.get("about", {})
            result = play.get("result", {})
            period = _parse_int(about.get("period"))
            sequence = _parse_int(about.get("eventIdx"))
            if sequence is None:
                continue

            play_index = (period or 0) * NHL_PERIOD_MULTIPLIER + sequence
            game_clock = about.get("periodTimeRemaining") or about.get("periodTime")

            primary_player = _pick_primary_player(play.get("players", []))
            team_abbr = _team_abbr_from_play(play.get("team"))

            # NHL uses periods and includes stoppage/penalty events; we keep period numeric
            # and store both remaining clock and absolute timestamps for schema clarity.
            plays.append(
                NormalizedPlay(
                    play_index=play_index,
                    quarter=period,
                    game_clock=game_clock,
                    play_type=result.get("eventTypeId"),
                    team_abbreviation=team_abbr,
                    player_id=str(primary_player.get("player", {}).get("id")) if primary_player else None,
                    player_name=primary_player.get("player", {}).get("fullName") if primary_player else None,
                    description=result.get("description"),
                    home_score=_parse_int(about.get("goals", {}).get("home")),
                    away_score=_parse_int(about.get("goals", {}).get("away")),
                    raw_data={
                        "event_time": about.get("dateTime"),
                        "event_time_remaining": game_clock,
                        "event_idx": sequence,
                        "event_id": about.get("eventId"),
                        "secondary_type": result.get("secondaryType"),
                    },
                )
            )

        logger.info("nhl_pbp_parsed", game_id=game_id, count=len(plays))
        return NormalizedPlayByPlay(source_game_key=str(game_id), plays=plays)


def _build_team_identity(team_payload: dict) -> TeamIdentity:
    name = team_payload.get("name") or ""
    canonical_name, abbreviation = normalize_team_name("NHL", name)
    return TeamIdentity(
        league_code="NHL",
        name=canonical_name,
        short_name=canonical_name,
        abbreviation=abbreviation,
        external_ref=abbreviation,
    )


def _team_abbr_from_play(team_payload: dict | None) -> str | None:
    if not team_payload:
        return None
    name = team_payload.get("name")
    if not name:
        return None
    _, abbreviation = normalize_team_name("NHL", name)
    return abbreviation


def _pick_primary_player(players: list[dict]) -> dict | None:
    if not players:
        return None
    for player in players:
        if player.get("playerType") in {"Scorer", "Shooter", "Goalie", "PenaltyOn"}:
            return player
    return players[0]


def _map_nhl_status(state: str | None, detailed: str | None) -> str:
    if state == "Final" or (detailed or "").lower() == "final":
        return "final"
    if state == "Live" or (detailed or "").lower() in {"in progress", "in progress - critical"}:
        return "live"
    return "scheduled"


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return now_utc()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return now_utc()


def _parse_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
