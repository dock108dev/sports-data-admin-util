"""Data models for NBA boxscore processing.

Contains dataclasses representing boxscores from the NBA CDN API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models import TeamIdentity


@dataclass
class NBABoxscore:
    """Represents boxscore data from the NBA CDN API.

    Contains team and player stats parsed from the boxscore endpoint.
    """

    game_id: str
    game_date: datetime
    status: str
    home_team: TeamIdentity
    away_team: TeamIdentity
    home_score: int
    away_score: int
    team_boxscores: list  # List of NormalizedTeamBoxscore
    player_boxscores: list  # List of NormalizedPlayerBoxscore
