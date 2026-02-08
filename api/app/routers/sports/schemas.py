"""Pydantic schemas for sports admin endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    @model_validator(mode="after")
    def cap_end_date_for_boxscores(self) -> "ScrapeRunConfig":
        """Auto-cap end_date to yesterday when boxscores are enabled.

        Boxscores aren't available until the next day, so requesting today
        or later would fail. Instead of rejecting, silently cap to yesterday.
        """
        from datetime import timedelta

        if self.boxscores and self.end_date:
            yesterday = date.today() - timedelta(days=1)
            if self.end_date > yesterday:
                self.end_date = yesterday

        return self

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
    """Game summary for list view with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    league_code: str = Field(..., alias="leagueCode")
    game_date: datetime = Field(..., alias="gameDate")
    home_team: str = Field(..., alias="homeTeam")
    away_team: str = Field(..., alias="awayTeam")
    home_score: int | None = Field(None, alias="homeScore")
    away_score: int | None = Field(None, alias="awayScore")
    has_boxscore: bool = Field(..., alias="hasBoxscore")
    has_player_stats: bool = Field(..., alias="hasPlayerStats")
    has_odds: bool = Field(..., alias="hasOdds")
    has_social: bool = Field(..., alias="hasSocial")
    has_pbp: bool = Field(..., alias="hasPbp")
    has_story: bool = Field(..., alias="hasStory")
    play_count: int = Field(..., alias="playCount")
    social_post_count: int = Field(..., alias="socialPostCount")
    has_required_data: bool = Field(..., alias="hasRequiredData")
    scrape_version: int | None = Field(None, alias="scrapeVersion")
    last_scraped_at: datetime | None = Field(None, alias="lastScrapedAt")
    last_ingested_at: datetime | None = Field(None, alias="lastIngestedAt")
    last_pbp_at: datetime | None = Field(None, alias="lastPbpAt")
    last_social_at: datetime | None = Field(None, alias="lastSocialAt")


class GameListResponse(BaseModel):
    """Game list response with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    games: list[GameSummary]
    total: int
    next_offset: int | None = Field(None, alias="nextOffset")
    with_boxscore_count: int | None = Field(0, alias="withBoxscoreCount")
    with_player_stats_count: int | None = Field(0, alias="withPlayerStatsCount")
    with_odds_count: int | None = Field(0, alias="withOddsCount")
    with_social_count: int | None = Field(0, alias="withSocialCount")
    with_pbp_count: int | None = Field(0, alias="withPbpCount")
    with_story_count: int | None = Field(0, alias="withStoryCount")


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


class GameMeta(BaseModel):
    """Game metadata with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    league_code: str = Field(..., alias="leagueCode")
    season: int
    season_type: str | None = Field(None, alias="seasonType")
    game_date: datetime = Field(..., alias="gameDate")
    home_team: str = Field(..., alias="homeTeam")
    away_team: str = Field(..., alias="awayTeam")
    home_score: int | None = Field(None, alias="homeScore")
    away_score: int | None = Field(None, alias="awayScore")
    status: str
    scrape_version: int | None = Field(None, alias="scrapeVersion")
    last_scraped_at: datetime | None = Field(None, alias="lastScrapedAt")
    last_ingested_at: datetime | None = Field(None, alias="lastIngestedAt")
    last_pbp_at: datetime | None = Field(None, alias="lastPbpAt")
    last_social_at: datetime | None = Field(None, alias="lastSocialAt")
    has_boxscore: bool = Field(..., alias="hasBoxscore")
    has_player_stats: bool = Field(..., alias="hasPlayerStats")
    has_odds: bool = Field(..., alias="hasOdds")
    has_social: bool = Field(..., alias="hasSocial")
    has_pbp: bool = Field(..., alias="hasPbp")
    has_story: bool = Field(..., alias="hasStory")
    play_count: int = Field(..., alias="playCount")
    social_post_count: int = Field(..., alias="socialPostCount")
    home_team_x_handle: str | None = Field(None, alias="homeTeamXHandle")
    away_team_x_handle: str | None = Field(None, alias="awayTeamXHandle")


