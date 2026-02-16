"""Pydantic request/response models for timeline generation endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TimelineGenerationRequest(BaseModel):
    """Request to generate timeline for a specific game."""

    timeline_version: str = Field(
        default="v1", description="Timeline version identifier"
    )
    force: bool = Field(
        default=False,
        description="Force regeneration even if a timeline already exists (admin override)",
    )


class TimelineGenerationResponse(BaseModel):
    """Response after generating a timeline."""

    game_id: int
    timeline_version: str
    success: bool
    message: str


class MissingTimelineGame(BaseModel):
    """Game missing timeline artifact."""

    game_id: int
    game_date: str
    league: str
    home_team: str
    away_team: str
    status: str
    has_pbp: bool


class MissingTimelinesResponse(BaseModel):
    """List of games missing timeline artifacts."""

    games: list[MissingTimelineGame]
    total_count: int


class BatchGenerationRequest(BaseModel):
    """Request to generate timelines for multiple games."""

    league_code: str = Field(..., description="League to process (NBA, NHL, NCAAB)")
    days_back: int = Field(default=7, ge=1, le=30, description="Days back to check")
    max_games: int | None = Field(default=None, description="Max games to process")


class BatchGenerationResponse(BaseModel):
    """Response after batch timeline generation."""

    job_id: str
    message: str
    games_found: int


class SyncBatchGenerationResponse(BaseModel):
    """Response after synchronous batch timeline generation."""

    games_processed: int
    games_successful: int
    games_failed: int
    failed_game_ids: list[int]
    message: str


class RegenerateBatchRequest(BaseModel):
    """Request to regenerate timelines for specific games or all games with existing timelines."""

    game_ids: list[int] | None = Field(
        default=None, description="Specific game IDs to regenerate (None = all)"
    )
    league_code: str = Field(..., description="League to filter by (NBA, NHL, NCAAB)")
    days_back: int = Field(default=7, ge=1, le=90, description="Days back to check")


class ExistingTimelineGame(BaseModel):
    """Game with an existing timeline artifact."""

    game_id: int
    game_date: str
    league: str
    home_team: str
    away_team: str
    status: str
    timeline_generated_at: str


class ExistingTimelinesResponse(BaseModel):
    """List of games with existing timeline artifacts."""

    games: list[ExistingTimelineGame]
    total_count: int
