"""Pydantic models used by scrapers and odds clients."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


SportCode = Literal["NBA", "NFL", "NCAAF", "NCAAB", "MLB", "NHL"]
MarketType = Literal["spread", "total", "moneyline"]
ScraperType = Literal["boxscore", "odds", "boxscore_and_odds", "social", "all"]


class TeamIdentity(BaseModel):
    league_code: SportCode
    name: str
    short_name: str | None = None
    abbreviation: str | None = None
    external_ref: str | None = None


class GameIdentification(BaseModel):
    league_code: SportCode
    season: int
    season_type: str = "regular"
    game_date: datetime
    home_team: TeamIdentity
    away_team: TeamIdentity
    source_game_key: str | None = None


class NormalizedTeamBoxscore(BaseModel):
    team: TeamIdentity
    is_home: bool
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    turnovers: int | None = None
    passing_yards: int | None = None
    rushing_yards: int | None = None
    receiving_yards: int | None = None
    hits: int | None = None
    runs: int | None = None
    errors: int | None = None
    shots_on_goal: int | None = None
    penalty_minutes: int | None = None
    raw_stats: dict = Field(default_factory=dict)


class NormalizedPlayerBoxscore(BaseModel):
    player_id: str
    player_name: str
    team: TeamIdentity
    minutes: float | None = None
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    yards: int | None = None
    touchdowns: int | None = None
    shots_on_goal: int | None = None
    penalties: int | None = None
    raw_stats: dict = Field(default_factory=dict)


class NormalizedGame(BaseModel):
    identity: GameIdentification
    status: str = "completed"
    venue: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    team_boxscores: list[NormalizedTeamBoxscore] = Field(default_factory=list)
    player_boxscores: list[NormalizedPlayerBoxscore] = Field(default_factory=list)

    @field_validator("team_boxscores")
    @classmethod
    def ensure_team_alignment(cls, value: list[NormalizedTeamBoxscore]) -> list[NormalizedTeamBoxscore]:
        if not value:
            msg = "team_boxscores cannot be empty"
            raise ValueError(msg)
        return value


class NormalizedOddsSnapshot(BaseModel):
    league_code: SportCode
    book: str
    market_type: MarketType
    side: str | None = None
    line: float | None = None
    price: float | None = None
    observed_at: datetime
    home_team: TeamIdentity
    away_team: TeamIdentity
    game_date: datetime
    source_key: str | None = None
    is_closing_line: bool = True
    raw_payload: dict = Field(default_factory=dict)


class IngestionConfig(BaseModel):
    scraper_type: ScraperType = "boxscore_and_odds"
    league_code: SportCode
    season: int | None = None
    season_type: str = "regular"
    start_date: date | None = None
    end_date: date | None = None
    include_boxscores: bool = True
    include_odds: bool = True
    include_social: bool = False  # Scrape X posts for games
    rescrape_existing: bool = False
    only_missing: bool = False
    include_books: list[str] | None = None
    backfill_player_stats: bool = False  # Re-scrape games missing player boxscores
    backfill_odds: bool = False  # Fetch odds for games missing odds data
    backfill_social: bool = False  # Fetch social posts for games missing them
    # Social scraping specific options
    social_pre_game_hours: int = 2  # Hours before game to start collecting
    social_post_game_hours: int = 1  # Hours after game to stop collecting


