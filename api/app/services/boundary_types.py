"""Boundary detection data types.

Dataclasses and constants used by the boundary detection system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .lead_ladder import LeadState, TierCrossing
    from .moments import MomentType


# Default configuration
DEFAULT_HYSTERESIS_PLAYS = 2
DEFAULT_FLIP_HYSTERESIS_PLAYS = 3
DEFAULT_TIE_HYSTERESIS_PLAYS = 2
RUN_BOUNDARY_MIN_POINTS = 8
RUN_BOUNDARY_MIN_TIER_CHANGE = 1

# Density gating configuration
# Prevents rapid FLIP/TIE sequences from emitting multiple boundaries
DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS = 8  # Min canonical plays between FLIP/TIE boundaries
DENSITY_GATE_LATE_GAME_PROGRESS = 0.85  # Q4 late or OT threshold for override consideration
DENSITY_GATE_OVERRIDE_MAX_TIER = 1  # Max tier to qualify for late-game override

# Late-game outcome threat configuration
# Prevents false drama from cuts that don't materially threaten the result
LATE_GAME_MIN_QUARTER = 4  # Q4 or OT
LATE_GAME_MAX_SECONDS = 150  # 2.5 minutes remaining
LATE_GAME_SAFE_MARGIN = 10  # Points: if margin > this after change, no threat
LATE_GAME_SAFE_TIER = 2  # Tier threshold: if tier >= this after change, no threat


@dataclass
class BoundaryEvent:
    """
    Represents a detected moment boundary.

    A boundary occurs when game control changes significantly enough
    to warrant starting a new moment.
    """
    index: int  # Index in timeline where boundary occurs
    moment_type: "MomentType"
    prev_state: "LeadState"
    curr_state: "LeadState"
    crossing: "TierCrossing | None" = None
    note: str | None = None


@dataclass
class RunBoundaryDecision:
    """Record of a run boundary decision for diagnostics."""
    run_start_idx: int
    run_end_idx: int
    run_points: int
    run_team: str
    created_boundary: bool
    reason: str  # e.g., "run_created_boundary", "run_no_tier_change", "run_overlaps_existing"
    tier_before: int | None = None
    tier_after: int | None = None


@dataclass
class DensityGateDecision:
    """Record of a density gate decision for FLIP/TIE boundaries.

    Used for diagnostics to trace why a FLIP or TIE boundary was suppressed.
    """
    event_index: int
    crossing_type: str  # "FLIP" or "TIE"
    density_gate_applied: bool
    reason: str  # e.g., "within_window", "override_late_close", "no_recent_boundary"
    last_flip_tie_index: int | None = None
    last_flip_tie_canonical_pos: int | None = None
    current_canonical_pos: int | None = None
    window_size: int = DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS
    game_progress: float = 0.0
    tier_at_event: int = 0
    override_qualified: bool = False


@dataclass
class LateFalseDramaDecision:
    """Record of a late-game outcome threat decision.

    Used for diagnostics to trace why a TIER_DOWN/CUT boundary was suppressed
    due to lack of outcome threat (late-game "false drama").

    SPORT-AGNOSTIC: Uses unified phase detection instead of quarter checks.

    A boundary is suppressed if ALL are true:
    - is_final_phase == true (Q4/2H/P3 or OT)
    - seconds_remaining <= threshold
    - margin_after_change > SAFE_MARGIN
    - tier_after >= SAFE_TIER
    - no FLIP/TIE involved
    - no HIGH_IMPACT event
    """
    event_index: int
    crossing_type: str  # "TIER_DOWN", "CUT", "RUN"
    suppressed: bool
    suppressed_reason: str  # "late_false_drama" or "outcome_threatening" or specific reason

    # Sport-agnostic phase info
    phase_number: int = 0  # Quarter, half, or period number
    phase_label: str = ""  # "Q4", "2H", "P3", "OT"
    is_final_phase: bool = False
    is_overtime: bool = False

    seconds_remaining: int = 0
    margin_before: int = 0
    margin_after: int = 0
    tier_before: int = 0
    tier_after: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_index": self.event_index,
            "crossing_type": self.crossing_type,
            "suppressed": self.suppressed,
            "suppressed_reason": self.suppressed_reason,
            "phase_number": self.phase_number,
            "phase_label": self.phase_label,
            "is_final_phase": self.is_final_phase,
            "is_overtime": self.is_overtime,
            "seconds_remaining": self.seconds_remaining,
            "margin_before": self.margin_before,
            "margin_after": self.margin_after,
            "tier_before": self.tier_before,
            "tier_after": self.tier_after,
        }
