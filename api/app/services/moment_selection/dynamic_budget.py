"""Phase 2.3: Dynamic Budget (Game-Aware Soft Cap).

This module computes target moment count from game signals,
with configurable bounds and full traceability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import BudgetConfig, DEFAULT_BUDGET_CONFIG

if TYPE_CHECKING:
    from ..moments import Moment


@dataclass
class GameSignals:
    """Game-level signals for budget computation."""

    final_margin: int = 0
    closeness_duration: float = 0.0
    plays_in_close_range: int = 0
    total_plays: int = 0
    total_lead_changes: int = 0
    late_lead_changes: int = 0
    lead_change_score: float = 0.0
    has_overtime: bool = False
    overtime_periods: int = 0
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

    target_moment_count: int = 22
    signals: GameSignals = field(default_factory=GameSignals)

    # Individual contributions
    base_budget: int = 22
    margin_adjustment: float = 0.0
    closeness_adjustment: float = 0.0
    lead_change_adjustment: float = 0.0
    overtime_adjustment: float = 0.0
    comeback_adjustment: float = 0.0

    raw_budget_score: float = 22.0

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
    """Extract game-level signals from timeline and moments."""
    from ..lead_ladder import compute_lead_state, Leader

    signals = GameSignals()

    pbp_events = [e for e in events if e.get("event_type") == "pbp"]
    if not pbp_events:
        return signals

    signals.total_plays = len(pbp_events)

    prev_leader: Leader | None = None
    max_home_deficit = 0
    max_away_deficit = 0

    for i, event in enumerate(pbp_events):
        home = event.get("home_score", 0) or 0
        away = event.get("away_score", 0) or 0
        quarter = event.get("quarter", 1) or 1

        state = compute_lead_state(home, away, thresholds)

        if state.tier <= 1:
            signals.plays_in_close_range += 1

        if prev_leader is not None and state.leader != prev_leader:
            if prev_leader != Leader.TIED and state.leader != Leader.TIED:
                signals.total_lead_changes += 1
                if quarter >= 4:
                    signals.late_lead_changes += 1

        margin = home - away
        if margin < 0:
            max_home_deficit = max(max_home_deficit, abs(margin))
        else:
            max_away_deficit = max(max_away_deficit, margin)

        prev_leader = state.leader

    if pbp_events:
        last_event = pbp_events[-1]
        final_home = last_event.get("home_score", 0) or 0
        final_away = last_event.get("away_score", 0) or 0
        signals.final_margin = abs(final_home - final_away)

        if final_home > final_away:
            signals.max_deficit_overcome = max_home_deficit
        else:
            signals.max_deficit_overcome = max_away_deficit

    if signals.total_plays > 0:
        signals.closeness_duration = signals.plays_in_close_range / signals.total_plays

    signals.lead_change_score = signals.total_lead_changes + signals.late_lead_changes

    max_quarter = max(
        (e.get("quarter", 1) or 1 for e in pbp_events),
        default=4,
    )
    if max_quarter > 4:
        signals.has_overtime = True
        signals.overtime_periods = max_quarter - 4

    return signals


def compute_dynamic_budget(
    signals: GameSignals,
    config: BudgetConfig = DEFAULT_BUDGET_CONFIG,
) -> DynamicBudget:
    """Compute target moment count from game signals."""
    budget = DynamicBudget()
    budget.signals = signals
    budget.base_budget = config.base_budget
    budget.min_bound = config.min_budget
    budget.max_bound = config.max_budget

    score = float(config.base_budget)

    # 1. Final margin adjustment
    if signals.final_margin >= config.margin_blowout_threshold:
        budget.margin_adjustment = config.margin_blowout_penalty
    elif signals.final_margin <= config.margin_close_threshold:
        budget.margin_adjustment = config.margin_close_bonus
    else:
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
        range_size = config.closeness_high_threshold - config.closeness_low_threshold
        position = (
            signals.closeness_duration - config.closeness_low_threshold
        ) / range_size
        budget.closeness_adjustment = (
            config.closeness_onesided_penalty
            + (config.closeness_thriller_bonus - config.closeness_onesided_penalty)
            * position
        )

    score += budget.closeness_adjustment

    # 3. Lead change adjustment
    if signals.lead_change_score > config.lead_changes_high_threshold:
        excess = signals.lead_change_score - config.lead_changes_high_threshold
        budget.lead_change_adjustment = min(
            excess * config.lead_changes_bonus_per, config.lead_changes_cap
        )

    score += budget.lead_change_adjustment

    # 4. Overtime adjustment
    if signals.has_overtime:
        budget.overtime_adjustment = min(
            signals.overtime_periods * config.overtime_bonus_per_period,
            config.overtime_cap,
        )

    score += budget.overtime_adjustment

    # 5. Comeback adjustment
    if signals.max_deficit_overcome >= config.comeback_significant_threshold:
        budget.comeback_adjustment = config.comeback_bonus

    score += budget.comeback_adjustment

    budget.raw_budget_score = score

    if score < config.min_budget:
        budget.target_moment_count = config.min_budget
        budget.was_clamped_low = True
    elif score > config.max_budget:
        budget.target_moment_count = config.max_budget
        budget.was_clamped_high = True
    else:
        budget.target_moment_count = round(score)

    return budget
