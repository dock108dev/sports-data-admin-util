"""Data models for NCAAB live feed processing.

Contains dataclasses representing games and boxscores from the CBB API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import (
    NormalizedPlayerBoxscore,
    NormalizedTeamBoxscore,
    TeamIdentity,
)


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
