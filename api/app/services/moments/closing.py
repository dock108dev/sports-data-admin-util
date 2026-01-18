"""Unified closing situation classification.

This module provides a SINGLE, EXPLICIT closing taxonomy used across
the entire pipeline:
- Boundary detection
- Construction improvements
- Closing expansion logic

CLOSING TAXONOMY:
1. CLOSE_GAME_CLOSING - Game is competitive late, needs expansion
2. DECIDED_GAME_CLOSING - Game is decided late, needs compression
3. NOT_CLOSING - Not in closing window or not in final phase

SPORT-AGNOSTIC:
This module uses the unified game structure abstraction.
- `is_final_phase` replaces `quarter >= 4`
- Works for NBA (Q4), NCAAB (2H), NHL (P3), NFL (Q4), etc.

Usage:
    from app.services.moments.closing import (
        ClosingCategory,
        ClosingClassification,
        classify_closing_situation,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..lead_ladder import LeadState

from .config import (
    CLOSING_WINDOW_SECONDS,
    CLOSE_GAME_MAX_TIER,
    CLOSE_GAME_POSSESSION_THRESHOLD,
    DECIDED_GAME_MIN_TIER,
    DECIDED_GAME_SAFE_MARGIN,
)
from .game_structure import (
    GamePhaseState,
    compute_game_phase_state,
    get_game_structure,
    get_phase_label,
)

logger = logging.getLogger(__name__)


class ClosingCategory(str, Enum):
    """Closing situation category.
    
    NOT_CLOSING:
        Not in closing window (before Q4, or too much time remaining).
        Behavior: Normal pipeline processing.
    
    CLOSE_GAME_CLOSING:
        Q4/OT with limited time, game is competitive.
        Criteria: tier <= 1 OR margin <= possession threshold.
        Behavior: Expand, allow micro-moments, relax density gating.
    
    DECIDED_GAME_CLOSING:
        Q4/OT with limited time, game is decided.
        Criteria: tier >= 2 AND margin > safe margin.
        Behavior: Suppress cuts, absorb runs, no semantic escalation.
    """
    
    NOT_CLOSING = "NOT_CLOSING"
    CLOSE_GAME_CLOSING = "CLOSE_GAME_CLOSING"
    DECIDED_GAME_CLOSING = "DECIDED_GAME_CLOSING"


@dataclass
class ClosingClassification:
    """Result of closing situation classification.
    
    Contains the category and all diagnostic information needed for tracing.
    Uses sport-agnostic phase detection.
    """
    category: ClosingCategory
    
    # Phase info (sport-agnostic)
    phase_number: int  # Quarter, half, or period number
    phase_label: str  # Human-readable: "Q4", "2H", "P3", "OT"
    seconds_remaining: int  # Remaining in regulation (or OT phase)
    
    # Lead state
    tier: int
    margin: int
    
    # Sport context
    sport: str = "NBA"
    
    # Threshold checks (for diagnostics)
    is_final_phase: bool = False  # Final quarter/half/period or OT
    is_overtime: bool = False
    is_within_window: bool = False  # seconds <= closing_window
    is_close_by_tier: bool = False  # tier <= CLOSE_GAME_MAX_TIER
    is_close_by_margin: bool = False  # margin <= CLOSE_GAME_POSSESSION_THRESHOLD
    is_decided_by_tier: bool = False  # tier >= DECIDED_GAME_MIN_TIER
    is_decided_by_margin: bool = False  # margin > DECIDED_GAME_SAFE_MARGIN
    
    reason: str = ""  # Human-readable explanation
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "phase_number": self.phase_number,
            "phase_label": self.phase_label,
            "seconds_remaining": self.seconds_remaining,
            "tier": self.tier,
            "margin": self.margin,
            "sport": self.sport,
            "is_final_phase": self.is_final_phase,
            "is_overtime": self.is_overtime,
            "is_within_window": self.is_within_window,
            "is_close_by_tier": self.is_close_by_tier,
            "is_close_by_margin": self.is_close_by_margin,
            "is_decided_by_tier": self.is_decided_by_tier,
            "is_decided_by_margin": self.is_decided_by_margin,
            "reason": self.reason,
        }
    
    @property
    def is_closing(self) -> bool:
        """True if in any closing situation (close or decided)."""
        return self.category != ClosingCategory.NOT_CLOSING
    
    @property
    def is_close_game(self) -> bool:
        """True if in close game closing (expansion mode)."""
        return self.category == ClosingCategory.CLOSE_GAME_CLOSING
    
    @property
    def is_decided_game(self) -> bool:
        """True if in decided game closing (compression mode)."""
        return self.category == ClosingCategory.DECIDED_GAME_CLOSING
    
    # Backward compatibility
    @property
    def quarter(self) -> int:
        """Alias for phase_number (backward compatibility)."""
        return self.phase_number


def classify_closing_situation(
    event: dict[str, Any],
    lead_state: LeadState,
    sport: str | None = None,
    closing_window_seconds: int | None = None,
    close_game_max_tier: int = CLOSE_GAME_MAX_TIER,
    close_game_possession_threshold: int = CLOSE_GAME_POSSESSION_THRESHOLD,
    decided_game_min_tier: int = DECIDED_GAME_MIN_TIER,
    decided_game_safe_margin: int = DECIDED_GAME_SAFE_MARGIN,
) -> ClosingClassification:
    """
    Classify the closing situation for a given event and lead state.
    
    This is the SINGLE SOURCE OF TRUTH for closing classification.
    All pipeline components should use this function instead of ad-hoc checks.
    
    SPORT-AGNOSTIC: Uses unified game phase state.
    - NBA: Q4 or OT
    - NCAAB: 2nd half or OT
    - NHL: 3rd period or OT
    - NFL: Q4 or OT
    
    Args:
        event: Timeline event with quarter/period and game_clock
        lead_state: Current lead ladder state
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
        closing_window_seconds: Time window for closing (default from sport config)
        close_game_max_tier: Max tier for close game (default 1)
        close_game_possession_threshold: Max margin for one-possession (default 6)
        decided_game_min_tier: Min tier for decided game (default 2)
        decided_game_safe_margin: Min margin for safe lead (default 10)
    
    Returns:
        ClosingClassification with category and diagnostics
    """
    # Compute sport-agnostic phase state
    phase_state = compute_game_phase_state(event, sport)
    
    # Use sport-specific closing window if not overridden
    structure = get_game_structure(sport)
    if closing_window_seconds is None:
        closing_window_seconds = structure.closing_window_seconds
    
    # Calculate margin
    margin = abs(lead_state.home_score - lead_state.away_score)
    tier = lead_state.tier
    
    # Build classification with diagnostic flags
    classification = ClosingClassification(
        category=ClosingCategory.NOT_CLOSING,
        phase_number=phase_state.phase_number,
        phase_label=get_phase_label(phase_state),
        seconds_remaining=phase_state.remaining_seconds,
        tier=tier,
        margin=margin,
        sport=phase_state.sport,
        is_final_phase=phase_state.is_final_phase,
        is_overtime=phase_state.is_overtime,
    )
    
    # Check 1: Is this the final phase or OT?
    if not classification.is_final_phase:
        classification.reason = (
            f"{classification.phase_label} is not final phase "
            f"(need {structure.phase_type.value} {structure.final_phase_number}+)"
        )
        return classification
    
    # Check 2: Is this within the closing window?
    classification.is_within_window = (
        phase_state.remaining_seconds <= closing_window_seconds
    )
    if not classification.is_within_window:
        classification.reason = (
            f"{phase_state.remaining_seconds}s remaining exceeds "
            f"window ({closing_window_seconds}s)"
        )
        return classification
    
    # We're in the closing window - determine category
    classification.is_close_by_tier = tier <= close_game_max_tier
    classification.is_close_by_margin = margin <= close_game_possession_threshold
    classification.is_decided_by_tier = tier >= decided_game_min_tier
    classification.is_decided_by_margin = margin > decided_game_safe_margin
    
    phase_label = classification.phase_label
    
    # CLOSE_GAME_CLOSING: tier <= max OR margin <= possession threshold
    if classification.is_close_by_tier or classification.is_close_by_margin:
        classification.category = ClosingCategory.CLOSE_GAME_CLOSING
        if classification.is_close_by_tier and classification.is_close_by_margin:
            classification.reason = (
                f"Close game ({phase_label}): tier {tier} <= {close_game_max_tier} "
                f"AND margin {margin} <= {close_game_possession_threshold}"
            )
        elif classification.is_close_by_tier:
            classification.reason = (
                f"Close game ({phase_label}): tier {tier} <= {close_game_max_tier}"
            )
        else:
            classification.reason = (
                f"Close game ({phase_label}): margin {margin} <= "
                f"{close_game_possession_threshold} (one possession)"
            )
        return classification
    
    # DECIDED_GAME_CLOSING: tier >= min AND margin > safe margin
    if classification.is_decided_by_tier and classification.is_decided_by_margin:
        classification.category = ClosingCategory.DECIDED_GAME_CLOSING
        classification.reason = (
            f"Decided game ({phase_label}): tier {tier} >= {decided_game_min_tier} "
            f"AND margin {margin} > {decided_game_safe_margin}"
        )
        return classification
    
    # Edge case: in window but doesn't fit either category cleanly
    # Default to CLOSE_GAME_CLOSING if margin is not clearly safe
    if margin <= decided_game_safe_margin:
        classification.category = ClosingCategory.CLOSE_GAME_CLOSING
        classification.reason = (
            f"Close game ({phase_label}, default): "
            f"margin {margin} <= {decided_game_safe_margin}"
        )
    else:
        classification.category = ClosingCategory.DECIDED_GAME_CLOSING
        classification.reason = (
            f"Decided game ({phase_label}, default): "
            f"margin {margin} > {decided_game_safe_margin}"
        )
    
    return classification


def classify_closing_from_scores(
    phase_number: int,
    seconds_remaining: int,
    home_score: int,
    away_score: int,
    sport: str | None = None,
    thresholds: list[int] | tuple[int, ...] | None = None,
) -> ClosingClassification:
    """
    Classify closing situation from raw scores (without LeadState).
    
    Convenience function when you don't already have a LeadState.
    Works across all sports - phase_number is quarter, half, or period.
    
    Args:
        phase_number: Current phase (quarter, half, or period number)
        seconds_remaining: Seconds left in the phase
        home_score: Home team score
        away_score: Away team score
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
        thresholds: Lead ladder thresholds (optional, for tier calculation)
    
    Returns:
        ClosingClassification with category and diagnostics
    """
    from ..lead_ladder import compute_lead_state
    
    # Default thresholds if not provided
    if thresholds is None:
        thresholds = [5, 10, 15, 20]
    
    lead_state = compute_lead_state(home_score, away_score, thresholds)
    
    # Build a minimal event dict
    minutes = seconds_remaining // 60
    secs = seconds_remaining % 60
    clock = f"{minutes}:{secs:02d}"
    
    event = {
        "quarter": phase_number,
        "period": phase_number,
        "game_clock": clock,
    }
    
    return classify_closing_situation(event, lead_state, sport=sport)


# =============================================================================
# BEHAVIOR HELPERS
# =============================================================================
# These functions encode the behavior rules for each closing category.


def should_expand_in_closing(classification: ClosingClassification) -> bool:
    """
    Check if we should expand (allow more detail) in this closing situation.
    
    Expansion means:
    - Allow short moments (1-3 plays)
    - Relax merge restrictions
    - Allow multiple FLIP/TIE close together
    
    Returns True for CLOSE_GAME_CLOSING, False otherwise.
    """
    return classification.is_close_game


def should_suppress_cut_boundary(classification: ClosingClassification) -> bool:
    """
    Check if CUT/TIER_DOWN boundaries should be suppressed.
    
    Suppression means:
    - Don't create new moments for margin cuts
    - Absorb the tier change into surrounding moment
    
    Returns True for DECIDED_GAME_CLOSING, False otherwise.
    """
    return classification.is_decided_game


def should_suppress_run_boundary(
    classification: ClosingClassification,
    run_points: int,
    threat_threshold: int = 6,
) -> bool:
    """
    Check if a run boundary should be suppressed in this closing situation.
    
    In decided games, runs are absorbed unless they cross the threat threshold.
    
    Args:
        classification: Closing classification
        run_points: Points in the run
        threat_threshold: Points needed to potentially threaten outcome
    
    Returns True if the run should be suppressed.
    """
    if not classification.is_decided_game:
        return False
    
    # In decided games, suppress unless the run is large enough to threaten
    # Check if the run could bring the game within threat range
    new_margin = classification.margin - run_points
    return new_margin > CLOSE_GAME_POSSESSION_THRESHOLD


def should_relax_density_gating(classification: ClosingClassification) -> bool:
    """
    Check if FLIP/TIE density gating should be relaxed.
    
    In close game closing, we want to capture every lead change.
    
    Returns True for CLOSE_GAME_CLOSING, False otherwise.
    """
    return classification.is_close_game


def should_emit_closing_control(
    classification: ClosingClassification,
    moment_type_str: str,
) -> bool:
    """
    Check if this event should emit CLOSING_CONTROL moment type.
    
    CLOSING_CONTROL (dagger) moments only occur in DECIDED_GAME_CLOSING
    when the leading team extends or maintains their lead.
    
    Args:
        classification: Closing classification
        moment_type_str: The moment type that would otherwise be emitted
    
    Returns True if CLOSING_CONTROL should be emitted instead.
    """
    if not classification.is_decided_game:
        return False
    
    # CLOSING_CONTROL replaces LEAD_BUILD or FLIP in decided closing
    return moment_type_str in ("LEAD_BUILD", "FLIP", "TIE_BROKEN")
