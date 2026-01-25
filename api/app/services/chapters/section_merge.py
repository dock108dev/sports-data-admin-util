"""
Section Merge Operations: Merging, thin/lumpy handling, and count enforcement.

This module handles:
- Beat-aware merge rules (which beats can be merged)
- Section merging operations
- Thin section handling (always merge, never drop)
- Lumpy section / dominance capping
- Underpowered section handling
- Section count enforcement (0-10 sections)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .beat_types import BeatType
from .section_types import (
    StorySection,
    TeamStatDelta,
    PlayerStatDelta,
)
from .section_signal import (
    get_section_total_points,
    is_section_thin,
    is_section_lumpy,
    is_section_underpowered,
    get_dominant_player_share,
    DOMINANCE_CAP_PCT,
)

if TYPE_CHECKING:
    from .types import Chapter


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
# PROTECTED SECTION DETECTION
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


# ============================================================================
# NOTES GENERATION (for merged sections)
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
                f"Teams matched scoring {high_team.points_scored}–{low_team.points_scored}"
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
# SECTION MERGE OPERATION
# ============================================================================


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


# ============================================================================
# THIN SECTION HANDLING
# ============================================================================


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
    chapters: list["Chapter"],
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
                merged = _merge_sections(result[thin_idx], result[target_idx], thin_idx)
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
# LUMPY SECTION / DOMINANCE CAPPING
# ============================================================================


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
            target_section.player_stat_deltas[
                dominant_key
            ].points_scored += excess_points
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
# UNDERPOWERED SECTION HANDLING
# ============================================================================


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
    chapters: list["Chapter"],
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


# ============================================================================
# SECTION COUNT ENFORCEMENT
# ============================================================================


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
        min_sections: Minimum section count (default: 0)
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
