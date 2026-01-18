"""Moment Construction Trace - Explainability Layer.

Every generated moment should be fully explainable. This module provides
data structures and utilities for capturing the complete construction
trace of each moment, including:

1. TRIGGER REASONS - What signal caused this moment to be created
2. INPUT PLAY RANGE - Which plays were considered
3. SIGNALS USED - Lead states, tier crossings, runs that influenced the moment
4. VALIDATION RESULTS - Pass/fail status and any issues detected

Additionally, this module tracks:
- REJECTED MOMENTS - Moments that were generated but rejected during validation
- MERGED MOMENTS - Moments that were combined during budget enforcement

PHASE 0 ENHANCEMENTS (Guardrails & Observability)
=================================================
- trigger_types: List of triggers that caused this moment
- importance_score: Numeric placeholder for future importance weighting
- merge_history: Ordered list of merge events with phase and reason
- budget_pressure: Whether this moment was affected by budget enforcement
- moment_distribution: Aggregate metrics for pacing analysis

This enables full auditability of the moment generation pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class TraceAction(str, Enum):
    """Actions taken during moment generation."""
    
    CREATED = "created"          # Moment was initially created
    VALIDATED = "validated"      # Moment passed validation
    REJECTED = "rejected"        # Moment was rejected (with reason)
    MERGED_INTO = "merged_into"  # Moment was merged into another
    ABSORBED = "absorbed"        # Moment absorbed another (merged from)
    SPLIT_FROM = "split_from"    # Moment was split from a mega-moment
    BUDGET_CLAMP = "budget_clamp"  # Moment was removed due to budget
    QUARTER_LIMIT = "quarter_limit"  # Moment removed due to quarter limit


class RejectionReason(str, Enum):
    """Reasons why a moment was rejected."""
    
    NO_CAUSAL_TRIGGER = "no_causal_trigger"  # Missing or invalid trigger
    NO_PARTICIPANTS = "no_participants"       # No teams/players
    MICRO_MOMENT = "micro_moment"            # Too few plays (< 2)
    NO_NARRATIVE_CHANGE = "no_narrative_change"  # No score/tier change
    BUDGET_EXCEEDED = "budget_exceeded"       # Budget enforcement
    QUARTER_LIMIT_EXCEEDED = "quarter_limit_exceeded"
    INVALID_SCORE_CONTINUITY = "invalid_score_continuity"


class MergePhase(str, Enum):
    """Phase during which a merge occurred."""
    
    SAME_TYPE = "same_type"                  # Merged consecutive same-type moments
    INVALID_ABSORPTION = "invalid_absorption"  # Invalid moment absorbed into valid
    QUARTER_LIMIT = "quarter_limit"          # Merged due to per-quarter limit
    BUDGET_PHASE_1 = "budget_phase_1"        # Soft merge (NEUTRAL sequences)
    BUDGET_PHASE_2 = "budget_phase_2"        # Hard clamp (same-type consecutive)
    BUDGET_PHASE_3 = "budget_phase_3"        # Nuclear (any consecutive)


# =============================================================================
# SIGNAL SNAPSHOT
# =============================================================================


@dataclass
class SignalSnapshot:
    """Snapshot of signals at a specific point during moment creation.
    
    Captures the Lead Ladder state and any tier crossings that influenced
    the moment boundary decision.
    """
    
    # Lead state at moment start
    start_lead_state: dict[str, Any] = field(default_factory=dict)
    # Lead state at moment end
    end_lead_state: dict[str, Any] = field(default_factory=dict)
    # Tier crossing that triggered this moment (if any)
    tier_crossing: dict[str, Any] | None = None
    # Detected runs within this moment
    runs: list[dict[str, Any]] = field(default_factory=list)
    # Thresholds used for lead ladder calculation
    thresholds: list[int] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "start_lead_state": self.start_lead_state,
            "end_lead_state": self.end_lead_state,
            "tier_crossing": self.tier_crossing,
            "runs": self.runs,
            "thresholds": self.thresholds,
        }


# =============================================================================
# VALIDATION RESULT
# =============================================================================


@dataclass
class ValidationResult:
    """Result of validating a moment."""
    
    passed: bool
    checks_performed: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks_performed": self.checks_performed,
            "issues": self.issues,
            "warnings": self.warnings,
        }


# =============================================================================
# MERGE EVENT
# =============================================================================


@dataclass
class MergeEvent:
    """Record of a single merge operation.
    
    Tracks what was merged, when, and why.
    """
    
    merged_moment_id: str          # ID of the moment that was merged INTO another
    merged_into_id: str            # ID of the moment that absorbed this one
    phase: MergePhase              # Which phase triggered this merge
    reason: str                    # Human-readable reason
    timestamp: str = ""            # When the merge occurred
    pre_merge_type: str = ""       # Type of moment before merge
    post_merge_type: str = ""      # Type of resulting merged moment
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "merged_moment_id": self.merged_moment_id,
            "merged_into_id": self.merged_into_id,
            "phase": self.phase.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "pre_merge_type": self.pre_merge_type,
            "post_merge_type": self.post_merge_type,
        }


# =============================================================================
# BUDGET PRESSURE
# =============================================================================


@dataclass
class BudgetPressure:
    """Tracks how budget enforcement affected a moment.
    
    For any moment, this captures:
    - Whether it survived budget enforcement
    - What phase affected it (if merged)
    - The budget state at time of enforcement
    """
    
    # Was this moment subject to budget pressure?
    under_pressure: bool = False
    # Did this moment survive budget enforcement?
    survived: bool = True
    # Was this moment merged due to budget?
    merged_due_to_budget: bool = False
    # Did this moment displace another?
    displaced_moment_id: str | None = None
    # Total moments before budget enforcement
    total_pre_budget: int = 0
    # Target budget
    target_budget: int = 0
    # Which enforcement phase affected this moment
    enforcement_phase: MergePhase | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "under_pressure": self.under_pressure,
            "survived": self.survived,
            "merged_due_to_budget": self.merged_due_to_budget,
            "displaced_moment_id": self.displaced_moment_id,
            "total_pre_budget": self.total_pre_budget,
            "target_budget": self.target_budget,
            "enforcement_phase": self.enforcement_phase.value if self.enforcement_phase else None,
        }


# =============================================================================
# MOMENT TRACE
# =============================================================================


@dataclass
class MomentTrace:
    """Complete construction trace for a single moment.
    
    This captures everything about how and why a moment was created,
    enabling full explainability and debugging.
    """
    
    # Moment identification
    moment_id: str
    moment_type: str
    
    # Input play range (indices into timeline)
    input_start_idx: int
    input_end_idx: int
    play_count: int
    
    # What triggered this moment's creation
    trigger_type: str  # "tier_cross", "flip", "tie", "closing_lock", "high_impact", "stable"
    trigger_description: str
    
    # === PHASE 0 ADDITIONS ===
    
    # All trigger types that contributed to this moment
    # A moment may have multiple triggers (e.g., TIER_UP during a RUN)
    trigger_types: list[str] = field(default_factory=list)
    
    # Importance score (placeholder for future weighting)
    # Currently constant, but must exist for future phases
    importance_score: float = 1.0
    
    # PHASE 2.1: Full breakdown of importance factors
    importance_factors: dict[str, Any] = field(default_factory=dict)
    
    # Ordered history of merge events affecting this moment
    merge_history: list[MergeEvent] = field(default_factory=list)
    
    # Budget pressure tracking
    budget_pressure: BudgetPressure = field(default_factory=BudgetPressure)
    
    # Quarter this moment belongs to (for distribution analysis)
    quarter: int | None = None
    
    # === END PHASE 0 ADDITIONS ===
    
    # Signals that influenced this moment
    signals: SignalSnapshot = field(default_factory=SignalSnapshot)
    
    # Validation results
    validation: ValidationResult = field(default_factory=lambda: ValidationResult(passed=True))
    
    # Action history (what happened to this moment)
    actions: list[dict[str, Any]] = field(default_factory=list)
    
    # Final status
    is_final: bool = False  # True if this moment made it to the final output
    final_moment_id: str | None = None  # ID in final output (may differ if renumbered)
    
    # If rejected or merged
    rejection_reason: str | None = None
    merged_into_id: str | None = None
    absorbed_moment_ids: list[str] = field(default_factory=list)
    
    # Timestamps
    created_at: str = ""
    
    def add_action(self, action: TraceAction, details: dict[str, Any] | None = None) -> None:
        """Record an action taken on this moment."""
        self.actions.append({
            "action": action.value,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        })
    
    def add_merge_event(
        self,
        merged_into_id: str,
        phase: MergePhase,
        reason: str,
        pre_merge_type: str = "",
        post_merge_type: str = "",
    ) -> None:
        """Record a merge event affecting this moment."""
        event = MergeEvent(
            merged_moment_id=self.moment_id,
            merged_into_id=merged_into_id,
            phase=phase,
            reason=reason,
            timestamp=datetime.utcnow().isoformat(),
            pre_merge_type=pre_merge_type,
            post_merge_type=post_merge_type,
        )
        self.merge_history.append(event)
    
    def set_budget_pressure(
        self,
        total_pre_budget: int,
        target_budget: int,
        survived: bool = True,
        merged_due_to_budget: bool = False,
        enforcement_phase: MergePhase | None = None,
        displaced_moment_id: str | None = None,
    ) -> None:
        """Set budget pressure information for this moment."""
        self.budget_pressure = BudgetPressure(
            under_pressure=total_pre_budget > target_budget,
            survived=survived,
            merged_due_to_budget=merged_due_to_budget,
            displaced_moment_id=displaced_moment_id,
            total_pre_budget=total_pre_budget,
            target_budget=target_budget,
            enforcement_phase=enforcement_phase,
        )
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "moment_type": self.moment_type,
            "input_start_idx": self.input_start_idx,
            "input_end_idx": self.input_end_idx,
            "play_count": self.play_count,
            "trigger_type": self.trigger_type,
            "trigger_description": self.trigger_description,
            # Phase 0 additions
            "trigger_types": self.trigger_types,
            "importance_score": round(self.importance_score, 2),
            "importance_factors": self.importance_factors,  # PHASE 2.1
            "merge_history": [e.to_dict() for e in self.merge_history],
            "budget_pressure": self.budget_pressure.to_dict(),
            "quarter": self.quarter,
            # Original fields
            "signals": self.signals.to_dict(),
            "validation": self.validation.to_dict(),
            "actions": self.actions,
            "is_final": self.is_final,
            "final_moment_id": self.final_moment_id,
            "rejection_reason": self.rejection_reason,
            "merged_into_id": self.merged_into_id,
            "absorbed_moment_ids": self.absorbed_moment_ids,
            "created_at": self.created_at,
        }


# =============================================================================
# MOMENT DISTRIBUTION METRICS
# =============================================================================


@dataclass
class MomentDistribution:
    """Aggregate metrics about moment distribution.
    
    This enables instant detection of pacing problems without
    reading individual moments.
    """
    
    # Count per quarter/period
    moments_per_quarter: dict[str, int] = field(default_factory=dict)
    
    # Count per trigger type
    moments_by_trigger_type: dict[str, int] = field(default_factory=dict)
    
    # Count per tier (tier at end of moment)
    moments_by_tier: dict[int, int] = field(default_factory=dict)
    
    # Average plays per moment
    average_plays_per_moment: float = 0.0
    
    # First half vs second half distribution
    first_half_moment_count: int = 0
    second_half_moment_count: int = 0
    overtime_moment_count: int = 0
    first_half_percentage: float = 0.0
    
    # Budget utilization
    total_moments: int = 0
    budget: int = 0
    budget_utilization_percentage: float = 0.0
    
    # Merge statistics
    total_moments_before_merge: int = 0
    total_merged: int = 0
    merge_ratio: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moments_per_quarter": self.moments_per_quarter,
            "moments_by_trigger_type": self.moments_by_trigger_type,
            "moments_by_tier": {str(k): v for k, v in self.moments_by_tier.items()},
            "average_plays_per_moment": round(self.average_plays_per_moment, 2),
            "first_half_vs_second_half": {
                "first_half": self.first_half_moment_count,
                "second_half": self.second_half_moment_count,
                "overtime": self.overtime_moment_count,
                "first_half_percentage": round(self.first_half_percentage, 1),
            },
            "budget_utilization": {
                "total_moments": self.total_moments,
                "budget": self.budget,
                "utilization_percentage": round(self.budget_utilization_percentage, 1),
            },
            "merge_statistics": {
                "total_before_merge": self.total_moments_before_merge,
                "total_merged": self.total_merged,
                "merge_ratio": round(self.merge_ratio, 2),
            },
        }


# =============================================================================
# GENERATION TRACE
# =============================================================================


@dataclass
class GenerationTrace:
    """Complete trace of a moment generation run.
    
    Captures all moments created, rejected, and merged during a single
    execution of the partition_game algorithm.
    """
    
    # Run identification
    game_id: int
    pipeline_run_id: int | None = None
    
    # Input summary
    total_timeline_events: int = 0
    pbp_event_count: int = 0
    
    # Configuration used
    thresholds: list[int] = field(default_factory=list)
    budget: int = 0
    sport: str = "NBA"
    
    # All moment traces (keyed by original moment_id)
    moment_traces: dict[str, MomentTrace] = field(default_factory=dict)
    
    # Summary statistics
    initial_moment_count: int = 0
    rejected_count: int = 0
    merged_count: int = 0
    final_moment_count: int = 0
    
    # Phase 0: Moment distribution metrics
    distribution: MomentDistribution = field(default_factory=MomentDistribution)
    
    # Timing
    started_at: str = ""
    finished_at: str = ""
    
    def add_moment_trace(self, trace: MomentTrace) -> None:
        """Add a moment trace."""
        self.moment_traces[trace.moment_id] = trace
    
    def get_rejected_moments(self) -> list[MomentTrace]:
        """Get all rejected moments."""
        return [
            t for t in self.moment_traces.values()
            if t.rejection_reason is not None
        ]
    
    def get_merged_moments(self) -> list[MomentTrace]:
        """Get all moments that were merged into others."""
        return [
            t for t in self.moment_traces.values()
            if t.merged_into_id is not None
        ]
    
    def get_final_moments(self) -> list[MomentTrace]:
        """Get traces for moments that made it to final output."""
        return [
            t for t in self.moment_traces.values()
            if t.is_final
        ]
    
    def compute_distribution(
        self,
        moments: list[dict[str, Any]],
        events: list[dict[str, Any]] | None = None,
    ) -> MomentDistribution:
        """Compute moment distribution metrics from final moments.
        
        Args:
            moments: List of final moment dicts
            events: Optional timeline events for quarter lookup
            
        Returns:
            Populated MomentDistribution
        """
        dist = MomentDistribution()
        
        if not moments:
            return dist
        
        # Initialize counters
        quarters: dict[str, int] = {}
        triggers: dict[str, int] = {}
        tiers: dict[int, int] = {}
        total_plays = 0
        
        for moment in moments:
            # Count by quarter
            quarter = self._get_quarter_for_moment(moment, events)
            quarter_key = f"Q{quarter}" if quarter and quarter <= 4 else f"OT{quarter - 4}" if quarter else "unknown"
            quarters[quarter_key] = quarters.get(quarter_key, 0) + 1
            
            # Track half distribution
            if quarter:
                if quarter <= 2:
                    dist.first_half_moment_count += 1
                elif quarter <= 4:
                    dist.second_half_moment_count += 1
                else:
                    dist.overtime_moment_count += 1
            
            # Count by trigger type
            reason = moment.get("reason", {})
            trigger = reason.get("trigger", "unknown") if isinstance(reason, dict) else "unknown"
            triggers[trigger] = triggers.get(trigger, 0) + 1
            
            # Count by tier (end tier)
            tier = moment.get("ladder_tier_after", 0)
            tiers[tier] = tiers.get(tier, 0) + 1
            
            # Sum plays
            total_plays += moment.get("play_count", 0)
        
        # Populate distribution
        dist.moments_per_quarter = quarters
        dist.moments_by_trigger_type = triggers
        dist.moments_by_tier = tiers
        dist.total_moments = len(moments)
        dist.budget = self.budget
        
        if len(moments) > 0:
            dist.average_plays_per_moment = total_plays / len(moments)
        
        # Calculate percentages
        total_in_game = dist.first_half_moment_count + dist.second_half_moment_count
        if total_in_game > 0:
            dist.first_half_percentage = (dist.first_half_moment_count / total_in_game) * 100
        
        if self.budget > 0:
            dist.budget_utilization_percentage = (len(moments) / self.budget) * 100
        
        # Merge statistics
        dist.total_moments_before_merge = self.initial_moment_count
        dist.total_merged = self.merged_count
        if self.initial_moment_count > 0:
            dist.merge_ratio = self.merged_count / self.initial_moment_count
        
        self.distribution = dist
        return dist
    
    def _get_quarter_for_moment(
        self,
        moment: dict[str, Any],
        events: list[dict[str, Any]] | None,
    ) -> int | None:
        """Get the quarter for a moment based on its start play."""
        if events is None:
            # Try to extract from clock string (e.g., "Q1 12:00–10:30")
            clock = moment.get("clock", "")
            if clock.startswith("Q"):
                try:
                    return int(clock[1])
                except (ValueError, IndexError):
                    pass
            return None
        
        start_idx = moment.get("start_play", 0)
        if 0 <= start_idx < len(events):
            return events[start_idx].get("quarter")
        return None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "pipeline_run_id": self.pipeline_run_id,
            "total_timeline_events": self.total_timeline_events,
            "pbp_event_count": self.pbp_event_count,
            "thresholds": self.thresholds,
            "budget": self.budget,
            "sport": self.sport,
            "moment_traces": {
                k: v.to_dict() for k, v in self.moment_traces.items()
            },
            "summary": {
                "initial_moment_count": self.initial_moment_count,
                "rejected_count": self.rejected_count,
                "merged_count": self.merged_count,
                "final_moment_count": self.final_moment_count,
            },
            "distribution": self.distribution.to_dict(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
    
    def to_summary(self) -> dict[str, Any]:
        """Return a summary without full moment traces."""
        return {
            "game_id": self.game_id,
            "pipeline_run_id": self.pipeline_run_id,
            "pbp_event_count": self.pbp_event_count,
            "thresholds": self.thresholds,
            "budget": self.budget,
            "sport": self.sport,
            "summary": {
                "initial_moment_count": self.initial_moment_count,
                "rejected_count": self.rejected_count,
                "merged_count": self.merged_count,
                "final_moment_count": self.final_moment_count,
            },
            "distribution": self.distribution.to_dict(),
            "rejected_moment_ids": [t.moment_id for t in self.get_rejected_moments()],
            "merged_moment_ids": [t.moment_id for t in self.get_merged_moments()],
            "final_moment_ids": [t.final_moment_id for t in self.get_final_moments()],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


# =============================================================================
# TRACE BUILDER UTILITIES
# =============================================================================


def create_moment_trace_from_moment(
    moment: Any,  # Moment dataclass from moments.py
    signals: SignalSnapshot | None = None,
    events: list[dict[str, Any]] | None = None,
) -> MomentTrace:
    """Create a MomentTrace from a Moment object.
    
    Args:
        moment: The Moment object to create a trace for
        signals: Optional signal snapshot (if available)
        events: Optional timeline events for quarter lookup
    """
    # Determine trigger type and description from moment's reason
    trigger_type = "unknown"
    trigger_description = "No trigger information available"
    trigger_types: list[str] = []
    
    if hasattr(moment, 'reason') and moment.reason:
        trigger_type = moment.reason.trigger
        trigger_description = moment.reason.narrative_delta
        trigger_types.append(trigger_type.upper())
    
    # Add moment type as a trigger type if different
    if hasattr(moment, 'type'):
        moment_type_str = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)
        if moment_type_str not in trigger_types:
            trigger_types.append(moment_type_str)
    
    # PHASE 2.1: Use moment's actual importance if computed, otherwise default
    importance_score = 1.0
    importance_factors: dict[str, Any] = {}
    
    if hasattr(moment, 'importance_score') and moment.importance_score > 0:
        importance_score = moment.importance_score
    if hasattr(moment, 'importance_factors') and moment.importance_factors:
        importance_factors = moment.importance_factors
    
    # Get quarter if events available
    quarter = None
    if events and hasattr(moment, 'start_play'):
        start_idx = moment.start_play
        if 0 <= start_idx < len(events):
            quarter = events[start_idx].get("quarter")
    
    trace = MomentTrace(
        moment_id=moment.id,
        moment_type=moment.type.value if hasattr(moment.type, 'value') else str(moment.type),
        input_start_idx=moment.start_play,
        input_end_idx=moment.end_play,
        play_count=moment.play_count,
        trigger_type=trigger_type,
        trigger_description=trigger_description,
        trigger_types=trigger_types,
        importance_score=importance_score,
        importance_factors=importance_factors,  # PHASE 2.1
        quarter=quarter,
        signals=signals or SignalSnapshot(),
        created_at=datetime.utcnow().isoformat(),
    )
    
    trace.add_action(TraceAction.CREATED, {
        "type": trace.moment_type,
        "play_range": f"{moment.start_play}-{moment.end_play}",
        "score": f"{moment.score_before} → {moment.score_after}",
        "trigger_types": trigger_types,
    })
    
    return trace


def validate_moment_and_trace(
    moment: Any,  # Moment dataclass
    trace: MomentTrace,
) -> MomentTrace:
    """Run validation on a moment and update its trace.
    
    Args:
        moment: The Moment object to validate
        trace: The trace to update with validation results
    """
    from .moments_merging import is_valid_moment
    
    checks_performed = []
    issues = []
    warnings = []
    
    # Check 1: Causal trigger
    checks_performed.append("causal_trigger")
    if not moment.reason or moment.reason.trigger in ("unknown", "stable"):
        if moment.score_before == moment.score_after:
            issues.append("No causal trigger and no score change")
    
    # Check 2: Participants
    checks_performed.append("participants")
    if not moment.teams:
        issues.append("No teams identified")
    
    # Check 3: Micro-moment
    checks_performed.append("minimum_plays")
    if moment.play_count < 2:
        from .moments import MomentType
        if moment.type not in (MomentType.FLIP, MomentType.TIE, MomentType.CLOSING_CONTROL, MomentType.HIGH_IMPACT):
            issues.append(f"Micro-moment ({moment.play_count} plays) without high-impact type")
    
    # Check 4: Narrative change
    checks_performed.append("narrative_change")
    if moment.score_before == moment.score_after and moment.ladder_tier_before == moment.ladder_tier_after:
        from .moments import MomentType
        if moment.type not in (MomentType.FLIP, MomentType.TIE, MomentType.CLOSING_CONTROL, MomentType.HIGH_IMPACT):
            warnings.append("No score or tier change detected")
    
    # Update trace with validation results
    passed = is_valid_moment(moment)
    trace.validation = ValidationResult(
        passed=passed,
        checks_performed=checks_performed,
        issues=issues,
        warnings=warnings,
    )
    
    action = TraceAction.VALIDATED if passed else TraceAction.REJECTED
    trace.add_action(action, {
        "passed": passed,
        "issues": issues,
        "warnings": warnings,
    })
    
    if not passed:
        # Determine the primary rejection reason
        if "No causal trigger" in str(issues):
            trace.rejection_reason = RejectionReason.NO_CAUSAL_TRIGGER.value
        elif "No teams" in str(issues):
            trace.rejection_reason = RejectionReason.NO_PARTICIPANTS.value
        elif "Micro-moment" in str(issues):
            trace.rejection_reason = RejectionReason.MICRO_MOMENT.value
        else:
            trace.rejection_reason = RejectionReason.NO_NARRATIVE_CHANGE.value
    
    return trace


def record_merge(
    absorbed_trace: MomentTrace,
    absorber_trace: MomentTrace,
    phase: MergePhase,
    reason: str = "consecutive_same_type",
) -> None:
    """Record that one moment was merged into another.
    
    Args:
        absorbed_trace: Trace of the moment being absorbed
        absorber_trace: Trace of the moment absorbing
        phase: Which phase triggered this merge
        reason: Why the merge happened
    """
    # Add merge event to absorbed trace
    absorbed_trace.add_merge_event(
        merged_into_id=absorber_trace.moment_id,
        phase=phase,
        reason=reason,
        pre_merge_type=absorbed_trace.moment_type,
        post_merge_type=absorber_trace.moment_type,
    )
    
    absorbed_trace.merged_into_id = absorber_trace.moment_id
    absorbed_trace.is_final = False
    absorbed_trace.add_action(TraceAction.MERGED_INTO, {
        "merged_into": absorber_trace.moment_id,
        "phase": phase.value,
        "reason": reason,
    })
    
    absorber_trace.absorbed_moment_ids.append(absorbed_trace.moment_id)
    absorber_trace.add_action(TraceAction.ABSORBED, {
        "absorbed": absorbed_trace.moment_id,
        "phase": phase.value,
        "reason": reason,
    })
