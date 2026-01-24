"""
Pydantic schemas for Chapters-First Story Generation API.

This module defines the authoritative output contracts for the
chapters-first game story system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# PLAY ENTRY
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

    Chapters are the structural unit defined by deterministic boundaries.
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

    # Plays (for expansion)
    plays: list[PlayEntry] = Field(
        default_factory=list, description="Raw plays in chapter"
    )

    # Debug-only (optional)
    chapter_fingerprint: str | None = Field(
        None, description="Deterministic chapter hash"
    )
    boundary_logs: list[dict[str, Any]] | None = Field(
        None, description="Debug boundary events"
    )


# ============================================================================
# SECTION ENTRY (CHAPTERS-FIRST)
# ============================================================================


class SectionEntry(BaseModel):
    """
    A narrative section of the game story (chapters-first architecture).

    Sections are collapsed from chapters, assigned beat types,
    and have deterministic one-sentence headers.
    """

    section_index: int = Field(..., description="0-based section index")
    beat_type: str = Field(
        ..., description="Beat type (e.g., 'FAST_START', 'RUN', 'CLOSING_SEQUENCE')"
    )
    header: str = Field(..., description="Deterministic one-sentence header")
    chapters_included: list[str] = Field(..., description="Chapter IDs in this section")

    # Score bookends
    start_score: dict[str, int] = Field(
        ..., description="Score at section start {'home': int, 'away': int}"
    )
    end_score: dict[str, int] = Field(
        ..., description="Score at section end {'home': int, 'away': int}"
    )

    # Deterministic notes
    notes: list[str] = Field(
        default_factory=list, description="Machine-generated bullets"
    )


# ============================================================================
# GAME STORY RESPONSE
# ============================================================================


class GameStoryResponse(BaseModel):
    """
    The authoritative output for apps (chapters-first architecture).

    Represents a game with chapters, sections, and a compact story.
    """

    game_id: int
    sport: str
    story_version: str = Field(default="2.0.0", description="Story generation version")

    # Chapters (structural)
    chapters: list[ChapterEntry] = Field(default_factory=list)
    chapter_count: int = Field(..., description="Total number of chapters")
    total_plays: int = Field(..., description="Total number of plays")

    # Sections (narrative, chapters-first)
    sections: list[SectionEntry] = Field(
        default_factory=list, description="Narrative sections (3-10)"
    )
    section_count: int = Field(default=0, description="Total number of sections")

    # AI-generated compact story
    compact_story: str | None = Field(
        None, description="Full game recap (SINGLE AI CALL)"
    )
    word_count: int | None = Field(None, description="Actual word count")
    target_word_count: int | None = Field(None, description="Target word count")
    quality: str | None = Field(None, description="Game quality (LOW/MEDIUM/HIGH)")
    reading_time_estimate_minutes: float | None = Field(
        None, description="Estimated reading time"
    )

    # Metadata
    generated_at: datetime | None = Field(None, description="When story was generated")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    # Generation status
    has_compact_story: bool = Field(False, description="Whether compact story exists")


# ============================================================================
# REGENERATION
# ============================================================================


class RegenerateRequest(BaseModel):
    """Request to regenerate story."""

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
    """Request for bulk story generation."""

    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    leagues: list[str] = Field(default=["NBA"], description="League codes to include")
    force: bool = Field(False, description="Force regeneration even if story exists")


class BulkGenerateAsyncResponse(BaseModel):
    """Response when starting async bulk generation."""

    job_id: str
    message: str
    status_url: str


class BulkGenerateStatusResponse(BaseModel):
    """Response for bulk generation job status."""

    job_id: str
    state: str = Field(..., description="PENDING, PROGRESS, SUCCESS, or FAILURE")
    current: int | None = Field(None, description="Current game being processed")
    total: int | None = Field(None, description="Total games to process")
    status: str | None = Field(None, description="Status message")
    successful: int | None = Field(None, description="Number of successful generations")
    failed: int | None = Field(None, description="Number of failed generations")
    skipped: int | None = Field(
        None, description="Number of games skipped (story already exists)"
    )
    result: dict[str, Any] | None = Field(
        None, description="Final result when complete"
    )


# ============================================================================
# PIPELINE DEBUG (for viewing data transformation flow)
# ============================================================================


class PipelineStageInfo(BaseModel):
    """Info about a pipeline stage."""

    stage_name: str
    description: str
    input_count: int | None = None
    output_count: int | None = None


class PipelineDebugResponse(BaseModel):
    """
    Debug view of the story generation pipeline.

    Shows the data flow from raw PBP → chapters → sections → prompt → story.
    """

    game_id: int
    sport: str

    # Stage 1: Raw PBP sample
    raw_pbp_sample: list[dict[str, Any]] = Field(
        default_factory=list,
        description="First 15 plays from raw PBP data",
    )
    total_plays: int = Field(0, description="Total number of plays in game")

    # Stage 2: Chapters
    chapters_summary: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Chapter breakdown with reason codes",
    )
    chapter_count: int = 0

    # Stage 3: Sections
    sections_summary: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Section breakdown with beat types and headers",
    )
    section_count: int = 0

    # Stage 4: Render input (what gets sent to AI)
    render_input_summary: dict[str, Any] | None = Field(
        None, description="Structured data prepared for AI"
    )

    # Stage 5: OpenAI prompt
    openai_prompt: str | None = Field(
        None, description="The actual prompt sent to OpenAI"
    )

    # Stage 6: AI response
    ai_raw_response: str | None = Field(
        None, description="Raw response from OpenAI"
    )

    # Final output
    compact_story: str | None = Field(None, description="Final rendered story")
    word_count: int | None = None
    target_word_count: int | None = None

    # Pipeline stages overview
    pipeline_stages: list[PipelineStageInfo] = Field(
        default_factory=list, description="Overview of pipeline stages"
    )
