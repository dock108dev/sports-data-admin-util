"""Helper functions for GROUP_BLOCKS stage.

Contains block creation, key play selection, and block count calculation.
"""

from __future__ import annotations

from typing import Any

from .block_types import (
    MAX_BLOCKS,
    MAX_KEY_PLAYS,
    MIN_BLOCKS,
    NarrativeBlock,
    SemanticRole,
)
from .box_score_helpers import compute_block_mini_box


def calculate_block_count(
    moments: list[dict[str, Any]],
    lead_changes: int,
    total_plays: int,
    is_blowout: bool = False,
) -> int:
    """Calculate optimal block count based on game intensity.

    Args:
        moments: List of validated moments
        lead_changes: Number of lead changes in the game
        total_plays: Total play count
        is_blowout: Whether the game was a blowout

    Returns:
        Block count in range [3, 7]
    """
    # Blowouts with minimal lead changes get 3 blocks
    if is_blowout and lead_changes <= 1:
        return MIN_BLOCKS  # 3

    base = 4  # Default base for non-blowout games

    # More lead changes = more dramatic game = more blocks
    if lead_changes >= 3:
        base += 1
    if lead_changes >= 6:
        base += 1

    # Longer games need more blocks
    if total_plays > 400:
        base += 1

    return min(base, MAX_BLOCKS)


def select_key_plays(
    moments: list[dict[str, Any]],
    moment_indices: list[int],
    pbp_events: list[dict[str, Any]],
) -> list[int]:
    """Select 1-3 key plays for a block.

    Priority:
    1. Lead change plays
    2. Late-game / clutch-time plays (Q4/OT/final 2 minutes)
    3. Plays ending scoring runs (8+ point run)
    4. Scoring plays (reduced weight vs lead changes)
    5. Explicitly narrated plays from moments

    Competitive window: plays in blowout margins (>15) get reduced importance.
    """
    key_plays: list[int] = []
    play_id_to_event: dict[int, dict[str, Any]] = {
        e["play_index"]: e for e in pbp_events if "play_index" in e
    }

    # Collect all plays in this block's moments
    all_play_ids: list[int] = []
    for idx in moment_indices:
        if idx < len(moments):
            all_play_ids.extend(moments[idx].get("play_ids", []))

    # Collect explicitly narrated plays
    explicit_plays: list[int] = []
    for idx in moment_indices:
        if idx < len(moments):
            explicit_plays.extend(
                moments[idx].get("explicitly_narrated_play_ids", [])
            )

    # Detect scoring runs for run-ending bonus
    run_ending_plays: set[int] = set()
    consecutive_scorer: int | None = None
    run_points = 0
    run_last_play: int | None = None
    for play_id in all_play_ids:
        event = play_id_to_event.get(play_id, {})
        play_type = event.get("play_type", "")
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        # Determine scoring team (simplified)
        if play_type and "score" in play_type.lower():
            scorer = 1 if home_score > away_score else -1
            if consecutive_scorer == scorer:
                run_points += 2  # approximate
                run_last_play = play_id
            else:
                if run_points >= 8 and run_last_play is not None:
                    run_ending_plays.add(run_last_play)
                consecutive_scorer = scorer
                run_points = 2
                run_last_play = play_id
    if run_points >= 8 and run_last_play is not None:
        run_ending_plays.add(run_last_play)

    # Score each play
    play_scores: dict[int, float] = {}
    prev_leader: int | None = None

    for play_id in all_play_ids:
        event = play_id_to_event.get(play_id, {})
        score = 0.0

        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0

        # Check for lead change
        if home_score > away_score:
            current_leader = 1
        elif away_score > home_score:
            current_leader = -1
        else:
            current_leader = 0

        if prev_leader is not None and prev_leader != 0 and current_leader != 0:
            if prev_leader != current_leader:
                score += 100  # Lead change - highest priority

        if current_leader != 0:
            prev_leader = current_leader

        # Scoring plays (reduced from +10 to +5)
        play_type = event.get("play_type", "")
        if play_type and "score" in play_type.lower():
            score += 5

        # Explicitly narrated
        if play_id in explicit_plays:
            score += 20

        # Clock context: Q4/OT plays get a bonus
        period = event.get("period", 1) or 1
        if period >= 4:
            score += 15

        # Run-ending bonus
        if play_id in run_ending_plays:
            score += 25

        # Competitive window: reduce importance in blowout margin
        margin = abs(home_score - away_score)
        if margin > 15:
            score *= 0.5

        play_scores[play_id] = score

    # Sort by score and take top 1-3
    sorted_plays = sorted(play_scores.keys(), key=lambda x: play_scores[x], reverse=True)

    # Ensure we have at least 1, at most 3
    key_plays = sorted_plays[:MAX_KEY_PLAYS]
    if not key_plays and all_play_ids:
        key_plays = [all_play_ids[-1]]  # Fallback to last play

    return key_plays[:MAX_KEY_PLAYS]


