"""Narrative-First Moment Selection - Phases 2.2, 2.3, 2.4

This module replaces the destructive adjacency-based hard clamp (enforce_budget)
with a narrative-aware selection strategy.

PHASE 2.2: Rank + Select (Replace Hard Budget Clamp)
- Rank all candidates by importance_score
- Select top K moments (using static budget)
- Every keep/drop decision is explainable
- No pacing constraints yet

PHASE 2.3: Dynamic Budget (Game-Aware Soft Cap)
- Compute target_moment_count from game signals
- Configurable bounds (min/max)
- Full traceability

PHASE 2.4: Pacing Constraints / Narrative Quotas
- Early-game cap
- Closing reservation
- Act structure enforcement
- Importance-based selection within constraints

This module CONSUMES importance scores from Phase 2.1.
It does NOT reorder moments or modify triggers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .moments import Moment

logger = logging.getLogger(__name__)


# =============================================================================
# PHASE 2.2: RANK + SELECT (Pure Importance-Based Selection)
# =============================================================================


# Static budgets per sport (legacy values, used as Phase 2.2 baseline)
STATIC_BUDGET = {
    "NBA": 30,
    "NHL": 25,
    "NFL": 25,
    "MLS": 20,
    "SOCCER": 20,
}
DEFAULT_STATIC_BUDGET = 30


@dataclass
class MomentRankRecord:
    """Record of a moment's rank and selection decision.
    
    This provides full traceability for why each moment was kept or dropped.
    """
    
    moment_id: str
    importance_score: float
    importance_rank: int  # 1 = highest importance
    
    # Selection decision
    selected: bool
    rejection_reason: str | None = None
    # Possible reasons: "below_rank_cutoff", "structural_invalid", "pre_existing_merge"
    
    # Context
    displaced_by: list[str] = field(default_factory=list)  # IDs of higher-ranked moments
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "importance_score": round(self.importance_score, 3),
            "importance_rank": self.importance_rank,
            "selected": self.selected,
            "rejection_reason": self.rejection_reason,
            "displaced_by": self.displaced_by[:5] if self.displaced_by else [],  # Limit for readability
        }


@dataclass
class RankSelectResult:
    """Result of Phase 2.2 rank+select operation.
    
    Provides complete diagnostics for the selection process.
    """
    
    # Selected moments (in chronological order)
    selected_moments: list["Moment"] = field(default_factory=list)
    
    # All rank records (selected and rejected)
    rank_records: list[MomentRankRecord] = field(default_factory=list)
    
    # Aggregate diagnostics
    total_candidates: int = 0
    selected_count: int = 0
    rejected_count: int = 0
    budget_used: int = 0
    
    # Importance distribution
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
        candidates: All candidate moments (with importance scores from Phase 2.1)
        budget: Number of moments to select (static K for Phase 2.2)
    
    Returns:
        RankSelectResult with selected moments and full traceability
    """
    result = RankSelectResult()
    result.total_candidates = len(candidates)
    result.budget_used = budget
    
    if not candidates:
        return result
    
    # Step 1: Rank by importance_score (descending)
    ranked_indices = sorted(
        range(len(candidates)),
        key=lambda i: (candidates[i].importance_score, -candidates[i].start_play),
        reverse=True
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
            # Record which moments displaced this one
            record.displaced_by = selected_ids[:5]  # Top 5 that beat it
        
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
    
    # Step 4: Merge rejected moments into selected neighbors (maintain coverage)
    from .moments_merging import merge_two_moments
    
    # Sort all by start_play to process in order
    all_sorted = sorted(range(len(candidates)), key=lambda i: candidates[i].start_play)
    
    final_moments: list["Moment"] = []
    pending_merge: "Moment" | None = None
    
    for orig_idx in all_sorted:
        moment = candidates[orig_idx]
        is_selected = orig_idx in selected_indices
        
        if is_selected:
            # If we have pending merges, merge them into this selected moment
            if pending_merge is not None:
                moment = merge_two_moments(pending_merge, moment)
                pending_merge = None
            final_moments.append(moment)
        else:
            # Not selected - merge into nearest selected moment
            if final_moments:
                # Merge into previous selected moment
                final_moments[-1] = merge_two_moments(final_moments[-1], moment)
            else:
                # No selected moment yet - hold for later
                if pending_merge is None:
                    pending_merge = moment
                else:
                    pending_merge = merge_two_moments(pending_merge, moment)
    
    # If we still have pending (all early moments were rejected), merge into first selected
    if pending_merge is not None and final_moments:
        final_moments[0] = merge_two_moments(pending_merge, final_moments[0])
    
    # Sort by start_play to ensure chronological order
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
        }
    )
    
    return result


