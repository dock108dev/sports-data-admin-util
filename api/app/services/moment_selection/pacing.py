"""Phase 2.4: Pacing Constraints / Narrative Quotas.

This module applies pacing constraints on top of importance-based selection:
- Early-game cap
- Closing reservation
- Act structure enforcement
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import BudgetConfig, PacingConfig, DEFAULT_BUDGET_CONFIG, DEFAULT_PACING_CONFIG
from .rank_select import RankSelectResult, rank_and_select
from .dynamic_budget import DynamicBudget, compute_game_signals, compute_dynamic_budget

if TYPE_CHECKING:
    from ..moments import Moment

logger = logging.getLogger(__name__)


@dataclass
class SelectionDecision:
    """Record of why a moment was selected or rejected."""

    moment_id: str
    importance_rank: int
    importance_score: float

    selected: bool
    selection_reason: str

    quarter: int | None = None
    is_early_game: bool = False
    is_closing: bool = False
    act: str = ""

    constraints_satisfied: list[str] = field(default_factory=list)
    constraint_violated: str | None = None

    swapped_for_id: str | None = None
    swapped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "importance_rank": self.importance_rank,
            "importance_score": round(self.importance_score, 2),
            "selected": self.selected,
            "selection_reason": self.selection_reason,
            "quarter": self.quarter,
            "is_early_game": self.is_early_game,
            "is_closing": self.is_closing,
            "act": self.act,
            "constraints_satisfied": self.constraints_satisfied,
            "constraint_violated": self.constraint_violated,
            "swapped_for_id": self.swapped_for_id,
            "swapped_reason": self.swapped_reason,
        }


@dataclass
class SelectionResult:
    """Complete result of narrative selection (Phase 2.3 + 2.4)."""

    selected_moments: list["Moment"] = field(default_factory=list)

    rank_select: RankSelectResult | None = None
    budget: DynamicBudget = field(default_factory=DynamicBudget)
    decisions: list[SelectionDecision] = field(default_factory=list)

    total_candidates: int = 0
    total_selected: int = 0
    early_game_count: int = 0
    closing_count: int = 0

    has_opening_moment: bool = False
    has_middle_moment: bool = False
    has_closing_moment: bool = False

    swaps_performed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase_2_2_rank_select": self.rank_select.to_dict() if self.rank_select else None,
            "phase_2_3_budget": self.budget.to_dict(),
            "phase_2_4_pacing": {
                "early_game_count": self.early_game_count,
                "closing_count": self.closing_count,
                "swaps_performed": self.swaps_performed,
                "act_coverage": {
                    "has_opening": self.has_opening_moment,
                    "has_middle": self.has_middle_moment,
                    "has_closing": self.has_closing_moment,
                },
            },
            "summary": {
                "total_candidates": self.total_candidates,
                "total_selected": self.total_selected,
            },
            "decisions": [d.to_dict() for d in self.decisions],
        }


def classify_moment_act(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    sport: str | None = None,
) -> tuple[str, int | None, bool, bool]:
    """Classify a moment into narrative acts.
    
    SPORT-AGNOSTIC: Uses game progress instead of quarter numbers.
    Works for NBA (quarters), NCAAB (halves), NHL (periods), etc.

    Returns:
        Tuple of (act, phase_number, is_early_game, is_closing)
    """
    from ..moments.game_structure import compute_game_phase_state
    
    start_idx = moment.start_play
    phase_number = None
    
    if 0 <= start_idx < len(events):
        event = events[start_idx]
        phase_state = compute_game_phase_state(event, sport)
        phase_number = phase_state.phase_number
        
        # Use progress-based classification (sport-agnostic)
        is_early_game = phase_state.game_progress <= 0.35
        is_closing = phase_state.is_final_phase
        
        # Classify into narrative acts based on progress
        if phase_state.game_progress <= 0.25:
            act = "opening"
        elif phase_state.game_progress <= 0.75:
            act = "middle"
        else:
            act = "closing"
    else:
        is_early_game = False
        is_closing = False
        act = "unknown"

    return act, phase_number, is_early_game, is_closing


def select_moments_with_pacing(
    candidates: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    budget_config: BudgetConfig = DEFAULT_BUDGET_CONFIG,
    pacing_config: PacingConfig = DEFAULT_PACING_CONFIG,
) -> SelectionResult:
    """Select moments using importance + pacing constraints.

    Algorithm:
    1. Compute dynamic budget (Phase 2.3)
    2. Use Phase 2.2 rank+select as base
    3. Apply pacing constraints (Phase 2.4)
    4. Perform swaps if constraints violated
    5. Return chronologically ordered selection
    """
    from ..moments_merging import merge_two_moments

    result = SelectionResult()
    result.total_candidates = len(candidates)

    if not candidates:
        return result

    # PHASE 2.3: Compute dynamic budget
    signals = compute_game_signals(events, candidates, thresholds)
    budget = compute_dynamic_budget(signals, budget_config)
    result.budget = budget

    target = budget.target_moment_count

    logger.info(
        "phase_2_3_dynamic_budget_computed",
        extra={
            "target": target,
            "signals": signals.to_dict(),
            "raw_score": budget.raw_budget_score,
        },
    )

    # PHASE 2.2: Run base rank+select
    rank_select_result = rank_and_select(candidates, target)
    result.rank_select = rank_select_result

    # PHASE 2.4: Apply pacing constraints
    moment_info: list[tuple["Moment", str, int | None, bool, bool]] = []
    for m in candidates:
        act, quarter, is_early, is_closing = classify_moment_act(m, events)
        moment_info.append((m, act, quarter, is_early, is_closing))

    ranked = sorted(
        range(len(candidates)),
        key=lambda i: candidates[i].importance_score,
        reverse=True,
    )

    for rank, idx in enumerate(ranked, 1):
        m = candidates[idx]
        _, act, quarter, is_early, is_closing = moment_info[idx]

        decision = SelectionDecision(
            moment_id=m.id,
            importance_rank=rank,
            importance_score=m.importance_score,
            selected=False,
            selection_reason="pending",
            quarter=quarter,
            is_early_game=is_early,
            is_closing=is_closing,
            act=act,
        )
        result.decisions.append(decision)

    max_early_game = int(target * pacing_config.early_game_max_percentage)

    if signals.final_margin <= pacing_config.close_game_margin_threshold:
        min_closing = max(
            pacing_config.closing_min_moments,
            int(target * pacing_config.closing_min_percentage_close),
        )
    else:
        min_closing = max(
            pacing_config.closing_min_moments,
            int(target * pacing_config.closing_min_percentage_normal),
        )

    selected_indices: set[int] = set()
    early_game_selected = 0
    closing_selected = 0
    acts_covered: set[str] = set()

    for rank_idx, orig_idx in enumerate(ranked):
        if len(selected_indices) >= target:
            break

        m = candidates[orig_idx]
        _, act, quarter, is_early, is_closing = moment_info[orig_idx]
        decision = result.decisions[rank_idx]

        if is_early and early_game_selected >= max_early_game:
            if m.importance_score >= pacing_config.early_game_override_importance:
                decision.constraints_satisfied.append("early_cap_override")
            else:
                decision.selection_reason = "rejected_early_cap"
                decision.constraint_violated = "early_game_cap"
                continue

        selected_indices.add(orig_idx)
        decision.selected = True
        decision.selection_reason = "importance"

        if is_early:
            early_game_selected += 1
        if is_closing:
            closing_selected += 1
        if act:
            acts_covered.add(act)

    # Enforce closing reservation
    if closing_selected < min_closing:
        closing_candidates = [
            (i, candidates[i])
            for i in range(len(candidates))
            if moment_info[i][4] and i not in selected_indices
        ]
        closing_candidates.sort(key=lambda x: x[1].importance_score, reverse=True)

        needed = min_closing - closing_selected
        for i, m in closing_candidates[:needed]:
            if len(selected_indices) < target:
                selected_indices.add(i)
                closing_selected += 1

                for d in result.decisions:
                    if d.moment_id == m.id:
                        d.selected = True
                        d.selection_reason = "closing_reservation"
                        break
            else:
                non_closing_selected = [
                    (j, candidates[j])
                    for j in selected_indices
                    if not moment_info[j][4]
                ]
                if not non_closing_selected:
                    break

                non_closing_selected.sort(key=lambda x: x[1].importance_score)
                swap_out_idx, swap_out_m = non_closing_selected[0]

                selected_indices.remove(swap_out_idx)
                selected_indices.add(i)
                closing_selected += 1
                result.swaps_performed += 1

                for d in result.decisions:
                    if d.moment_id == swap_out_m.id:
                        d.selected = False
                        d.selection_reason = "swapped_for_closing"
                        d.swapped_for_id = m.id
                        d.swapped_reason = "closing_reservation"
                    elif d.moment_id == m.id:
                        d.selected = True
                        d.selection_reason = "closing_reservation"
                        d.swapped_for_id = swap_out_m.id

    # Enforce act structure
    for required_act in ["opening", "middle", "closing"]:
        if required_act not in acts_covered:
            act_candidates = [
                (i, candidates[i])
                for i in range(len(candidates))
                if moment_info[i][1] == required_act and i not in selected_indices
            ]

            if not act_candidates:
                continue

            act_candidates.sort(key=lambda x: x[1].importance_score, reverse=True)
            best_idx, best_m = act_candidates[0]

            if len(selected_indices) < target:
                selected_indices.add(best_idx)
                acts_covered.add(required_act)

                for d in result.decisions:
                    if d.moment_id == best_m.id:
                        d.selected = True
                        d.selection_reason = f"act_enforcement_{required_act}"
                        break
            else:
                other_act_selected = [
                    (j, candidates[j])
                    for j in selected_indices
                    if moment_info[j][1] != required_act
                ]
                if not other_act_selected:
                    continue

                other_act_selected.sort(key=lambda x: x[1].importance_score)
                swap_out_idx, swap_out_m = other_act_selected[0]

                selected_indices.remove(swap_out_idx)
                selected_indices.add(best_idx)
                acts_covered.add(required_act)
                result.swaps_performed += 1

                for d in result.decisions:
                    if d.moment_id == swap_out_m.id:
                        d.selected = False
                        d.selection_reason = f"swapped_for_act_{required_act}"
                        d.swapped_for_id = best_m.id
                    elif d.moment_id == best_m.id:
                        d.selected = True
                        d.selection_reason = f"act_enforcement_{required_act}"
                        d.swapped_for_id = swap_out_m.id

    for d in result.decisions:
        if not d.selected and d.selection_reason == "pending":
            d.selection_reason = "rejected_budget"

    # Merge rejected moments into selected neighbors
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
    result.total_selected = len(final_moments)

    for m in final_moments:
        _, _, is_early, is_closing = classify_moment_act(m, events)
        if is_early:
            result.early_game_count += 1
        if is_closing:
            result.closing_count += 1

    result.has_opening_moment = "opening" in acts_covered
    result.has_middle_moment = "middle" in acts_covered
    result.has_closing_moment = "closing" in acts_covered

    logger.info(
        "moment_selection_complete",
        extra={
            "candidates": result.total_candidates,
            "selected": result.total_selected,
            "target": target,
            "early_game": result.early_game_count,
            "closing": result.closing_count,
            "swaps": result.swaps_performed,
            "acts_covered": list(acts_covered),
        },
    )

    return result
