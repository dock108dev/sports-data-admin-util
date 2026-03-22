"""Data models for NFL live feed processing.

Contains dataclasses representing games and boxscores from the ESPN API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import TeamIdentity


@dataclass(frozen=True)
class NFLLiveGame:
    """Represents a game from the ESPN NFL scoreboard API."""

    game_id: int
    game_date: datetime
    status: str
    status_text: str | None
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int | None
    away_score: int | None
    season_type: str | None


@dataclass
class NFLBoxscore:
    """Represents boxscore data from the ESPN NFL summary API."""

    game_id: int
    game_date: datetime
    status: str
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int
    away_score: int
    team_boxscores: list  # List of NormalizedTeamBoxscore
    player_boxscores: list  # List of NormalizedPlayerBoxscore
