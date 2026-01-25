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

See section_merge.py for merge rules and section_signal.py for signal thresholds.
"""

from __future__ import annotations

from .types import Chapter, Play
from .beat_types import BeatType, BeatDescriptor, BEAT_PRIORITY
from .beat_classifier import BeatClassification, detect_opening_section_beat
from .running_stats import SectionDelta, RunningStatsSnapshot, PlayerDelta

# Import types from section_types
from .section_types import (
    ForcedBreakReason,
    TeamStatDelta,
    PlayerStatDelta,
    StorySection,
    ChapterMetadata,
)

# Import player prominence functions
from .player_prominence import (
    PlayerProminence,
    compute_player_prominence,
    select_prominent_players,
)

# Import signal evaluation functions and constants
from .section_signal import (
    SECTION_MIN_POINTS_THRESHOLD,
    SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD,
    THIN_SECTION_MAX_POINTS,
    THIN_SECTION_MAX_SCORING_PLAYS,
    LUMPY_DOMINANCE_THRESHOLD_PCT,
    DOMINANCE_CAP_PCT,
    count_meaningful_events,
    get_section_total_points,
    is_section_underpowered,
    count_section_scoring_plays,
    is_section_thin,
    get_dominant_player_share,
    is_section_lumpy,
)

# Import merge operations and constants
from .section_merge import (
    INCOMPATIBLE_BEAT_PAIRS,
    CRUNCH_TIER_BEATS,
    NON_CRUNCH_BEATS,
    are_beats_compatible_for_merge,
    generate_section_notes,
    handle_thin_sections,
    apply_dominance_cap,
    handle_underpowered_sections,
    enforce_section_count,
    _is_protected_section,  # Re-export for tests
)

# Re-exports for backward compatibility (used by __init__.py and tests)
__all__ = [
    # Types
    "StorySection",
    "TeamStatDelta",
    "PlayerStatDelta",
    "ChapterMetadata",
    "ForcedBreakReason",
    # Player prominence
    "PlayerProminence",
    "compute_player_prominence",
    "select_prominent_players",
    # Signal threshold constants
    "SECTION_MIN_POINTS_THRESHOLD",
    "SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD",
    # Thin section constants
    "THIN_SECTION_MAX_POINTS",
    "THIN_SECTION_MAX_SCORING_PLAYS",
    # Lumpy section constants
    "LUMPY_DOMINANCE_THRESHOLD_PCT",
    "DOMINANCE_CAP_PCT",
    # Beat compatibility
    "INCOMPATIBLE_BEAT_PAIRS",
    "CRUNCH_TIER_BEATS",
    "NON_CRUNCH_BEATS",
    "are_beats_compatible_for_merge",
    # Signal evaluation
    "count_meaningful_events",
    "get_section_total_points",
    "is_section_underpowered",
    "handle_underpowered_sections",
    # Thin section functions
    "count_section_scoring_plays",
    "is_section_thin",
    "handle_thin_sections",
    # Lumpy section functions
    "get_dominant_player_share",
    "is_section_lumpy",
    "apply_dominance_cap",
    # Core functions
    "detect_forced_break",
    "build_story_sections",
    "enforce_section_count",
    "generate_section_notes",
    "format_sections_debug",
    # Internal for tests
    "_is_final_2_minutes_entry",
    "_is_protected_section",
]


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
# SECTION CONSTRUCTION
# ============================================================================


def _find_play_with_score(plays: list[Play], reverse: bool = False) -> tuple[int, int] | None:
    """Find the first/last play with valid scores.

    Some plays (like "End of Quarter") may not have scores attached.
    This function searches for a play that has valid (non-None) scores.

    Args:
        plays: List of Play objects to search
        reverse: If True, search from end to start (for end scores)

    Returns:
        Tuple of (home_score, away_score) or None if no valid scores found
    """
    play_list = reversed(plays) if reverse else plays
    for play in play_list:
        home_score = play.raw_data.get("home_score")
        away_score = play.raw_data.get("away_score")
        # Both scores must be present and valid (not None)
        if home_score is not None and away_score is not None:
            return (home_score, away_score)
    return None


def _extract_chapter_metadata(
    chapter: Chapter,
    classification: BeatClassification,
) -> ChapterMetadata:
    """Extract metadata needed for section construction."""
    # Extract start period from first play
    start_period = None
    if chapter.plays:
        start_period = chapter.plays[0].raw_data.get("quarter")

    # Extract end period from last play (used for overtime check)
    # Always derive from last play to handle chapters that span quarter boundaries
    end_period = None
    if chapter.plays:
        end_period = chapter.plays[-1].raw_data.get("quarter")
    # Fallback to chapter.period if no plays (shouldn't happen in practice)
    if end_period is None:
        end_period = chapter.period

    is_overtime = end_period is not None and end_period > 4

    # Extract time remaining from first play (start time)
    start_time_remaining_seconds = None
    if chapter.plays:
        first_play = chapter.plays[0]
        clock_str = first_play.raw_data.get("game_clock")
        if clock_str and ":" in clock_str:
            try:
                parts = clock_str.split(":")
                start_time_remaining_seconds = int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                # Malformed clock string (e.g., "12:XX") - leave as None
                # Time context is optional; missing it won't break rendering
                pass

    # Extract time remaining from last play (end time)
    time_remaining_seconds = None
    if chapter.plays:
        last_play = chapter.plays[-1]
        clock_str = last_play.raw_data.get("game_clock")
        if clock_str and ":" in clock_str:
            try:
                parts = clock_str.split(":")
                time_remaining_seconds = int(parts[0]) * 60 + int(parts[1])
            except (ValueError, IndexError):
                # Malformed clock string - leave as None (time context is optional)
                pass

    # Extract scores - find plays with valid scores
    # Some plays (like "End of Quarter") may not have scores, so we search
    # for the first play with a score (for start) and last play with a score (for end)
    start_home = 0
    start_away = 0
    end_home = 0
    end_away = 0

    if chapter.plays:
        # Find first play with valid scores for start
        start_scores = _find_play_with_score(chapter.plays, reverse=False)
        if start_scores:
            start_home, start_away = start_scores

        # Find last play with valid scores for end
        end_scores = _find_play_with_score(chapter.plays, reverse=True)
        if end_scores:
            end_home, end_away = end_scores

    return ChapterMetadata(
        chapter_id=chapter.chapter_id,
        chapter_index=classification.debug_info.get("chapter_index", 0),
        beat_type=classification.beat_type,
        period=end_period,  # End period (for overtime check and legacy compatibility)
        time_remaining_seconds=time_remaining_seconds,
        is_overtime=is_overtime,
        start_home_score=start_home,
        start_away_score=start_away,
        end_home_score=end_home,
        end_away_score=end_away,
        descriptors=classification.descriptors or set(),  # Phase 2.1
        start_time_remaining_seconds=start_time_remaining_seconds,
        start_period=start_period,
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

    # Get time context from first and last chapters
    start_period = chapters_meta[0].start_period or chapters_meta[0].period
    start_time_remaining = chapters_meta[0].start_time_remaining_seconds
    end_period = chapters_meta[-1].period
    end_time_remaining = chapters_meta[-1].time_remaining_seconds

    # Aggregate stats with prominence-based player selection
    team_deltas, player_deltas = _aggregate_section_deltas(section_deltas, end_snapshot)

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
        start_period=start_period,
        end_period=end_period,
        start_time_remaining=start_time_remaining,
        end_time_remaining=end_time_remaining,
        break_reason=break_reason,
    )


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

    # Store qualitative texture note for opening paragraph
    # (Notes should guide AI toward scene-setting, not stat-citing)
    if override.beat_type == BeatType.FAST_START:
        debug_info = override.debug_info
        margin = debug_info.get("final_margin", 0)
        if margin <= 3:
            opening.notes.insert(0, "Uptempo action with neither side pulling away")
        else:
            opening.notes.insert(0, "Quick scoring with one side gaining an early edge")
    elif override.beat_type == BeatType.EARLY_CONTROL:
        debug_info = override.debug_info
        leading_team = debug_info.get("leading_team", "unknown")
        opening.notes.insert(
            0, f"The {leading_team} team began asserting itself early"
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
