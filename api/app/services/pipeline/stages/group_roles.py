"""Role assignment logic for GROUP_BLOCKS stage.

Contains functions for assigning semantic roles (SETUP, MOMENTUM_SHIFT,
RESPONSE, DECISION_POINT, RESOLUTION) to narrative blocks.
"""

from __future__ import annotations

from .block_types import NarrativeBlock, SemanticRole
from .league_config import get_config


def calculate_swing_metrics(block: NarrativeBlock) -> dict[str, int | bool]:
    """Calculate swing metrics for a block.

    Returns:
        Dict with:
        - net_swing: abs(home_delta - away_delta), how much ground one team gained
        - deficit_before: how far behind was the team that ended up ahead
        - has_lead_change: whether the lead changed within this block
    """
    home_before, away_before = block.score_before
    home_after, away_after = block.score_after

    home_delta = home_after - home_before
    away_delta = away_after - away_before
    net_swing = abs(home_delta - away_delta)

    # Determine leader before and after
    leader_before = 1 if home_before > away_before else (-1 if away_before > home_before else 0)
    leader_after = 1 if home_after > away_after else (-1 if away_after > home_after else 0)

    has_lead_change = (
        leader_before != 0 and leader_after != 0 and leader_before != leader_after
    )

    # Calculate deficit overcome (how far behind was the team that took the lead)
    deficit_before = 0
    if has_lead_change:
        if leader_after == 1:  # Home took the lead
            deficit_before = away_before - home_before  # How far behind home was
        else:  # Away took the lead
            deficit_before = home_before - away_before  # How far behind away was

    return {
        "net_swing": net_swing,
        "deficit_before": deficit_before,
        "has_lead_change": has_lead_change,
    }


def assign_roles(blocks: list[NarrativeBlock], league_code: str = "NBA") -> None:
    """Assign semantic roles to blocks in place.

    Rules:
    For 3-block games (blowouts):
      - Block 0 -> SETUP
      - Block 1 -> DECISION_POINT
      - Block 2 -> RESOLUTION

    For 4+ block games:
    1. First block -> SETUP
    2. Last block -> RESOLUTION
    3. Block with significant swing -> MOMENTUM_SHIFT (league-tuned thresholds)
       In close games, thresholds are lowered
    4. Block after momentum shift -> RESPONSE
    5. Second-to-last block -> DECISION_POINT (if not assigned)
    6. Remaining -> RESPONSE (or DECISION_POINT for zero-scoring blocks)

    Constraint: No role > 2 occurrences
    """
    if not blocks:
        return

    cfg = get_config(league_code)
    n = len(blocks)

    # Special case: 3-block games (blowouts)
    if n == 3:
        blocks[0].role = SemanticRole.SETUP
        blocks[1].role = SemanticRole.DECISION_POINT
        blocks[2].role = SemanticRole.RESOLUTION
        return

    # Detect close game: check max margin across all blocks
    max_margin = 0
    for block in blocks:
        margin_before = abs(block.score_before[0] - block.score_before[1])
        margin_after = abs(block.score_after[0] - block.score_after[1])
        max_margin = max(max_margin, margin_before, margin_after, block.peak_margin)

    is_close_game = max_margin <= cfg["close_game_margin"]

    # Use lower thresholds for close games where small swings are the story
    swing_threshold = cfg["close_game_swing"] if is_close_game else cfg["momentum_swing"]
    deficit_threshold = cfg["close_game_deficit"] if is_close_game else cfg["deficit_overcome"]

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

    # Find blocks with SIGNIFICANT momentum shifts
    # A true momentum shift requires either:
    # - A large net swing (8+ points, or 4+ in close games)
    # - OR overcoming a meaningful deficit (6+ points, or 2+ in close games) to take the lead
    momentum_shift_candidates: list[tuple[int, int]] = []  # (index, score for sorting)

    for i, block in enumerate(blocks):
        if i == 0 or i == n - 1:
            continue  # Skip first/last

        metrics = calculate_swing_metrics(block)

        # Check if this qualifies as a momentum shift
        qualifies = False
        score = 0

        if metrics["net_swing"] >= swing_threshold:
            # Large swing regardless of lead change
            qualifies = True
            score = metrics["net_swing"]
        elif metrics["has_lead_change"] and metrics["deficit_before"] >= deficit_threshold:
            # Overcame meaningful deficit to take lead
            qualifies = True
            score = metrics["deficit_before"] + metrics["net_swing"]

        if qualifies:
            # Prefer later blocks (late game drama), then larger swings
            # Add period bonus: late-game blocks get priority
            period_bonus = 0
            if hasattr(block, "period_end") and block.period_end >= cfg["late_game_period"]:
                period_bonus = 100
            momentum_shift_candidates.append((i, period_bonus + score))

    # Select the best momentum shift candidate (highest score = latest + largest swing)
    if momentum_shift_candidates:
        momentum_shift_candidates.sort(key=lambda x: x[1], reverse=True)
        momentum_shift_idx = momentum_shift_candidates[0][0]

        # Rule 3: Significant swing block -> MOMENTUM_SHIFT
        if can_assign(SemanticRole.MOMENTUM_SHIFT):
            assign(blocks[momentum_shift_idx], SemanticRole.MOMENTUM_SHIFT)

            # Rule 4: Block after momentum shift -> RESPONSE
            if (
                momentum_shift_idx + 1 < n - 1
                and blocks[momentum_shift_idx + 1].role is None
                and can_assign(SemanticRole.RESPONSE)
            ):
                assign(blocks[momentum_shift_idx + 1], SemanticRole.RESPONSE)

    # Rule 5: Second-to-last block -> DECISION_POINT
    if n > 2 and blocks[-2].role is None and can_assign(SemanticRole.DECISION_POINT):
        assign(blocks[-2], SemanticRole.DECISION_POINT)

    # Rule 6: Remaining blocks -> RESPONSE (or DECISION_POINT for zero-scoring)
    for block in blocks:
        if block.role is None:
            # A block with no scoring change is a defensive stand, not a "response"
            if (
                block.score_before == block.score_after
                and can_assign(SemanticRole.DECISION_POINT)
            ):
                assign(block, SemanticRole.DECISION_POINT)
            elif can_assign(SemanticRole.RESPONSE):
                assign(block, SemanticRole.RESPONSE)
            elif can_assign(SemanticRole.MOMENTUM_SHIFT):
                assign(block, SemanticRole.MOMENTUM_SHIFT)
            elif can_assign(SemanticRole.DECISION_POINT):
                assign(block, SemanticRole.DECISION_POINT)
            else:
                # Fallback - should not happen with proper block counts
                block.role = SemanticRole.RESPONSE