def apply_rank_select(
    moments: list["Moment"],
    sport: str = "NBA",
) -> tuple[list["Moment"], RankSelectResult]:
    """Apply Phase 2.2 rank+select using static budget.
    
    This is the Phase 2.2 entry point that uses legacy static budgets.
    
    Args:
        moments: All candidate moments (with importance scores)
        sport: Sport name for budget lookup
    
    Returns:
        Tuple of (selected_moments, rank_select_result)
    """
    budget = STATIC_BUDGET.get(sport, DEFAULT_STATIC_BUDGET)
    
    result = rank_and_select(moments, budget)
    
    return result.selected_moments, result


# =============================================================================
# CONFIGURATION - Dynamic Budget
# =============================================================================


@dataclass
class BudgetConfig:
    """Configurable parameters for dynamic budget calculation."""
    
    # Base budget (starting point before adjustments)
    base_budget: int = 22
    
    # Hard bounds
    min_budget: int = 10
    max_budget: int = 40
    
    # Final margin impact
    margin_blowout_threshold: int = 20    # 20+ point margin = blowout
    margin_close_threshold: int = 5       # ≤5 point finish = close game
    margin_blowout_penalty: float = -6.0  # Reduce budget for blowouts
    margin_close_bonus: float = 4.0       # Increase for close games
    
    # Closeness duration impact (% of game in tier 0-1)
    closeness_high_threshold: float = 0.6  # 60%+ = thriller
    closeness_low_threshold: float = 0.2   # <20% = one-sided
    closeness_thriller_bonus: float = 6.0
    closeness_onesided_penalty: float = -4.0
    
    # Lead change impact (late-weighted)
    lead_changes_high_threshold: int = 8   # Many lead changes
    lead_changes_low_threshold: int = 2    # Few lead changes
    lead_changes_bonus_per: float = 0.5    # Per lead change above threshold
    lead_changes_cap: float = 5.0          # Max bonus from lead changes
    
    # Overtime impact
    overtime_bonus_per_period: float = 4.0
    overtime_cap: float = 8.0  # Max bonus from OT
    
    # Comeback depth impact
    comeback_significant_threshold: int = 12  # 12+ point comeback
    comeback_bonus: float = 3.0


@dataclass
class PacingConfig:
    """Configurable parameters for pacing constraints."""
    
    # Early-game cap (Q1 + Q2)
    early_game_max_percentage: float = 0.35  # Max 35% from Q1/Q2
    early_game_override_importance: float = 8.0  # Override if importance above this
    
    # Closing reservation (Q4 + OT)
    closing_min_percentage_close: float = 0.35  # Reserve 35% for Q4/OT in close games
    closing_min_percentage_normal: float = 0.20  # Reserve 20% for Q4/OT normally
    closing_min_moments: int = 3  # Always at least 3 closing moments
    
    # Act structure
    # Act 1 (Opening): Q1 or first 25% of game
    # Act 2 (Middle): Q2-Q3 or 25%-75% of game
    # Act 3 (Closing): Q4+ or last 25% of game
    require_opening_moment: bool = True
    require_middle_moment: bool = True
    require_closing_moment: bool = True
    
    # Close game threshold for higher closing reservation
    close_game_margin_threshold: int = 8


# Default configs
DEFAULT_BUDGET_CONFIG = BudgetConfig()
DEFAULT_PACING_CONFIG = PacingConfig()


# =============================================================================
# DYNAMIC BUDGET COMPUTATION (Phase 2.3)
# =============================================================================


@dataclass
class GameSignals:
    """Game-level signals for budget computation."""
    
    # Final margin
    final_margin: int = 0
    
    # Closeness duration (0.0 to 1.0)
    closeness_duration: float = 0.0
    plays_in_close_range: int = 0
    total_plays: int = 0
    
    # Lead changes (late-weighted)
    total_lead_changes: int = 0
    late_lead_changes: int = 0  # Q4/OT
    lead_change_score: float = 0.0  # Weighted score
    
    # Overtime
    has_overtime: bool = False
    overtime_periods: int = 0
    
    # Comeback
    max_deficit_overcome: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "final_margin": self.final_margin,
            "closeness_duration": round(self.closeness_duration, 3),
            "plays_in_close_range": self.plays_in_close_range,
            "total_plays": self.total_plays,
            "total_lead_changes": self.total_lead_changes,
            "late_lead_changes": self.late_lead_changes,
            "lead_change_score": round(self.lead_change_score, 2),
            "has_overtime": self.has_overtime,
            "overtime_periods": self.overtime_periods,
            "max_deficit_overcome": self.max_deficit_overcome,
        }


