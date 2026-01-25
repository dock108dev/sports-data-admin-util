"""
Section Types: Core dataclasses for story sections.

This module contains the authoritative schema for StorySections and related types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .beat_types import BeatType, BeatDescriptor


# ============================================================================
# FORCED BREAK REASONS
# ============================================================================


class ForcedBreakReason(str, Enum):
    """Reasons for forced section breaks.

    These are diagnostic only - they explain WHY a break occurred.
    """

    OVERTIME_START = "OVERTIME_START"
    FINAL_2_MINUTES = "FINAL_2_MINUTES"
    CRUNCH_SETUP_FIRST = "CRUNCH_SETUP_FIRST"
    CLOSING_SEQUENCE_FIRST = "CLOSING_SEQUENCE_FIRST"  # Phase 2.6
    QUARTER_BOUNDARY = "QUARTER_BOUNDARY"
    BEAT_CHANGE = "BEAT_CHANGE"
    GAME_START = "GAME_START"


# ============================================================================
# STAT DELTA TYPES
# ============================================================================


@dataclass
class TeamStatDelta:
    """Team statistics for a section."""

    team_key: str
    team_name: str
    points_scored: int = 0
    personal_fouls_committed: int = 0
    technical_fouls_committed: int = 0
    timeouts_used: int = 0
    possessions_estimate: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "team_key": self.team_key,
            "team_name": self.team_name,
            "points_scored": self.points_scored,
            "personal_fouls_committed": self.personal_fouls_committed,
            "technical_fouls_committed": self.technical_fouls_committed,
            "timeouts_used": self.timeouts_used,
            "possessions_estimate": self.possessions_estimate,
        }


@dataclass
class PlayerStatDelta:
    """Player statistics for a section (top 1-3 per team only)."""

    player_key: str
    player_name: str
    team_key: str | None
    points_scored: int = 0
    fg_made: int = 0
    three_pt_made: int = 0
    ft_made: int = 0
    # Expanded stats (Player Prominence)
    assists: int = 0
    blocks: int = 0
    steals: int = 0
    personal_foul_count: int = 0
    foul_trouble_flag: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "player_key": self.player_key,
            "player_name": self.player_name,
            "team_key": self.team_key,
            "points_scored": self.points_scored,
            "fg_made": self.fg_made,
            "three_pt_made": self.three_pt_made,
            "ft_made": self.ft_made,
            "assists": self.assists,
            "blocks": self.blocks,
            "steals": self.steals,
            "personal_foul_count": self.personal_foul_count,
            "foul_trouble_flag": self.foul_trouble_flag,
        }


# ============================================================================
# STORYSECTION SCHEMA (AUTHORITATIVE)
# ============================================================================


@dataclass
class StorySection:
    """A narrative section of the game story.

    SCHEMA (AUTHORITATIVE):
    - section_index: 0-based, sequential
    - beat_type: From BeatType enum (primary beat)
    - descriptors: Secondary context (Phase 2.1)
    - chapters_included: List of chapter IDs
    - start_score: {home: int, away: int}
    - end_score: {home: int, away: int}
    - team_stat_deltas: Per-team stats for this section
    - player_stat_deltas: Top 1-3 players per team
    - notes: Deterministic machine bullets

    Phase 2.1: Added descriptors field for MISSED_SHOT_CONTEXT, etc.
    """

    section_index: int
    beat_type: BeatType
    chapters_included: list[str]

    # Score bookends
    start_score: dict[str, int]  # {"home": int, "away": int}
    end_score: dict[str, int]  # {"home": int, "away": int}

    # Stats
    team_stat_deltas: dict[str, TeamStatDelta] = field(default_factory=dict)
    player_stat_deltas: dict[str, PlayerStatDelta] = field(default_factory=dict)

    # Deterministic notes
    notes: list[str] = field(default_factory=list)

    # Phase 2.1: Secondary descriptors (union of all chapter descriptors)
    descriptors: set[BeatDescriptor] = field(default_factory=set)

    # Debug info (not part of core schema)
    break_reason: ForcedBreakReason | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        result = {
            "section_index": self.section_index,
            "beat_type": self.beat_type.value,
            "chapters_included": self.chapters_included,
            "start_score": self.start_score,
            "end_score": self.end_score,
            "team_stat_deltas": {
                k: v.to_dict() for k, v in self.team_stat_deltas.items()
            },
            "player_stat_deltas": {
                k: v.to_dict() for k, v in self.player_stat_deltas.items()
            },
            "notes": self.notes,
        }
        # Include descriptors if present
        if self.descriptors:
            result["descriptors"] = [d.value for d in self.descriptors]
        return result

    def to_debug_dict(self) -> dict[str, Any]:
        """Serialize with debug info."""
        result = self.to_dict()
        result["break_reason"] = self.break_reason.value if self.break_reason else None
        return result


# ============================================================================
# CHAPTER METADATA FOR SECTION BUILDING
# ============================================================================


@dataclass
class ChapterMetadata:
    """Metadata needed for section construction."""

    chapter_id: str
    chapter_index: int
    beat_type: BeatType
    period: int | None
    time_remaining_seconds: int | None
    is_overtime: bool
    start_home_score: int
    start_away_score: int
    end_home_score: int
    end_away_score: int
    descriptors: set[BeatDescriptor] = field(default_factory=set)  # Phase 2.1