def create_blocks(
    moments: list[dict[str, Any]],
    split_points: list[int],
    pbp_events: list[dict[str, Any]],
    game_context: dict[str, str] | None = None,
    league_code: str = "NBA",
) -> list[NarrativeBlock]:
    """Create NarrativeBlock objects from moments and split points."""
    blocks: list[NarrativeBlock] = []

    # Add 0 at start and len(moments) at end for boundary handling
    boundaries = [0] + split_points + [len(moments)]

    # Extract game context for mini_box computation
    home_team = (game_context or {}).get("home_team_name", "Home")
    away_team = (game_context or {}).get("away_team_name", "Away")
    home_abbrev = (game_context or {}).get("home_team_abbrev", "")
    away_abbrev = (game_context or {}).get("away_team_abbrev", "")

    # Track previous block's last play index for delta computation
    prev_block_end_play_idx: int | None = None

    for i in range(len(boundaries) - 1):
        start_idx = boundaries[i]
        end_idx = boundaries[i + 1]

        moment_indices = list(range(start_idx, end_idx))
        if not moment_indices:
            continue

        # Collect all play_ids
        all_play_ids: list[int] = []
        for idx in moment_indices:
            all_play_ids.extend(moments[idx].get("play_ids", []))

        # Get period range
        period_start = moments[start_idx].get("period", 1)
        period_end = moments[end_idx - 1].get("period", 1)

        # Get score range
        score_before = tuple(moments[start_idx].get("score_before", [0, 0]))
        score_after = tuple(moments[end_idx - 1].get("score_after", [0, 0]))

        # Select key plays
        key_play_ids = select_key_plays(moments, moment_indices, pbp_events)

        # Compute mini box score with deltas
        block_start_play_idx = min(all_play_ids) if all_play_ids else 0
        block_end_play_idx = max(all_play_ids) if all_play_ids else 0

        mini_box = compute_block_mini_box(
            pbp_events=pbp_events,
            block_start_play_idx=block_start_play_idx,
            block_end_play_idx=block_end_play_idx,
            prev_block_end_play_idx=prev_block_end_play_idx,
            home_team=home_team,
            away_team=away_team,
            league_code=league_code,
            home_team_abbrev=home_abbrev,
            away_team_abbrev=away_abbrev,
        )

        block = NarrativeBlock(
            block_index=i,
            role=SemanticRole.RESPONSE,  # Placeholder, will be assigned later
            moment_indices=moment_indices,
            period_start=period_start,
            period_end=period_end,
            score_before=score_before,  # type: ignore
            score_after=score_after,  # type: ignore
            play_ids=all_play_ids,
            key_play_ids=key_play_ids,
            narrative=None,
            mini_box=mini_box,
        )
        blocks.append(block)

        # Update prev_block_end_play_idx for next iteration
        prev_block_end_play_idx = block_end_play_idx

    return blocks