@dataclass
class DynamicBudget:
    """Result of dynamic budget computation with full traceability."""
    
    # Final target
    target_moment_count: int = 22
    
    # Input signals
    signals: GameSignals = field(default_factory=GameSignals)
    
    # Individual contributions
    base_budget: int = 22
    margin_adjustment: float = 0.0
    closeness_adjustment: float = 0.0
    lead_change_adjustment: float = 0.0
    overtime_adjustment: float = 0.0
    comeback_adjustment: float = 0.0
    
    # Raw score before clamping
    raw_budget_score: float = 22.0
    
    # Bounds applied
    min_bound: int = 10
    max_bound: int = 40
    was_clamped_low: bool = False
    was_clamped_high: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "target_moment_count": self.target_moment_count,
            "signals": self.signals.to_dict(),
            "adjustments": {
                "base": self.base_budget,
                "margin": round(self.margin_adjustment, 2),
                "closeness": round(self.closeness_adjustment, 2),
                "lead_changes": round(self.lead_change_adjustment, 2),
                "overtime": round(self.overtime_adjustment, 2),
                "comeback": round(self.comeback_adjustment, 2),
            },
            "raw_budget_score": round(self.raw_budget_score, 2),
            "bounds": {
                "min": self.min_bound,
                "max": self.max_bound,
                "was_clamped_low": self.was_clamped_low,
                "was_clamped_high": self.was_clamped_high,
            },
        }


def compute_game_signals(
    events: Sequence[dict[str, Any]],
    moments: list["Moment"],
    thresholds: Sequence[int],
) -> GameSignals:
    """Extract game-level signals from timeline and moments.
    
    Args:
        events: Timeline events
        moments: All candidate moments (before selection)
        thresholds: Lead Ladder thresholds
    
    Returns:
        GameSignals with all computed values
    """
    from .lead_ladder import compute_lead_state, Leader
    
    signals = GameSignals()
    
    # Get PBP events only
    pbp_events = [e for e in events if e.get("event_type") == "pbp"]
    if not pbp_events:
        return signals
    
    signals.total_plays = len(pbp_events)
    
    # Track state through game
    prev_leader: Leader | None = None
    max_home_deficit = 0
    max_away_deficit = 0
    
    for i, event in enumerate(pbp_events):
        home = event.get("home_score", 0) or 0
        away = event.get("away_score", 0) or 0
        quarter = event.get("quarter", 1) or 1
        
        state = compute_lead_state(home, away, thresholds)
        
        # Closeness: tier 0-1 is "close"
        if state.tier <= 1:
            signals.plays_in_close_range += 1
        
        # Lead changes
        if prev_leader is not None and state.leader != prev_leader:
            if prev_leader != Leader.TIED and state.leader != Leader.TIED:
                signals.total_lead_changes += 1
                # Late-weighted: Q4+ lead changes count more
                if quarter >= 4:
                    signals.late_lead_changes += 1
        
        # Track deficits for comeback detection
        margin = home - away
        if margin < 0:  # Home is losing
            max_home_deficit = max(max_home_deficit, abs(margin))
        else:  # Away is losing
            max_away_deficit = max(max_away_deficit, margin)
        
        prev_leader = state.leader
    
    # Final margin
    if pbp_events:
        last_event = pbp_events[-1]
        final_home = last_event.get("home_score", 0) or 0
        final_away = last_event.get("away_score", 0) or 0
        signals.final_margin = abs(final_home - final_away)
        
        # Determine winner for comeback calculation
        if final_home > final_away:
            # Home won - their max deficit matters
            signals.max_deficit_overcome = max_home_deficit
        else:
            signals.max_deficit_overcome = max_away_deficit
    
    # Closeness duration
    if signals.total_plays > 0:
        signals.closeness_duration = signals.plays_in_close_range / signals.total_plays
    
    # Lead change score (late-weighted)
    # Late lead changes worth 2x
    signals.lead_change_score = (
        signals.total_lead_changes + 
        signals.late_lead_changes  # Double count late ones
    )
    
    # Overtime detection
    max_quarter = max(
        (e.get("quarter", 1) or 1 for e in pbp_events),
        default=4
    )
    if max_quarter > 4:
        signals.has_overtime = True
        signals.overtime_periods = max_quarter - 4
    
    return signals


