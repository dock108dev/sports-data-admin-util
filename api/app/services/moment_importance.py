"""Moment Importance Scoring - Phase 2.1

This module computes a quantitative, explainable importance score for every
moment candidate so the system can later decide what is worth telling.

PHASE 2.1 SCOPE:
- Compute importance_score for every moment
- Produce a breakdown of contributing factors
- Store score + breakdown in diagnostics and payload

PHASE 2.1 NON-GOALS:
- Does NOT decide which moments survive
- Does NOT change budgets or merging
- Does NOT reorder anything

SCORING SIGNALS:
1. Time Remaining Weight (Late > Early)
2. Margin / Tier Context
3. Lead Change / Tie Context
4. Run Magnitude & Run vs Response
5. High-Impact Play Types
6. Volatility / Back-and-Forth Cluster

All weights are configurable. Scores are deterministic and explainable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION - All weights are configurable
# =============================================================================


@dataclass
class ImportanceWeights:
    """Configurable weights for importance scoring components.
    
    Tune these to adjust relative importance of different factors.
    All weights should be non-negative. Sum need not equal 1.0.
    """
    
    # Time weight: How much late-game matters more than early-game
    time_weight_base: float = 1.0          # Base weight for time factor
    time_weight_late_game_multiplier: float = 3.0  # Extra boost for Q4/OT
    time_weight_final_minutes_bonus: float = 2.0   # Extra for < 5 min remaining
    time_weight_overtime_bonus: float = 1.5        # Additional for overtime
    
    # Margin/tier weight: How much close games matter
    margin_weight_base: float = 1.5        # Base weight for margin factor
    margin_tier_0_bonus: float = 2.0       # Tier 0 (very close) bonus
    margin_tier_1_bonus: float = 1.5       # Tier 1 (close) bonus
    margin_tier_change_bonus: float = 0.5  # Bonus per tier changed
    
    # Lead change weight: Value of flips and ties
    lead_change_weight: float = 2.0        # Base weight for lead changes
    tie_creation_bonus: float = 1.0        # Extra for creating a tie
    tie_breaking_bonus: float = 0.8        # Extra for breaking a tie
    flip_bonus: float = 1.5                # Extra for lead flips
    
    # Run weight: Value of scoring runs
    run_weight_base: float = 0.1           # Per point scored in run
    run_unanswered_multiplier: float = 1.5  # Multiplier for unanswered runs
    run_reversal_bonus: float = 1.0        # Bonus for runs that reverse momentum
    
    # High-impact weight: Value of special events
    high_impact_weight: float = 2.0        # Weight for high-impact plays
    high_impact_cap: float = 4.0           # Max contribution from high-impact
    
    # Volatility weight: Value of back-and-forth action
    volatility_weight_base: float = 0.3    # Per lead change in window
    volatility_cap: float = 2.0            # Max contribution from volatility


# Default weights instance
DEFAULT_WEIGHTS = ImportanceWeights()


# =============================================================================
# IMPORTANCE FACTORS - Breakdown of score components
# =============================================================================


@dataclass
class ImportanceFactors:
    """Breakdown of importance score components.
    
    Each factor is logged separately for explainability.
    """
    
    # Time component
    time_weight: float = 0.0
    game_progress: float = 0.0         # 0.0 to 1.0+
    quarter: int | None = None
    seconds_remaining: int | None = None
    is_overtime: bool = False
    is_final_minutes: bool = False
    
    # Margin component
    margin_weight: float = 0.0
    tier_before: int = 0
    tier_after: int = 0
    margin_before: int = 0
    margin_after: int = 0
    tier_delta: int = 0
    
    # Lead change component
    lead_change_bonus: float = 0.0
    lead_changed: bool = False
    tie_created: bool = False
    tie_broken: bool = False
    is_flip: bool = False
    
    # Run component
    run_bonus: float = 0.0
    run_points: int = 0
    run_team: str = ""
    run_unanswered: bool = False
    run_is_reversal: bool = False
    
    # High-impact component
    high_impact_bonus: float = 0.0
    high_impact_events: list[str] = field(default_factory=list)
    high_impact_count: int = 0
    
    # Volatility component
    volatility_bonus: float = 0.0
    lead_changes_in_window: int = 0
    ties_in_window: int = 0
    volatility_score: float = 0.0
    
    # Total score
    importance_score: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response and diagnostics."""
        return {
            "importance_score": round(self.importance_score, 2),
            "time": {
                "weight": round(self.time_weight, 2),
                "game_progress": round(self.game_progress, 3),
                "quarter": self.quarter,
                "seconds_remaining": self.seconds_remaining,
                "is_overtime": self.is_overtime,
                "is_final_minutes": self.is_final_minutes,
            },
            "margin": {
                "weight": round(self.margin_weight, 2),
                "tier_before": self.tier_before,
                "tier_after": self.tier_after,
                "margin_before": self.margin_before,
                "margin_after": self.margin_after,
                "tier_delta": self.tier_delta,
            },
            "lead_change": {
                "bonus": round(self.lead_change_bonus, 2),
                "lead_changed": self.lead_changed,
                "tie_created": self.tie_created,
                "tie_broken": self.tie_broken,
                "is_flip": self.is_flip,
            },
            "run": {
                "bonus": round(self.run_bonus, 2),
                "points": self.run_points,
                "team": self.run_team,
                "unanswered": self.run_unanswered,
                "is_reversal": self.run_is_reversal,
            },
            "high_impact": {
                "bonus": round(self.high_impact_bonus, 2),
                "events": self.high_impact_events,
                "count": self.high_impact_count,
            },
            "volatility": {
                "bonus": round(self.volatility_bonus, 2),
                "lead_changes_in_window": self.lead_changes_in_window,
                "ties_in_window": self.ties_in_window,
                "volatility_score": round(self.volatility_score, 2),
            },
        }


