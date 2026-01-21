"""
Core data types for the Book + Chapters model.

DEFINITIONS:

Play
    The atomic unit of game action. A single play-by-play event.
    Plays are never modified, summarized, or aggregated.
    They are the raw pages of the game's book.

Chapter
    A deterministic, contiguous range of plays representing a single narrative scene.
    
    A Chapter:
    - Has a start and end play index
    - Contains all raw plays in that range
    - Exists only to structure storytelling and UI expansion
    - Has no inherent narrative text (text is generated later by AI)
    - Is determined by structural boundaries, not narrative labels
    
    Chapters are logistics, not narrative. They answer "where are the scene breaks?"
    not "what happened in this scene?"

GameStory
    A narrative artifact produced from chapters.
    
    The GameStory is the final output consumed by apps. It contains:
    - All chapters (structural units)
    - Optional compact story text (AI-generated summary)
    - Game metadata
    
    Apps consume chapters directly. AI operates on chapters to produce narrative text.

ARCHITECTURAL PRINCIPLES:

1. Structure before narrative
   - Chapters are created deterministically from play structure
   - Narrative text is generated after chapters exist
   - AI never defines chapter boundaries

2. No event-first logic
   - Chapters are not "buckets for events between tier crossings"
   - Boundaries occur at structural inflection points, not metric thresholds
   - A chapter may contain multiple score changes, tier shifts, or runs

3. Determinism
   - Same PBP input → same chapters output
   - No randomness, no AI in chapter creation
   - Chapter boundaries are reproducible

4. Complete coverage
   - Every play belongs to exactly one chapter
   - Chapters are contiguous (no gaps)
   - Chapters are chronologically ordered
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Play:
    """The atomic unit of game action.
    
    A play is a single play-by-play event. Plays are the raw pages
    of the game's book. They are never modified or summarized.
    
    Properties:
        index: Position in the timeline (0-based)
        event_type: Type of event (pbp, social, etc.)
        raw_data: The complete event data from the feed
    """
    
    index: int
    event_type: str
    raw_data: dict[str, Any]
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "index": self.index,
            "event_type": self.event_type,
            "raw_data": self.raw_data,
        }


@dataclass
class ChapterBoundary:
    """A structural boundary between chapters.
    
    Boundaries are determined by structural inflection points in the game,
    not by narrative labels or metric thresholds.
    
    Reason codes explain why a boundary exists (for debugging/validation),
    but they do not determine narrative meaning.
    """
    
    play_index: int
    reason_codes: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "play_index": self.play_index,
            "reason_codes": self.reason_codes,
        }


@dataclass
class Chapter:
    """A contiguous range of plays representing a single narrative scene.
    
    Chapters are the fundamental structural unit of game storytelling.
    They answer "where are the scene breaks?" not "what happened?"
    
    A chapter is deterministic and reproducible. It contains:
    - A unique identifier
    - Start and end play indices (inclusive)
    - All plays in that range
    - Reason codes explaining why boundaries exist
    
    Chapters have NO inherent narrative text. Narrative is generated
    later by AI operating on the chapter's plays.
    
    GUARANTEES:
    - Chapters are contiguous (no gaps between chapters)
    - Every play belongs to exactly one chapter
    - Chapters are chronologically ordered
    - Chapter boundaries are deterministic
    
    Properties:
        chapter_id: Unique identifier (e.g., "ch_001")
        play_start_idx: First play index (inclusive)
        play_end_idx: Last play index (inclusive)
        plays: All plays in this chapter
        reason_codes: Why this chapter's boundaries exist
    """
    
    chapter_id: str
    play_start_idx: int
    play_end_idx: int
    plays: list[Play]
    reason_codes: list[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate chapter structure."""
        if self.play_start_idx > self.play_end_idx:
            raise ValueError(
                f"Invalid chapter: start_idx ({self.play_start_idx}) > "
                f"end_idx ({self.play_end_idx})"
            )
        
        if not self.plays:
            raise ValueError(f"Chapter {self.chapter_id} has no plays")
        
        # Validate play indices are contiguous
        expected_indices = list(range(self.play_start_idx, self.play_end_idx + 1))
        actual_indices = [p.index for p in self.plays]
        
        if actual_indices != expected_indices:
            raise ValueError(
                f"Chapter {self.chapter_id} has non-contiguous plays. "
                f"Expected {expected_indices}, got {actual_indices}"
            )
    
    @property
    def play_count(self) -> int:
        """Number of plays in this chapter."""
        return len(self.plays)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses.
        
        Returns JSON schema:
        {
            "chapter_id": str,
            "play_start_idx": int,
            "play_end_idx": int,
            "play_count": int,
            "plays": [...],
            "reason_codes": [...]
        }
        """
        return {
            "chapter_id": self.chapter_id,
            "play_start_idx": self.play_start_idx,
            "play_end_idx": self.play_end_idx,
            "play_count": self.play_count,
            "plays": [p.to_dict() for p in self.plays],
            "reason_codes": self.reason_codes,
        }


@dataclass
class GameStory:
    """A narrative artifact produced from chapters.
    
    The GameStory is the final output consumed by apps. It contains:
    - All chapters (structural units)
    - Optional compact story text (AI-generated summary)
    - Game metadata
    
    Apps consume chapters directly for UI rendering. AI operates on
    chapters to produce narrative text (headlines, summaries, etc.).
    
    ARCHITECTURE:
    
    PBP → Plays → Chapters → Story (AI) → App
    
    - Chapters are created deterministically from plays
    - AI generates narrative text from chapters
    - Apps consume both structure (chapters) and narrative (AI text)
    
    Properties:
        game_id: Database game ID
        chapters: All chapters in chronological order
        compact_story: Optional AI-generated game summary
        metadata: Game metadata (teams, score, etc.)
    """
    
    game_id: int
    chapters: list[Chapter]
    compact_story: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate story structure."""
        if not self.chapters:
            raise ValueError(f"GameStory for game {self.game_id} has no chapters")
        
        # Validate chapters are chronologically ordered
        for i in range(1, len(self.chapters)):
            prev_end = self.chapters[i - 1].play_end_idx
            curr_start = self.chapters[i].play_start_idx
            
            if curr_start != prev_end + 1:
                raise ValueError(
                    f"Chapters are not contiguous: chapter {i-1} ends at "
                    f"{prev_end}, chapter {i} starts at {curr_start}"
                )
    
    @property
    def chapter_count(self) -> int:
        """Number of chapters in this story."""
        return len(self.chapters)
    
    @property
    def total_plays(self) -> int:
        """Total number of plays across all chapters."""
        return sum(ch.play_count for ch in self.chapters)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses.
        
        Returns JSON schema:
        {
            "game_id": int,
            "chapter_count": int,
            "total_plays": int,
            "chapters": [...],
            "compact_story": str | null,
            "metadata": {...}
        }
        """
        return {
            "game_id": self.game_id,
            "chapter_count": self.chapter_count,
            "total_plays": self.total_plays,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "compact_story": self.compact_story,
            "metadata": self.metadata,
        }
