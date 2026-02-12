"""Split point algorithms for GROUP_BLOCKS stage.

Contains functions for finding optimal split points to divide moments into blocks:
- Regular split point detection based on lead changes, scoring runs, and periods
- Drama-weighted split point distribution (back-loaded allocation)
- Blowout game compression
"""

from __future__ import annotations

import logging
import math
from typing import Any

from .block_types import MIN_BLOCKS
from .block_analysis import (
    find_lead_change_indices,
    find_scoring_runs,
    find_period_boundaries,
)

# Blowout games get fewer blocks (less narrative needed)
BLOWOUT_MAX_BLOCKS = 5

logger = logging.getLogger(__name__)


def compress_blowout_blocks(
    moments: list[dict[str, Any]],
    decisive_idx: int,
    garbage_time_idx: int | None,
) -> list[int]:
    """Generate split points for blowout games.

    Blowout compression strategy:
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


def find_split_points(
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


def find_weighted_split_points(
    moments: list[dict[str, Any]],
    target_blocks: int,
    quarter_weights: dict[str, float],
    league_code: str = "NBA",
) -> list[int]:
    """Drama-first block distribution with back-loaded allocation.

    INVARIANTS (non-negotiable):
    1. Drama Monotonicity: No lower-weight quarter gets more blocks than higher-weight
    2. Back-Loaded Allocation: Rounding/deficit fills favor later quarters, never earlier
    3. Q1 Compression: Q1 gets max 1 block (SETUP) unless it's the peak quarter
    4. Allocation Before Positioning: Decide blocks/quarter THEN place splits locally

    Architecture:
    - Allocate blocks per quarter using floor() + back-biased deficit fill
    - Place splits WITHIN each quarter locally (not globally)
    - No even-spacing fallback that favors moment density

    Args:
        moments: List of validated moments
        target_blocks: Target number of blocks
        quarter_weights: Dict like {"Q1": 1.0, "Q2": 0.8, "Q3": 1.5, "Q4": 2.0}
        league_code: Sport code (NBA, NHL, NCAAB)

    Returns:
        List of split point indices
    """
    n = len(moments)
    if n <= target_blocks:
        return list(range(1, n))

    # =========================================================================
    # STEP 1: Group moments by quarter
    # =========================================================================
    quarter_moments: dict[str, list[int]] = {}
    for i, moment in enumerate(moments):
        period = moment.get("period", 1)
        q_key = f"Q{period}" if period <= 4 else f"OT{period - 4}"
        quarter_moments.setdefault(q_key, []).append(i)

    sorted_quarters = sorted(quarter_moments.keys())

    # Quarter index for back-bias tiebreaker (Q4=4 > Q3=3 > Q2=2 > Q1=1)
    quarter_index = {q: i for i, q in enumerate(sorted_quarters)}

    # =========================================================================
    # STEP 2: Apply late-game amplifier BEFORE any allocation
    # =========================================================================
    amplified_weights = _apply_league_amplifiers(quarter_weights, sorted_quarters, league_code)

    logger.info(f"League: {league_code}, Raw weights: {quarter_weights}")
    logger.info(f"Amplified weights: {amplified_weights}")

    # Use amplified weights for all subsequent calculations
    quarter_weights = amplified_weights

    # Find peak quarter and median weight (using amplified weights)
    peak_quarter = max(sorted_quarters, key=lambda q: quarter_weights.get(q, 1.0))
    peak_weight = quarter_weights.get(peak_quarter, 1.0)
    weights_list = [quarter_weights.get(q, 1.0) for q in sorted_quarters]

    logger.info(
        f"Peak quarter: {peak_quarter} (weight={peak_weight})"
    )

    # =========================================================================
    # STEP 3: Allocate blocks per quarter using floor() + deficit backfill
    # =========================================================================
    quarter_blocks, fill_order = _allocate_blocks_per_quarter(
        sorted_quarters, quarter_weights, quarter_index, target_blocks
    )

    logger.info(f"After deficit backfill: {quarter_blocks}")

    # =========================================================================
    # STEP 4: Enforce Q1 hard cap (INVARIANT 3)
    # =========================================================================
    _enforce_q1_cap(quarter_blocks, quarter_weights, weights_list, peak_weight, fill_order)

    # Ensure every quarter with moments gets at least 1 block
    for q in sorted_quarters:
        if quarter_moments.get(q) and quarter_blocks.get(q, 0) == 0:
            quarter_blocks[q] = 1

    # Ensure peak quarter gets at least 2 blocks if we have enough total
    if quarter_blocks.get(peak_quarter, 0) < 2 and target_blocks >= 4:
        # Steal from lowest-weight quarter (that isn't peak and has >1)
        for q in reversed(fill_order):  # Lowest weight first
            if q != peak_quarter and quarter_blocks.get(q, 0) > 1:
                quarter_blocks[q] -= 1
                quarter_blocks[peak_quarter] = quarter_blocks.get(peak_quarter, 0) + 1
                break

    logger.info(f"Final quarter allocation: {quarter_blocks}")

    # Verify allocation matches target (sanity check)
    total_allocated = sum(quarter_blocks.values())
    if total_allocated != target_blocks:
        logger.warning(
            f"Allocation mismatch: allocated={total_allocated}, "
            f"target={target_blocks}. Adjusting peak quarter."
        )
        diff = target_blocks - total_allocated
        quarter_blocks[peak_quarter] = max(1, quarter_blocks.get(peak_quarter, 0) + diff)

    # =========================================================================
    # STEP 5: Place splits WITHIN each quarter locally
    # =========================================================================
    split_points = _place_splits_within_quarters(
        sorted_quarters, quarter_moments, quarter_blocks, n
    )

    needed_splits = target_blocks - 1

    # =========================================================================
    # STEP 6: Trim excess splits (remove from lowest-drama quarters first)
    # =========================================================================
    split_points = _trim_excess_splits(
        split_points, needed_splits, quarter_moments, quarter_weights, quarter_index
    )

    # =========================================================================
    # STEP 7: Add missing splits in high-drama quarters (back-biased)
    # =========================================================================
    if len(split_points) < needed_splits:
        split_points = _add_missing_splits(
            split_points, needed_splits, fill_order, quarter_moments, n
        )

    # Final assertion: allocation should be complete
    if len(split_points) < needed_splits:
        logger.error(
            f"CRITICAL: Could not generate enough splits. "
            f"Have {len(split_points)}, need {needed_splits}. "
            f"This indicates a logic error."
        )

    result = sorted(split_points)[:needed_splits]
    logger.info(f"Final split points: {result}")
    return result


def _apply_league_amplifiers(
    quarter_weights: dict[str, float],
    sorted_quarters: list[str],
    league_code: str,
) -> dict[str, float]:
    """Apply sport-specific late-game amplifiers to weights."""
    amplified_weights: dict[str, float] = {}

    if league_code == "NCAAB":
        # NCAAB uses halves (H1, H2 internally stored as Q1, Q2)
        for q in sorted_quarters:
            base_weight = quarter_weights.get(q, 1.0)
            if q == "Q2":  # H2 = late game, boost like Q3+Q4 combined
                amplified_weights[q] = base_weight * 1.6
            elif q == "Q1":  # H1 = early game, suppress
                amplified_weights[q] = base_weight * 0.7
            elif q.startswith("OT"):  # Overtime is always dramatic
                amplified_weights[q] = base_weight * 1.8
            else:
                amplified_weights[q] = base_weight
    elif league_code == "NHL":
        # NHL uses 3 periods (P1, P2, P3 internally as Q1, Q2, Q3)
        for q in sorted_quarters:
            base_weight = quarter_weights.get(q, 1.0)
            if q == "Q3":  # P3 = late game
                amplified_weights[q] = base_weight * 1.5
            elif q == "Q2":  # P2 = middle
                amplified_weights[q] = base_weight * 1.1
            elif q == "Q1":  # P1 = early
                amplified_weights[q] = base_weight * 0.8
            elif q.startswith("OT"):
                amplified_weights[q] = base_weight * 1.8
            else:
                amplified_weights[q] = base_weight
    else:
        # NBA (default): 4 quarters
        for q in sorted_quarters:
            base_weight = quarter_weights.get(q, 1.0)
            if q == "Q4" or q.startswith("OT"):
                amplified_weights[q] = base_weight * 1.6  # Strong late-game boost
            elif q == "Q3":
                amplified_weights[q] = base_weight * 1.4  # Moderate boost
            elif q == "Q1":
                amplified_weights[q] = base_weight * 0.8  # Suppress early game
            else:
                amplified_weights[q] = base_weight

    return amplified_weights


def _allocate_blocks_per_quarter(
    sorted_quarters: list[str],
    quarter_weights: dict[str, float],
    quarter_index: dict[str, int],
    available_blocks: int,
) -> tuple[dict[str, int], list[str]]:
    """Allocate blocks per quarter using floor() + deficit backfill."""
    # Use weight^2 for amplification
    total_weight_sq = sum(quarter_weights.get(q, 1.0) ** 2 for q in sorted_quarters)
    if total_weight_sq == 0:
        total_weight_sq = len(sorted_quarters)

    quarter_blocks: dict[str, int] = {}
    remainders: dict[str, float] = {}

    for q_key in sorted_quarters:
        weight = quarter_weights.get(q_key, 1.0)
        raw = (weight**2 / total_weight_sq) * available_blocks
        quarter_blocks[q_key] = math.floor(raw)
        remainders[q_key] = raw - math.floor(raw)

    # Calculate deficit
    allocated = sum(quarter_blocks.values())
    deficit = available_blocks - allocated

    logger.info(
        f"Initial allocation (floor): {quarter_blocks}, deficit={deficit}"
    )

    # Q1 exclusion: Q1 only eligible for backfill if it's THE peak quarter
    q1_eligible_for_backfill = (
        "Q1" in sorted_quarters and
        quarter_weights.get("Q1", 0) == max(quarter_weights.get(q, 0) for q in sorted_quarters)
    )

    fill_order = sorted(
        [q for q in sorted_quarters if q != "Q1" or q1_eligible_for_backfill],
        key=lambda q: (quarter_weights.get(q, 1.0), quarter_index[q]),
        reverse=True,
    )

    logger.info(f"Fill order (Q1 eligible={q1_eligible_for_backfill}): {fill_order}")

    for q in fill_order:
        if deficit <= 0:
            break
        quarter_blocks[q] += 1
        deficit -= 1

    return quarter_blocks, fill_order


def _enforce_q1_cap(
    quarter_blocks: dict[str, int],
    quarter_weights: dict[str, float],
    weights_list: list[float],
    peak_weight: float,
    fill_order: list[str],
) -> None:
    """Enforce Q1 hard cap - max 1 block unless exceptional drama."""
    q1_weight = quarter_weights.get("Q1", 1.0)
    # Q1 is only "dramatic" if it's in the top 25% of weights AFTER amplification
    weight_75th = sorted(weights_list)[int(len(weights_list) * 0.75)] if len(weights_list) >= 4 else peak_weight
    q1_is_dramatic = q1_weight >= weight_75th

    logger.info(
        f"Q1 drama check: q1_weight={q1_weight}, 75th_percentile={weight_75th}, "
        f"q1_is_dramatic={q1_is_dramatic}"
    )

    if "Q1" in quarter_blocks and quarter_blocks["Q1"] > 1 and not q1_is_dramatic:
        overflow = quarter_blocks["Q1"] - 1
        quarter_blocks["Q1"] = 1

        logger.info(f"Q1 capped to 1 block, redistributing {overflow} to later quarters")

        # Push overflow into later quarters by drama priority (skip Q1 entirely)
        for q in fill_order:
            if overflow <= 0:
                break
            if q != "Q1":
                quarter_blocks[q] += overflow
                overflow = 0


def _place_splits_within_quarters(
    sorted_quarters: list[str],
    quarter_moments: dict[str, list[int]],
    quarter_blocks: dict[str, int],
    n: int,
) -> list[int]:
    """Place splits WITHIN each quarter locally (not globally)."""
    split_points: list[int] = []

    for q_key in sorted_quarters:
        moment_indices = quarter_moments.get(q_key, [])
        if not moment_indices:
            continue

        blocks_for_q = quarter_blocks.get(q_key, 1)

        # Add period boundary at END of this quarter (between this and next)
        q_idx = sorted_quarters.index(q_key)
        if q_idx < len(sorted_quarters) - 1:
            # Boundary is after the last moment of this quarter
            boundary = moment_indices[-1] + 1
            if boundary < n and boundary not in split_points:
                split_points.append(boundary)

        # Add internal splits if this quarter needs multiple blocks
        internal_splits = blocks_for_q - 1

        if internal_splits > 0 and len(moment_indices) >= 2:
            # Place splits evenly WITHIN THIS QUARTER only
            interval = len(moment_indices) / (internal_splits + 1)
            for i in range(1, internal_splits + 1):
                # Local index within quarter -> global index
                local_idx = int(i * interval)
                global_idx = moment_indices[0] + local_idx
                if 0 < global_idx < n and global_idx not in split_points:
                    # Don't place too close to existing splits
                    too_close = any(abs(global_idx - s) < 2 for s in split_points)
                    if not too_close:
                        split_points.append(global_idx)

    return sorted(set(split_points))


def _trim_excess_splits(
    split_points: list[int],
    needed_splits: int,
    quarter_moments: dict[str, list[int]],
    quarter_weights: dict[str, float],
    quarter_index: dict[str, int],
) -> list[int]:
    """Trim excess splits by removing from lowest-drama quarters first."""
    while len(split_points) > needed_splits:
        # Find split in lowest-weight, earliest quarter
        lowest_score = float("inf")
        split_to_remove = None

        for sp in split_points:
            for q_key, indices in quarter_moments.items():
                if indices and indices[0] <= sp <= indices[-1] + 1:
                    # Score: lower weight = lower score, earlier quarter = lower score
                    score = quarter_weights.get(q_key, 1.0) + quarter_index[q_key] * 0.1
                    if score < lowest_score:
                        lowest_score = score
                        split_to_remove = sp
                    break

        if split_to_remove is not None:
            split_points.remove(split_to_remove)
        else:
            split_points.pop(0)

    return split_points


def _add_missing_splits(
    split_points: list[int],
    needed_splits: int,
    fill_order: list[str],
    quarter_moments: dict[str, list[int]],
    n: int,
) -> list[int]:
    """Add missing splits in high-drama quarters (back-biased)."""
    logger.warning(
        f"Split deficit: have {len(split_points)}, need {needed_splits}. "
        f"Adding to high-drama quarters."
    )

    # Add splits to highest-weight, latest quarters first
    for q in fill_order:
        if len(split_points) >= needed_splits:
            break

        moment_indices = quarter_moments.get(q, [])
        if len(moment_indices) < 2:
            continue

        # Try adding at various positions within this quarter
        for ratio in [0.5, 0.33, 0.67, 0.25, 0.75]:
            if len(split_points) >= needed_splits:
                break
            local_idx = int(len(moment_indices) * ratio)
            global_idx = moment_indices[0] + local_idx
            if 0 < global_idx < n and global_idx not in split_points:
                too_close = any(abs(global_idx - s) < 2 for s in split_points)
                if not too_close:
                    split_points.append(global_idx)
                    split_points = sorted(split_points)

    return split_points
