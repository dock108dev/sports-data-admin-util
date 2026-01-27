"""Pydantic schemas for sports admin endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScrapeRunConfig(BaseModel):
    """Simplified scraper configuration."""

    model_config = ConfigDict(populate_by_name=True)

    league_code: str = Field(..., alias="leagueCode")
    season: int | None = Field(None, alias="season")
    season_type: str = Field("regular", alias="seasonType")
    start_date: date | None = Field(None, alias="startDate")
    end_date: date | None = Field(None, alias="endDate")

    @field_validator("end_date", mode="after")
    @classmethod
    def cap_end_date_to_reasonable_future(cls, v: date | None) -> date:
        """Ensure end_date is set and within a reasonable future window.

        If end_date is None, defaults to today.
        Allows up to 7 days in the future to support odds fetching for upcoming games.
        Boxscores for future dates simply return no data (graceful no-op).
        """
        from datetime import timedelta

        today = date.today()
        max_future = today + timedelta(days=7)

        if v is None:
            return today
        if v > max_future:
            return max_future
        return v

    # Data type toggles
    boxscores: bool = Field(True, alias="boxscores")
    odds: bool = Field(True, alias="odds")
    social: bool = Field(False, alias="social")
    pbp: bool = Field(False, alias="pbp")

    # Shared filters
    only_missing: bool = Field(False, alias="onlyMissing")
    updated_before: date | None = Field(None, alias="updatedBefore")

    # Optional book filter
    include_books: list[str] | None = Field(None, alias="books")

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "league_code": self.league_code.upper(),
            "season": self.season,
            "season_type": self.season_type,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "boxscores": self.boxscores,
            "odds": self.odds,
            "social": self.social,
            "pbp": self.pbp,
            "only_missing": self.only_missing,
            "updated_before": self.updated_before.isoformat()
            if self.updated_before
            else None,
            "include_books": self.include_books,
        }


class ScrapeRunCreateRequest(BaseModel):
    config: ScrapeRunConfig
    requested_by: str | None = Field(None, alias="requestedBy")


class ScrapeRunResponse(BaseModel):
    id: int
    league_code: str
    status: str
    scraper_type: str
    job_id: str | None = None
    season: int | None
    start_date: date | None
    end_date: date | None
    summary: str | None
    error_details: str | None = None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    requested_by: str | None
    config: dict[str, Any] | None = None


class GameSummary(BaseModel):
    id: int
    league_code: str
    game_date: datetime
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    has_boxscore: bool
    has_player_stats: bool
    has_odds: bool
    has_social: bool
    has_pbp: bool
    has_story: bool
    play_count: int
    social_post_count: int
    has_required_data: bool
    scrape_version: int | None
    last_scraped_at: datetime | None
    last_ingested_at: datetime | None
    last_pbp_at: datetime | None
    last_social_at: datetime | None


class GameListResponse(BaseModel):
    games: list[GameSummary]
    total: int
    next_offset: int | None
    with_boxscore_count: int | None = 0
    with_player_stats_count: int | None = 0
    with_odds_count: int | None = 0
    with_social_count: int | None = 0
    with_pbp_count: int | None = 0
    with_story_count: int | None = 0


class TeamStat(BaseModel):
    team: str
    is_home: bool
    stats: dict[str, Any]
    source: str | None = None
    updated_at: datetime | None = None


class PlayerStat(BaseModel):
    """Generic player stat for NBA/NCAAB/NFL."""

    team: str
    player_name: str
    # Flattened common stats for frontend display
    minutes: float | None = None
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    yards: int | None = None
    touchdowns: int | None = None
    # Full raw stats dict for detail view
    raw_stats: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_at: datetime | None = None


class NHLSkaterStat(BaseModel):
    """NHL skater (non-goalie) stats."""

    team: str
    player_name: str
    # Time on ice in MM:SS format
    toi: str | None = None
    goals: int | None = None
    assists: int | None = None
    points: int | None = None
    shots_on_goal: int | None = None
    plus_minus: int | None = None
    penalty_minutes: int | None = None
    hits: int | None = None
    blocked_shots: int | None = None
    raw_stats: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_at: datetime | None = None


class NHLGoalieStat(BaseModel):
    """NHL goalie stats."""

    team: str
    player_name: str
    # Time on ice in MM:SS format
    toi: str | None = None
    shots_against: int | None = None
    saves: int | None = None
    goals_against: int | None = None
    save_percentage: float | None = None
    raw_stats: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_at: datetime | None = None


class OddsEntry(BaseModel):
    book: str
    market_type: str
    side: str | None
    line: float | None
    price: float | None
    is_closing_line: bool
    observed_at: datetime | None


class GameMeta(BaseModel):
    id: int
    league_code: str
    season: int
    season_type: str | None
    game_date: datetime
    home_team: str
    away_team: str
    home_score: int | None
    away_score: int | None
    status: str
    scrape_version: int | None
    last_scraped_at: datetime | None
    last_ingested_at: datetime | None
    last_pbp_at: datetime | None
    last_social_at: datetime | None
    has_boxscore: bool
    has_player_stats: bool
    has_odds: bool
    has_social: bool
    has_pbp: bool
    has_story: bool
    play_count: int
    social_post_count: int
    home_team_x_handle: str | None = None
    away_team_x_handle: str | None = None


class GamePreviewScoreResponse(BaseModel):
    game_id: str
    excitement_score: int
    quality_score: int
    tags: list[str]
    nugget: str


class SocialPostEntry(BaseModel):
    id: int
    post_url: str
    posted_at: datetime
    has_video: bool
    team_abbreviation: str
    tweet_text: str | None = None
    video_url: str | None = None
    image_url: str | None = None
    source_handle: str | None = None
    media_type: str | None = None


class PlayEntry(BaseModel):
    play_index: int
    quarter: int | None = None
    game_clock: str | None = None
    play_type: str | None = None
    team_abbreviation: str | None = None
    player_name: str | None = None
    description: str | None = None
    home_score: int | None = None
    away_score: int | None = None


class NHLDataHealth(BaseModel):
    """NHL-specific data health indicators.

    Helps distinguish between legitimate empty data vs ingestion failure.
    Only populated for NHL games.
    """

    skater_count: int = 0
    goalie_count: int = 0
    is_healthy: bool = True
    issues: list[str] = Field(default_factory=list)


class GameDetailResponse(BaseModel):
    game: GameMeta
    team_stats: list[TeamStat]
    # Generic player stats (NBA, NCAAB, NFL, etc.)
    player_stats: list[PlayerStat]
    # NHL-specific player stats (only populated for NHL games)
    nhl_skaters: list[NHLSkaterStat] | None = None
    nhl_goalies: list[NHLGoalieStat] | None = None
    odds: list[OddsEntry]
    social_posts: list[SocialPostEntry]
    plays: list[PlayEntry]
    derived_metrics: dict[str, Any]
    raw_payloads: dict[str, Any]
    # NHL-specific data health (only populated for NHL games)
    data_health: NHLDataHealth | None = None


class JobResponse(BaseModel):
    run_id: int
    job_id: str | None
    message: str


class JobRunResponse(BaseModel):
    id: int
    phase: str
    leagues: list[str]
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    error_summary: str | None
    created_at: datetime


class MissingPbpEntry(BaseModel):
    game_id: int
    league_code: str
    status: str
    reason: str
    detected_at: datetime
    updated_at: datetime


class GameConflictEntry(BaseModel):
    league_code: str
    game_id: int
    conflict_game_id: int
    external_id: str
    source: str
    conflict_fields: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None


class TeamSummary(BaseModel):
    """Team summary for list view."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str = Field(alias="shortName")
    abbreviation: str
    league_code: str = Field(alias="leagueCode")
    games_count: int = Field(alias="gamesCount")


