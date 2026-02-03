"""GROUP_BLOCKS Stage Implementation.

This stage deterministically groups validated moments into 4-7 narrative blocks.
No AI is used - block boundaries and role assignments are rule-based.

BLOCK GROUPING ALGORITHM
========================
1. Calculate target block count based on game intensity
2. Identify natural break points (lead changes, scoring runs, period boundaries)
3. Split moments into blocks using these break points
4. Assign semantic roles deterministically

BLOCK COUNT FORMULA
===================
base = 4
if lead_changes >= 3: base += 1
if lead_changes >= 6: base += 1
if total_plays > 400: base += 1
return min(base, 7)

ROLE ASSIGNMENT RULES
=====================
1. Block 0 -> SETUP (always)
2. Block N-1 -> RESOLUTION (always)
3. First lead change -> MOMENTUM_SHIFT
4. Response to lead change -> RESPONSE
5. Second-to-last block -> DECISION_POINT (if not already assigned)
6. Remaining middle blocks -> RESPONSE

CONSTRAINTS
===========
- No role appears more than twice
- SETUP always first
- RESOLUTION always last
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import StageInput, StageOutput
from .block_types import (
    NarrativeBlock,
    SemanticRole,
    MIN_BLOCKS,
    MAX_BLOCKS,
    MAX_KEY_PLAYS,
)
from .block_analysis import (
    count_lead_changes,
    find_lead_change_indices,
    find_scoring_runs,
    find_period_boundaries,
    detect_blowout,
    find_garbage_time_start,
)

# Blowout games get fewer blocks (less narrative needed)
BLOWOUT_MAX_BLOCKS = 5

logger = logging.getLogger(__name__)


def calculate_block_count(
    moments: list[dict[str, Any]],
    lead_changes: int,
    total_plays: int,
) -> int:
    """Calculate optimal block count based on game intensity.

    Args:
        moments: List of validated moments
        lead_changes: Number of lead changes in the game
        total_plays: Total play count

    Returns:
        Block count in range [4, 7]
    """
    base = MIN_BLOCKS

    # More lead changes = more dramatic game = more blocks
    if lead_changes >= 3:
        base += 1
    if lead_changes >= 6:
        base += 1

    # Longer games need more blocks
    if total_plays > 400:
        base += 1

    return min(base, MAX_BLOCKS)



def _compress_blowout_blocks(
    moments: list[dict[str, Any]],
    decisive_idx: int,
    garbage_time_idx: int | None,
) -> list[int]:
    """Generate split points for blowout games.

    Task 1.5: Blowout compression strategy:
    - 1-2 blocks before decisive moment (the interesting part)
    - 1 block for the decisive stretch
    - 1 block for everything after (compressed)

    Args:
        moments: List of validated moments
        decisive_idx: Index where game became decisive
        garbage_time_idx: Index where garbage time starts (if any)

    Returns:
        List of split point indices
    """
    n = len(moments)
    split_points: list[int] = []

    # Ensure we have at least MIN_BLOCKS
    # For blowout: [SETUP][MOMENTUM_SHIFT][RESPONSE or compress][RESOLUTION]

    if decisive_idx is None:
        decisive_idx = n // 3  # Default to 1/3 mark

    # First split: After SETUP (first ~15-20% of moments, but before decisive)
    setup_end = min(max(1, n // 6), decisive_idx - 1)
    if setup_end > 0:
        split_points.append(setup_end)

    # Second split: The decisive moment (where blowout began)
    if decisive_idx > setup_end:
        split_points.append(decisive_idx)

    # Third split: If garbage time exists, compress everything after
    if garbage_time_idx is not None and garbage_time_idx > decisive_idx:
        # Put garbage time in its own minimal block
        split_points.append(garbage_time_idx)
    else:
        # If no garbage time, split remaining ~evenly
        remaining_start = max(split_points) if split_points else 0
        remaining = n - remaining_start
        if remaining > n // 3:
            # Add one more split for DECISION_POINT
            mid_remaining = remaining_start + remaining // 2
            if mid_remaining not in split_points and mid_remaining > remaining_start:
                split_points.append(mid_remaining)

    # Ensure unique and sorted
    split_points = sorted(set(sp for sp in split_points if 0 < sp < n))

    # Ensure we have at least MIN_BLOCKS - 1 split points
    while len(split_points) < MIN_BLOCKS - 1:
        # Add evenly distributed splits between existing points
        for i in range(len(split_points) - 1):
            gap = split_points[i + 1] - split_points[i]
            if gap > 2:
                new_split = split_points[i] + gap // 2
                if new_split not in split_points:
                    split_points.append(new_split)
                    break
        else:
            # Add at end if needed
            if split_points and split_points[-1] < n - 2:
                split_points.append(split_points[-1] + (n - split_points[-1]) // 2)
            else:
                break
        split_points = sorted(set(split_points))

    return split_points[:BLOWOUT_MAX_BLOCKS - 1]  # Cap at blowout max


def _find_split_points(
    moments: list[dict[str, Any]],
    target_blocks: int,
) -> list[int]:
    """Find optimal split points for dividing moments into blocks.

    Priority for split points:
    1. Lead changes
    2. Scoring runs
    3. Period boundaries
    4. Even distribution

    Returns indices where new blocks should start.
    """
    n = len(moments)
    if n <= target_blocks:
        # Each moment is its own block
        return list(range(1, n))

    # Collect candidate split points with priorities
    lead_changes = find_lead_change_indices(moments)
    scoring_runs = find_scoring_runs(moments)
    period_boundaries = find_period_boundaries(moments)

    # Build set of all candidate points with priorities
    candidates: dict[int, int] = {}  # index -> priority (lower = better)

    for idx in lead_changes:
        if 0 < idx < n:
            candidates[idx] = 1  # Highest priority

    for start, end, _ in scoring_runs:
        if 0 < start < n:
            candidates[start] = candidates.get(start, 2)
        if 0 < end + 1 < n:
            candidates[end + 1] = candidates.get(end + 1, 2)

    for idx in period_boundaries:
        if 0 < idx < n:
            candidates[idx] = candidates.get(idx, 3)

    # We need target_blocks - 1 split points (to create target_blocks blocks)
    needed_splits = target_blocks - 1

    # Sort candidates by priority then by index
    sorted_candidates = sorted(candidates.keys(), key=lambda x: (candidates[x], x))

    # Select split points ensuring good distribution
    selected: list[int] = []

    # First, reserve positions for SETUP (first ~20% of moments) and RESOLUTION (last ~20%)
    setup_end = max(1, n // 5)
    resolution_start = n - max(1, n // 5)

    # Add split at end of setup section
    setup_split = None
    for c in sorted_candidates:
        if 1 <= c <= setup_end:
            setup_split = c
            break
    if setup_split is None:
        setup_split = setup_end
    selected.append(setup_split)

    # Add split at start of resolution section
    resolution_split = None
    for c in sorted_candidates:
        if resolution_start <= c < n:
            resolution_split = c
            break
    if resolution_split is None:
        resolution_split = resolution_start
    if resolution_split != setup_split:
        selected.append(resolution_split)

    # Fill in remaining splits from candidates
    for c in sorted_candidates:
        if len(selected) >= needed_splits:
            break
        if c not in selected:
            # Ensure minimum spacing between splits
            too_close = any(abs(c - s) < n // (target_blocks + 1) for s in selected)
            if not too_close:
                selected.append(c)

    # If we still need more splits, add evenly distributed ones
    if len(selected) < needed_splits:
        interval = n / (needed_splits + 1)
        for i in range(1, needed_splits + 1):
            split = int(i * interval)
            if split not in selected and 0 < split < n:
                selected.append(split)
            if len(selected) >= needed_splits:
                break

    # Sort and limit to needed count
    selected = sorted(set(selected))[:needed_splits]

    return selected


def _select_key_plays(
    moments: list[dict[str, Any]],
    moment_indices: list[int],
    pbp_events: list[dict[str, Any]],
) -> list[int]:
    """Select 1-3 key plays for a block.

    Priority:
    1. Lead change plays
    2. High-point scoring plays
    3. Explicitly narrated plays from moments
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

        # Scoring plays
        play_type = event.get("play_type", "")
        if play_type and "score" in play_type.lower():
            score += 10

        # Explicitly narrated
        if play_id in explicit_plays:
            score += 20

        play_scores[play_id] = score

    # Sort by score and take top 1-3
    sorted_plays = sorted(play_scores.keys(), key=lambda x: play_scores[x], reverse=True)

    # Ensure we have at least 1, at most 3
    key_plays = sorted_plays[:MAX_KEY_PLAYS]
    if not key_plays and all_play_ids:
        key_plays = [all_play_ids[-1]]  # Fallback to last play

    return key_plays[:MAX_KEY_PLAYS]


