"""Shared stat models and common types."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TeamStat(BaseModel):
    """Team boxscore stats with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    is_home: bool = Field(..., alias="isHome")
    stats: dict[str, Any]
    source: str | None = None
    updated_at: datetime | None = Field(None, alias="updatedAt")


class PlayerStat(BaseModel):
    """Generic player stat for NBA/NCAAB/NFL with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    # Flattened common stats for frontend display
    minutes: float | None = None
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    yards: int | None = None
    touchdowns: int | None = None
    # Full raw stats dict for detail view
    raw_stats: dict[str, Any] = Field(default_factory=dict, alias="rawStats")
    source: str | None = None
    updated_at: datetime | None = Field(None, alias="updatedAt")


class NHLSkaterStat(BaseModel):
    """NHL skater (non-goalie) stats with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    # Time on ice in MM:SS format
    toi: str | None = None
    goals: int | None = None
    assists: int | None = None
    points: int | None = None
    shots_on_goal: int | None = Field(None, alias="shotsOnGoal")
    plus_minus: int | None = Field(None, alias="plusMinus")
    penalty_minutes: int | None = Field(None, alias="penaltyMinutes")
    hits: int | None = None
    blocked_shots: int | None = Field(None, alias="blockedShots")
    raw_stats: dict[str, Any] = Field(default_factory=dict, alias="rawStats")
    source: str | None = None
    updated_at: datetime | None = Field(None, alias="updatedAt")


class NHLGoalieStat(BaseModel):
    """NHL goalie stats with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    player_name: str = Field(..., alias="playerName")
    # Time on ice in MM:SS format
    toi: str | None = None
    shots_against: int | None = Field(None, alias="shotsAgainst")
    saves: int | None = None
    goals_against: int | None = Field(None, alias="goalsAgainst")
    save_percentage: float | None = Field(None, alias="savePercentage")
    raw_stats: dict[str, Any] = Field(default_factory=dict, alias="rawStats")
    source: str | None = None
    updated_at: datetime | None = Field(None, alias="updatedAt")


class OddsEntry(BaseModel):
    """Odds entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    book: str
    market_type: str = Field(..., alias="marketType")
    side: str | None = None
    line: float | None = None
    price: float | None = None
    is_closing_line: bool = Field(..., alias="isClosingLine")
    observed_at: datetime | None = Field(None, alias="observedAt")


class GamePhase(str, Enum):
    pregame = "pregame"
    in_game = "in_game"
    postgame = "postgame"


class SocialPostEntry(BaseModel):
    """Social post entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    post_url: str = Field(..., alias="postUrl")
    posted_at: datetime = Field(..., alias="postedAt")
    has_video: bool = Field(..., alias="hasVideo")
    team_abbreviation: str = Field(..., alias="teamAbbreviation")
    tweet_text: str | None = Field(None, alias="tweetText")
    video_url: str | None = Field(None, alias="videoUrl")
    image_url: str | None = Field(None, alias="imageUrl")
    source_handle: str | None = Field(None, alias="sourceHandle")
    media_type: str | None = Field(None, alias="mediaType")
    game_phase: GamePhase | None = Field(None, alias="gamePhase")
    likes_count: int | None = Field(None, alias="likesCount")
    retweets_count: int | None = Field(None, alias="retweetsCount")
    replies_count: int | None = Field(None, alias="repliesCount")


class PlayEntry(BaseModel):
    """Play entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    play_index: int = Field(..., alias="playIndex")
    quarter: int | None = None
    game_clock: str | None = Field(None, alias="gameClock")
    period_label: str | None = Field(None, alias="periodLabel")
    time_label: str | None = Field(None, alias="timeLabel")
    play_type: str | None = Field(None, alias="playType")
    team_abbreviation: str | None = Field(None, alias="teamAbbreviation")
    player_name: str | None = Field(None, alias="playerName")
    description: str | None = None
    home_score: int | None = Field(None, alias="homeScore")
    away_score: int | None = Field(None, alias="awayScore")
    tier: int | None = None


class TieredPlayGroup(BaseModel):
    """Group of consecutive Tier-3 plays collapsed into a summary."""

    model_config = ConfigDict(populate_by_name=True)

    start_index: int = Field(..., alias="startIndex")
    end_index: int = Field(..., alias="endIndex")
    play_indices: list[int] = Field(..., alias="playIndices")
    summary_label: str = Field(..., alias="summaryLabel")


class NHLDataHealth(BaseModel):
    """NHL-specific data health indicators with camelCase output.

    Helps distinguish between legitimate empty data vs ingestion failure.
    Only populated for NHL games.
    """

    model_config = ConfigDict(populate_by_name=True)

    skater_count: int = Field(0, alias="skaterCount")
    goalie_count: int = Field(0, alias="goalieCount")
    is_healthy: bool = Field(True, alias="isHealthy")
    issues: list[str] = Field(default_factory=list)