# =============================================================================
# SIGNAL COMPUTATION FUNCTIONS
# =============================================================================


def _compute_time_weight(
    game_progress: float,
    quarter: int | None,
    seconds_remaining: int | None,
    weights: ImportanceWeights,
) -> tuple[float, dict[str, Any]]:
    """Compute time-based importance weight.
    
    Late-game moments are more important than early-game.
    Overtime is more important than regulation.
    
    Returns:
        Tuple of (weight, diagnostic_info)
    """
    weight = weights.time_weight_base
    is_overtime = False
    is_final_minutes = False
    
    # Non-linear increase as game progresses
    # Use exponential curve: importance grows faster late in game
    if game_progress <= 0.5:
        # First half: low importance
        time_factor = 0.5 + (game_progress * 0.5)  # 0.5 to 0.75
    elif game_progress <= 0.75:
        # Third quarter: moderate importance
        time_factor = 0.75 + ((game_progress - 0.5) * 1.0)  # 0.75 to 1.0
    elif game_progress <= 1.0:
        # Fourth quarter: high importance
        time_factor = 1.0 + ((game_progress - 0.75) * weights.time_weight_late_game_multiplier)
    else:
        # Overtime: very high importance
        is_overtime = True
        time_factor = 1.0 + weights.time_weight_late_game_multiplier + weights.time_weight_overtime_bonus
    
    weight *= time_factor
    
    # Bonus for final minutes (< 5 min in Q4 or OT)
    if quarter and quarter >= 4:
        if seconds_remaining is not None and seconds_remaining <= 300:
            is_final_minutes = True
            weight += weights.time_weight_final_minutes_bonus
            
            # Extra bonus for final minute
            if seconds_remaining <= 60:
                weight += weights.time_weight_final_minutes_bonus * 0.5
    
    return weight, {
        "is_overtime": is_overtime,
        "is_final_minutes": is_final_minutes,
    }