def _assign_roles(blocks: list[NarrativeBlock]) -> None:
    """Assign semantic roles to blocks in place.

    Rules:
    1. First block -> SETUP
    2. Last block -> RESOLUTION
    3. First lead change block -> MOMENTUM_SHIFT
    4. Block after lead change -> RESPONSE
    5. Second-to-last block -> DECISION_POINT (if not assigned)
    6. Remaining -> RESPONSE

    Constraint: No role > 2 occurrences
    """
    if not blocks:
        return

    n = len(blocks)

    # Reset all roles to None first - blocks may come with pre-assigned roles
    for block in blocks:
        block.role = None  # type: ignore

    role_counts: dict[SemanticRole, int] = {r: 0 for r in SemanticRole}

    def can_assign(role: SemanticRole) -> bool:
        return role_counts[role] < 2

    def assign(block: NarrativeBlock, role: SemanticRole) -> None:
        block.role = role
        role_counts[role] += 1

    # Rule 1: First block is SETUP
    assign(blocks[0], SemanticRole.SETUP)

    # Rule 2: Last block is RESOLUTION
    if n > 1:
        assign(blocks[-1], SemanticRole.RESOLUTION)

    # Find blocks with lead changes
    lead_change_block_idx: int | None = None
    for i, block in enumerate(blocks):
        if i == 0 or i == n - 1:
            continue  # Skip first/last
        score_before = block.score_before
        score_after = block.score_after

        # Check if lead changed
        leader_before = 1 if score_before[0] > score_before[1] else (
            -1 if score_before[1] > score_before[0] else 0
        )
        leader_after = 1 if score_after[0] > score_after[1] else (
            -1 if score_after[1] > score_after[0] else 0
        )

        if leader_before != 0 and leader_after != 0 and leader_before != leader_after:
            lead_change_block_idx = i
            break

    # Rule 3: First lead change block -> MOMENTUM_SHIFT
    if lead_change_block_idx is not None and can_assign(SemanticRole.MOMENTUM_SHIFT):
        assign(blocks[lead_change_block_idx], SemanticRole.MOMENTUM_SHIFT)

        # Rule 4: Block after lead change -> RESPONSE
        if (
            lead_change_block_idx + 1 < n - 1
            and blocks[lead_change_block_idx + 1].role is None
            and can_assign(SemanticRole.RESPONSE)
        ):
            assign(blocks[lead_change_block_idx + 1], SemanticRole.RESPONSE)

    # Rule 5: Second-to-last block -> DECISION_POINT
    if n > 2 and blocks[-2].role is None and can_assign(SemanticRole.DECISION_POINT):
        assign(blocks[-2], SemanticRole.DECISION_POINT)

    # Rule 6: Remaining blocks -> RESPONSE
    for block in blocks:
        if block.role is None:
            if can_assign(SemanticRole.RESPONSE):
                assign(block, SemanticRole.RESPONSE)
            elif can_assign(SemanticRole.MOMENTUM_SHIFT):
                assign(block, SemanticRole.MOMENTUM_SHIFT)
            elif can_assign(SemanticRole.DECISION_POINT):
                assign(block, SemanticRole.DECISION_POINT)
            else:
                # Fallback - should not happen with proper block counts
                block.role = SemanticRole.RESPONSE


