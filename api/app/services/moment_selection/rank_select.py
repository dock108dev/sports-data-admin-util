"""Phase 2.2: Rank + Select (Pure Importance-Based Selection).

This module provides pure importance-based moment selection,
replacing the destructive adjacency-based hard clamp.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from .config import STATIC_BUDGET, DEFAULT_STATIC_BUDGET

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class MomentRankRecord:
    """Record of a moment's rank and selection decision."""

    moment_id: str
    importance_score: float
    importance_rank: int  # 1 = highest importance

    selected: bool
    rejection_reason: str | None = None

    displaced_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "importance_score": round(self.importance_score, 3),
            "importance_rank": self.importance_rank,
            "selected": self.selected,
            "rejection_reason": self.rejection_reason,
            "displaced_by": self.displaced_by[:5] if self.displaced_by else [],
        }


@dataclass
class RankSelectResult:
    """Result of Phase 2.2 rank+select operation."""

    selected_moments: list["Moment"] = field(default_factory=list)
    rank_records: list[MomentRankRecord] = field(default_factory=list)

    total_candidates: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    budget_used: int = 0

    min_selected_importance: float = 0.0
    max_rejected_importance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": "2.2_rank_select",
            "total_candidates": self.total_candidates,
            "selected_count": self.selected_count,
            "rejected_count": self.rejected_count,
            "budget_used": self.budget_used,
            "min_selected_importance": round(self.min_selected_importance, 3),
            "max_rejected_importance": round(self.max_rejected_importance, 3),
            "rank_records": [r.to_dict() for r in self.rank_records],
        }


def rank_and_select(
    candidates: list["Moment"],
    budget: int,
) -> RankSelectResult:
    """Phase 2.2: Pure importance-based rank and select.

    This replaces enforce_budget() entirely. Instead of merging adjacent
    moments blindly, we:
    1. Rank all candidates by importance_score (descending)
    2. Select the top K moments
    3. Re-emit selected moments in chronological order

    Args:
        candidates: All candidate moments (with importance scores)
        budget: Number of moments to select

    Returns:
        RankSelectResult with selected moments and full traceability
    """
    from ..moments_merging import merge_two_moments

    result = RankSelectResult()
    result.total_candidates = len(candidates)
    result.budget_used = budget

    if not candidates:
        return result

    # Step 1: Rank by importance_score (descending)
    ranked_indices = sorted(
        range(len(candidates)),
        key=lambda i: (candidates[i].importance_score, -candidates[i].start_play),
        reverse=True,
    )

    # Step 2: Create rank records and select top K
    selected_indices: set[int] = set()
    selected_ids: list[str] = []

    for rank, idx in enumerate(ranked_indices, 1):
        moment = candidates[idx]
        is_selected = rank <= budget

        record = MomentRankRecord(
            moment_id=moment.id,
            importance_score=moment.importance_score,
            importance_rank=rank,
            selected=is_selected,
            rejection_reason=None if is_selected else "below_rank_cutoff",
        )

        if is_selected:
            selected_indices.add(idx)
            selected_ids.append(moment.id)
        else:
            record.displaced_by = selected_ids[:5]

        result.rank_records.append(record)

    # Step 3: Compute aggregate diagnostics
    result.selected_count = len(selected_indices)
    result.rejected_count = result.total_candidates - result.selected_count

    selected_scores = [candidates[i].importance_score for i in selected_indices]
    rejected_scores = [
        candidates[i].importance_score
        for i in range(len(candidates))
        if i not in selected_indices
    ]

    if selected_scores:
        result.min_selected_importance = min(selected_scores)
    if rejected_scores:
        result.max_rejected_importance = max(rejected_scores)

    # Step 4: Merge rejected moments into selected neighbors
    all_sorted = sorted(range(len(candidates)), key=lambda i: candidates[i].start_play)

    final_moments: list["Moment"] = []
    pending_merge: "Moment" | None = None

    for orig_idx in all_sorted:
        moment = candidates[orig_idx]
        is_selected = orig_idx in selected_indices

        if is_selected:
            if pending_merge is not None:
                moment = merge_two_moments(pending_merge, moment)
                pending_merge = None
            final_moments.append(moment)
        else:
            if final_moments:
                final_moments[-1] = merge_two_moments(final_moments[-1], moment)
            else:
                if pending_merge is None:
                    pending_merge = moment
                else:
                    pending_merge = merge_two_moments(pending_merge, moment)

    if pending_merge is not None and final_moments:
        final_moments[0] = merge_two_moments(pending_merge, final_moments[0])

    final_moments.sort(key=lambda m: m.start_play)

    result.selected_moments = final_moments

    logger.info(
        "rank_and_select_complete",
        extra={
            "phase": "2.2",
            "candidates": result.total_candidates,
            "budget": budget,
            "selected": result.selected_count,
            "rejected": result.rejected_count,
            "min_selected_importance": result.min_selected_importance,
            "max_rejected_importance": result.max_rejected_importance,
        },
    )

    return result


def apply_rank_select(
    moments: list["Moment"],
    sport: str = "NBA",
) -> tuple[list["Moment"], RankSelectResult]:
    """Apply Phase 2.2 rank+select using static budget.

    Args:
        moments: All candidate moments (with importance scores)
        sport: Sport name for budget lookup

    Returns:
        Tuple of (selected_moments, rank_select_result)
    """
    budget = STATIC_BUDGET.get(sport, DEFAULT_STATIC_BUDGET)
    result = rank_and_select(moments, budget)
    return result.selected_moments, result
