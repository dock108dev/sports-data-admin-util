"""
Book + Chapters Model

A game is a book. Plays are pages. Chapters are contiguous play ranges
that represent coherent scenes.

This module replaces the legacy "Moments" concept with a simpler,
narrative-first architecture.

Issue 0.2: Canonical data model and output contract.
"""

from .types import Play, Chapter, GameStory, ChapterBoundary, TimeRange
from .builder import build_chapters
from .story_state import (
    StoryState,
    PlayerStoryState,
    TeamStoryState,
    MomentumHint,
    derive_story_state_from_chapters,
)
from .ai_context import (
    ChapterSummary,
    ChapterAIInput,
    BookAIInput,
    build_chapter_ai_input,
    build_book_ai_input,
    validate_no_future_context,
)

__all__ = [
    # Core types
    "Play",
    "Chapter",
    "GameStory",
    "ChapterBoundary",
    "TimeRange",
    # Builder
    "build_chapters",
    # Story state
    "StoryState",
    "PlayerStoryState",
    "TeamStoryState",
    "MomentumHint",
    "derive_story_state_from_chapters",
    # AI context
    "ChapterSummary",
    "ChapterAIInput",
    "BookAIInput",
    "build_chapter_ai_input",
    "build_book_ai_input",
    "validate_no_future_context",
]
