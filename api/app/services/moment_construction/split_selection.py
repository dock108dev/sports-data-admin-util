"""Split point selection.

Selects optimal split points from candidates based on constraints
and narrative quality.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .config import SplitConfig, DEFAULT_SPLIT_CONFIG
from .split_types import SplitPoint

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


def select_best_split_points(
    split_points: list[SplitPoint],
    moment: "Moment",
    config: SplitConfig = DEFAULT_SPLIT_CONFIG,
) -> list[SplitPoint]:
    """Select the best split points respecting constraints.

    Selection strategy:
    1. For large mega-moments (80+ plays), aim for balanced segment sizes
    2. Prioritize by split reason (tier_change > quarter > run_start > etc.)
    3. Enforce minimum segment sizes and gaps between splits

    Args:
        split_points: All candidate split points
        moment: The mega-moment being split
        config: Split configuration

    Returns:
        Selected split points, sorted by play index
    """
    if not split_points:
        return []

    is_large_mega = moment.play_count >= config.large_mega_threshold

    # For large mega-moments, determine ideal split locations
    ideal_splits: list[int] = []
    if is_large_mega:
        ideal_splits = compute_ideal_split_locations(moment, config)

    # Sort candidates by priority (stored in SplitPoint.priority)
    sorted_points = sorted(
        split_points,
        key=lambda sp: (sp.priority, sp.play_index),
    )

    selected: list[SplitPoint] = []
    last_split_idx = moment.start_play

    for sp in sorted_points:
        if len(selected) >= config.max_splits_per_moment:
            break

        # Enforce minimum gap from last split
        if sp.play_index - last_split_idx < config.min_plays_between_splits:
            continue

        # Enforce minimum remaining segment size
        if moment.end_play - sp.play_index < config.min_segment_plays:
            continue

        # For large mega-moments, prefer points near ideal locations
        if is_large_mega and ideal_splits:
            if not is_near_ideal_location(sp.play_index, ideal_splits, config):
                # Skip unless this is a high-priority point
                if sp.priority > config.priority_quarter:
                    continue

        selected.append(sp)
        last_split_idx = sp.play_index

    # If we didn't find enough splits for a large mega-moment,
    # try again with relaxed ideal location requirement
    if is_large_mega and len(selected) < min(2, config.max_splits_per_moment):
        selected = select_fallback_splits(split_points, moment, config, selected)

    result = sorted(selected, key=lambda sp: sp.play_index)

    logger.debug(
        "split_points_selected",
        extra={
            "moment_id": moment.id,
            "is_large_mega": is_large_mega,
            "candidates": len(split_points),
            "selected": len(result),
            "selected_reasons": [sp.split_reason for sp in result],
        },
    )

    return result


def compute_ideal_split_locations(
    moment: "Moment",
    config: SplitConfig,
) -> list[int]:
    """Compute ideal split locations for balanced segments.

    For a large mega-moment, we want segments of roughly equal size,
    targeting the configured target_segment_plays.

    Args:
        moment: The mega-moment being split
        config: Split configuration

    Returns:
        List of ideal play indices for splits
    """
    play_count = moment.play_count

    # Determine how many segments we want
    if play_count >= config.target_segment_plays * 3:
        # Want 3 segments (2 splits)
        num_splits = 2
    else:
        # Want 2 segments (1 split)
        num_splits = 1

    # Compute ideal locations (evenly spaced)
    ideal_locations: list[int] = []
    segment_size = play_count // (num_splits + 1)

    for i in range(1, num_splits + 1):
        ideal_idx = moment.start_play + (segment_size * i)
        ideal_locations.append(ideal_idx)

    return ideal_locations


def is_near_ideal_location(
    play_index: int,
    ideal_locations: list[int],
    config: SplitConfig,
) -> bool:
    """Check if a play index is near an ideal split location.

    "Near" means within half the minimum segment size.
    """
    tolerance = config.min_segment_plays // 2

    for ideal in ideal_locations:
        if abs(play_index - ideal) <= tolerance:
            return True

    return False


def select_fallback_splits(
    split_points: list[SplitPoint],
    moment: "Moment",
    config: SplitConfig,
    already_selected: list[SplitPoint],
) -> list[SplitPoint]:
    """Fallback selection for large mega-moments without ideal splits.

    When we don't find splits near ideal locations, try to select
    any valid splits that create reasonably balanced segments.
    """
    already_indices = {sp.play_index for sp in already_selected}

    # Sort by how close to ideal segment boundaries
    ideal_locations = compute_ideal_split_locations(moment, config)

    def distance_to_ideal(sp: SplitPoint) -> int:
        if not ideal_locations:
            return 0
        return min(abs(sp.play_index - ideal) for ideal in ideal_locations)

    # Sort by distance to ideal (closest first), then by priority
    sorted_points = sorted(
        [sp for sp in split_points if sp.play_index not in already_indices],
        key=lambda sp: (distance_to_ideal(sp), sp.priority),
    )

    selected = list(already_selected)
    last_split_idx = moment.start_play

    # Update last_split_idx based on already selected
    if already_selected:
        sorted_already = sorted(already_selected, key=lambda sp: sp.play_index)
        last_split_idx = sorted_already[-1].play_index

    for sp in sorted_points:
        if len(selected) >= config.max_splits_per_moment:
            break

        if sp.play_index - last_split_idx < config.min_plays_between_splits:
            continue

        if moment.end_play - sp.play_index < config.min_segment_plays:
            continue

        selected.append(sp)
        last_split_idx = sp.play_index

    return selected
