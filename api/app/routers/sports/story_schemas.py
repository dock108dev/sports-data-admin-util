"""
Pydantic schemas for Chapters-First Story Generation API.

ISSUE 14: Wire GameStory Output to Admin UI
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# PLAY ENTRY (REUSED)
# ============================================================================

class PlayEntry(BaseModel):
    """A single play from the game timeline."""
    
    play_index: int
    quarter: int | None = None
    game_clock: str | None = None
    play_type: str | None = None
    description: str
    team: str | None = None
    score_home: int | None = None
    score_away: int | None = None


# ============================================================================
# CHAPTER ENTRY
# ============================================================================

class TimeRange(BaseModel):
    """Game clock time range for a chapter."""
    
    start: str
    end: str


class ChapterEntry(BaseModel):
    """
    A contiguous narrative segment (scene) in the game.
    
    Chapters are the structural unit for storytelling and UI expansion.
    They are deterministic and defined by structural boundaries.
    """
    
    chapter_id: str = Field(..., description="Unique chapter ID (e.g., 'ch_001')")
    index: int = Field(..., description="Explicit chapter index for UI ordering")
    
    # Play range
    play_start_idx: int = Field(..., description="First play index (inclusive)")
    play_end_idx: int = Field(..., description="Last play index (inclusive)")
    play_count: int = Field(..., description="Number of plays in chapter")
    
    # Boundary explanation
    reason_codes: list[str] = Field(..., description="Why this chapter boundary exists")
    
    # Metadata
    period: int | None = Field(None, description="Quarter/period number")
    time_range: TimeRange | None = Field(None, description="Game clock range")
    
    # AI-generated (optional)
    chapter_summary: str | None = Field(None, description="1-3 sentence summary")
    chapter_title: str | None = Field(None, description="Short title (3-8 words)")
    
    # Plays (for expansion)
    plays: list[PlayEntry] = Field(default_factory=list, description="Raw plays in chapter")
    
    # Debug-only (optional)
    chapter_fingerprint: str | None = Field(None, description="Deterministic chapter hash")
    boundary_logs: list[dict[str, Any]] | None = Field(None, description="Debug boundary events")


# ============================================================================
# STORY STATE (FOR INSPECTION)
# ============================================================================

class PlayerStoryState(BaseModel):
    """Player signals exposed to AI."""
    
    player_name: str
    points_so_far: int
    made_fg_so_far: int
    made_3pt_so_far: int
    made_ft_so_far: int
    notable_actions_so_far: list[str] = Field(default_factory=list)


class TeamStoryState(BaseModel):
    """Team signals exposed to AI."""
    
    team_name: str
    score_so_far: int | None = None


class StoryStateResponse(BaseModel):
    """
    Running context for AI generation.
    
    Derived deterministically from prior chapters only.
    """
    
    chapter_index_last_processed: int
    players: dict[str, PlayerStoryState] = Field(default_factory=dict)
    teams: dict[str, TeamStoryState] = Field(default_factory=dict)
    momentum_hint: str = Field(..., description="surging | steady | slipping | volatile | unknown")
    theme_tags: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(
        default_factory=lambda: {
            "no_future_knowledge": True,
            "source": "derived_from_prior_chapters_only"
        }
    )


# ============================================================================
# GAME STORY RESPONSE
# ============================================================================

class GameStoryResponse(BaseModel):
    """
    The authoritative output for apps.
    
    Represents a game as a book with chapters.
    """
    
    game_id: int
    sport: str
    story_version: str = Field(default="1.0.0", description="Story generation version")
    
    # Chapters
    chapters: list[ChapterEntry] = Field(default_factory=list)
    chapter_count: int = Field(..., description="Total number of chapters")
    total_plays: int = Field(..., description="Total number of plays")
    
    # AI-generated full story (optional)
    compact_story: str | None = Field(None, description="Full game recap")
    reading_time_estimate_minutes: float | None = Field(None, description="Estimated reading time")
    
    # Metadata
    generated_at: datetime | None = Field(None, description="When story was generated")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    # Generation status
    has_summaries: bool = Field(False, description="Whether chapter summaries exist")
    has_titles: bool = Field(False, description="Whether chapter titles exist")
    has_compact_story: bool = Field(False, description="Whether compact story exists")


# ============================================================================
# REGENERATION REQUESTS
# ============================================================================

class RegenerateRequest(BaseModel):
    """Request to regenerate story components."""
    
    force: bool = Field(False, description="Force regeneration even if already exists")
    debug: bool = Field(False, description="Include debug info in response")


class RegenerateResponse(BaseModel):
    """Response from regeneration operation."""
    
    success: bool
    message: str
    story: GameStoryResponse | None = None
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# BULK GENERATION
# ============================================================================

class BulkGenerateRequest(BaseModel):
    """Request to generate stories for multiple games."""
    
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    leagues: list[str] = Field(default_factory=lambda: ["NBA", "NHL"], description="Leagues to include")
    force: bool = Field(False, description="Force regeneration even if already exists")


class BulkGenerateResult(BaseModel):
    """Result for a single game in bulk generation."""
    
    game_id: int
    success: bool
    message: str
    chapter_count: int | None = None
    error: str | None = None


class BulkGenerateResponse(BaseModel):
    """Response from bulk generation operation."""
    
    success: bool
    message: str
    total_games: int
    successful: int
    failed: int
    results: list[BulkGenerateResult] = Field(default_factory=list)