def _compute_margin_weight(
    tier_before: int,
    tier_after: int,
    margin_before: int,
    margin_after: int,
    weights: ImportanceWeights,
) -> tuple[float, dict[str, Any]]:
    """Compute margin/tier-based importance weight.
    
    Close games (lower tiers) are more important.
    Tier changes add importance, but blowouts are penalized.
    
    Returns:
        Tuple of (weight, diagnostic_info)
    """
    weight = weights.margin_weight_base
    
    # Use the ENDING tier to determine current game state
    # A moment that ends in tier 3+ is less interesting regardless of where it started
    end_tier = tier_after
    
    # Tier-based bonuses (close games matter more)
    if end_tier == 0:
        weight += weights.margin_tier_0_bonus
    elif end_tier == 1:
        weight += weights.margin_tier_1_bonus
    elif end_tier >= 3:
        # Blowouts are less interesting - heavy penalty
        weight *= 0.3
    
    # Tier change bonus - but only if moving toward closer game
    tier_delta = abs(tier_after - tier_before)
    if tier_after < tier_before:
        # Game getting closer - this is dramatic
        weight += tier_delta * weights.margin_tier_change_bonus
    elif tier_after > tier_before and end_tier >= 3:
        # Game becoming a blowout - less interesting
        weight -= tier_delta * 0.2
    
    return weight, {
        "tier_delta": tier_delta,
    }


def _compute_lead_change_weight(
    moment_type: str,
    leader_before: str | None,
    leader_after: str | None,
    was_tied_before: bool,
    is_tied_after: bool,
    weights: ImportanceWeights,
) -> tuple[float, dict[str, Any]]:
    """Compute lead change/tie importance weight.
    
    Lead changes and ties add drama.
    
    Returns:
        Tuple of (weight, diagnostic_info)
    """
    weight = 0.0
    lead_changed = False
    tie_created = False
    tie_broken = False
    is_flip = False
    
    # Check for lead change
    if leader_before != leader_after and leader_before and leader_after:
        lead_changed = True
        weight += weights.lead_change_weight
    
    # Check for FLIP moment type
    if moment_type in ("FLIP", "CLOSING_CONTROL"):
        is_flip = True
        weight += weights.flip_bonus
    
    # Tie creation
    if is_tied_after and not was_tied_before:
        tie_created = True
        weight += weights.tie_creation_bonus
    
    # Tie breaking
    if was_tied_before and not is_tied_after:
        tie_broken = True
        weight += weights.tie_breaking_bonus
    
    return weight, {
        "lead_changed": lead_changed,
        "tie_created": tie_created,
        "tie_broken": tie_broken,
        "is_flip": is_flip,
    }


def _compute_run_weight(
    run_points: int,
    run_team: str,
    run_unanswered: bool,
    previous_run_team: str | None,
    weights: ImportanceWeights,
) -> tuple[float, dict[str, Any]]:
    """Compute scoring run importance weight.
    
    Larger runs are more important.
    Unanswered runs are more dramatic.
    Runs that reverse momentum are most important.
    
    Returns:
        Tuple of (weight, diagnostic_info)
    """
    if run_points <= 0:
        return 0.0, {"is_reversal": False}
    
    weight = run_points * weights.run_weight_base
    
    # Unanswered runs are more impactful
    if run_unanswered:
        weight *= weights.run_unanswered_multiplier
    
    # Check for momentum reversal (run by team that was being run on)
    is_reversal = previous_run_team is not None and previous_run_team != run_team
    if is_reversal:
        weight += weights.run_reversal_bonus
    
    return weight, {
        "is_reversal": is_reversal,
    }


def _compute_high_impact_weight(
    high_impact_events: list[str],
    weights: ImportanceWeights,
) -> tuple[float, dict[str, Any]]:
    """Compute high-impact play importance weight.
    
    Special events (ejections, flagrants, etc.) add importance.
    
    Returns:
        Tuple of (weight, diagnostic_info)
    """
    if not high_impact_events:
        return 0.0, {"count": 0}
    
    count = len(high_impact_events)
    weight = min(
        count * weights.high_impact_weight,
        weights.high_impact_cap,
    )
    
    return weight, {"count": count}


def _compute_volatility_weight(
    lead_changes_in_window: int,
    ties_in_window: int,
    weights: ImportanceWeights,
) -> tuple[float, dict[str, Any]]:
    """Compute volatility/back-and-forth importance weight.
    
    Rapid momentum swings add drama.
    
    Returns:
        Tuple of (weight, diagnostic_info)
    """
    volatility_score = lead_changes_in_window + (ties_in_window * 0.5)
    
    weight = min(
        volatility_score * weights.volatility_weight_base,
        weights.volatility_cap,
    )
    
    return weight, {"volatility_score": volatility_score}


