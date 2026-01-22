"""
AI Context Builder: Constructs AI input payloads following Prior Chapters Only policy.

This module builds AI input payloads that enforce the "prior chapters only" rule.

ISSUE 0.4: AI Context Rules (Prior Chapters Only)

CONTRACT:
- Chapter N generation receives only chapters 0..N-1 + current chapter N
- No future knowledge allowed
- Story state derived from prior chapters only
- Two generation modes: Sequential (chapter) vs Full Book
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from .types import Chapter, GameStory
from .story_state import StoryState, derive_story_state_from_chapters


@dataclass
class ChapterSummary:
    """Summary of a chapter (for AI context).
    
    This is what the AI receives about prior chapters.
    """
    
    chapter_id: str
    title: str | None = None        # Optional chapter title
    summary: str | None = None      # Chapter narrative (required after generation)
    reason_codes: list[str] = field(default_factory=list)
    period: int | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            k: v for k, v in asdict(self).items()
            if v is not None or k == "summary"  # Include summary even if None
        }


@dataclass
class ChapterAIInput:
    """AI input for generating a single chapter summary (Mode A: Sequential).
    
    CONTRACT (Issue 0.4):
    - current_chapter: Chapter N plays + metadata
    - prior_chapters: Summaries of chapters 0..N-1 only
    - story_state: Derived from chapters 0..N-1 only
    - No future knowledge allowed
    """
    
    chapter: dict[str, Any]                 # Current chapter (plays + metadata)
    prior_chapters: list[ChapterSummary]    # Summaries of prior chapters
    story_state: dict[str, Any]             # Running state from prior chapters
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "chapter": self.chapter,
            "prior_chapters": [ch.to_dict() for ch in self.prior_chapters],
            "story_state": self.story_state,
        }


@dataclass
class BookAIInput:
    """AI input for generating full book narrative (Mode B: Full Arc).
    
    CONTRACT (Issue 0.4):
    - All chapter summaries (hindsight allowed)
    - Game metadata (final score allowed)
    - This is the ONLY mode where hindsight language is permitted
    """
    
    game_id: int
    sport: str
    chapters: list[ChapterSummary]          # All chapter summaries
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "game_id": self.game_id,
            "sport": self.sport,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "metadata": self.metadata,
        }


def build_chapter_ai_input(
    current_chapter: Chapter,
    prior_chapters: list[Chapter],
    prior_summaries: list[ChapterSummary] | None = None,
    sport: str = "NBA"
) -> ChapterAIInput:
    """Build AI input for generating Chapter N summary (Mode A: Sequential).
    
    ENFORCES: Prior Chapters Only policy (Issue 0.4)
    
    Args:
        current_chapter: Chapter N to generate summary for
        prior_chapters: Chapters 0..N-1 (already processed)
        prior_summaries: Summaries of prior chapters (if available)
        sport: Sport identifier
        
    Returns:
        ChapterAIInput with prior context + current chapter
        
    Raises:
        ValueError: If future chapters detected or policy violated
    """
    # Validate: prior chapters must be before current chapter
    current_idx = _extract_chapter_index(current_chapter.chapter_id)
    for prior_ch in prior_chapters:
        prior_idx = _extract_chapter_index(prior_ch.chapter_id)
        if prior_idx >= current_idx:
            raise ValueError(
                f"Future chapter detected: {prior_ch.chapter_id} >= {current_chapter.chapter_id}. "
                "Prior chapters only policy violated."
            )
    
    # Build story state from prior chapters only
    story_state = derive_story_state_from_chapters(prior_chapters, sport=sport)
    
    # Validate story state constraints
    if not story_state.constraints.get("no_future_knowledge"):
        raise ValueError("Story state must have no_future_knowledge=true")
    
    # Build prior chapter summaries
    if prior_summaries is None:
        prior_summaries = [
            ChapterSummary(
                chapter_id=ch.chapter_id,
                title=None,  # Not generated yet
                summary=None,  # Not generated yet
                reason_codes=ch.reason_codes,
                period=ch.period,
            )
            for ch in prior_chapters
        ]
    
    # Build current chapter payload (plays + metadata, no future info)
    chapter_payload = {
        "chapter_id": current_chapter.chapter_id,
        "plays": [
            {
                "index": play.index,
                "description": play.raw_data.get("description", ""),
                "quarter": play.raw_data.get("quarter"),
                "game_clock": play.raw_data.get("game_clock"),
                "home_score": play.raw_data.get("home_score"),
                "away_score": play.raw_data.get("away_score"),
            }
            for play in current_chapter.plays
        ],
        "reason_codes": current_chapter.reason_codes,
        "period": current_chapter.period,
        "time_range": {
            "start": current_chapter.time_range.start if current_chapter.time_range else None,
            "end": current_chapter.time_range.end if current_chapter.time_range else None,
        } if current_chapter.time_range else None,
    }
    
    return ChapterAIInput(
        chapter=chapter_payload,
        prior_chapters=prior_summaries,
        story_state=story_state.to_dict(),
    )


def build_book_ai_input(
    game_story: GameStory,
    chapter_summaries: list[ChapterSummary],
    metadata: dict[str, Any] | None = None
) -> BookAIInput:
    """Build AI input for generating full book narrative (Mode B: Full Arc).
    
    This is the ONLY mode where hindsight language is allowed.
    
    Args:
        game_story: Complete GameStory with all chapters
        chapter_summaries: Summaries of all chapters (already generated)
        metadata: Game metadata (final score, etc.)
        
    Returns:
        BookAIInput with all chapter summaries
    """
    return BookAIInput(
        game_id=game_story.game_id,
        sport=game_story.sport,
        chapters=chapter_summaries,
        metadata=metadata or game_story.metadata,
    )


def _extract_chapter_index(chapter_id: str) -> int:
    """Extract chapter index from chapter_id.
    
    Example: "ch_003" → 3
    
    Args:
        chapter_id: Chapter ID (e.g., "ch_003")
        
    Returns:
        Chapter index (0-based)
    """
    try:
        # Extract numeric part after "ch_"
        if chapter_id.startswith("ch_"):
            return int(chapter_id.split("_")[1])
        else:
            raise ValueError(f"Invalid chapter_id format: {chapter_id}")
    except (IndexError, ValueError) as e:
        raise ValueError(f"Cannot extract index from chapter_id: {chapter_id}") from e


def validate_no_future_context(
    current_chapter: Chapter,
    prior_chapters: list[Chapter],
    story_state: StoryState
) -> None:
    """Validate that no future context is present.
    
    ENFORCES: Prior Chapters Only policy (Issue 0.4)
    
    Args:
        current_chapter: Current chapter
        prior_chapters: Prior chapters
        story_state: Story state
        
    Raises:
        ValueError: If future context detected
    """
    # Check: all prior chapters are before current
    current_idx = _extract_chapter_index(current_chapter.chapter_id)
    for prior_ch in prior_chapters:
        prior_idx = _extract_chapter_index(prior_ch.chapter_id)
        if prior_idx >= current_idx:
            raise ValueError(
                f"Future chapter detected: {prior_ch.chapter_id} >= {current_chapter.chapter_id}"
            )
    
    # Check: story state last processed is before current
    if story_state.chapter_index_last_processed >= current_idx:
        raise ValueError(
            f"Story state includes future context: "
            f"last_processed={story_state.chapter_index_last_processed} >= current={current_idx}"
        )
    
    # Check: story state constraints
    if not story_state.constraints.get("no_future_knowledge"):
        raise ValueError("Story state missing no_future_knowledge constraint")
    
    if story_state.constraints.get("source") != "derived_from_prior_chapters_only":
        raise ValueError("Story state source must be 'derived_from_prior_chapters_only'")
