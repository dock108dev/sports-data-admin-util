"""
Running Stats Builder: Authoritative statistical signals for game story generation.

This module computes CUMULATIVE statistical snapshots at chapter boundaries and
SECTION-LEVEL DELTAS for use in StorySection construction.

DESIGN PRINCIPLES:
- This layer is INTERNAL, post-game only, and deterministic
- Contains NO AI logic and NO narrative decisions
- Produces signals that will later be used by a single AI call

ARCHITECTURE:
- RunningStatsSnapshot: Cumulative totals from game start → end of chapter
- SectionDelta: Difference between two snapshots (section_end - section_start)

RELATIONSHIP TO story_state.py:
- story_state.py is for AI PROMPT BUILDING (momentum hints, theme tags, top 6 global)
- running_stats.py is for AUTHORITATIVE STATISTICAL SIGNALS (fouls, timeouts, deltas)
- Both are deterministic, but serve different purposes
- This module does NOT replace story_state.py; they complement each other

ISSUE: Running Stats Builder (Chapters-First Architecture)
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from .types import Chapter, Play

# Import data structures from stat_types
from .stat_types import (
    normalize_player_key,
    PlayerSnapshot,
    TeamSnapshot,
    RunningStatsSnapshot,
    PlayerDelta,
    TeamDelta,
    SectionDelta,
)

# Import extraction functions from play_extractors
from .play_extractors import (
    extract_team_key,
    extract_player_info,
    is_made_field_goal,
    is_made_free_throw,
    is_personal_foul,
    is_technical_foul,
    is_timeout,
    is_possession_ending,
    extract_notable_action,
    is_assist,
    is_block,
    is_steal,
)

if TYPE_CHECKING:
    from .player_identity import PlayerIdentityResolver

# Re-export for backward compatibility
__all__ = [
    # Types
    "normalize_player_key",
    "PlayerSnapshot",
    "TeamSnapshot",
    "RunningStatsSnapshot",
    "PlayerDelta",
    "TeamDelta",
    "SectionDelta",
    # Extraction functions (aliased with underscore prefix for internal use)
    "_extract_team_key",
    "_extract_player_info",
    "_is_made_field_goal",
    "_is_made_free_throw",
    "_is_personal_foul",
    "_is_technical_foul",
    "_is_timeout",
    "_is_possession_ending",
    "_extract_notable_action",
    "_is_assist",
    "_is_block",
    "_is_steal",
    # Builder functions
    "build_initial_snapshot",
    "update_snapshot",
    "build_running_snapshots",
    "compute_section_delta",
    "compute_section_deltas_from_snapshots",
]

# Aliases with underscore prefix for internal/test compatibility
_extract_team_key = extract_team_key
_extract_player_info = extract_player_info
_is_made_field_goal = is_made_field_goal
_is_made_free_throw = is_made_free_throw
_is_personal_foul = is_personal_foul
_is_technical_foul = is_technical_foul
_is_timeout = is_timeout
_is_possession_ending = is_possession_ending
_extract_notable_action = extract_notable_action
_is_assist = is_assist
_is_block = is_block
_is_steal = is_steal


# ============================================================================
# SNAPSHOT BUILDING
# ============================================================================


def build_initial_snapshot() -> RunningStatsSnapshot:
    """Build initial empty snapshot (before any chapters).

    Returns:
        Empty snapshot with chapter_index=-1
    """
    return RunningStatsSnapshot(chapter_index=-1)


def _ensure_team(
    snapshot: RunningStatsSnapshot, team_key: str, team_name: str | None = None
) -> TeamSnapshot:
    """Ensure team exists in snapshot, create if needed."""
    if team_key not in snapshot.teams:
        snapshot.teams[team_key] = TeamSnapshot(
            team_key=team_key,
            team_name=team_name or team_key,
        )
    return snapshot.teams[team_key]


def _ensure_player(
    snapshot: RunningStatsSnapshot,
    player_key: str,
    player_name: str,
    player_id: str | None = None,
    team_key: str | None = None,
) -> PlayerSnapshot:
    """Ensure player exists in snapshot, create if needed."""
    if player_key not in snapshot.players:
        snapshot.players[player_key] = PlayerSnapshot(
            player_key=player_key,
            player_name=player_name,
            player_id=player_id,
            team_key=team_key,
        )
    else:
        # Update player_id if we now have it
        if player_id and not snapshot.players[player_key].player_id:
            snapshot.players[player_key].player_id = player_id
        # Update team_key if we now have it
        if team_key and not snapshot.players[player_key].team_key:
            snapshot.players[player_key].team_key = team_key
    return snapshot.players[player_key]


def _process_play(
    play: Play,
    snapshot: RunningStatsSnapshot,
    resolver: "PlayerIdentityResolver | None" = None,
) -> None:
    """Process a single play and update snapshot in place.

    This function implements all event parsing rules.
    When a resolver is provided, player names are resolved to canonical forms.

    Args:
        play: Play to process
        snapshot: Snapshot to update
        resolver: Optional PlayerIdentityResolver for name canonicalization
    """
    # Extract player info (using resolver if available)
    player_key, player_name, player_id = extract_player_info(play, resolver)
    team_key = extract_team_key(play)

    # Get team name for display
    team_name = play.raw_data.get("team_name") or play.raw_data.get("team")

    # Process scoring
    made_fg, fg_points = is_made_field_goal(play)
    if made_fg and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.points_scored_total += fg_points
        player.fg_made_total += 1
        if fg_points == 3:
            player.three_pt_made_total += 1

        # Update team score
        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.points_scored_total += fg_points

    if is_made_free_throw(play) and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.points_scored_total += 1
        player.ft_made_total += 1

        # Update team score
        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.points_scored_total += 1

    # Process fouls
    if is_personal_foul(play) and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.personal_foul_count_total += 1

        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.personal_fouls_committed_total += 1

    if is_technical_foul(play) and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.technical_foul_count_total += 1

        if team_key:
            team = _ensure_team(snapshot, team_key, team_name)
            team.technical_fouls_committed_total += 1

    # Process timeouts
    timeout_detected, timeout_team = is_timeout(play)
    if timeout_detected and timeout_team:
        team = _ensure_team(snapshot, timeout_team, team_name)
        team.timeouts_used_total += 1

    # Process possessions estimate
    if is_possession_ending(play) and team_key:
        team = _ensure_team(snapshot, team_key, team_name)
        team.possessions_estimate_total += 1

    # Process notable actions
    notable_action = extract_notable_action(play)
    if notable_action and player_key:
        player = _ensure_player(snapshot, player_key, player_name, player_id, team_key)
        player.notable_actions_set.add(notable_action)

    # Process assists (Player Prominence)
    assist_detected, assister_key, assister_name, assister_id = is_assist(play)
    if assist_detected and assister_key and assister_name:
        # Resolve assister name if resolver available
        if resolver is not None:
            resolved = resolver.resolve(assister_name, assister_id, team_key)
            if resolved:
                assister_key = resolved.canonical_key
                assister_name = resolved.canonical_name
                assister_id = resolved.player_id
        assister = _ensure_player(
            snapshot, assister_key, assister_name, assister_id, team_key
        )
        assister.assists_total += 1

    # Process blocks (Player Prominence)
    block_detected, blocker_key, blocker_name, blocker_id = is_block(play)
    if block_detected and blocker_key and blocker_name:
        # Resolve blocker name if resolver available
        if resolver is not None:
            resolved = resolver.resolve(blocker_name, blocker_id, team_key)
            if resolved:
                blocker_key = resolved.canonical_key
                blocker_name = resolved.canonical_name
                blocker_id = resolved.player_id
        blocker = _ensure_player(
            snapshot, blocker_key, blocker_name, blocker_id, team_key
        )
        blocker.blocks_total += 1

    # Process steals (Player Prominence)
    steal_detected, stealer_key, stealer_name, stealer_id = is_steal(play)
    if steal_detected and stealer_key and stealer_name:
        # Resolve stealer name if resolver available
        if resolver is not None:
            resolved = resolver.resolve(stealer_name, stealer_id, team_key)
            if resolved:
                stealer_key = resolved.canonical_key
                stealer_name = resolved.canonical_name
                stealer_id = resolved.player_id
        stealer = _ensure_player(
            snapshot, stealer_key, stealer_name, stealer_id, team_key
        )
        stealer.steals_total += 1


def update_snapshot(
    previous: RunningStatsSnapshot,
    chapter: Chapter,
    resolver: "PlayerIdentityResolver | None" = None,
) -> RunningStatsSnapshot:
    """Update snapshot with a new chapter's plays.

    This creates a NEW snapshot (immutable) by copying previous state
    and adding the chapter's data.

    Args:
        previous: Snapshot from previous chapter boundary
        chapter: New chapter to process
        resolver: Optional PlayerIdentityResolver for name canonicalization

    Returns:
        New snapshot including data from this chapter
    """
    # Deep copy previous snapshot
    new_snapshot = RunningStatsSnapshot(
        chapter_index=previous.chapter_index + 1,
        teams={k: copy.deepcopy(v) for k, v in previous.teams.items()},
        players={k: copy.deepcopy(v) for k, v in previous.players.items()},
    )

    # Deep copy the sets (they don't copy properly with copy.deepcopy on dataclass)
    for player in new_snapshot.players.values():
        player.notable_actions_set = set(player.notable_actions_set)

    # Process each play in the chapter
    for play in chapter.plays:
        _process_play(play, new_snapshot, resolver)

    return new_snapshot


def build_running_snapshots(
    chapters: list[Chapter],
    resolver: "PlayerIdentityResolver | None" = None,
) -> list[RunningStatsSnapshot]:
    """Build snapshots at every chapter boundary.

    NAME RESOLUTION:
    When a PlayerIdentityResolver is provided, all player names are resolved
    to canonical forms during stat aggregation. This prevents stat loss and
    ghost players caused by truncated or aliased names.

    Args:
        chapters: List of chapters in chronological order
        resolver: Optional PlayerIdentityResolver for name canonicalization

    Returns:
        List of snapshots, one after each chapter.
        snapshots[0] = state after chapter 0
        snapshots[N] = state after chapter N
    """
    snapshots = []
    current = build_initial_snapshot()

    for chapter in chapters:
        current = update_snapshot(current, chapter, resolver)
        snapshots.append(current)

    return snapshots


# ============================================================================
# SECTION DELTA COMPUTATION
# ============================================================================


def _compute_player_delta(
    player_key: str,
    start_player: PlayerSnapshot | None,
    end_player: PlayerSnapshot,
) -> PlayerDelta:
    """Compute player delta between two snapshots."""
    if start_player is None:
        # No prior data, delta equals end values
        delta = PlayerDelta(
            player_key=end_player.player_key,
            player_name=end_player.player_name,
            player_id=end_player.player_id,
            team_key=end_player.team_key,
            points_scored=end_player.points_scored_total,
            fg_made=end_player.fg_made_total,
            three_pt_made=end_player.three_pt_made_total,
            ft_made=end_player.ft_made_total,
            assists=end_player.assists_total,
            blocks=end_player.blocks_total,
            steals=end_player.steals_total,
            personal_foul_count=end_player.personal_foul_count_total,
            technical_foul_count=end_player.technical_foul_count_total,
            notable_actions=set(end_player.notable_actions_set),
        )
    else:
        delta = PlayerDelta(
            player_key=end_player.player_key,
            player_name=end_player.player_name,
            player_id=end_player.player_id,
            team_key=end_player.team_key,
            points_scored=end_player.points_scored_total
            - start_player.points_scored_total,
            fg_made=end_player.fg_made_total - start_player.fg_made_total,
            three_pt_made=end_player.three_pt_made_total
            - start_player.three_pt_made_total,
            ft_made=end_player.ft_made_total - start_player.ft_made_total,
            assists=end_player.assists_total - start_player.assists_total,
            blocks=end_player.blocks_total - start_player.blocks_total,
            steals=end_player.steals_total - start_player.steals_total,
            personal_foul_count=end_player.personal_foul_count_total
            - start_player.personal_foul_count_total,
            technical_foul_count=end_player.technical_foul_count_total
            - start_player.technical_foul_count_total,
            notable_actions=end_player.notable_actions_set
            - start_player.notable_actions_set,
        )

    # Set foul trouble flag
    delta.foul_trouble_flag = delta.personal_foul_count >= 4

    return delta


def _compute_team_delta(
    team_key: str,
    start_team: TeamSnapshot | None,
    end_team: TeamSnapshot,
) -> TeamDelta:
    """Compute team delta between two snapshots."""
    if start_team is None:
        return TeamDelta(
            team_key=end_team.team_key,
            team_name=end_team.team_name,
            points_scored=end_team.points_scored_total,
            personal_fouls_committed=end_team.personal_fouls_committed_total,
            technical_fouls_committed=end_team.technical_fouls_committed_total,
            timeouts_used=end_team.timeouts_used_total,
            possessions_estimate=end_team.possessions_estimate_total,
        )
    else:
        return TeamDelta(
            team_key=end_team.team_key,
            team_name=end_team.team_name,
            points_scored=end_team.points_scored_total - start_team.points_scored_total,
            personal_fouls_committed=end_team.personal_fouls_committed_total
            - start_team.personal_fouls_committed_total,
            technical_fouls_committed=end_team.technical_fouls_committed_total
            - start_team.technical_fouls_committed_total,
            timeouts_used=end_team.timeouts_used_total - start_team.timeouts_used_total,
            possessions_estimate=end_team.possessions_estimate_total
            - start_team.possessions_estimate_total,
        )


def _player_sort_key(delta: PlayerDelta) -> tuple:
    """Sort key for player bounding.

    PLAYER BOUNDING TIE-BREAKERS (in order):
    1. points_scored (descending)
    2. fg_made (descending)
    3. three_pt_made (descending)
    4. player_key (ascending, for determinism)
    """
    return (
        -delta.points_scored,
        -delta.fg_made,
        -delta.three_pt_made,
        delta.player_key,  # Ascending for determinism
    )


def compute_section_delta(
    start_snapshot: RunningStatsSnapshot | None,
    end_snapshot: RunningStatsSnapshot,
    section_start_chapter: int,
    section_end_chapter: int,
    players_per_team: int = 3,
) -> SectionDelta:
    """Compute section delta between two snapshots.

    PLAYER BOUNDING:
    - Include ONLY the top N players per team by points_scored (section delta)
    - Tie-breakers: fg_made, three_pt_made, player_key

    Args:
        start_snapshot: Snapshot at section start (None for initial)
        end_snapshot: Snapshot at section end
        section_start_chapter: First chapter in section (inclusive)
        section_end_chapter: Last chapter in section (inclusive)
        players_per_team: Number of top players per team to include (default: 3)

    Returns:
        SectionDelta with bounded player list
    """
    # Compute team deltas
    team_deltas: dict[str, TeamDelta] = {}
    for team_key, end_team in end_snapshot.teams.items():
        start_team = start_snapshot.teams.get(team_key) if start_snapshot else None
        team_deltas[team_key] = _compute_team_delta(team_key, start_team, end_team)

    # Compute all player deltas
    all_player_deltas: dict[str, PlayerDelta] = {}
    for player_key, end_player in end_snapshot.players.items():
        start_player = (
            start_snapshot.players.get(player_key) if start_snapshot else None
        )
        all_player_deltas[player_key] = _compute_player_delta(
            player_key, start_player, end_player
        )

    # Group players by team
    players_by_team: dict[str, list[PlayerDelta]] = {}
    unaffiliated_players: list[PlayerDelta] = []

    for delta in all_player_deltas.values():
        if delta.team_key:
            if delta.team_key not in players_by_team:
                players_by_team[delta.team_key] = []
            players_by_team[delta.team_key].append(delta)
        else:
            unaffiliated_players.append(delta)

    # Select top N per team
    bounded_players: dict[str, PlayerDelta] = {}

    for team_key, team_players in players_by_team.items():
        # Sort by bounding criteria
        sorted_players = sorted(team_players, key=_player_sort_key)
        # Take top N
        for player in sorted_players[:players_per_team]:
            bounded_players[player.player_key] = player

    # Handle unaffiliated players (take top N overall if any)
    if unaffiliated_players:
        sorted_unaffiliated = sorted(unaffiliated_players, key=_player_sort_key)
        for player in sorted_unaffiliated[:players_per_team]:
            bounded_players[player.player_key] = player

    return SectionDelta(
        section_start_chapter=section_start_chapter,
        section_end_chapter=section_end_chapter,
        teams=team_deltas,
        players=bounded_players,
    )


def compute_section_deltas_from_snapshots(
    snapshots: list[RunningStatsSnapshot],
    section_boundaries: list[int] | None = None,
    players_per_team: int = 3,
) -> list[SectionDelta]:
    """Compute section deltas from a list of snapshots.

    If section_boundaries is not provided, each chapter becomes its own section.

    Args:
        snapshots: List of snapshots (one per chapter)
        section_boundaries: List of chapter indices where sections end.
                           If None, each chapter is its own section.
        players_per_team: Number of top players per team to include

    Returns:
        List of SectionDelta objects
    """
    if not snapshots:
        return []

    # Default: each chapter is its own section
    if section_boundaries is None:
        section_boundaries = list(range(len(snapshots)))

    deltas = []
    prev_boundary = -1
    prev_snapshot: RunningStatsSnapshot | None = None

    for boundary in section_boundaries:
        if boundary >= len(snapshots):
            break

        end_snapshot = snapshots[boundary]
        delta = compute_section_delta(
            start_snapshot=prev_snapshot,
            end_snapshot=end_snapshot,
            section_start_chapter=prev_boundary + 1,
            section_end_chapter=boundary,
            players_per_team=players_per_team,
        )
        deltas.append(delta)

        prev_boundary = boundary
        prev_snapshot = end_snapshot

    return deltas


# ============================================================================
# KNOWN LIMITATIONS (BY DESIGN)
# ============================================================================

"""
KNOWN LIMITATIONS (Documented as Required):