class GamePreviewScoreResponse(BaseModel):
    """Game preview score with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    game_id: str = Field(..., alias="gameId")
    excitement_score: int = Field(..., alias="excitementScore")
    quality_score: int = Field(..., alias="qualityScore")
    tags: list[str]
    nugget: str


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


class PlayEntry(BaseModel):
    """Play entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    play_index: int = Field(..., alias="playIndex")
    quarter: int | None = None
    game_clock: str | None = Field(None, alias="gameClock")
    play_type: str | None = Field(None, alias="playType")
    team_abbreviation: str | None = Field(None, alias="teamAbbreviation")
    player_name: str | None = Field(None, alias="playerName")
    description: str | None = None
    home_score: int | None = Field(None, alias="homeScore")
    away_score: int | None = Field(None, alias="awayScore")


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


class GameDetailResponse(BaseModel):
    """Game detail response with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    game: GameMeta
    team_stats: list[TeamStat] = Field(..., alias="teamStats")
    # Generic player stats (NBA, NCAAB, NFL, etc.)
    player_stats: list[PlayerStat] = Field(..., alias="playerStats")
    # NHL-specific player stats (only populated for NHL games)
    nhl_skaters: list[NHLSkaterStat] | None = Field(None, alias="nhlSkaters")
    nhl_goalies: list[NHLGoalieStat] | None = Field(None, alias="nhlGoalies")
    odds: list[OddsEntry]
    social_posts: list[SocialPostEntry] = Field(..., alias="socialPosts")
    plays: list[PlayEntry]
    derived_metrics: dict[str, Any] = Field(..., alias="derivedMetrics")
    raw_payloads: dict[str, Any] = Field(..., alias="rawPayloads")
    # NHL-specific data health (only populated for NHL games)
    data_health: NHLDataHealth | None = Field(None, alias="dataHealth")


class JobResponse(BaseModel):
    """Job response with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    run_id: int = Field(..., alias="runId")
    job_id: str | None = Field(None, alias="jobId")
    message: str


class JobRunResponse(BaseModel):
    """Job run response with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    phase: str
    leagues: list[str]
    status: str
    started_at: datetime = Field(..., alias="startedAt")
    finished_at: datetime | None = Field(None, alias="finishedAt")
    duration_seconds: float | None = Field(None, alias="durationSeconds")
    error_summary: str | None = Field(None, alias="errorSummary")
    created_at: datetime = Field(..., alias="createdAt")


class MissingPbpEntry(BaseModel):
    """Missing PBP entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    game_id: int = Field(..., alias="gameId")
    league_code: str = Field(..., alias="leagueCode")
    status: str
    reason: str
    detected_at: datetime = Field(..., alias="detectedAt")
    updated_at: datetime = Field(..., alias="updatedAt")


class GameConflictEntry(BaseModel):
    """Game conflict entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    league_code: str = Field(..., alias="leagueCode")
    game_id: int = Field(..., alias="gameId")
    conflict_game_id: int = Field(..., alias="conflictGameId")
    external_id: str = Field(..., alias="externalId")
    source: str
    conflict_fields: dict[str, Any] = Field(..., alias="conflictFields")
    created_at: datetime = Field(..., alias="createdAt")
    resolved_at: datetime | None = Field(None, alias="resolvedAt")


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


class MomentPlayerStat(BaseModel):
    """Player stat entry for cumulative box score."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    # Basketball stats
    pts: int | None = None
    reb: int | None = None
    ast: int | None = None
    three_pm: int | None = Field(None, alias="3pm")
    # Hockey stats
    goals: int | None = None
    assists: int | None = None
    sog: int | None = None
    plus_minus: int | None = Field(None, alias="plusMinus")


