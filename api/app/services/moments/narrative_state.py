"""Narrative state machine for moment coherence.

PHASE 4: Tracks narrative state across moments to prevent:
- Fake comebacks
- Repeated structural patterns
- False drama in garbage time
- Noisy middle quarters

This module provides a lightweight state machine that ensures each moment
represents a genuine narrative state change, not just a numeric change.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .types import Moment, MomentType


class ControlStrength(str, Enum):
    """How strongly a team controls the game."""
    STRONG = "strong"      # Tier 3+ lead, stable
    MODERATE = "moderate"  # Tier 2 lead, or tier 3 volatile
    WEAK = "weak"          # Tier 1 lead
    NONE = "none"          # Tied or no clear control


class ThreatLevel(str, Enum):
    """How much the trailing team threatens the lead."""
    NONE = "none"          # No realistic threat (blowout)
    POTENTIAL = "potential"  # Could threaten if sustained
    REAL = "real"          # Actively threatening


class GamePhase(str, Enum):
    """Where in the game we are."""
    OPENING = "opening"    # Q1 or early Q2
    MIDDLE = "middle"      # Q2-Q3
    CLOSING = "closing"    # Q4 or late Q3


@dataclass
class NarrativeState:
    """Tracks the current narrative state of the game.
    
    PHASE 4: Used to determine if a new moment represents a genuine
    state change or is just numeric noise.
    """
    controlling_team: str | None  # "home" | "away" | None
    control_strength: ControlStrength
    threat_level: ThreatLevel
    phase: GamePhase
    
    # Tracking for coherence checks
    consecutive_cuts: int = 0  # Count of consecutive CUT moments
    consecutive_builds: int = 0  # Count of consecutive LEAD_BUILD moments
    last_comeback_moment_idx: int | None = None  # Index of last comeback
    dormant_play_count: int = 0  # Plays since last meaningful change
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "controlling_team": self.controlling_team,
            "control_strength": self.control_strength.value,
            "threat_level": self.threat_level.value,
            "phase": self.phase.value,
            "consecutive_cuts": self.consecutive_cuts,
            "consecutive_builds": self.consecutive_builds,
            "dormant_play_count": self.dormant_play_count,
        }


def compute_control_strength(
    lead_margin: int,
    tier: int,
    volatility: str,
    time_remaining_pct: float,
) -> ControlStrength:
    """Determine control strength from game state.
    
    Args:
        lead_margin: Current lead margin (absolute value)
        tier: Current lead tier (0-4)
        volatility: "stable" | "oscillating" | "shifting"
        time_remaining_pct: Percentage of game remaining (0.0-1.0)
    
    Returns:
        ControlStrength enum
    """
    if tier == 0:
        return ControlStrength.NONE
    
    # Strong control: Tier 3+ and stable, or tier 4 always
    if tier >= 4:
        return ControlStrength.STRONG
    if tier == 3 and volatility == "stable":
        return ControlStrength.STRONG
    
    # Weak control: Tier 1, or volatile tier 2
    if tier == 1:
        return ControlStrength.WEAK
    if tier == 2 and volatility in ["oscillating", "shifting"]:
        return ControlStrength.WEAK
    
    # Moderate: Everything else
    return ControlStrength.MODERATE


def compute_threat_level(
    lead_margin: int,
    tier: int,
    time_remaining_pct: float,
    recent_momentum: str,
) -> ThreatLevel:
    """Determine threat level from game state.
    
    Args:
        lead_margin: Current lead margin (absolute value)
        tier: Current lead tier (0-4)
        time_remaining_pct: Percentage of game remaining (0.0-1.0)
        recent_momentum: "trailing" | "leading" | "neutral"
    
    Returns:
        ThreatLevel enum
    """
    # No threat if tier 4+
    if tier >= 4:
        return ThreatLevel.NONE
    
    # Real threat: Close game with time + trailing team has momentum
    if tier <= 1 and time_remaining_pct > 0.05:
        if recent_momentum == "trailing":
            return ThreatLevel.REAL
        return ThreatLevel.POTENTIAL
    
    # Potential threat: Tier 2 with time
    if tier == 2 and time_remaining_pct > 0.10:
        if recent_momentum == "trailing":
            return ThreatLevel.POTENTIAL
        return ThreatLevel.NONE
    
    # Tier 3 with lots of time
    if tier == 3 and time_remaining_pct > 0.25:
        return ThreatLevel.POTENTIAL
    
    # Default: No threat
    return ThreatLevel.NONE


def compute_game_phase_enum(phase_progress: float, is_closing_window: bool) -> GamePhase:
    """Convert phase progress to GamePhase enum.
    
    Args:
        phase_progress: 0.0 to 1.0 (percentage through game)
        is_closing_window: Boolean from game_structure
    
    Returns:
        GamePhase enum
    """
    if is_closing_window or phase_progress > 0.75:
        return GamePhase.CLOSING
    if phase_progress < 0.25:
        return GamePhase.OPENING
    return GamePhase.MIDDLE


def build_narrative_state(
    moment: Moment,
    previous_state: NarrativeState | None,
    phase_progress: float,
    is_closing_window: bool,
) -> NarrativeState:
    """Build narrative state from moment and game context.
    
    PHASE 4: This is the core state machine update function.
    
    Args:
        moment: Current moment
        previous_state: Previous narrative state (or None for first moment)
        phase_progress: 0.0 to 1.0
        is_closing_window: Boolean
    
    Returns:
        Updated NarrativeState
    """
    # Extract moment data
    lead_margin = abs(moment.score_after[0] - moment.score_after[1])
    tier = moment.ladder_tier_after
    controlling_team = moment.team_in_control
    
    # Get volatility from narrative context if available
    volatility = "stable"
    if moment.narrative_context:
        volatility = moment.narrative_context.tier_stability
    
    # Compute time remaining (approximate)
    time_remaining_pct = 1.0 - phase_progress
    
    # Determine recent momentum (simplified)
    recent_momentum = "neutral"
    if moment.type == MomentType.CUT:
        recent_momentum = "trailing"
    elif moment.type == MomentType.LEAD_BUILD:
        recent_momentum = "leading"
    
    # Compute new state components
    control_strength = compute_control_strength(
        lead_margin, tier, volatility, time_remaining_pct
    )
    threat_level = compute_threat_level(
        lead_margin, tier, time_remaining_pct, recent_momentum
    )
    phase = compute_game_phase_enum(phase_progress, is_closing_window)
    
    # Track consecutive patterns
    consecutive_cuts = 0
    consecutive_builds = 0
    dormant_play_count = 0
    last_comeback_idx = None
    
    if previous_state:
        # Increment consecutive counters
        if moment.type == MomentType.CUT:
            consecutive_cuts = previous_state.consecutive_cuts + 1
            consecutive_builds = 0
        elif moment.type == MomentType.LEAD_BUILD:
            consecutive_builds = previous_state.consecutive_builds + 1
            consecutive_cuts = 0
        else:
            consecutive_cuts = 0
            consecutive_builds = 0
        
        # Track dormancy
        if (control_strength == previous_state.control_strength and
            threat_level == previous_state.threat_level and
            controlling_team == previous_state.controlling_team):
            dormant_play_count = previous_state.dormant_play_count + moment.play_count
        else:
            dormant_play_count = 0
        
        last_comeback_idx = previous_state.last_comeback_moment_idx
    
    return NarrativeState(
        controlling_team=controlling_team,
        control_strength=control_strength,
        threat_level=threat_level,
        phase=phase,
        consecutive_cuts=consecutive_cuts,
        consecutive_builds=consecutive_builds,
        last_comeback_moment_idx=last_comeback_idx,
        dormant_play_count=dormant_play_count,
    )


def is_genuine_state_change(
    moment: Moment,
    current_state: NarrativeState,
    previous_state: NarrativeState | None,
) -> tuple[bool, str]:
    """Determine if moment represents a genuine narrative state change.
    
    PHASE 4: Core coherence check.
    
    Args:
        moment: Moment to check
        current_state: Narrative state after this moment
        previous_state: Narrative state before this moment
    
    Returns:
        (is_genuine, reason) tuple
        - is_genuine: True if moment should exist
        - reason: Explanation of decision
    """
    if not previous_state:
        return True, "first_moment"
    
    # Check 1: Control strength changed
    if current_state.control_strength != previous_state.control_strength:
        return True, "control_strength_change"
    
    # Check 2: Threat level changed
    if current_state.threat_level != previous_state.threat_level:
        return True, "threat_level_change"
    
    # Check 3: Controlling team changed (FLIP, TIE)
    if current_state.controlling_team != previous_state.controlling_team:
        return True, "control_shift"
    
    # Check 4: Phase boundary crossed
    if current_state.phase != previous_state.phase:
        return True, "phase_boundary"
    
    # Check 5: Tier changed (even if control/threat same)
    if moment.ladder_tier_after != moment.ladder_tier_before:
        # But suppress if dormant
        if current_state.dormant_play_count < 15:  # ~2-3 minutes
            return True, "tier_change"
    
    # Check 6: Special moment types always allowed
    if moment.type in [
        MomentType.FLIP,
        MomentType.TIE,
        MomentType.CLOSING_CONTROL,
        MomentType.HIGH_IMPACT,
    ]:
        return True, f"special_type_{moment.type.value}"
    
    # Otherwise: No genuine state change
    return False, "no_state_change"


def is_fake_comeback(
    moment: Moment,
    current_state: NarrativeState,
    previous_state: NarrativeState | None,
    moment_idx: int,
) -> bool:
    """Check if moment is a fake comeback.
    
    PHASE 4: Prevents repeated comeback language.
    
    A comeback is fake if:
    1. It's a CUT moment
    2. Threat level didn't increase to REAL
    3. Another comeback happened recently
    
    Args:
        moment: Moment to check
        current_state: Current narrative state
        previous_state: Previous narrative state
        moment_idx: Index of this moment in sequence
    
    Returns:
        True if this is a fake comeback
    """
    if moment.type != MomentType.CUT:
        return False
    
    if not previous_state:
        return False
    
    # Real comeback: Threat level increased to REAL
    if (previous_state.threat_level != ThreatLevel.REAL and
        current_state.threat_level == ThreatLevel.REAL):
        return False
    
    # Fake comeback: Recent comeback already happened
    if previous_state.last_comeback_moment_idx is not None:
        if moment_idx - previous_state.last_comeback_moment_idx < 3:
            return True
    
    # Fake comeback: No threat increase
    if current_state.threat_level == ThreatLevel.NONE:
        return True
    
    return False


def should_suppress_late_game_cut(
    moment: Moment,
    current_state: NarrativeState,
) -> bool:
    """Check if late-game CUT should be suppressed.
    
    PHASE 4: Hard suppression of garbage-time cuts.
    
    Suppress if:
    1. Closing phase
    2. Strong control
    3. No real threat
    
    Args:
        moment: Moment to check
        current_state: Current narrative state
    
    Returns:
        True if moment should be suppressed
    """
    if moment.type != MomentType.CUT:
        return False
    
    if current_state.phase != GamePhase.CLOSING:
        return False
    
    if current_state.control_strength != ControlStrength.STRONG:
        return False
    
    if current_state.threat_level == ThreatLevel.REAL:
        return False
    
    return True


def is_dormant_window(
    current_state: NarrativeState,
    dormancy_threshold: int = 20,
) -> bool:
    """Check if we're in a narrative dormancy window.
    
    PHASE 4: Detects quiet stretches where nothing meaningful happens.
    
    Args:
        current_state: Current narrative state
        dormancy_threshold: Number of plays to consider dormant
    
    Returns:
        True if dormant
    """
    return current_state.dormant_play_count >= dormancy_threshold


def should_suppress_semantic_split(
    moment: Moment,
    current_state: NarrativeState,
    previous_state: NarrativeState | None,
) -> bool:
    """Check if semantic split should be suppressed.
    
    PHASE 4: Quality gate for semantic splits.
    
    Suppress if:
    1. Trigger is semantic_split
    2. No tier change
    3. No threat change
    4. No control change
    5. No phase boundary
    
    Args:
        moment: Moment to check
        current_state: Current narrative state
        previous_state: Previous narrative state
    
    Returns:
        True if split should be suppressed
    """
    if not moment.reason or moment.reason.trigger != "semantic_split":
        return False
    
    if not previous_state:
        return False
    
    # Check for any meaningful change
    has_tier_change = moment.ladder_tier_after != moment.ladder_tier_before
    has_threat_change = current_state.threat_level != previous_state.threat_level
    has_control_change = current_state.controlling_team != previous_state.controlling_team
    has_phase_change = current_state.phase != previous_state.phase
    
    # Suppress if no meaningful change
    if not (has_tier_change or has_threat_change or has_control_change or has_phase_change):
        return True
    
    return False
