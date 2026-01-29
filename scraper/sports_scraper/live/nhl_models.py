"""Data models for NHL live feed processing.

Contains dataclasses representing games and boxscores from the NHL API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import TeamIdentity


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