def compute_dynamic_budget(
    signals: GameSignals,
    config: BudgetConfig = DEFAULT_BUDGET_CONFIG,
) -> DynamicBudget:
    """Compute target moment count from game signals.
    
    Args:
        signals: Game-level signals
        config: Budget configuration
    
    Returns:
        DynamicBudget with target and full breakdown
    """
    budget = DynamicBudget()
    budget.signals = signals
    budget.base_budget = config.base_budget
    budget.min_bound = config.min_budget
    budget.max_bound = config.max_budget
    
    # Start with base
    score = float(config.base_budget)
    
    # 1. Final margin adjustment
    if signals.final_margin >= config.margin_blowout_threshold:
        budget.margin_adjustment = config.margin_blowout_penalty
    elif signals.final_margin <= config.margin_close_threshold:
        budget.margin_adjustment = config.margin_close_bonus
    else:
        # Linear interpolation between thresholds
        range_size = config.margin_blowout_threshold - config.margin_close_threshold
        position = (signals.final_margin - config.margin_close_threshold) / range_size
        budget.margin_adjustment = config.margin_close_bonus * (1 - position)
    
    score += budget.margin_adjustment
    
    # 2. Closeness duration adjustment
    if signals.closeness_duration >= config.closeness_high_threshold:
        budget.closeness_adjustment = config.closeness_thriller_bonus
    elif signals.closeness_duration <= config.closeness_low_threshold:
        budget.closeness_adjustment = config.closeness_onesided_penalty
    else:
        # Linear interpolation
        range_size = config.closeness_high_threshold - config.closeness_low_threshold
        position = (signals.closeness_duration - config.closeness_low_threshold) / range_size
        budget.closeness_adjustment = (
            config.closeness_onesided_penalty + 
            (config.closeness_thriller_bonus - config.closeness_onesided_penalty) * position
        )
    
    score += budget.closeness_adjustment
    
    # 3. Lead change adjustment
    if signals.lead_change_score > config.lead_changes_high_threshold:
        excess = signals.lead_change_score - config.lead_changes_high_threshold
        budget.lead_change_adjustment = min(
            excess * config.lead_changes_bonus_per,
            config.lead_changes_cap
        )
    
    score += budget.lead_change_adjustment
    
    # 4. Overtime adjustment
    if signals.has_overtime:
        budget.overtime_adjustment = min(
            signals.overtime_periods * config.overtime_bonus_per_period,
            config.overtime_cap
        )
    
    score += budget.overtime_adjustment
    
    # 5. Comeback adjustment
    if signals.max_deficit_overcome >= config.comeback_significant_threshold:
        budget.comeback_adjustment = config.comeback_bonus
    
    score += budget.comeback_adjustment
    
    # Store raw score
    budget.raw_budget_score = score
    
    # Clamp to bounds
    if score < config.min_budget:
        budget.target_moment_count = config.min_budget
        budget.was_clamped_low = True
    elif score > config.max_budget:
        budget.target_moment_count = config.max_budget
        budget.was_clamped_high = True
    else:
        budget.target_moment_count = round(score)
    
    return budget


# =============================================================================
# PACING CONSTRAINTS (Phase 2.4)
# =============================================================================


@dataclass
class SelectionDecision:
    """Record of why a moment was selected or rejected."""
    
    moment_id: str
    importance_rank: int  # 1 = highest importance
    importance_score: float
    
    selected: bool
    selection_reason: str  # "importance", "act_enforcement", "closing_reservation", etc.
    
    # Pacing info
    quarter: int | None = None
    is_early_game: bool = False  # Q1-Q2
    is_closing: bool = False     # Q4+
    act: str = ""                # "opening", "middle", "closing"
    
    # Constraint satisfaction
    constraints_satisfied: list[str] = field(default_factory=list)
    constraint_violated: str | None = None
    
    # If swapped
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
    """Complete result of narrative selection (Phase 2.3 + 2.4).
    
    Includes Phase 2.2 rank+select as the base, plus dynamic budget and pacing.
    """
    
    # Selected moments (in chronological order)
    selected_moments: list["Moment"] = field(default_factory=list)
    
    # Phase 2.2: Rank+Select base result
    rank_select: RankSelectResult | None = None
    
    # Phase 2.3: Dynamic budget info
    budget: DynamicBudget = field(default_factory=DynamicBudget)
    
    # Phase 2.4: Pacing decisions
    decisions: list[SelectionDecision] = field(default_factory=list)
    
    # Summary stats
    total_candidates: int = 0
    total_selected: int = 0
    early_game_count: int = 0
    closing_count: int = 0
    
    # Act coverage
    has_opening_moment: bool = False
    has_middle_moment: bool = False
    has_closing_moment: bool = False
    
    # Swaps performed
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