# =============================================================================
# MAIN SCORING FUNCTION
# =============================================================================


def compute_importance(
    moment: Any,  # Moment dataclass
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    weights: ImportanceWeights = DEFAULT_WEIGHTS,
    context: dict[str, Any] | None = None,
) -> ImportanceFactors:
    """Compute importance score and factors for a moment.
    
    This is the main entry point for importance scoring.
    
    Args:
        moment: The Moment object to score
        events: Timeline events for context lookup
        thresholds: Lead Ladder thresholds for tier calculation
        weights: Configurable weights (defaults to DEFAULT_WEIGHTS)
        context: Optional additional context (previous_run_team, etc.)
    
    Returns:
        ImportanceFactors with score and full breakdown
    """
    from .moments import _get_game_progress
    from ..utils.datetime_utils import parse_clock_to_seconds
    
    factors = ImportanceFactors()
    context = context or {}
    
    # Get moment data
    start_idx = moment.start_play
    end_idx = moment.end_play
    moment_type = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)
    
    # Get reference event (use end event for timing context)
    end_event = events[end_idx] if 0 <= end_idx < len(events) else {}
    
    # === 1. TIME WEIGHT ===
    game_progress = _get_game_progress(end_event)
    quarter = end_event.get("quarter")
    clock = end_event.get("game_clock", "")
    seconds_remaining = parse_clock_to_seconds(clock)
    
    time_weight, time_info = _compute_time_weight(
        game_progress, quarter, seconds_remaining, weights
    )
    factors.time_weight = time_weight
    factors.game_progress = game_progress
    factors.quarter = quarter
    factors.seconds_remaining = seconds_remaining
    factors.is_overtime = time_info["is_overtime"]
    factors.is_final_minutes = time_info["is_final_minutes"]
    
    # === 2. MARGIN WEIGHT ===
    tier_before = moment.ladder_tier_before
    tier_after = moment.ladder_tier_after
    
    # Compute margins from scores
    score_before = moment.score_before
    score_after = moment.score_after
    margin_before = abs(score_before[0] - score_before[1]) if score_before else 0
    margin_after = abs(score_after[0] - score_after[1]) if score_after else 0
    
    margin_weight, margin_info = _compute_margin_weight(
        tier_before, tier_after, margin_before, margin_after, weights
    )
    factors.margin_weight = margin_weight
    factors.tier_before = tier_before
    factors.tier_after = tier_after
    factors.margin_before = margin_before
    factors.margin_after = margin_after
    factors.tier_delta = margin_info["tier_delta"]
    
    # === 3. LEAD CHANGE WEIGHT ===
    # Determine leaders
    def get_leader(home: int, away: int) -> tuple[str | None, bool]:
        if home > away:
            return "home", False
        elif away > home:
            return "away", False
        else:
            return None, True
    
    leader_before, was_tied_before = get_leader(score_before[0], score_before[1]) if score_before else (None, True)
    leader_after, is_tied_after = get_leader(score_after[0], score_after[1]) if score_after else (None, True)
    
    lead_change_weight, lead_info = _compute_lead_change_weight(
        moment_type, leader_before, leader_after, was_tied_before, is_tied_after, weights
    )
    factors.lead_change_bonus = lead_change_weight
    factors.lead_changed = lead_info["lead_changed"]
    factors.tie_created = lead_info["tie_created"]
    factors.tie_broken = lead_info["tie_broken"]
    factors.is_flip = lead_info["is_flip"]
    
    # === 4. RUN WEIGHT ===
    run_points = 0
    run_team = ""
    run_unanswered = False
    
    if moment.run_info:
        run_points = moment.run_info.points
        run_team = moment.run_info.team
        run_unanswered = moment.run_info.unanswered
    
    previous_run_team = context.get("previous_run_team")
    
    run_weight, run_info = _compute_run_weight(
        run_points, run_team, run_unanswered, previous_run_team, weights
    )
    factors.run_bonus = run_weight
    factors.run_points = run_points
    factors.run_team = run_team
    factors.run_unanswered = run_unanswered
    factors.run_is_reversal = run_info["is_reversal"]
    
    # === 5. HIGH-IMPACT WEIGHT ===
    high_impact_events = context.get("high_impact_events", [])
    
    # Also check moment type
    if moment_type == "HIGH_IMPACT":
        if moment.note and moment.note not in high_impact_events:
            high_impact_events = high_impact_events + [moment.note]
    
    high_impact_weight, hi_info = _compute_high_impact_weight(high_impact_events, weights)
    factors.high_impact_bonus = high_impact_weight
    factors.high_impact_events = high_impact_events
    factors.high_impact_count = hi_info["count"]
    
    # === 6. VOLATILITY WEIGHT ===
    lead_changes_in_window = context.get("lead_changes_in_window", 0)
    ties_in_window = context.get("ties_in_window", 0)
    
    # Count lead changes within moment's play range
    if not lead_changes_in_window:
        lead_changes_in_window, ties_in_window = _count_volatility_in_range(
            events, start_idx, end_idx, thresholds
        )
    
    volatility_weight, vol_info = _compute_volatility_weight(
        lead_changes_in_window, ties_in_window, weights
    )
    factors.volatility_bonus = volatility_weight
    factors.lead_changes_in_window = lead_changes_in_window
    factors.ties_in_window = ties_in_window
    factors.volatility_score = vol_info["volatility_score"]
    
    # === TOTAL SCORE ===
    factors.importance_score = (
        factors.time_weight +
        factors.margin_weight +
        factors.lead_change_bonus +
        factors.run_bonus +
        factors.high_impact_bonus +
        factors.volatility_bonus
    )
    
    return factors


