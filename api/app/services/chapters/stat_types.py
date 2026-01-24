"""
Stat Types: Data structures for running stats and section deltas.

This module defines the authoritative data structures for:
- RunningStatsSnapshot: Cumulative totals from game start → end of chapter
- SectionDelta: Difference between two snapshots (section_end - section_start)

PLAYER ID DECISION:
- Primary key: player_name (deterministically normalized to lowercase, stripped)
- Reason: player_id is an external reference that may be null or inconsistent
- player_id is PRESERVED in snapshots when available for future reference
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ============================================================================
# PLAYER ID NORMALIZATION
# ============================================================================


def normalize_player_key(player_name: str) -> str:
    """Normalize player name for use as dictionary key.

    PLAYER ID DECISION (DOCUMENTED):
    - We use player_name as the primary key because player_id is an external
      reference that may be null or inconsistent across data sources.
    - Normalization: lowercase, stripped whitespace, collapsed internal spaces.
    - This ensures deterministic matching regardless of case variations.

    Args:
        player_name: Raw player name from play data

    Returns:
        Normalized key for dictionary lookups
    """
    if not player_name:
        return ""
    # Lowercase, strip whitespace, collapse internal spaces
    return " ".join(player_name.lower().split())


# ============================================================================
# SNAPSHOT DATA STRUCTURES (CUMULATIVE TOTALS)
# ============================================================================


@dataclass
class PlayerSnapshot:
    """Cumulative player statistics from game start → end of chapter.

    Snapshots are IMMUTABLE once computed.

    PLAYER ID NOTE:
    - player_key is the normalized name used for lookups
    - player_name is the display name (original case preserved)
    - player_id is the external reference (preserved when available, may be null)
    """

    # Identity
    player_key: str  # Normalized name (primary key)
    player_name: str  # Display name (original case)
    player_id: str | None = None  # External ref (may be null)
    team_key: str | None = None  # Which team this player is on

    # Scoring (Cumulative Totals)
    points_scored_total: int = 0
    fg_made_total: int = 0  # Field goals made
    three_pt_made_total: int = 0  # 3-pointers made
    ft_made_total: int = 0  # Free throws made

    # Expanded Stats (Cumulative Totals) - Player Prominence
    assists_total: int = 0
    blocks_total: int = 0
    steals_total: int = 0

    # Fouls (Cumulative Totals)
    personal_foul_count_total: int = 0
    technical_foul_count_total: int = 0  # Separate from personal fouls

    # Notable Actions (Unique Set)
    notable_actions_set: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "player_key": self.player_key,
            "player_name": self.player_name,
            "player_id": self.player_id,
            "team_key": self.team_key,
            "points_scored_total": self.points_scored_total,
            "fg_made_total": self.fg_made_total,
            "three_pt_made_total": self.three_pt_made_total,
            "ft_made_total": self.ft_made_total,
            "assists_total": self.assists_total,
            "blocks_total": self.blocks_total,
            "steals_total": self.steals_total,
            "personal_foul_count_total": self.personal_foul_count_total,
            "technical_foul_count_total": self.technical_foul_count_total,
            "notable_actions_set": sorted(self.notable_actions_set),
        }


@dataclass
class TeamSnapshot:
    """Cumulative team statistics from game start → end of chapter.

    Snapshots are IMMUTABLE once computed.
    """

    # Identity
    team_key: str  # Normalized team identifier
    team_name: str  # Display name

    # Scoring
    points_scored_total: int = 0

    # Fouls (Cumulative Totals)
    personal_fouls_committed_total: int = 0
    technical_fouls_committed_total: int = 0

    # Timeouts
    timeouts_used_total: int = 0

    # Pace (Very Rough Estimate)
    possessions_estimate_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "team_key": self.team_key,
            "team_name": self.team_name,
            "points_scored_total": self.points_scored_total,
            "personal_fouls_committed_total": self.personal_fouls_committed_total,
            "technical_fouls_committed_total": self.technical_fouls_committed_total,
            "timeouts_used_total": self.timeouts_used_total,
            "possessions_estimate_total": self.possessions_estimate_total,
        }


@dataclass
class RunningStatsSnapshot:
    """Complete statistical snapshot at a chapter boundary.

    Represents totals from game start → end of the specified chapter.
    Snapshots are IMMUTABLE once computed.

    SEMANTICS:
    - chapter_index: The chapter this snapshot is taken AFTER (0-indexed)
    - A snapshot at chapter_index=2 contains totals through chapters 0, 1, 2
    - Initial snapshot (before any chapters) has chapter_index=-1
    """

    chapter_index: int  # -1 for initial, 0+ for after chapter N

    # Team snapshots (keyed by team_key)
    teams: dict[str, TeamSnapshot] = field(default_factory=dict)

    # Player snapshots (keyed by player_key)
    players: dict[str, PlayerSnapshot] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "chapter_index": self.chapter_index,
            "teams": {k: v.to_dict() for k, v in self.teams.items()},
            "players": {k: v.to_dict() for k, v in self.players.items()},
        }


# ============================================================================
# SECTION DELTA DATA STRUCTURES
# ============================================================================


@dataclass
class PlayerDelta:
    """Player statistics for a SECTION (delta between two snapshots).

    Computed as: snapshot_at_section_end - snapshot_at_section_start
    """

    player_key: str
    player_name: str
    player_id: str | None = None
    team_key: str | None = None

    # Scoring (Section Delta)
    points_scored: int = 0
    fg_made: int = 0
    three_pt_made: int = 0
    ft_made: int = 0

    # Expanded Stats (Section Delta) - Player Prominence
    assists: int = 0
    blocks: int = 0
    steals: int = 0

    # Fouls (Section Delta)
    personal_foul_count: int = 0
    technical_foul_count: int = 0

    # Notable Actions (Unique set for this section)
    notable_actions: set[str] = field(default_factory=set)

    # Flags
    foul_trouble_flag: bool = False  # personal_foul_count >= 4 in section

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "player_key": self.player_key,
            "player_name": self.player_name,
            "player_id": self.player_id,
            "team_key": self.team_key,
            "points_scored": self.points_scored,
            "fg_made": self.fg_made,
            "three_pt_made": self.three_pt_made,
            "ft_made": self.ft_made,
            "assists": self.assists,
            "blocks": self.blocks,
            "steals": self.steals,
            "personal_foul_count": self.personal_foul_count,
            "technical_foul_count": self.technical_foul_count,
            "notable_actions": sorted(self.notable_actions),
            "foul_trouble_flag": self.foul_trouble_flag,
        }


@dataclass
class TeamDelta:
    """Team statistics for a SECTION (delta between two snapshots)."""

    team_key: str
    team_name: str

    # Scoring (Section Delta)
    points_scored: int = 0

    # Fouls (Section Delta)
    personal_fouls_committed: int = 0
    technical_fouls_committed: int = 0

    # Timeouts (Section Delta)
    timeouts_used: int = 0

    # Pace (Section Delta)
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
class SectionDelta:
    """Complete statistics for a SECTION (chapter range).

    Computed by differencing snapshots at section boundaries.

    PLAYER BOUNDING:
    - Only top 3 players per team by points_scored (section delta) are included
    - Tie-breakers: fg_made, three_pt_made, then player_key (deterministic)
    """

    section_start_chapter: int  # First chapter in section (inclusive)
    section_end_chapter: int  # Last chapter in section (inclusive)

    # Team deltas
    teams: dict[str, TeamDelta] = field(default_factory=dict)

    # Player deltas (bounded: top 3 per team)
    players: dict[str, PlayerDelta] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON."""
        return {
            "section_start_chapter": self.section_start_chapter,
            "section_end_chapter": self.section_end_chapter,
            "teams": {k: v.to_dict() for k, v in self.teams.items()},
            "players": {k: v.to_dict() for k, v in self.players.items()},
        }
