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
    def cap_end_date_to_today(cls, v: date | None) -> date:
        """Ensure end_date is never null or in the future.
        
        If end_date is None or in the future, cap it to today.
        This prevents scraper from trying to query future games.
        """
        today = date.today()
        if v is None or v > today:
            return today
        return v

    # Data type toggles
    boxscores: bool = Field(True, alias="boxscores")
    odds: bool = Field(True, alias="odds")
    social: bool = Field(False, alias="social")
    pbp: bool = Field(False, alias="pbp")
    team_stats: bool = Field(False, alias="teamStats")
    player_stats: bool = Field(False, alias="playerStats")

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
            "team_stats": self.team_stats,
            "player_stats": self.player_stats,
            "only_missing": self.only_missing,
            "updated_before": self.updated_before.isoformat() if self.updated_before else None,
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


class TeamStat(BaseModel):
    team: str
    is_home: bool
    stats: dict[str, Any]
    source: str | None = None
    updated_at: datetime | None = None


class PlayerStat(BaseModel):
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


class PlayerContribution(BaseModel):
    """Player with their stats in a moment."""
    name: str
    stats: dict[str, int] = Field(default_factory=dict)
    summary: str | None = None


class RunInfo(BaseModel):
    """Run metadata when a run contributed to a moment."""
    team: str  # "home" or "away"
    points: int
    unanswered: bool = True
    play_ids: list[int] = Field(default_factory=list)


class MomentEntry(BaseModel):
    """
    The single narrative unit.
    
    Every play belongs to exactly one moment.
    Moments are always chronological.
    
    MomentTypes:
    - LEAD_BUILD: Lead tier increased
    - CUT: Lead tier decreased (comeback)
    - TIE: Game returned to even
    - FLIP: Leader changed
    - CLOSING_CONTROL: Late-game lock-in
    - HIGH_IMPACT: Ejection, injury, etc.
    - NEUTRAL: Normal flow
    
    Moments are aggressively merged to stay within sport-specific budgets.
    """
    id: str                           # "m_001"
    type: str                         # See MomentTypes above
    start_play: int                   # First play index
    end_play: int                     # Last play index
    play_count: int                   # Number of plays
    teams: list[str] = Field(default_factory=list)
    primary_team: str | None = None
    players: list[PlayerContribution] = Field(default_factory=list)
    score_start: str = ""             # "12–15"
    score_end: str = ""               # "18–15"
    clock: str = ""                   # "Q2 8:45–6:12"
    is_notable: bool = False          # True for notable moments (key game events)
    is_period_start: bool = False     # True if this moment starts a new period
    note: str | None = None           # "7-0 run"
    
    # Lead Ladder state (may be None in legacy data)
    ladder_tier_before: int | None = 0
    ladder_tier_after: int | None = 0
    team_in_control: str | None = None  # "home", "away", or None
    key_play_ids: list[int] = Field(default_factory=list)
    
    # WHY THIS MOMENT EXISTS - mandatory for narrative clarity
    reason: dict | None = None  # {trigger, control_shift, narrative_delta}
    
    # Run metadata if a run contributed
    run_info: RunInfo | None = None
    
    # AI-generated content (SportsCenter-style, spoiler-safe)
    headline: str = ""   # max 60 chars
    summary: str = ""    # max 150 chars
    
    # Display hints (frontend doesn't need to guess)
    display_weight: str = "low"      # "high" | "medium" | "low"
    display_icon: str = "circle"     # Icon name suggestion
    display_color_hint: str = "neutral"  # "tension" | "positive" | "neutral" | "highlight"


class MomentReasonEntry(BaseModel):
    """Explains WHY a moment exists."""
    trigger: str  # "tier_cross" | "flip" | "tie" | "closing_lock" | "high_impact" | "opener"
    control_shift: str | None = None  # "home" | "away" | None
    narrative_delta: str  # "tension ↑" | "control gained" | "pressure relieved" | etc.


class MomentsResponse(BaseModel):
    """
    Response for GET /games/{game_id}/moments endpoint.
    
    Moments are already merged and within sport-specific budgets (e.g., NBA: 30 max).
    Each moment has a 'reason' field explaining why it exists.
    """
    game_id: int
    generated_at: datetime | None = None
    moments: list[MomentEntry]
    total_count: int
    
    # AI-generated game-level copy (SportsCenter-style, spoiler-safe)
    game_headline: str = ""   # max 80 chars
    game_subhead: str = ""    # max 120 chars


class GameDetailResponse(BaseModel):
    game: GameMeta
    team_stats: list[TeamStat]
    player_stats: list[PlayerStat]
    odds: list[OddsEntry]
    social_posts: list[SocialPostEntry]
    plays: list[PlayEntry]
    moments: list[MomentEntry]  # Full coverage; filter by is_notable for key moments
    derived_metrics: dict[str, Any]
    raw_payloads: dict[str, Any]


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