1. PLAYER IDENTIFICATION:
   - Uses player_name as primary key because player_id is not reliably available
   - Name normalization may incorrectly merge players with same name on different teams
   - This is mitigated by also tracking team_key per player

2. SCORING ACCURACY:
   - Relies on "makes" appearing in play descriptions
   - 3PT detection relies on "3-pt", "three", "3-pointer" patterns
   - May miss scoring if play description format changes

3. FOUL TRACKING:
   - Personal vs technical distinction relies on "technical" keyword
   - Flagrant fouls counted as personal (they do affect foul limits)
   - Ejection tracking not implemented

4. TIMEOUT ATTRIBUTION:
   - Ignores official/media timeouts (cannot attribute to team)
   - Team attribution relies on play data having team info

5. POSSESSIONS ESTIMATE:
   - Very rough approximation (made FG + turnover + defensive rebound)
   - NOT a true possession count
   - Intended only for pace description, not advanced metrics

6. NOTABLE ACTIONS:
   - Only extracts: block, steal, dunk
   - No inference, no synonyms
   - May miss actions if keyword not in description

7. TEAM SCORE TRACKING:
   - Computed from individual plays, not from scoreboard
   - May diverge from actual score if plays are missing

These limitations are intentional design choices to maintain determinism
and avoid inference/guessing. The AI layer can address ambiguities later.
"""
