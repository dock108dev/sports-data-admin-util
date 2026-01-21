"""
Core data types for the Book + Chapters model.

ISSUE 0.2: Canonical Data Model and Output Contract

This module defines the authoritative schemas for:
- Chapter: The fundamental structural unit
- GameStory: The output contract consumed by apps

These contracts are locked and enforced by validation tests.
Breaking changes require explicit schema versioning.

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
from typing import Any


@dataclass
class Play:
    """The atomic unit of game action.
    
    A play is a single play-by-play event. Plays are the raw pages
    of the game's book. They are never modified or summarized.
    
    CONTRACT (Issue 0.2):
    - index: Required, non-negative integer
    - event_type: Required, non-empty string
    - raw_data: Required, contains complete event data
    
    Properties:
        index: Position in the timeline (0-based)
        event_type: Type of event (pbp, social, etc.)
        raw_data: The complete event data from the feed
    """
    
    index: int
    event_type: str
    raw_data: dict[str, Any]
    
    def __post_init__(self):
        """Validate play structure."""
        if self.index < 0:
            raise ValueError(f"Play index must be non-negative, got {self.index}")
        
        if not self.event_type:
            raise ValueError("Play event_type cannot be empty")
        
        if not isinstance(self.raw_data, dict):
            raise ValueError("Play raw_data must be a dict")
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "index": self.index,
            "event_type": self.event_type,
            "raw_data": self.raw_data,
        }


@dataclass
class TimeRange:
    """Time range for a chapter.
    
    Represents the game clock time span covered by a chapter.
    Both start and end are optional (nullable) if PBP does not provide time.
    
    CONTRACT (Issue 0.2):
    - start: Game clock at chapter start (e.g., "12:00", "2:30")
    - end: Game clock at chapter end (e.g., "10:45", "0:00")
    - Both nullable if sport/feed lacks clock data
    
    Properties:
        start: Game clock at chapter start
        end: Game clock at chapter end
    """
    
    start: str | None = None
    end: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "start": self.start,
            "end": self.end,
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
    - Period/quarter information (if available)
    - Time range (if available)
    
    Chapters have NO inherent narrative text. Narrative is generated
    later by AI operating on the chapter's plays.
    
    GUARANTEES:
    - Chapters are contiguous (no gaps between chapters)
    - Every play belongs to exactly one chapter
    - Chapters are chronologically ordered
    - Chapter boundaries are deterministic
    
    CONTRACT (Issue 0.2):
    
    REQUIRED FIELDS:
    - chapter_id: Unique within game, stable, deterministic (e.g., "ch_001")
    - play_start_idx: First play index (inclusive, non-negative)
    - play_end_idx: Last play index (inclusive, >= play_start_idx)
    - plays: Ordered list of Play objects (non-empty, contiguous)
    - reason_codes: Non-empty list explaining boundary (debugging/tuning)
    
    CONDITIONALLY REQUIRED:
    - period: Required if available in PBP, nullable only if sport lacks periods
    
    OPTIONAL:
    - time_range: {start, end} clock values if available, nullable if no clock
    
    FORBIDDEN:
    - No narrative text fields
    - No AI-derived fields
    - No ladder, tiers, or moment types
    
    INVARIANTS:
    - len(plays) == play_end_idx - play_start_idx + 1
    - plays[i].index == play_start_idx + i for all i
    - len(reason_codes) > 0
    - chapter_id is unique within game
    
    Properties:
        chapter_id: Unique identifier (e.g., "ch_001")
        play_start_idx: First play index (inclusive)
        play_end_idx: Last play index (inclusive)
        plays: All plays in this chapter
        reason_codes: Why this chapter's boundaries exist
        period: Period/quarter number (nullable)
        time_range: Game clock range (nullable)
    """
    
    chapter_id: str
    play_start_idx: int
    play_end_idx: int
    plays: list[Play]
    reason_codes: list[str]
    period: int | None = None
    time_range: TimeRange | None = None
    
    def __post_init__(self):
        """Validate chapter structure.
        
        Enforces all CONTRACT invariants from Issue 0.2.
        """
        # Validate chapter_id
        if not self.chapter_id:
            raise ValueError("Chapter chapter_id cannot be empty")
        
        # Validate indices
        if self.play_start_idx < 0:
            raise ValueError(
                f"Chapter {self.chapter_id}: play_start_idx must be non-negative, "
                f"got {self.play_start_idx}"
            )
        
        if self.play_start_idx > self.play_end_idx:
            raise ValueError(
                f"Chapter {self.chapter_id}: start_idx ({self.play_start_idx}) > "
                f"end_idx ({self.play_end_idx})"
            )
        
        # Validate plays
        if not self.plays:
            raise ValueError(f"Chapter {self.chapter_id} has no plays")
        
        # INVARIANT: len(plays) == play_end_idx - play_start_idx + 1
        expected_count = self.play_end_idx - self.play_start_idx + 1
        actual_count = len(self.plays)
        if actual_count != expected_count:
            raise ValueError(
                f"Chapter {self.chapter_id}: play count mismatch. "
                f"Expected {expected_count} (from indices), got {actual_count}"
            )
        
        # INVARIANT: plays[i].index == play_start_idx + i
        expected_indices = list(range(self.play_start_idx, self.play_end_idx + 1))
        actual_indices = [p.index for p in self.plays]
        
        if actual_indices != expected_indices:
            raise ValueError(
                f"Chapter {self.chapter_id} has non-contiguous plays. "
                f"Expected {expected_indices}, got {actual_indices}"
            )
        
        # INVARIANT: len(reason_codes) > 0
        if not self.reason_codes:
            raise ValueError(
                f"Chapter {self.chapter_id} has empty reason_codes. "
                f"All chapters must explain why their boundaries exist."
            )
        
        # Validate period if provided
        if self.period is not None and self.period < 1:
            raise ValueError(
                f"Chapter {self.chapter_id}: period must be >= 1, got {self.period}"
            )
    
    @property
    def play_count(self) -> int:
        """Number of plays in this chapter."""
        return len(self.plays)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses.
        
        Returns JSON schema (Issue 0.2):
        {
            "chapter_id": str,              # Required
            "play_start_idx": int,          # Required
            "play_end_idx": int,            # Required
            "play_count": int,              # Computed
            "plays": [...],                 # Required
            "reason_codes": [...],          # Required, non-empty
            "period": int | null,           # Conditionally required
            "time_range": {...} | null      # Optional
        }
        """
        result: dict[str, Any] = {
            "chapter_id": self.chapter_id,
            "play_start_idx": self.play_start_idx,
            "play_end_idx": self.play_end_idx,
            "play_count": self.play_count,
            "plays": [p.to_dict() for p in self.plays],
            "reason_codes": self.reason_codes,
            "period": self.period,
        }
        
        if self.time_range is not None:
            result["time_range"] = self.time_range.to_dict()
        else:
            result["time_range"] = None
        
        return result


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
    
    CONTRACT (Issue 0.2):
    
    REQUIRED FIELDS:
    - game_id: Database game ID (positive integer)
    - sport: Sport identifier (non-empty string, e.g., "NBA", "NHL")
    - chapters: Ordered list of Chapter objects (non-empty, contiguous)
    - compact_story: Nullable string (null at this phase, must exist in schema)
    
    OPTIONAL BUT RECOMMENDED:
    - reading_time_estimate_minutes: Estimated reading time (nullable)
    - metadata: Extensible map for game metadata (teams, score, etc.)
    
    INVARIANTS:
    - len(chapters) > 0
    - chapters are chronologically ordered
    - chapters are contiguous (no gaps)
    - chapter_ids are unique within game
    
    FORWARD COMPATIBILITY:
    - Schema is serializable as JSON
    - New fields can be added without breaking existing consumers
    - Required fields cannot be removed without version bump
    
    Properties:
        game_id: Database game ID
        sport: Sport identifier
        chapters: All chapters in chronological order
        compact_story: Optional AI-generated game summary
        reading_time_estimate_minutes: Estimated reading time
        metadata: Game metadata (teams, score, etc.)
    """
    
    game_id: int
    sport: str
    chapters: list[Chapter]
    compact_story: str | None = None
    reading_time_estimate_minutes: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate story structure.
        
        Enforces all CONTRACT invariants from Issue 0.2.
        """
        # Validate game_id
        if self.game_id <= 0:
            raise ValueError(f"GameStory game_id must be positive, got {self.game_id}")
        
        # Validate sport
        if not self.sport:
            raise ValueError("GameStory sport cannot be empty")
        
        # INVARIANT: len(chapters) > 0
        if not self.chapters:
            raise ValueError(f"GameStory for game {self.game_id} has no chapters")
        
        # INVARIANT: chapters are chronologically ordered and contiguous
        for i in range(1, len(self.chapters)):
            prev_end = self.chapters[i - 1].play_end_idx
            curr_start = self.chapters[i].play_start_idx
            
            if curr_start != prev_end + 1:
                raise ValueError(
                    f"GameStory for game {self.game_id}: chapters are not contiguous. "
                    f"Chapter {i-1} ends at {prev_end}, chapter {i} starts at {curr_start}"
                )
        
        # INVARIANT: chapter_ids are unique
        chapter_ids = [ch.chapter_id for ch in self.chapters]
        if len(chapter_ids) != len(set(chapter_ids)):
            duplicates = [cid for cid in chapter_ids if chapter_ids.count(cid) > 1]
            raise ValueError(
                f"GameStory for game {self.game_id}: duplicate chapter_ids found: {duplicates}"
            )
        
        # Validate reading_time_estimate_minutes if provided
        if self.reading_time_estimate_minutes is not None:
            if self.reading_time_estimate_minutes < 0:
                raise ValueError(
                    f"GameStory reading_time_estimate_minutes must be non-negative, "
                    f"got {self.reading_time_estimate_minutes}"
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
        
        Returns JSON schema (Issue 0.2):
        {
            "game_id": int,                             # Required
            "sport": str,                               # Required
            "chapter_count": int,                       # Computed
            "total_plays": int,                         # Computed
            "chapters": [...],                          # Required, non-empty
            "compact_story": str | null,                # Required (nullable)
            "reading_time_estimate_minutes": float | null,  # Optional
            "metadata": {...}                           # Optional
        }
        """
        return {
            "game_id": self.game_id,
            "sport": self.sport,
            "chapter_count": self.chapter_count,
            "total_plays": self.total_plays,
            "chapters": [ch.to_dict() for ch in self.chapters],
            "compact_story": self.compact_story,
            "reading_time_estimate_minutes": self.reading_time_estimate_minutes,
            "metadata": self.metadata,
        }
