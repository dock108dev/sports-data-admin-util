"""Narrative-First Moment Selection.

This package replaces the destructive adjacency-based hard clamp
with a narrative-aware selection strategy.

Phases:
- 2.2: Rank + Select (pure importance-based)
- 2.3: Dynamic Budget (game-aware soft cap)
- 2.4: Pacing Constraints / Narrative Quotas

Usage:
    from app.services.moment_selection import apply_narrative_selection
"""

from __future__ import annotations

from typing import Sequence, TYPE_CHECKING

from .config import (
    BudgetConfig,
    PacingConfig,
    STATIC_BUDGET,
    DEFAULT_STATIC_BUDGET,
    DEFAULT_BUDGET_CONFIG,
    DEFAULT_PACING_CONFIG,
)
from .rank_select import (
    MomentRankRecord,
    RankSelectResult,
    apply_rank_select,
    rank_and_select,
)
from .dynamic_budget import (
    DynamicBudget,
    GameSignals,
    compute_dynamic_budget,
    compute_game_signals,
)
from .pacing import (
    SelectionDecision,
    SelectionResult,
    classify_moment_act,
    select_moments_with_pacing,
)

if TYPE_CHECKING:
    from typing import Any
    from ..moments import Moment


def apply_narrative_selection(
    moments: list["Moment"],
    events: Sequence[dict[str, "Any"]],
    thresholds: Sequence[int],
    sport: str = "NBA",
) -> tuple[list["Moment"], SelectionResult]:
    """Apply narrative selection to replace fixed budget enforcement.

    This is the main entry point, replacing enforce_budget().

    Args:
        moments: All candidate moments (with importance scores)
        events: Timeline events
        thresholds: Lead Ladder thresholds
        sport: Sport name for config lookup

    Returns:
        Tuple of (selected_moments, selection_result)
    """
    budget_config = BudgetConfig()
    pacing_config = PacingConfig()

    # Sport-specific adjustments
    if sport == "NHL":
        budget_config.base_budget = 18
        budget_config.min_budget = 8
    elif sport == "NFL":
        budget_config.base_budget = 20
        budget_config.min_budget = 10

    result = select_moments_with_pacing(
        moments, events, thresholds, budget_config, pacing_config
    )

    return result.selected_moments, result


__all__ = [
    # Configuration
    "BudgetConfig",
    "PacingConfig",
    "STATIC_BUDGET",
    "DEFAULT_STATIC_BUDGET",
    "DEFAULT_BUDGET_CONFIG",
    "DEFAULT_PACING_CONFIG",
    # Rank + Select (Phase 2.2)
    "MomentRankRecord",
    "RankSelectResult",
    "apply_rank_select",
    "rank_and_select",
    # Dynamic Budget (Phase 2.3)
    "DynamicBudget",
    "GameSignals",
    "compute_dynamic_budget",
    "compute_game_signals",
    # Pacing (Phase 2.4)
    "SelectionDecision",
    "SelectionResult",
    "classify_moment_act",
    "select_moments_with_pacing",
    # Main entry point
    "apply_narrative_selection",
]