def _classify_moment_act(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
) -> tuple[str, int | None, bool, bool]:
    """Classify a moment into narrative acts.
    
    Returns:
        Tuple of (act, quarter, is_early_game, is_closing)
    """
    # Get quarter from moment's start event
    start_idx = moment.start_play
    quarter = None
    if 0 <= start_idx < len(events):
        quarter = events[start_idx].get("quarter")
    
    is_early_game = quarter is not None and quarter <= 2
    is_closing = quarter is not None and quarter >= 4
    
    if quarter is None:
        act = "unknown"
    elif quarter == 1:
        act = "opening"
    elif quarter in (2, 3):
        act = "middle"
    else:
        act = "closing"
    
    return act, quarter, is_early_game, is_closing


def select_moments_with_pacing(
    candidates: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    budget_config: BudgetConfig = DEFAULT_BUDGET_CONFIG,
    pacing_config: PacingConfig = DEFAULT_PACING_CONFIG,
) -> SelectionResult:
    """Select moments using importance + pacing constraints.
    
    This is Phase 2.3 + 2.4, building on Phase 2.2 rank+select.
    
    Algorithm:
    1. Compute dynamic budget (Phase 2.3)
    2. Use Phase 2.2 rank+select as base
    3. Apply pacing constraints (Phase 2.4):
       - Respect early-game cap
       - Reserve closing slots
       - Enforce act coverage
    4. Perform swaps if constraints violated
    5. Return chronologically ordered selection
    
    Args:
        candidates: All candidate moments (with importance scores)
        events: Timeline events
        thresholds: Lead Ladder thresholds
        budget_config: Budget parameters
        pacing_config: Pacing parameters
    
    Returns:
        SelectionResult with selected moments and full traceability
    """
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
        }
    )
    
    # PHASE 2.2: Run base rank+select (pure importance-based selection)
    # This provides the foundation that Phase 2.4 pacing builds upon
    rank_select_result = rank_and_select(candidates, target)
    result.rank_select = rank_select_result
    
    # PHASE 2.4: Apply pacing constraints on top of rank+select
    # Classify all moments
    moment_info: list[tuple["Moment", str, int | None, bool, bool]] = []
    for m in candidates:
        act, quarter, is_early, is_closing = _classify_moment_act(m, events)
        moment_info.append((m, act, quarter, is_early, is_closing))
    
    # 3. Rank by importance (descending)
    ranked = sorted(
        range(len(candidates)),
        key=lambda i: candidates[i].importance_score,
        reverse=True
    )
    
    # Create decisions for all candidates
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
    
    # 4. Compute pacing quotas
    max_early_game = int(target * pacing_config.early_game_max_percentage)
    
    # Closing reservation depends on game closeness
    if signals.final_margin <= pacing_config.close_game_margin_threshold:
        min_closing = max(
            pacing_config.closing_min_moments,
            int(target * pacing_config.closing_min_percentage_close)
        )
    else:
        min_closing = max(
            pacing_config.closing_min_moments,
            int(target * pacing_config.closing_min_percentage_normal)
        )
    
    # 5. Select with constraints
    selected_indices: set[int] = set()
    early_game_selected = 0
    closing_selected = 0
    acts_covered: set[str] = set()
    
    # First pass: select by importance with constraints
    for rank_idx, orig_idx in enumerate(ranked):
        if len(selected_indices) >= target:
            break
        
        m = candidates[orig_idx]
        _, act, quarter, is_early, is_closing = moment_info[orig_idx]
        decision = result.decisions[rank_idx]
        
        # Check early-game cap
        if is_early and early_game_selected >= max_early_game:
            # Can override if importance is high enough
            if m.importance_score >= pacing_config.early_game_override_importance:
                decision.constraints_satisfied.append("early_cap_override")
            else:
                decision.selection_reason = "rejected_early_cap"
                decision.constraint_violated = "early_game_cap"
                continue
        
        # Select this moment
        selected_indices.add(orig_idx)
        decision.selected = True
        decision.selection_reason = "importance"
        
        if is_early:
            early_game_selected += 1
        if is_closing:
            closing_selected += 1
        if act:
            acts_covered.add(act)
    
    # 6. Enforce closing reservation
    if closing_selected < min_closing:
        # Find closing moments not yet selected
        closing_candidates = [
            (i, candidates[i])
            for i in range(len(candidates))
            if moment_info[i][4] and i not in selected_indices  # is_closing
        ]
        closing_candidates.sort(key=lambda x: x[1].importance_score, reverse=True)
        
        # Swap in closing moments
        needed = min_closing - closing_selected
        for i, m in closing_candidates[:needed]:
            if len(selected_indices) < target:
                # Just add it
                selected_indices.add(i)
                closing_selected += 1
                
                # Find decision for this moment
                for d in result.decisions:
                    if d.moment_id == m.id:
                        d.selected = True
                        d.selection_reason = "closing_reservation"
                        break
            else:
                # Need to swap out lowest importance non-closing moment
                non_closing_selected = [
                    (j, candidates[j])
                    for j in selected_indices
                    if not moment_info[j][4]  # not is_closing
                ]
                if not non_closing_selected:
                    break
                
                # Find lowest importance
                non_closing_selected.sort(key=lambda x: x[1].importance_score)
                swap_out_idx, swap_out_m = non_closing_selected[0]
                
                # Perform swap
                selected_indices.remove(swap_out_idx)
                selected_indices.add(i)
                closing_selected += 1
                result.swaps_performed += 1
                
                # Update decisions
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
    
    # 7. Enforce act structure
    for required_act in ["opening", "middle", "closing"]:
        if required_act not in acts_covered:
            # Find best candidate for this act
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
                # Just add it
                selected_indices.add(best_idx)
                acts_covered.add(required_act)
                
                for d in result.decisions:
                    if d.moment_id == best_m.id:
                        d.selected = True
                        d.selection_reason = f"act_enforcement_{required_act}"
                        break
            else:
                # Need to swap
                # Find lowest importance moment from a different act
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
    
    # 8. Mark remaining as rejected
    for d in result.decisions:
        if not d.selected and d.selection_reason == "pending":
            d.selection_reason = "rejected_budget"
    
    # 9. Merge rejected moments into selected neighbors to maintain coverage
    # This is critical: we can't drop moments, we must merge them
    from .moments_merging import merge_two_moments
    
    # Sort all by start_play to process in order
    all_sorted = sorted(range(len(candidates)), key=lambda i: candidates[i].start_play)
    
    # Build final list by merging rejected moments into adjacent selected moments
    final_moments: list["Moment"] = []
    pending_merge: "Moment" | None = None
    
    for orig_idx in all_sorted:
        moment = candidates[orig_idx]
        is_selected = orig_idx in selected_indices
        
        if is_selected:
            # If we have pending merges, merge them into this selected moment
            if pending_merge is not None:
                moment = merge_two_moments(pending_merge, moment)
                pending_merge = None
            final_moments.append(moment)
        else:
            # Not selected - merge into nearest selected moment
            if final_moments:
                # Merge into previous selected moment
                final_moments[-1] = merge_two_moments(final_moments[-1], moment)
            else:
                # No selected moment yet - hold for later
                if pending_merge is None:
                    pending_merge = moment
                else:
                    pending_merge = merge_two_moments(pending_merge, moment)
    
    # If we still have pending (all early moments were rejected), merge into first selected
    if pending_merge is not None and final_moments:
        final_moments[0] = merge_two_moments(pending_merge, final_moments[0])
    
    # Sort by start_play to ensure chronological order
    final_moments.sort(key=lambda m: m.start_play)
    
    result.selected_moments = final_moments
    result.total_selected = len(final_moments)
    
    # Count stats
    for m in final_moments:
        _, _, is_early, is_closing = _classify_moment_act(m, events)
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
        }
    )
    
    return result


def apply_narrative_selection(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
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
    # Use default configs (can be sport-specific in future)
    budget_config = DEFAULT_BUDGET_CONFIG
    pacing_config = DEFAULT_PACING_CONFIG
    
    # Sport-specific adjustments (optional)
    if sport == "NHL":
        # Hockey has fewer scoring events
        budget_config.base_budget = 18
        budget_config.min_budget = 8
    elif sport == "NFL":
        # Football has natural breaks
        budget_config.base_budget = 20
        budget_config.min_budget = 10
    
    result = select_moments_with_pacing(
        moments, events, thresholds, budget_config, pacing_config
    )
    
    return result.selected_moments, result
