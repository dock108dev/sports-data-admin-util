"""
StorySection Builder: Collapse chapters into narrative sections.

This module constructs StorySections from chapters, beat types, and stat deltas.

DESIGN PRINCIPLES:
- Deterministic: Same input → same sections every run
- Structural: Builds outline only, no narrative generation
- Constrained: 0-10 sections (underpowered sections removed)
- No AI usage
- No plays may ever be dropped

COLLAPSE RULES:
- Adjacent chapters with same beat_type MAY merge
- Forced breaks ALWAYS override merging
- Incompatible beats NEVER merge (beat-aware rules)

FORCED SECTION BREAKS:
1. Overtime start
2. Entry into final 2:00 of regulation (CLOSING_SEQUENCE)
3. First chapter labeled CRUNCH_SETUP
4. Quarter boundary
5. Beat change (fallback)

BEAT-AWARE MERGE RULES:
- non-crunch beats cannot merge with CRUNCH_SETUP or CLOSING_SEQUENCE
- RUN/RESPONSE cannot merge with STALL
- FAST_START/EARLY_CONTROL cannot merge with CLOSING_SEQUENCE
- Any beat cannot merge with OVERTIME

SIGNAL THRESHOLD:
A section is underpowered if BOTH:
- Total points scored < 8
- Meaningful events < 3 (scoring plays, lead changes, run events, ties)
Underpowered sections are merged into compatible neighbors or dropped.

THIN SECTION HANDLING:
A section is thin if BOTH:
- Total points scored ≤ 4
- Number of scoring plays ≤ 2
Thin sections are ALWAYS merged, NEVER dropped:
- Early game (Q1-Q3): Merge upward into previous
- Crunch/late game: Merge downward into next
- Final fallback: Merge forward (if not end-of-game)
- End-of-game: Must merge backward
Never crosses OVERTIME boundaries.

LUMPY SECTION HANDLING (DOMINANCE CAPPING):
A section is lumpy if single player accounts for ≥ 65% of section points.
When lumpy:
- Cap dominant player contribution at 60% of section points
- Spill excess to nearest compatible adjacent section
- Preserve total game stats
- Never cross OVERTIME boundaries

SECTION COUNT CONSTRAINTS:
- Minimum: 0 sections (low-signal games may have fewer than 3)
- Maximum: 10 sections
- Protected from merging: opening, CRUNCH_SETUP, CLOSING_SEQUENCE, OVERTIME
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .types import Chapter
from .beat_classifier import (
    BeatType,
    BeatClassification,
    BeatDescriptor,
    BEAT_PRIORITY,
    detect_opening_section_beat,
)
from .running_stats import SectionDelta, RunningStatsSnapshot


# ============================================================================
# PLAYER PROMINENCE ACCUMULATOR
# ============================================================================


@dataclass
class PlayerProminence:
    """Player prominence metrics for selection purposes.

    PLAYER PROMINENCE SYSTEM:
    Used ONLY for player selection - these values are NOT passed to AI.
    The AI receives only section-level deltas (points_scored in section).

    Selection logic (per team):
    1. Rank by section_points → Top 1-2 as "section leaders"
    2. Rank by game_points_so_far → Top 1 as "game presence"
    3. No duplicates, max 3 per team

    Attributes:
        player_key: Normalized player identifier
        player_name: Display name
        team_key: Team identifier
        section_points: Points scored in THIS section only
        game_points_so_far: Cumulative game points (for selection only)
        run_involvement_count: Number of run events player was involved in
    """

    player_key: str
    player_name: str
    team_key: str | None = None
    section_points: int = 0
    game_points_so_far: int = 0
    run_involvement_count: int = 0


def compute_player_prominence(
    section_delta: SectionDelta,
    end_snapshot: RunningStatsSnapshot | None = None,
) -> dict[str, PlayerProminence]:
    """Compute prominence metrics for all players in a section.

    Args:
        section_delta: Section-level player statistics
        end_snapshot: Cumulative snapshot at section end (for game totals)

    Returns:
        Dict of player_key -> PlayerProminence
    """
    prominence_map: dict[str, PlayerProminence] = {}

    for player_key, delta in section_delta.players.items():
        # Get game totals from snapshot if available
        game_points = 0
        if end_snapshot and player_key in end_snapshot.players:
            game_points = end_snapshot.players[player_key].points_scored_total

        prominence_map[player_key] = PlayerProminence(
            player_key=delta.player_key,
            player_name=delta.player_name,
            team_key=delta.team_key,
            section_points=delta.points_scored,
            game_points_so_far=game_points,
            run_involvement_count=0,  # Stub for now - can add run tracking later
        )

    return prominence_map


def select_prominent_players(
    prominence_map: dict[str, PlayerProminence],
    max_per_team: int = 3,
) -> set[str]:
    """Select prominent players using prominence-based rules.

    SELECTION RULES (per team):
    1. Top 1-2 by section_points ("section leaders")
    2. Top 1 by game_points_so_far ("game presence") if not already selected
    3. No duplicates, max 3 per team

    Args:
        prominence_map: Player prominence metrics
        max_per_team: Maximum players to select per team (default: 3)

    Returns:
        Set of selected player_keys
    """
    selected: set[str] = set()

    # Group by team
    players_by_team: dict[str, list[PlayerProminence]] = {}
    for p in prominence_map.values():
        team = p.team_key or "unknown"
        if team not in players_by_team:
            players_by_team[team] = []
        players_by_team[team].append(p)

    for team_key, team_players in players_by_team.items():
        team_selected: list[str] = []

        # Step 1: Top 1-2 by section_points (section leaders)
        by_section_points = sorted(
            team_players,
            key=lambda x: (-x.section_points, -x.game_points_so_far, x.player_key),
        )

        # Take up to 2 section leaders
        for p in by_section_points[:2]:
            if p.section_points > 0:  # Only if they actually scored
                team_selected.append(p.player_key)

        # Step 2: Top 1 by game_points_so_far (game presence)
        if len(team_selected) < max_per_team:
            by_game_points = sorted(
                team_players,
                key=lambda x: (-x.game_points_so_far, -x.section_points, x.player_key),
            )

            for p in by_game_points:
                if p.player_key not in team_selected:
                    if p.game_points_so_far > 0:  # Only if they've scored in game
                        team_selected.append(p.player_key)
                        break

        # Ensure we don't exceed max_per_team
        selected.update(team_selected[:max_per_team])

    return selected


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
# STORYSECTION SCHEMA (AUTHORITATIVE)
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


# ============================================================================
# FORCED BREAK DETECTION
# ============================================================================


def _is_overtime_start(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
) -> bool:
    """Check if this chapter is the start of overtime.

    RULE: Overtime is ALWAYS a new section.
    """
    if not curr.is_overtime:
        return False

    # First chapter or transition from regulation
    if prev is None:
        return True

    return not prev.is_overtime


def _is_final_2_minutes_entry(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
) -> bool:
    """Check if this chapter enters the final 2 minutes of regulation.

    RULE: First chapter with time_remaining <= 120s in Q4 forces a break.
    Beat type should already be CLOSING_SEQUENCE.
    """
    # Must be Q4 and regulation
    if curr.is_overtime:
        return False

    if curr.period != 4:
        return False

    if curr.time_remaining_seconds is None:
        return False

    # Must be <= 2 minutes
    if curr.time_remaining_seconds > 120:
        return False

    # Check if previous was NOT in final 2 minutes
    if prev is None:
        return True

    if prev.period != 4:
        return True

    if prev.time_remaining_seconds is None:
        return True

    # Previous was > 2 minutes, now <= 2 minutes
    return prev.time_remaining_seconds > 120


def _is_first_crunch_setup(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
    seen_crunch: bool,
) -> bool:
    """Check if this is the FIRST chapter labeled CRUNCH_SETUP.

    RULE: First CRUNCH_SETUP forces a new section.
    """
    if curr.beat_type != BeatType.CRUNCH_SETUP:
        return False

    return not seen_crunch


def _is_first_closing_sequence(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
    seen_closing: bool,
) -> bool:
    """Check if this is the FIRST chapter labeled CLOSING_SEQUENCE.

    Phase 2.6: CLOSING_SEQUENCE must always start its own section.
    """
    if curr.beat_type != BeatType.CLOSING_SEQUENCE:
        return False

    return not seen_closing


def _is_quarter_boundary(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
) -> bool:
    """Check if this chapter is at a quarter boundary.

    RULE: Quarter changes force new sections.
    """
    if prev is None:
        return False  # First chapter handled by GAME_START

    if curr.period is None or prev.period is None:
        return False

    return curr.period != prev.period


def _is_beat_change(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
) -> bool:
    """Check if beat type changed from previous chapter.

    RULE: Beat changes MAY force sections (lowest priority).
    """
    if prev is None:
        return False

    return curr.beat_type != prev.beat_type


def detect_forced_break(
    curr: ChapterMetadata,
    prev: ChapterMetadata | None,
    seen_crunch: bool,
    seen_closing: bool = False,  # Phase 2.6
) -> ForcedBreakReason | None:
    """Detect if a forced section break is required.

    Checks in priority order:
    1. Game start (first chapter)
    2. Overtime start
    3. First CLOSING_SEQUENCE (Phase 2.6)
    4. Final 2 minutes entry (legacy - now handled by CLOSING_SEQUENCE)
    5. First CRUNCH_SETUP
    6. Quarter boundary
    7. Beat change

    Args:
        curr: Current chapter metadata
        prev: Previous chapter metadata (None if first)
        seen_crunch: Whether CRUNCH_SETUP has been seen before
        seen_closing: Whether CLOSING_SEQUENCE has been seen before

    Returns:
        ForcedBreakReason if break required, None otherwise
    """
    # First chapter always starts a section
    if prev is None:
        return ForcedBreakReason.GAME_START

    # Priority 1: Overtime start
    if _is_overtime_start(curr, prev):
        return ForcedBreakReason.OVERTIME_START

    # Priority 2: First CLOSING_SEQUENCE (Phase 2.6)
    if _is_first_closing_sequence(curr, prev, seen_closing):
        return ForcedBreakReason.CLOSING_SEQUENCE_FIRST

    # Priority 3: Final 2 minutes entry (legacy)
    if _is_final_2_minutes_entry(curr, prev):
        return ForcedBreakReason.FINAL_2_MINUTES

    # Priority 4: First CRUNCH_SETUP
    if _is_first_crunch_setup(curr, prev, seen_crunch):
        return ForcedBreakReason.CRUNCH_SETUP_FIRST

    # Priority 5: Quarter boundary
    if _is_quarter_boundary(curr, prev):
        return ForcedBreakReason.QUARTER_BOUNDARY

    # Priority 6: Beat change
    if _is_beat_change(curr, prev):
        return ForcedBreakReason.BEAT_CHANGE

    return None


# ============================================================================
# NOTES GENERATION (DETERMINISTIC)
# ============================================================================


def generate_section_notes(
    team_deltas: dict[str, TeamStatDelta],
    player_deltas: dict[str, PlayerStatDelta],
    home_team_key: str | None = None,
    away_team_key: str | None = None,
) -> list[str]:
    """Generate deterministic notes for a section.

    RULES:
    - Derived ONLY from section stat deltas
    - Factual and deterministic
    - Short, single-sentence bullets

    Allowed:
    - "Toronto outscored LA 14–6"
    - "Four turnovers in the section"
    - "Two timeouts used by Lakers"
    - "Technical foul assessed"

    Disallowed:
    - Adjectives
    - Opinions
    - Inferred momentum
    - Narrative language
    """
    notes = []

    # Collect team data
    teams = list(team_deltas.values())

    if len(teams) >= 2:
        # Sort by points scored (descending)
        sorted_teams = sorted(teams, key=lambda t: t.points_scored, reverse=True)
        high_team = sorted_teams[0]
        low_team = sorted_teams[1]

        # Scoring comparison
        if high_team.points_scored > low_team.points_scored:
            notes.append(
                f"{high_team.team_name} outscored {low_team.team_name} "
                f"{high_team.points_scored}–{low_team.points_scored}"
            )
        elif (
            high_team.points_scored == low_team.points_scored
            and high_team.points_scored > 0
        ):
            notes.append(
                f"Teams tied {high_team.points_scored}–{low_team.points_scored} in section"
            )

    # Timeouts
    for team in teams:
        if team.timeouts_used >= 2:
            notes.append(f"{team.timeouts_used} timeouts used by {team.team_name}")
        elif team.timeouts_used == 1:
            notes.append(f"Timeout used by {team.team_name}")

    # Technical fouls
    for team in teams:
        if team.technical_fouls_committed > 0:
            if team.technical_fouls_committed == 1:
                notes.append(f"Technical foul assessed to {team.team_name}")
            else:
                notes.append(
                    f"{team.technical_fouls_committed} technical fouls assessed to {team.team_name}"
                )

    # Foul trouble
    for player in player_deltas.values():
        if player.foul_trouble_flag:
            notes.append(f"{player.player_name} in foul trouble")

    # High scorers (> 6 points in section)
    high_scorers = [p for p in player_deltas.values() if p.points_scored >= 6]
    high_scorers_sorted = sorted(
        high_scorers, key=lambda p: p.points_scored, reverse=True
    )

    for player in high_scorers_sorted[:2]:  # Max 2 high scorer notes
        notes.append(f"{player.player_name} scored {player.points_scored} points")

    return notes


# ============================================================================
# SECTION CONSTRUCTION
# ============================================================================


def _extract_chapter_metadata(
    chapter: Chapter,
    classification: BeatClassification,
) -> ChapterMetadata:
    """Extract metadata needed for section construction."""
    # Extract period
    period = chapter.period
    if period is None and chapter.plays:
        period = chapter.plays[0].raw_data.get("quarter")

    is_overtime = period is not None and period > 4

    # Extract time remaining from last play
    time_remaining_seconds = None
    if chapter.plays:
        last_play = chapter.plays[-1]
        clock_str = last_play.raw_data.get("game_clock")
        if clock_str and ":" in clock_str:
            try:
                parts = clock_str.split(":")
                time_remaining_seconds = int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                pass

    # Extract scores
    start_home = 0
    start_away = 0
    end_home = 0
    end_away = 0

    if chapter.plays:
        first_play = chapter.plays[0]
        start_home = first_play.raw_data.get("home_score", 0) or 0
        start_away = first_play.raw_data.get("away_score", 0) or 0

        last_play = chapter.plays[-1]
        end_home = last_play.raw_data.get("home_score", 0) or 0
        end_away = last_play.raw_data.get("away_score", 0) or 0

    return ChapterMetadata(
        chapter_id=chapter.chapter_id,
        chapter_index=classification.debug_info.get("chapter_index", 0),
        beat_type=classification.beat_type,
        period=period,
        time_remaining_seconds=time_remaining_seconds,
        is_overtime=is_overtime,
        start_home_score=start_home,
        start_away_score=start_away,
        end_home_score=end_home,
        end_away_score=end_away,
        descriptors=classification.descriptors or set(),  # Phase 2.1
    )


def _aggregate_section_deltas(
    section_deltas: list[SectionDelta],
    end_snapshot: RunningStatsSnapshot | None = None,
) -> tuple[dict[str, TeamStatDelta], dict[str, PlayerStatDelta]]:
    """Aggregate section deltas from multiple chapters into one section.

    PLAYER PROMINENCE SELECTION:
    Uses prominence-based selection when end_snapshot is provided:
    - Top 1-2 by section_points (section leaders)
    - Top 1 by game_points_so_far (game presence)
    - Max 3 per team, no duplicates

    Falls back to simple "top 3 by points" when no snapshot available.

    Args:
        section_deltas: List of SectionDelta objects to aggregate
        end_snapshot: Optional snapshot at section end for prominence selection

    Returns:
        Tuple of (team_deltas, player_deltas)
    """
    team_totals: dict[str, TeamStatDelta] = {}
    player_totals: dict[str, PlayerStatDelta] = {}

    for delta in section_deltas:
        # Aggregate team stats
        for team_key, team_delta in delta.teams.items():
            if team_key not in team_totals:
                team_totals[team_key] = TeamStatDelta(
                    team_key=team_delta.team_key,
                    team_name=team_delta.team_name,
                )

            t = team_totals[team_key]
            t.points_scored += team_delta.points_scored
            t.personal_fouls_committed += team_delta.personal_fouls_committed
            t.technical_fouls_committed += team_delta.technical_fouls_committed
            t.timeouts_used += team_delta.timeouts_used
            t.possessions_estimate += team_delta.possessions_estimate

        # Aggregate player stats
        for player_key, player_delta in delta.players.items():
            if player_key not in player_totals:
                player_totals[player_key] = PlayerStatDelta(
                    player_key=player_delta.player_key,
                    player_name=player_delta.player_name,
                    team_key=player_delta.team_key,
                )

            p = player_totals[player_key]
            p.points_scored += player_delta.points_scored
            p.fg_made += player_delta.fg_made
            p.three_pt_made += player_delta.three_pt_made
            p.ft_made += player_delta.ft_made
            # Expanded stats (Player Prominence)
            p.assists += player_delta.assists
            p.blocks += player_delta.blocks
            p.steals += player_delta.steals
            p.personal_foul_count += player_delta.personal_foul_count
            # Foul trouble if 4+ fouls in this aggregated section
            p.foul_trouble_flag = p.personal_foul_count >= 4

    # Select players using prominence-based rules
    bounded_players: dict[str, PlayerStatDelta] = {}

    if end_snapshot is not None:
        # Use prominence-based selection
        # Build a fake section delta for the aggregated stats
        from .running_stats import PlayerDelta

        aggregated_delta = SectionDelta(
            section_start_chapter=0,
            section_end_chapter=0,
            players={
                key: PlayerDelta(
                    player_key=p.player_key,
                    player_name=p.player_name,
                    team_key=p.team_key,
                    points_scored=p.points_scored,
                )
                for key, p in player_totals.items()
            },
        )

        prominence_map = compute_player_prominence(aggregated_delta, end_snapshot)
        selected_keys = select_prominent_players(prominence_map, max_per_team=3)

        for key in selected_keys:
            if key in player_totals:
                bounded_players[key] = player_totals[key]
    else:
        # Fallback: top 3 per team by section points (original behavior)
        players_by_team: dict[str, list[PlayerStatDelta]] = {}
        for p in player_totals.values():
            team = p.team_key or "unknown"
            if team not in players_by_team:
                players_by_team[team] = []
            players_by_team[team].append(p)

        for team_key, players in players_by_team.items():
            sorted_players = sorted(
                players,
                key=lambda x: (-x.points_scored, -x.fg_made, x.player_key),
            )
            for p in sorted_players[:3]:
                bounded_players[p.player_key] = p

    return team_totals, bounded_players


def _select_section_beat(chapters_meta: list[ChapterMetadata]) -> BeatType:
    """Select the primary beat for a section based on priority.

    Phase 2.1: Uses priority-based selection instead of "first chapter wins".

    Priority order (highest first):
    1. OVERTIME
    2. CLOSING_SEQUENCE
    3. CRUNCH_SETUP
    4. RUN
    5. RESPONSE
    6. BACK_AND_FORTH
    7. EARLY_CONTROL
    8. FAST_START
    9. STALL (default)

    Args:
        chapters_meta: List of ChapterMetadata in the section

    Returns:
        The highest-priority beat type present in any chapter
    """
    # Collect all beat types in the section
    beat_types = {m.beat_type for m in chapters_meta}

    # Select highest-priority beat
    for beat in BEAT_PRIORITY:
        if beat in beat_types:
            return beat

    # Default to STALL if no match (shouldn't happen)
    return BeatType.STALL


def _aggregate_descriptors(chapters_meta: list[ChapterMetadata]) -> set[BeatDescriptor]:
    """Aggregate all descriptors from chapters in a section.

    Phase 2.1: Descriptors are unioned across all chapters.

    Args:
        chapters_meta: List of ChapterMetadata in the section

    Returns:
        Union of all descriptors from all chapters
    """
    result: set[BeatDescriptor] = set()
    for meta in chapters_meta:
        result.update(meta.descriptors)
    return result


def _build_section(
    section_index: int,
    chapters_meta: list[ChapterMetadata],
    section_deltas: list[SectionDelta],
    break_reason: ForcedBreakReason,
    end_snapshot: RunningStatsSnapshot | None = None,
) -> StorySection:
    """Build a single StorySection from chapters.

    Phase 2.1: Uses priority-based beat selection instead of first chapter.
    Aggregates descriptors from all chapters.

    Player Prominence: When end_snapshot is provided, uses prominence-based
    player selection (top 1-2 by section points, top 1 by game points).
    """
    # Phase 2.1: Use priority-based beat selection
    beat_type = _select_section_beat(chapters_meta)

    # Phase 2.1: Union all descriptors from chapters
    descriptors = _aggregate_descriptors(chapters_meta)

    # Get chapter IDs
    chapter_ids = [m.chapter_id for m in chapters_meta]

    # Get score bookends
    start_score = {
        "home": chapters_meta[0].start_home_score,
        "away": chapters_meta[0].start_away_score,
    }
    end_score = {
        "home": chapters_meta[-1].end_home_score,
        "away": chapters_meta[-1].end_away_score,
    }

    # Aggregate stats with prominence-based player selection
    team_deltas, player_deltas = _aggregate_section_deltas(
        section_deltas, end_snapshot
    )

    # Generate notes
    notes = generate_section_notes(team_deltas, player_deltas)

    return StorySection(
        section_index=section_index,
        beat_type=beat_type,
        chapters_included=chapter_ids,
        start_score=start_score,
        end_score=end_score,
        team_stat_deltas=team_deltas,
        player_stat_deltas=player_deltas,
        notes=notes,
        descriptors=descriptors,  # Phase 2.1
        break_reason=break_reason,
    )


# ============================================================================
# SIGNAL THRESHOLD CONSTANTS
# ============================================================================

# Minimum points scored in a section to be considered "powered"
SECTION_MIN_POINTS_THRESHOLD = 8

# Minimum meaningful events in a section to be considered "powered"
SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD = 3


# ============================================================================
# THIN SECTION CONSTANTS
# ============================================================================

# A section is "thin" if BOTH conditions are true
THIN_SECTION_MAX_POINTS = 4  # Total points scored ≤ 4
THIN_SECTION_MAX_SCORING_PLAYS = 2  # Number of scoring plays ≤ 2


# ============================================================================
# LUMPY SECTION CONSTANTS (DOMINANCE CAPPING)
# ============================================================================

# A section is "lumpy" if single player has ≥ this % of section points
LUMPY_DOMINANCE_THRESHOLD_PCT = 0.65  # 65%

# Cap dominant player contribution at this % of section points
DOMINANCE_CAP_PCT = 0.60  # 60%


# ============================================================================
# BEAT-AWARE MERGE RULES
# ============================================================================


# Beat pairs that are incompatible for merging (cannot be in same section)
# Format: (beat_a, beat_b) - order doesn't matter, both directions blocked
INCOMPATIBLE_BEAT_PAIRS: set[frozenset[BeatType]] = {
    # RUN/RESPONSE cannot merge with STALL
    frozenset({BeatType.RUN, BeatType.STALL}),
    frozenset({BeatType.RESPONSE, BeatType.STALL}),
    # FAST_START/EARLY_CONTROL cannot merge with CLOSING_SEQUENCE
    frozenset({BeatType.FAST_START, BeatType.CLOSING_SEQUENCE}),
    frozenset({BeatType.EARLY_CONTROL, BeatType.CLOSING_SEQUENCE}),
}

# Beats that are "crunch-tier" and should not merge with non-crunch beats
CRUNCH_TIER_BEATS: set[BeatType] = {
    BeatType.CRUNCH_SETUP,
    BeatType.CLOSING_SEQUENCE,
}

# Non-crunch beats (everything except crunch-tier and overtime)
NON_CRUNCH_BEATS: set[BeatType] = {
    BeatType.FAST_START,
    BeatType.BACK_AND_FORTH,
    BeatType.EARLY_CONTROL,
    BeatType.RUN,
    BeatType.RESPONSE,
    BeatType.STALL,
    BeatType.MISSED_SHOT_FEST,  # Deprecated but still in enum
}


def are_beats_compatible_for_merge(beat_a: BeatType, beat_b: BeatType) -> bool:
    """Check if two beats can be merged into the same section.

    Beat-aware merge rules:
    1. OVERTIME cannot merge with anything (always isolated)
    2. Non-crunch beats cannot merge with crunch-tier beats (CRUNCH_SETUP, CLOSING_SEQUENCE)
    3. RUN/RESPONSE cannot merge with STALL
    4. FAST_START/EARLY_CONTROL cannot merge with CLOSING_SEQUENCE

    Args:
        beat_a: Beat type of first section
        beat_b: Beat type of second section

    Returns:
        True if the beats are compatible for merging
    """
    # Rule 1: OVERTIME never merges
    if beat_a == BeatType.OVERTIME or beat_b == BeatType.OVERTIME:
        return False

    # Rule 2: Non-crunch cannot merge with crunch-tier
    a_is_crunch = beat_a in CRUNCH_TIER_BEATS
    b_is_crunch = beat_b in CRUNCH_TIER_BEATS
    a_is_non_crunch = beat_a in NON_CRUNCH_BEATS
    b_is_non_crunch = beat_b in NON_CRUNCH_BEATS

    if (a_is_crunch and b_is_non_crunch) or (a_is_non_crunch and b_is_crunch):
        return False

    # Rules 3 & 4: Check explicit incompatible pairs
    pair = frozenset({beat_a, beat_b})
    if pair in INCOMPATIBLE_BEAT_PAIRS:
        return False

    return True


# ============================================================================
# SECTION SIGNAL EVALUATION
# ============================================================================


def _count_scoring_plays(chapters: list[Chapter], chapter_ids: list[str]) -> int:
    """Count scoring plays in the given chapters.

    A scoring play is any play where the score changes.
    """
    count = 0
    chapters_map = {ch.chapter_id: ch for ch in chapters}

    for chapter_id in chapter_ids:
        chapter = chapters_map.get(chapter_id)
        if not chapter or not chapter.plays:
            continue

        prev_home = None
        prev_away = None

        for play in chapter.plays:
            raw = play.raw_data
            home = raw.get("home_score") or 0
            away = raw.get("away_score") or 0

            if prev_home is not None and prev_away is not None:
                if home != prev_home or away != prev_away:
                    count += 1

            prev_home = home
            prev_away = away

    return count


def _count_lead_changes_and_ties(
    chapters: list[Chapter], chapter_ids: list[str]
) -> tuple[int, int]:
    """Count lead changes and tie creations in the given chapters.

    Returns:
        Tuple of (lead_change_count, tie_creation_count)
    """
    lead_changes = 0
    tie_creations = 0
    chapters_map = {ch.chapter_id: ch for ch in chapters}

    prev_leader: str | None = None
    first_play = True

    for chapter_id in chapter_ids:
        chapter = chapters_map.get(chapter_id)
        if not chapter or not chapter.plays:
            continue

        for play in chapter.plays:
            raw = play.raw_data
            home = raw.get("home_score") or 0
            away = raw.get("away_score") or 0

            # Determine current leader
            if home > away:
                curr_leader: str | None = "home"
            elif away > home:
                curr_leader = "away"
            else:
                curr_leader = None  # Tied

            if not first_play:
                # Lead change: one team was leading, now the other is
                if prev_leader is not None and curr_leader is not None:
                    if prev_leader != curr_leader:
                        lead_changes += 1

                # Tie creation: one team was leading, now tied
                if prev_leader is not None and curr_leader is None:
                    tie_creations += 1

            # Update for next iteration
            if curr_leader is not None:
                prev_leader = curr_leader
            first_play = False

    return lead_changes, tie_creations


def _count_run_events(chapters: list[Chapter], chapter_ids: list[str]) -> int:
    """Count run start/end events in the given chapters.

    A run starts when one team scores >= 6 unanswered points.
    A run ends when the opposing team scores.
    """
    from .virtual_boundaries import RUN_THRESHOLD_POINTS

    run_events = 0
    chapters_map = {ch.chapter_id: ch for ch in chapters}

    run_team: str | None = None
    run_points: int = 0
    run_announced: bool = False
    prev_home: int | None = None
    prev_away: int | None = None

    for chapter_id in chapter_ids:
        chapter = chapters_map.get(chapter_id)
        if not chapter or not chapter.plays:
            continue

        for play in chapter.plays:
            raw = play.raw_data
            home = raw.get("home_score") or 0
            away = raw.get("away_score") or 0

            if prev_home is not None and prev_away is not None:
                home_delta = home - prev_home
                away_delta = away - prev_away

                if home_delta > 0 and away_delta == 0:
                    # Home scored
                    if run_team == "home":
                        run_points += home_delta
                    else:
                        if run_team == "away" and run_announced:
                            run_events += 1  # RUN_END
                        run_team = "home"
                        run_points = home_delta
                        run_announced = False

                    if run_points >= RUN_THRESHOLD_POINTS and not run_announced:
                        run_events += 1  # RUN_START
                        run_announced = True

                elif away_delta > 0 and home_delta == 0:
                    # Away scored
                    if run_team == "away":
                        run_points += away_delta
                    else:
                        if run_team == "home" and run_announced:
                            run_events += 1  # RUN_END
                        run_team = "away"
                        run_points = away_delta
                        run_announced = False

                    if run_points >= RUN_THRESHOLD_POINTS and not run_announced:
                        run_events += 1  # RUN_START
                        run_announced = True

                elif home_delta > 0 and away_delta > 0:
                    # Both scored - end any run
                    if run_announced:
                        run_events += 1  # RUN_END
                    run_team = None
                    run_points = 0
                    run_announced = False

            prev_home = home
            prev_away = away

    return run_events


def count_meaningful_events(section: StorySection, chapters: list[Chapter]) -> int:
    """Count meaningful events in a section.

    Meaningful events include:
    - Scoring plays
    - Lead changes
    - Run start/end
    - Tie creation

    Args:
        section: The section to evaluate
        chapters: All chapters (for looking up chapter content)

    Returns:
        Total count of meaningful events
    """
    chapter_ids = section.chapters_included

    scoring_plays = _count_scoring_plays(chapters, chapter_ids)
    lead_changes, tie_creations = _count_lead_changes_and_ties(chapters, chapter_ids)
    run_events = _count_run_events(chapters, chapter_ids)

    return scoring_plays + lead_changes + tie_creations + run_events


def get_section_total_points(section: StorySection) -> int:
    """Get total points scored in a section (both teams combined)."""
    total = 0
    for team_delta in section.team_stat_deltas.values():
        total += team_delta.points_scored
    return total


def is_section_underpowered(
    section: StorySection,
    chapters: list[Chapter],
) -> bool:
    """Check if a section is underpowered (below signal threshold).

    A section is underpowered if BOTH:
    - Total points scored < SECTION_MIN_POINTS_THRESHOLD (8)
    - Meaningful event count < SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD (3)

    Args:
        section: The section to evaluate
        chapters: All chapters (for meaningful event detection)

    Returns:
        True if the section is underpowered
    """
    total_points = get_section_total_points(section)
    meaningful_events = count_meaningful_events(section, chapters)

    # Underpowered if BOTH conditions are true
    return (
        total_points < SECTION_MIN_POINTS_THRESHOLD
        and meaningful_events < SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD
    )


# ============================================================================
# THIN SECTION DETECTION & HANDLING
# ============================================================================


def count_section_scoring_plays(
    section: StorySection, chapters: list[Chapter]
) -> int:
    """Count number of scoring plays in a section.

    A scoring play is any play where the score changes.
    """
    return _count_scoring_plays(chapters, section.chapters_included)


def is_section_thin(section: StorySection, chapters: list[Chapter]) -> bool:
    """Check if a section is thin (very low signal).

    A section is thin if BOTH:
    - Total points scored ≤ THIN_SECTION_MAX_POINTS (4)
    - Number of scoring plays ≤ THIN_SECTION_MAX_SCORING_PLAYS (2)

    Thin sections must ALWAYS be merged, never dropped.

    Args:
        section: The section to evaluate
        chapters: All chapters (for scoring play count)

    Returns:
        True if the section is thin
    """
    total_points = get_section_total_points(section)
    scoring_plays = count_section_scoring_plays(section, chapters)

    return (
        total_points <= THIN_SECTION_MAX_POINTS
        and scoring_plays <= THIN_SECTION_MAX_SCORING_PLAYS
    )


def _is_crunch_or_late_game(section: StorySection) -> bool:
    """Check if section is in crunch or late game phase.

    Returns True for CRUNCH_SETUP or CLOSING_SEQUENCE beats.
    """
    return section.beat_type in (BeatType.CRUNCH_SETUP, BeatType.CLOSING_SEQUENCE)


def _is_early_game_section(section: StorySection) -> bool:
    """Check if section is in early game phase (Q1-Q3).

    Returns True if section is NOT crunch/late game.
    """
    return not _is_crunch_or_late_game(section)


def _find_thin_section_merge_target(
    sections: list[StorySection],
    thin_idx: int,
    is_end_of_game: bool,
) -> int | None:
    """Find merge target for a thin section following merge rules.

    THIN SECTION MERGE RULES (Authoritative):
    1. Early game (Q1-Q3): Merge upward (into previous)
    2. Crunch/late game: Merge downward (into next)
    3. Final fallback (non-end-of-game): Merge forward into next
    4. End-of-game exception: Final section merges backward only

    Never crosses OVERTIME boundaries.

    Args:
        sections: List of sections
        thin_idx: Index of the thin section
        is_end_of_game: True if thin section is the last section

    Returns:
        Index of merge target, or None if no valid target found
    """
    thin_section = sections[thin_idx]

    # Rule 4: End-of-game exception - must merge backward
    if is_end_of_game:
        # Find previous non-OVERTIME section
        for i in range(thin_idx - 1, -1, -1):
            if sections[i].beat_type != BeatType.OVERTIME:
                return i
        return None

    # Rule 1: Early game - merge upward (into previous)
    if _is_early_game_section(thin_section):
        # Try previous section first
        if thin_idx > 0:
            prev_section = sections[thin_idx - 1]
            # Can't cross OVERTIME boundary
            if prev_section.beat_type != BeatType.OVERTIME:
                return thin_idx - 1

        # Rule 3: Fallback - merge forward (if not end-of-game)
        if thin_idx < len(sections) - 1:
            next_section = sections[thin_idx + 1]
            if next_section.beat_type != BeatType.OVERTIME:
                return thin_idx + 1

        return None

    # Rule 2: Crunch/late game - merge downward (into next)
    if thin_idx < len(sections) - 1:
        next_section = sections[thin_idx + 1]
        # Can't cross OVERTIME boundary
        if next_section.beat_type != BeatType.OVERTIME:
            return thin_idx + 1

    # Rule 3: Fallback - merge backward
    if thin_idx > 0:
        prev_section = sections[thin_idx - 1]
        if prev_section.beat_type != BeatType.OVERTIME:
            return thin_idx - 1

    return None


def handle_thin_sections(
    sections: list[StorySection],
    chapters: list[Chapter],
) -> list[StorySection]:
    """Handle thin sections by merging them (never dropping).

    THIN SECTION MERGE RULES:
    1. Early game (Q1-Q3): Merge upward into previous
    2. Crunch/late game: Merge downward into next
    3. Final fallback: Merge forward (if not end-of-game)
    4. End-of-game: Must merge backward

    Key constraints:
    - Thin sections are ALWAYS merged, NEVER dropped
    - PROTECTED sections (opening, CRUNCH_SETUP, CLOSING_SEQUENCE, OVERTIME)
      cannot be merged away - they are skipped even if thin
    - Never crosses OVERTIME boundaries

    Args:
        sections: List of sections to process
        chapters: All chapters (for signal evaluation)

    Returns:
        List of sections with thin sections merged
    """
    if not sections:
        return sections

    result = list(sections)
    changed = True

    # Process iteratively until no more thin sections
    while changed:
        changed = False

        # Find first thin section that is NOT protected
        thin_idx = None
        for i, section in enumerate(result):
            # Skip protected sections - they cannot be merged away
            if _is_protected_section(section):
                continue
            if is_section_thin(section, chapters):
                thin_idx = i
                break

        if thin_idx is None:
            break  # No more thin sections (or all remaining thin sections are protected)

        # Determine if this is end-of-game
        is_end_of_game = thin_idx == len(result) - 1

        # Find merge target
        target_idx = _find_thin_section_merge_target(result, thin_idx, is_end_of_game)

        if target_idx is not None:
            # Perform merge
            if target_idx < thin_idx:
                # Merge thin into previous (upward merge)
                merged = _merge_sections(
                    result[target_idx], result[thin_idx], target_idx
                )
                result = result[:target_idx] + [merged] + result[thin_idx + 1 :]
            else:
                # Merge thin into next (downward merge)
                merged = _merge_sections(
                    result[thin_idx], result[target_idx], thin_idx
                )
                result = result[:thin_idx] + [merged] + result[target_idx + 1 :]

            changed = True

            # Renumber remaining sections
            for j, s in enumerate(result):
                s.section_index = j
        else:
            # No valid merge target - this should rarely happen
            # (only if section is completely isolated by OVERTIME boundaries)
            # In this case, we leave it as-is rather than dropping
            break

    return result


# ============================================================================
# LUMPY SECTION DETECTION & DOMINANCE CAPPING
# ============================================================================


def get_dominant_player_share(section: StorySection) -> tuple[str | None, float]:
    """Get the most dominant player and their share of section points.

    Args:
        section: The section to evaluate

    Returns:
        Tuple of (player_key, share_pct) where share_pct is 0.0-1.0.
        Returns (None, 0.0) if no players or no points.
    """
    total_points = get_section_total_points(section)
    if total_points == 0:
        return None, 0.0

    max_player_key = None
    max_player_points = 0

    for player_key, delta in section.player_stat_deltas.items():
        if delta.points_scored > max_player_points:
            max_player_points = delta.points_scored
            max_player_key = player_key

    if max_player_key is None:
        return None, 0.0

    share = max_player_points / total_points
    return max_player_key, share


def is_section_lumpy(section: StorySection) -> bool:
    """Check if a section is lumpy (dominated by single player).

    A section is lumpy if a single player accounts for ≥ 65% of section points.

    Args:
        section: The section to evaluate

    Returns:
        True if the section is lumpy
    """
    _, share = get_dominant_player_share(section)
    return share >= LUMPY_DOMINANCE_THRESHOLD_PCT


def _find_spillover_target(
    sections: list[StorySection],
    source_idx: int,
) -> int | None:
    """Find a section to receive spillover stats.

    Spillover goes to the nearest compatible adjacent section.
    Never crosses OVERTIME boundaries.

    Preference: previous section, then next section.

    Args:
        sections: List of sections
        source_idx: Index of the lumpy section

    Returns:
        Index of spillover target, or None if no valid target
    """
    # Try previous section first
    if source_idx > 0:
        prev_section = sections[source_idx - 1]
        # Can't cross OVERTIME boundary
        if prev_section.beat_type != BeatType.OVERTIME:
            source_beat = sections[source_idx].beat_type
            if are_beats_compatible_for_merge(prev_section.beat_type, source_beat):
                return source_idx - 1

    # Try next section
    if source_idx < len(sections) - 1:
        next_section = sections[source_idx + 1]
        if next_section.beat_type != BeatType.OVERTIME:
            source_beat = sections[source_idx].beat_type
            if are_beats_compatible_for_merge(source_beat, next_section.beat_type):
                return source_idx + 1

    return None


def apply_dominance_cap(
    sections: list[StorySection],
) -> list[StorySection]:
    """Apply dominance capping to lumpy sections with spillover.

    When a section is lumpy (single player ≥ 65% of points):
    1. Cap dominant player at 60% of section points
    2. Spill excess to nearest compatible adjacent section
    3. Preserve total game stats
    4. Never cross OVERTIME boundaries

    Note: This modifies player_stat_deltas only, not team stats.
    Stat adjustments are deterministic.

    Args:
        sections: List of sections to process

    Returns:
        List of sections with dominance capping applied
    """
    if len(sections) < 2:
        return sections

    result = list(sections)

    for i, section in enumerate(result):
        if not is_section_lumpy(section):
            continue

        total_points = get_section_total_points(section)
        if total_points == 0:
            continue

        dominant_key, dominant_share = get_dominant_player_share(section)
        if dominant_key is None:
            continue

        # Calculate cap and excess
        cap_points = int(total_points * DOMINANCE_CAP_PCT)
        dominant_player = section.player_stat_deltas.get(dominant_key)
        if dominant_player is None:
            continue

        excess_points = dominant_player.points_scored - cap_points
        if excess_points <= 0:
            continue

        # Find spillover target
        target_idx = _find_spillover_target(result, i)
        if target_idx is None:
            # No valid spillover target - skip capping for this section
            continue

        # Apply cap to dominant player in this section
        dominant_player.points_scored = cap_points

        # Apply spillover to target section
        target_section = result[target_idx]

        # Find or create player entry in target section
        if dominant_key in target_section.player_stat_deltas:
            target_section.player_stat_deltas[dominant_key].points_scored += (
                excess_points
            )
        else:
            # Create new player entry with just the spillover points
            target_section.player_stat_deltas[dominant_key] = PlayerStatDelta(
                player_key=dominant_player.player_key,
                player_name=dominant_player.player_name,
                team_key=dominant_player.team_key,
                points_scored=excess_points,
            )

    return result


# ============================================================================
# SECTION COUNT ENFORCEMENT
# ============================================================================


def _is_protected_section(section: StorySection) -> bool:
    """Check if section is protected from merging.

    Protected sections:
    - Opening section (index 0)
    - CRUNCH_SETUP
    - CLOSING_SEQUENCE
    - OVERTIME
    """
    if section.section_index == 0:
        return True

    if section.beat_type in (
        BeatType.CRUNCH_SETUP,
        BeatType.CLOSING_SEQUENCE,
        BeatType.OVERTIME,
    ):
        return True

    return False


def _merge_sections(
    section_a: StorySection,
    section_b: StorySection,
    new_index: int,
) -> StorySection:
    """Merge two adjacent sections into one.

    The merged section:
    - Takes beat_type from section_a (earlier)
    - Combines chapters_included
    - Uses start_score from section_a, end_score from section_b
    - Aggregates stats and notes
    """
    # Combine chapters
    chapters = section_a.chapters_included + section_b.chapters_included

    # Merge team deltas
    merged_teams: dict[str, TeamStatDelta] = {}
    for team_key, delta in section_a.team_stat_deltas.items():
        merged_teams[team_key] = TeamStatDelta(
            team_key=delta.team_key,
            team_name=delta.team_name,
            points_scored=delta.points_scored,
            personal_fouls_committed=delta.personal_fouls_committed,
            technical_fouls_committed=delta.technical_fouls_committed,
            timeouts_used=delta.timeouts_used,
            possessions_estimate=delta.possessions_estimate,
        )

    for team_key, delta in section_b.team_stat_deltas.items():
        if team_key in merged_teams:
            t = merged_teams[team_key]
            t.points_scored += delta.points_scored
            t.personal_fouls_committed += delta.personal_fouls_committed
            t.technical_fouls_committed += delta.technical_fouls_committed
            t.timeouts_used += delta.timeouts_used
            t.possessions_estimate += delta.possessions_estimate
        else:
            merged_teams[team_key] = TeamStatDelta(
                team_key=delta.team_key,
                team_name=delta.team_name,
                points_scored=delta.points_scored,
                personal_fouls_committed=delta.personal_fouls_committed,
                technical_fouls_committed=delta.technical_fouls_committed,
                timeouts_used=delta.timeouts_used,
                possessions_estimate=delta.possessions_estimate,
            )

    # Merge player deltas (take all, re-bound later)
    merged_players: dict[str, PlayerStatDelta] = {}
    for player_key, delta in section_a.player_stat_deltas.items():
        merged_players[player_key] = PlayerStatDelta(
            player_key=delta.player_key,
            player_name=delta.player_name,
            team_key=delta.team_key,
            points_scored=delta.points_scored,
            fg_made=delta.fg_made,
            three_pt_made=delta.three_pt_made,
            ft_made=delta.ft_made,
            assists=delta.assists,
            blocks=delta.blocks,
            steals=delta.steals,
            personal_foul_count=delta.personal_foul_count,
            foul_trouble_flag=delta.foul_trouble_flag,
        )

    for player_key, delta in section_b.player_stat_deltas.items():
        if player_key in merged_players:
            p = merged_players[player_key]
            p.points_scored += delta.points_scored
            p.fg_made += delta.fg_made
            p.three_pt_made += delta.three_pt_made
            p.ft_made += delta.ft_made
            p.assists += delta.assists
            p.blocks += delta.blocks
            p.steals += delta.steals
            p.personal_foul_count += delta.personal_foul_count
            p.foul_trouble_flag = p.personal_foul_count >= 4
        else:
            merged_players[player_key] = PlayerStatDelta(
                player_key=delta.player_key,
                player_name=delta.player_name,
                team_key=delta.team_key,
                points_scored=delta.points_scored,
                fg_made=delta.fg_made,
                three_pt_made=delta.three_pt_made,
                ft_made=delta.ft_made,
                assists=delta.assists,
                blocks=delta.blocks,
                steals=delta.steals,
                personal_foul_count=delta.personal_foul_count,
                foul_trouble_flag=delta.foul_trouble_flag,
            )

    # Re-bound players (top 3 per team)
    players_by_team: dict[str, list[PlayerStatDelta]] = {}
    for p in merged_players.values():
        team = p.team_key or "unknown"
        if team not in players_by_team:
            players_by_team[team] = []
        players_by_team[team].append(p)

    bounded_players: dict[str, PlayerStatDelta] = {}
    for players in players_by_team.values():
        sorted_players = sorted(
            players,
            key=lambda x: (-x.points_scored, -x.fg_made, x.player_key),
        )
        for p in sorted_players[:3]:
            bounded_players[p.player_key] = p

    # Regenerate notes
    notes = generate_section_notes(merged_teams, bounded_players)

    # Phase 2.1: Merge descriptors from both sections
    merged_descriptors = section_a.descriptors | section_b.descriptors

    return StorySection(
        section_index=new_index,
        beat_type=section_a.beat_type,
        chapters_included=chapters,
        start_score=section_a.start_score,
        end_score=section_b.end_score,
        team_stat_deltas=merged_teams,
        player_stat_deltas=bounded_players,
        notes=notes,
        descriptors=merged_descriptors,  # Phase 2.1
        break_reason=section_a.break_reason,
    )


def _find_closing_sequence_index(sections: list[StorySection]) -> int | None:
    """Find the index of the first CLOSING_SEQUENCE section.

    Phase 2.6: Used to prevent merging after CLOSING_SEQUENCE.

    Returns:
        Index of first CLOSING_SEQUENCE section, or None if not found
    """
    for i, section in enumerate(sections):
        if section.beat_type == BeatType.CLOSING_SEQUENCE:
            return i
    return None


def _can_merge_pair(
    sections: list[StorySection],
    idx: int,
    closing_sequence_idx: int | None,
) -> bool:
    """Check if a pair of sections at idx and idx+1 can be merged.

    Phase 2.6: Prevents merging sections at or after CLOSING_SEQUENCE.
    Beat-aware: Prevents merging incompatible beat types.

    Args:
        sections: List of sections
        idx: Index of first section in pair
        closing_sequence_idx: Index of CLOSING_SEQUENCE section (or None)

    Returns:
        True if the pair can be merged
    """
    # Check protected sections
    if _is_protected_section(sections[idx]) or _is_protected_section(sections[idx + 1]):
        return False

    # Phase 2.6: No merging at or after CLOSING_SEQUENCE
    if closing_sequence_idx is not None:
        if idx >= closing_sequence_idx or idx + 1 >= closing_sequence_idx:
            return False

    # Beat-aware: Check beat compatibility
    if not are_beats_compatible_for_merge(
        sections[idx].beat_type, sections[idx + 1].beat_type
    ):
        return False

    return True


def _find_compatible_neighbor_for_merge(
    sections: list[StorySection],
    idx: int,
    closing_sequence_idx: int | None,
) -> int | None:
    """Find a compatible neighbor section to merge an underpowered section into.

    Preference order:
    1. Previous section (if compatible)
    2. Next section (if compatible)

    Args:
        sections: List of sections
        idx: Index of the underpowered section
        closing_sequence_idx: Index of CLOSING_SEQUENCE section (or None)

    Returns:
        Index of compatible neighbor, or None if none found
    """
    underpowered = sections[idx]

    # Try previous section first
    if idx > 0:
        prev_section = sections[idx - 1]
        # Check if previous is not protected and beats are compatible
        if not _is_protected_section(prev_section):
            if are_beats_compatible_for_merge(
                prev_section.beat_type, underpowered.beat_type
            ):
                # Check CLOSING_SEQUENCE constraint
                if closing_sequence_idx is None or (
                    idx - 1 < closing_sequence_idx and idx < closing_sequence_idx
                ):
                    return idx - 1

    # Try next section
    if idx < len(sections) - 1:
        next_section = sections[idx + 1]
        # Check if next is not protected and beats are compatible
        if not _is_protected_section(next_section):
            if are_beats_compatible_for_merge(
                underpowered.beat_type, next_section.beat_type
            ):
                # Check CLOSING_SEQUENCE constraint
                if closing_sequence_idx is None or (
                    idx < closing_sequence_idx and idx + 1 < closing_sequence_idx
                ):
                    return idx + 1

    return None


def handle_underpowered_sections(
    sections: list[StorySection],
    chapters: list[Chapter],
) -> list[StorySection]:
    """Handle underpowered sections by merging or dropping them.

    For each underpowered section:
    1. Try to merge into nearest compatible neighbor
    2. If no compatible neighbor, drop the section

    Args:
        sections: List of sections to process
        chapters: All chapters (for signal evaluation)

    Returns:
        List of sections with underpowered sections handled
    """
    if not sections:
        return sections

    result = list(sections)
    changed = True

    # Process iteratively until no more changes
    while changed:
        changed = False
        closing_idx = _find_closing_sequence_index(result)

        # Find first underpowered section
        underpowered_idx = None
        for i, section in enumerate(result):
            # Protected sections cannot be dropped/merged
            if _is_protected_section(section):
                continue

            if is_section_underpowered(section, chapters):
                underpowered_idx = i
                break

        if underpowered_idx is None:
            break  # No more underpowered sections

        # Try to find compatible neighbor
        neighbor_idx = _find_compatible_neighbor_for_merge(
            result, underpowered_idx, closing_idx
        )

        if neighbor_idx is not None:
            # Merge into neighbor
            if neighbor_idx < underpowered_idx:
                # Merge underpowered into previous
                merged = _merge_sections(
                    result[neighbor_idx], result[underpowered_idx], neighbor_idx
                )
                result = (
                    result[:neighbor_idx] + [merged] + result[underpowered_idx + 1 :]
                )
            else:
                # Merge underpowered into next
                merged = _merge_sections(
                    result[underpowered_idx], result[neighbor_idx], underpowered_idx
                )
                result = (
                    result[:underpowered_idx] + [merged] + result[neighbor_idx + 1 :]
                )
            changed = True
        else:
            # No compatible neighbor - drop the section
            result = result[:underpowered_idx] + result[underpowered_idx + 1 :]
            changed = True

        # Renumber remaining sections
        for j, s in enumerate(result):
            s.section_index = j

    return result


def enforce_section_count(
    sections: list[StorySection],
    min_sections: int = 0,  # Updated: was 3, now 0 (allow fewer sections)
    max_sections: int = 10,
) -> list[StorySection]:
    """Enforce section count constraints.

    RULES:
    - If sections < min: Merge earliest adjacent sections
    - If sections > max: Merge middle sections first
    - NEVER merge: opening, CRUNCH_SETUP, CLOSING_SEQUENCE, OVERTIME
    - Phase 2.6: NEVER merge sections at or after CLOSING_SEQUENCE

    Args:
        sections: List of sections to constrain
        min_sections: Minimum section count (default: 3)
        max_sections: Maximum section count (default: 10)

    Returns:
        List of sections with count in [min, max]
    """
    result = list(sections)

    # Phase 2.6: Find CLOSING_SEQUENCE section to prevent merging after it
    closing_idx = _find_closing_sequence_index(result)

    # Merge if too few sections
    while len(result) < min_sections and len(result) >= 2:
        # Update closing index after potential merges
        closing_idx = _find_closing_sequence_index(result)

        # Find first pair of adjacent non-protected sections to merge
        merged = False
        for i in range(len(result) - 1):
            if _can_merge_pair(result, i, closing_idx):
                # Merge these two
                merged_section = _merge_sections(result[i], result[i + 1], i)
                result = result[:i] + [merged_section] + result[i + 2 :]

                # Renumber remaining sections
                for j, s in enumerate(result):
                    s.section_index = j

                merged = True
                break

        if not merged:
            break  # Can't merge any more

    # Merge if too many sections
    while len(result) > max_sections:
        # Update closing index after potential merges
        closing_idx = _find_closing_sequence_index(result)

        # Find best pair to merge (prefer middle sections)
        best_pair = None
        best_distance_from_edges = -1

        for i in range(len(result) - 1):
            if not _can_merge_pair(result, i, closing_idx):
                continue

            # Distance from edges (prefer middle)
            distance = min(i, len(result) - 2 - i)
            if distance > best_distance_from_edges:
                best_distance_from_edges = distance
                best_pair = i

        if best_pair is None:
            break  # Can't merge any more (all protected)

        # Merge the best pair
        merged_section = _merge_sections(
            result[best_pair], result[best_pair + 1], best_pair
        )
        result = result[:best_pair] + [merged_section] + result[best_pair + 2 :]

        # Renumber remaining sections
        for j, s in enumerate(result):
            s.section_index = j

    return result


# ============================================================================
# MAIN BUILDER FUNCTION
# ============================================================================


def build_story_sections(
    chapters: list[Chapter],
    classifications: list[BeatClassification],
    section_deltas: list[SectionDelta] | None = None,
    snapshots: list[RunningStatsSnapshot] | None = None,
) -> list[StorySection]:
    """Build StorySections from chapters and beat classifications.

    PLAYER PROMINENCE:
    When snapshots are provided, uses prominence-based player selection:
    - Top 1-2 by section_points (section leaders)
    - Top 1 by game_points_so_far (game presence)
    - Max 3 per team, no duplicates
    Rolling game totals are used ONLY for selection, not passed to AI.

    Args:
        chapters: List of chapters in chronological order
        classifications: Beat classification for each chapter
        section_deltas: Stats for each chapter (from running_stats)
        snapshots: Running stats snapshots for prominence selection (optional)

    Returns:
        List of StorySections (0-10 sections, underpowered sections removed)
    """
    if not chapters or not classifications:
        return []

    # Ensure we have matching data
    if len(chapters) != len(classifications):
        raise ValueError(
            f"Chapters ({len(chapters)}) and classifications ({len(classifications)}) "
            "must have same length"
        )

    # Build metadata for each chapter
    metadata_list: list[ChapterMetadata] = []
    for i, (chapter, classification) in enumerate(zip(chapters, classifications)):
        meta = _extract_chapter_metadata(chapter, classification)
        meta.chapter_index = i
        metadata_list.append(meta)

    # Group chapters into sections based on forced breaks
    section_groups: list[tuple[list[ChapterMetadata], ForcedBreakReason]] = []
    current_group: list[ChapterMetadata] = []
    current_break_reason: ForcedBreakReason | None = None
    seen_crunch = False
    seen_closing = False  # Phase 2.6

    for i, meta in enumerate(metadata_list):
        prev_meta = metadata_list[i - 1] if i > 0 else None

        # Track if we've seen CRUNCH_SETUP
        if meta.beat_type == BeatType.CRUNCH_SETUP:
            seen_crunch_before = seen_crunch
            seen_crunch = True
        else:
            seen_crunch_before = seen_crunch

        # Track if we've seen CLOSING_SEQUENCE (Phase 2.6)
        if meta.beat_type == BeatType.CLOSING_SEQUENCE:
            seen_closing_before = seen_closing
            seen_closing = True
        else:
            seen_closing_before = seen_closing

        # Check for forced break
        break_reason = detect_forced_break(
            meta, prev_meta, seen_crunch_before, seen_closing_before
        )

        if break_reason is not None:
            # Save current group if non-empty
            if current_group:
                section_groups.append(
                    (
                        current_group,
                        current_break_reason or ForcedBreakReason.GAME_START,
                    )
                )

            # Start new group
            current_group = [meta]
            current_break_reason = break_reason
        else:
            # Add to current group
            current_group.append(meta)

    # Don't forget the last group
    if current_group:
        section_groups.append(
            (current_group, current_break_reason or ForcedBreakReason.GAME_START)
        )

    # Build sections from groups
    sections: list[StorySection] = []

    for section_idx, (group_meta, break_reason) in enumerate(section_groups):
        # Get corresponding section deltas
        chapter_indices = [m.chapter_index for m in group_meta]
        group_deltas = []
        if section_deltas:
            for idx in chapter_indices:
                if idx < len(section_deltas):
                    group_deltas.append(section_deltas[idx])

        # Get end snapshot for prominence selection (last chapter in section)
        end_snapshot = None
        if snapshots and chapter_indices:
            last_chapter_idx = chapter_indices[-1]
            if last_chapter_idx < len(snapshots):
                end_snapshot = snapshots[last_chapter_idx]

        section = _build_section(
            section_idx, group_meta, group_deltas, break_reason, end_snapshot
        )
        sections.append(section)

    # Handle underpowered sections (merge or drop)
    sections = handle_underpowered_sections(sections, chapters)

    # Handle thin sections (always merge, never drop)
    sections = handle_thin_sections(sections, chapters)

    # Apply dominance capping to lumpy sections
    sections = apply_dominance_cap(sections)

    # Enforce section count constraints (max only, min is now 0)
    sections = enforce_section_count(sections)

    # Phase 2.5: Apply section-level beat overrides (FAST_START, EARLY_CONTROL)
    sections = _apply_opening_section_beat_override(sections, chapters)

    return sections


def _apply_opening_section_beat_override(
    sections: list[StorySection],
    chapters: list[Chapter],
) -> list[StorySection]:
    """Apply section-level beat override to opening section.

    Phase 2.5: FAST_START and EARLY_CONTROL are now detected at section level
    using early-game window analysis. If detected, they override the opening
    section's beat type.

    Args:
        sections: List of sections (opening section is index 0)
        chapters: Original chapters for early window analysis

    Returns:
        Sections with opening section beat potentially overridden
    """
    if not sections or not chapters:
        return sections

    # Detect section-level beat for opening section
    override = detect_opening_section_beat(chapters)

    if override is None:
        return sections

    # Override the opening section's beat type
    opening = sections[0]
    opening.beat_type = override.beat_type

    # Store override info in notes for debugging
    # (Notes are deterministic bullets, so we add a factual note about the beat)
    if override.beat_type == BeatType.FAST_START:
        debug_info = override.debug_info
        total_pts = debug_info.get("total_points", 0)
        margin = debug_info.get("final_margin", 0)
        opening.notes.insert(
            0, f"High-scoring early window: {total_pts} points, {margin}-point margin"
        )
    elif override.beat_type == BeatType.EARLY_CONTROL:
        debug_info = override.debug_info
        leading_team = debug_info.get("leading_team", "unknown")
        margin = debug_info.get("final_margin", 0)
        share_pct = int(debug_info.get("leading_team_share", 0) * 100)
        opening.notes.insert(
            0,
            f"Early control established: {leading_team} team led by {margin}, scored {share_pct}% of points",
        )

    return sections


# ============================================================================
# DEBUG OUTPUT
# ============================================================================


def format_sections_debug(sections: list[StorySection]) -> str:
    """Format sections for debug output.

    Shows:
    - section_index
    - beat_type
    - descriptors (Phase 2.1)
    - chapters_included
    - reason for section boundaries
    """
    lines = ["Story Sections:", "=" * 60]

    for section in sections:
        line = f"Section {section.section_index}: {section.beat_type.value}"
        if section.descriptors:
            descriptors_str = ", ".join(d.value for d in section.descriptors)
            line += f" [descriptors: {descriptors_str}]"
        lines.append(line)
        lines.append(f"  Chapters: {section.chapters_included}")
        lines.append(f"  Score: {section.start_score} → {section.end_score}")
        if section.break_reason:
            lines.append(f"  Break reason: {section.break_reason.value}")
        if section.notes:
            lines.append("  Notes:")
            for note in section.notes:
                lines.append(f"    - {note}")
        lines.append("")

    return "\n".join(lines)
