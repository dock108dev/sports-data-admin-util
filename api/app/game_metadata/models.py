"""Pydantic models for game metadata."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TeamRatings(BaseModel):
    team_id: str
    conference: str
    elo: float
    kenpom_adj_eff: float | None = None
    projected_seed: int | None = None


class StandingsEntry(BaseModel):
    team_id: str
    conference_rank: int
    wins: int
    losses: int


class GameContext(BaseModel):
    game_id: str
    home_team: str
    away_team: str
    league: str
    start_time: datetime
    rivalry: bool = False
    projected_spread: float | None = None
    has_big_name_players: bool = False
    coach_vs_former_team: bool = False
    playoff_implications: bool = False
    national_broadcast: bool = False
    projected_total: float | None = None