def _create_blocks(
    moments: list[dict[str, Any]],
    split_points: list[int],
    pbp_events: list[dict[str, Any]],
) -> list[NarrativeBlock]:
    """Create NarrativeBlock objects from moments and split points."""
    blocks: list[NarrativeBlock] = []

    # Add 0 at start and len(moments) at end for boundary handling
    boundaries = [0] + split_points + [len(moments)]

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
        key_play_ids = _select_key_plays(moments, moment_indices, pbp_events)

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
        )
        blocks.append(block)

    return blocks


async def execute_group_blocks(stage_input: StageInput) -> StageOutput:
    """Execute the GROUP_BLOCKS stage.

    Groups validated moments into 4-7 narrative blocks with semantic roles.
    This is a deterministic, rule-based stage with no AI involvement.

    Args:
        stage_input: Input containing previous_output with validated moments

    Returns:
        StageOutput with blocks data

    Raises:
        ValueError: If prerequisites not met
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting GROUP_BLOCKS for game {game_id}")

    # Get input data from previous stages
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("GROUP_BLOCKS requires previous stage output")

    # Verify validation passed
    validated = previous_output.get("validated")
    if validated is not True:
        raise ValueError(
            f"GROUP_BLOCKS requires VALIDATE_MOMENTS to pass. Got validated={validated}"
        )

    # Get moments and PBP data
    moments = previous_output.get("moments")
    if not moments:
        raise ValueError("No moments in previous stage output")

    pbp_events = previous_output.get("pbp_events", [])

    output.add_log(f"Processing {len(moments)} moments")

    # Calculate game metrics
    lead_changes = count_lead_changes(moments)
    total_plays = sum(len(m.get("play_ids", [])) for m in moments)
    scoring_runs = find_scoring_runs(moments)
    largest_run = max((r[2] for r in scoring_runs), default=0)

    output.add_log(f"Game metrics: {lead_changes} lead changes, {total_plays} plays")
    output.add_log(f"Found {len(scoring_runs)} scoring runs, largest: {largest_run}")

    # Task 1.5: Check for blowout
    is_blowout, decisive_idx, max_margin = detect_blowout(moments)
    garbage_time_idx = find_garbage_time_start(moments) if is_blowout else None

    if is_blowout:
        output.add_log(
            f"BLOWOUT DETECTED: Max margin {max_margin}, decisive at moment {decisive_idx}",
            level="warning",
        )
        if garbage_time_idx is not None:
            output.add_log(
                f"Garbage time starts at moment {garbage_time_idx}",
                level="warning",
            )

        # Use blowout compression for split points
        split_points = _compress_blowout_blocks(moments, decisive_idx, garbage_time_idx)
        target_blocks = len(split_points) + 1
        output.add_log(f"Using blowout compression: {target_blocks} blocks")
    else:
        # Calculate target block count normally
        target_blocks = calculate_block_count(moments, lead_changes, total_plays)
        output.add_log(f"Target block count: {target_blocks}")

        # Find optimal split points
        split_points = _find_split_points(moments, target_blocks)

    output.add_log(f"Split points: {split_points}")

    # Create blocks
    blocks = _create_blocks(moments, split_points, pbp_events)
    output.add_log(f"Created {len(blocks)} blocks")

    # Assign semantic roles
    _assign_roles(blocks)

    # Log role assignments
    role_summary = {}
    for block in blocks:
        role_summary[block.role.value] = role_summary.get(block.role.value, 0) + 1
    output.add_log(f"Role assignments: {role_summary}")

    # Verify block count constraints
    if len(blocks) < MIN_BLOCKS:
        output.add_log(
            f"WARNING: Only {len(blocks)} blocks created (min: {MIN_BLOCKS})",
            level="warning",
        )
    elif len(blocks) > MAX_BLOCKS:
        output.add_log(
            f"WARNING: {len(blocks)} blocks created (max: {MAX_BLOCKS})",
            level="warning",
        )

    output.add_log("GROUP_BLOCKS completed successfully")

    # Build output data
    output.data = {
        "blocks_grouped": True,
        "blocks": [b.to_dict() for b in blocks],
        "block_count": len(blocks),
        "total_moments": len(moments),
        "lead_changes": lead_changes,
        "largest_run": largest_run,
        "split_points": split_points,
        # Task 1.5: Blowout metrics
        "is_blowout": is_blowout,
        "max_margin": max_margin,
        "decisive_moment_idx": decisive_idx,
        "garbage_time_start_idx": garbage_time_idx,
        # Pass through from previous stages
        "moments": moments,
        "pbp_events": pbp_events,
        "validated": True,
    }

    return output