def _count_volatility_in_range(
    events: Sequence[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    thresholds: Sequence[int],
) -> tuple[int, int]:
    """Count lead changes and ties within a play range.
    
    Returns:
        Tuple of (lead_changes, ties)
    """
    from .lead_ladder import compute_lead_state, Leader
    
    lead_changes = 0
    ties = 0
    prev_leader: Leader | None = None
    
    for i in range(start_idx, min(end_idx + 1, len(events))):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue
        
        home = event.get("home_score", 0) or 0
        away = event.get("away_score", 0) or 0
        
        state = compute_lead_state(home, away, thresholds)
        
        if state.leader == Leader.TIED:
            ties += 1
        elif prev_leader is not None and state.leader != prev_leader and prev_leader != Leader.TIED:
            lead_changes += 1
        
        prev_leader = state.leader
    
    return lead_changes, ties


# =============================================================================
# BATCH SCORING FUNCTION
# =============================================================================


def score_all_moments(
    moments: list[Any],  # List of Moment objects
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    weights: ImportanceWeights = DEFAULT_WEIGHTS,
) -> list[ImportanceFactors]:
    """Score all moments in a game.
    
    This handles context passing between moments (e.g., previous_run_team).
    
    Args:
        moments: List of Moment objects to score
        events: Timeline events
        thresholds: Lead Ladder thresholds
        weights: Configurable weights
    
    Returns:
        List of ImportanceFactors corresponding to each moment
    """
    results: list[ImportanceFactors] = []
    previous_run_team: str | None = None
    
    for moment in moments:
        context = {
            "previous_run_team": previous_run_team,
        }
        
        factors = compute_importance(moment, events, thresholds, weights, context)
        results.append(factors)
        
        # Track for next iteration
        if moment.run_info:
            previous_run_team = moment.run_info.team
    
    return results


def log_importance_summary(
    moments: list[Any],
    factors_list: list[ImportanceFactors],
) -> None:
    """Log a summary of importance scores for debugging."""
    if not moments or not factors_list:
        return
    
    scores = [f.importance_score for f in factors_list]
    avg_score = sum(scores) / len(scores)
    max_score = max(scores)
    min_score = min(scores)
    
    logger.info(
        "importance_scoring_summary",
        extra={
            "total_moments": len(moments),
            "avg_score": round(avg_score, 2),
            "max_score": round(max_score, 2),
            "min_score": round(min_score, 2),
            "score_distribution": {
                "low": len([s for s in scores if s < 3]),
                "medium": len([s for s in scores if 3 <= s < 6]),
                "high": len([s for s in scores if s >= 6]),
            },
        },
    )
