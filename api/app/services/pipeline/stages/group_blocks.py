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

from ..models import StageInput, StageOutput
from .block_types import MIN_BLOCKS, MAX_BLOCKS
from .block_analysis import (
    count_lead_changes,
    find_scoring_runs,
    detect_blowout,
    find_garbage_time_start,
)

# Import from split modules
from .group_split_points import (
    compress_blowout_blocks,
    find_split_points,
    find_weighted_split_points,
)
from .group_roles import assign_roles
from .group_helpers import calculate_block_count, create_blocks

logger = logging.getLogger(__name__)


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

    # Check for blowout
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
        split_points = compress_blowout_blocks(moments, decisive_idx, garbage_time_idx)
        target_blocks = len(split_points) + 1
        output.add_log(f"Using blowout compression: {target_blocks} blocks")
    else:
        # Calculate target block count normally
        target_blocks = calculate_block_count(moments, lead_changes, total_plays)
        output.add_log(f"Target block count: {target_blocks}")

        # Find optimal split points - use drama weights if available from ANALYZE_DRAMA
        quarter_weights = previous_output.get("quarter_weights")
        league_code = stage_input.game_context.get("sport", "NBA")
        if quarter_weights:
            output.add_log(f"Using drama-weighted block distribution: {quarter_weights}")
            split_points = find_weighted_split_points(
                moments, target_blocks, quarter_weights, league_code
            )
        else:
            split_points = find_split_points(moments, target_blocks)

    output.add_log(f"Split points: {split_points}")

    # Create blocks with mini boxscores
    game_context = stage_input.game_context
    league_code = game_context.get("sport", "NBA") if game_context else "NBA"
    blocks = create_blocks(
        moments, split_points, pbp_events, game_context, league_code
    )
    output.add_log(f"Created {len(blocks)} blocks with mini boxscores")

    # Assign semantic roles
    assign_roles(blocks)

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
        # Blowout metrics
        "is_blowout": is_blowout,
        "max_margin": max_margin,
        "decisive_moment_idx": decisive_idx,
        "garbage_time_start_idx": garbage_time_idx,
        # Drama analysis passthrough from ANALYZE_DRAMA
        "quarter_weights": previous_output.get("quarter_weights"),
        "peak_quarter": previous_output.get("peak_quarter"),
        "story_type": previous_output.get("story_type"),
        "headline": previous_output.get("headline"),
        # Pass through from previous stages
        "moments": moments,
        "pbp_events": pbp_events,
        "validated": True,
    }

    return output