class MomentGoalieStat(BaseModel):
    """Goalie stat entry for NHL box score."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    saves: int
    ga: int
    save_pct: float = Field(..., alias="savePct")


class MomentTeamBoxScore(BaseModel):
    """Team box score for a moment."""

    model_config = ConfigDict(populate_by_name=True)

    team: str
    score: int
    players: list[MomentPlayerStat]
    goalie: MomentGoalieStat | None = None


class MomentBoxScore(BaseModel):
    """Cumulative box score at a moment in time."""

    model_config = ConfigDict(populate_by_name=True)

    home: MomentTeamBoxScore
    away: MomentTeamBoxScore


class StoryMoment(BaseModel):
    """A single condensed moment in the Story.

    This matches the Story contract exactly:
    - play_ids: All plays in this moment
    - explicitly_narrated_play_ids: Plays that must be narrated
    - period/clock/score: Context metadata
    - narrative: AI-generated narrative text
    - cumulative_box_score: Running player stats snapshot at this moment
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    play_ids: list[int] = Field(..., alias="playIds")
    explicitly_narrated_play_ids: list[int] = Field(..., alias="explicitlyNarratedPlayIds")
    period: int
    start_clock: str | None = Field(None, alias="startClock")
    end_clock: str | None = Field(None, alias="endClock")
    score_before: list[int] = Field(..., alias="scoreBefore")
    score_after: list[int] = Field(..., alias="scoreAfter")
    narrative: str | None = None  # Narrative is in blocks_json, not moments_json
    cumulative_box_score: MomentBoxScore | None = Field(None, alias="cumulativeBoxScore")


class StoryPlay(BaseModel):
    """A play referenced by a Story moment.

    Only plays referenced in moments are included.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

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

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    moments: list[StoryMoment]


class BlockMiniBox(BaseModel):
    """Mini box score for a narrative block with cumulative stats and segment deltas."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    home: dict[str, Any]  # {team, players: [{name, pts, delta_pts, ...}]}
    away: dict[str, Any]
    block_stars: list[str] = Field(default_factory=list)


class StoryBlock(BaseModel):
    """A narrative block grouping multiple moments.

    Blocks are the consumer-facing narrative output (Phase 1).
    Each block represents a stretch of play described in 1-2 sentences.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    block_index: int = Field(..., alias="blockIndex")
    role: str  # SemanticRole value: SETUP, MOMENTUM_SHIFT, RESPONSE, DECISION_POINT, RESOLUTION
    moment_indices: list[int] = Field(..., alias="momentIndices")
    period_start: int = Field(..., alias="periodStart")
    period_end: int = Field(..., alias="periodEnd")
    score_before: list[int] = Field(..., alias="scoreBefore")
    score_after: list[int] = Field(..., alias="scoreAfter")
    play_ids: list[int] = Field(..., alias="playIds")
    key_play_ids: list[int] = Field(..., alias="keyPlayIds")
    narrative: str | None = None
    mini_box: BlockMiniBox | None = Field(None, alias="miniBox")


class GameStoryResponse(BaseModel):
    """Response for GET /games/{game_id}/story.

    Returns the persisted Story exactly as stored.
    No transformation, no aggregation, no additional prose.

    Phase 1 additions:
    - blocks: 4-7 narrative blocks (consumer-facing output)
    - total_words: Total word count across all block narratives
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    game_id: int = Field(..., alias="gameId")
    story: StoryContent
    plays: list[StoryPlay]
    validation_passed: bool = Field(..., alias="validationPassed")
    validation_errors: list[str] = Field(default_factory=list, alias="validationErrors")
    # Phase 1: Block-based narratives
    blocks: list[StoryBlock] | None = None
    total_words: int | None = Field(None, alias="totalWords")


class TimelineArtifactResponse(BaseModel):
    """Finalized timeline artifact response."""

    model_config = ConfigDict(populate_by_name=True)

    game_id: int = Field(..., alias="gameId")
    sport: str
    timeline_version: str = Field(..., alias="timelineVersion")
    generated_at: datetime = Field(..., alias="generatedAt")
    timeline: list[dict[str, Any]]
    summary: dict[str, Any]
    game_analysis: dict[str, Any] = Field(..., alias="gameAnalysis")