class TeamListResponse(BaseModel):
    """Response for teams list endpoint."""

    teams: list[TeamSummary]
    total: int


class TeamGameSummary(BaseModel):
    """Game summary for team detail."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    game_date: str = Field(alias="gameDate")
    opponent: str
    is_home: bool = Field(alias="isHome")
    score: str
    result: str


class TeamDetail(BaseModel):
    """Team detail with recent games."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str = Field(alias="shortName")
    abbreviation: str
    league_code: str = Field(alias="leagueCode")
    location: str | None
    external_ref: str | None = Field(alias="externalRef")
    x_handle: str | None = Field(None, alias="xHandle")
    x_profile_url: str | None = Field(None, alias="xProfileUrl")
    recent_games: list[TeamGameSummary] = Field(alias="recentGames")


class TeamSocialInfo(BaseModel):
    """Team social media information."""

    team_id: int = Field(..., alias="teamId")
    abbreviation: str
    x_handle: str | None = Field(None, alias="xHandle")
    x_profile_url: str | None = Field(None, alias="xProfileUrl")


# =============================================================================
# Story API Response Models (Task 6)
# =============================================================================


class StoryMoment(BaseModel):
    """A single condensed moment in the Story.

    This matches the Story contract exactly:
    - play_ids: All plays in this moment
    - explicitly_narrated_play_ids: Plays that must be narrated
    - period/clock/score: Context metadata
    - narrative: AI-generated narrative text
    """

    model_config = ConfigDict(from_attributes=True)

    play_ids: list[int] = Field(..., alias="playIds")
    explicitly_narrated_play_ids: list[int] = Field(..., alias="explicitlyNarratedPlayIds")
    period: int
    start_clock: str | None = Field(None, alias="startClock")
    end_clock: str | None = Field(None, alias="endClock")
    score_before: list[int] = Field(..., alias="scoreBefore")
    score_after: list[int] = Field(..., alias="scoreAfter")
    narrative: str


class StoryPlay(BaseModel):
    """A play referenced by a Story moment.

    Only plays referenced in moments are included.
    """

    model_config = ConfigDict(from_attributes=True)

    play_id: int = Field(..., alias="playId")
    play_index: int = Field(..., alias="playIndex")
    period: int
    clock: str | None
    play_type: str | None = Field(None, alias="playType")
    description: str | None
    home_score: int | None = Field(None, alias="homeScore")
    away_score: int | None = Field(None, alias="awayScore")


class StoryContent(BaseModel):
    """The Story content containing ordered moments."""

    model_config = ConfigDict(from_attributes=True)

    moments: list[StoryMoment]


class GameStoryResponse(BaseModel):
    """Response for GET /games/{game_id}/story.

    Returns the persisted Story exactly as stored.
    No transformation, no aggregation, no additional prose.
    """

    model_config = ConfigDict(from_attributes=True)

    game_id: int = Field(..., alias="gameId")
    story: StoryContent
    plays: list[StoryPlay]
    validation_passed: bool = Field(..., alias="validationPassed")
    validation_errors: list[str] = Field(default_factory=list, alias="validationErrors")
