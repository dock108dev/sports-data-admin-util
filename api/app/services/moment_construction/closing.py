"""Closing expansion for late-game narrative detail.

When the game is close late, STOP collapsing and START expanding.
This module detects closing situations and relaxes merge restrictions
to allow more granular play-by-play tension in the final moments.

UNIFIED CLOSING TAXONOMY:
This module uses the unified closing classification from moments.closing:
- CLOSE_GAME_CLOSING: Expand, allow micro-moments, relax density gating
- DECIDED_GAME_CLOSING: Compress, suppress cuts, absorb runs

IMPORTANT: This module does NOT re-run selection or change importance scores.
It only relaxes merge restrictions and annotates moments for closing expansion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

from .config import ClosingConfig, DEFAULT_CLOSING_CONFIG

if TYPE_CHECKING:
    from ..moments import Moment
    from ..moments.closing import ClosingCategory

logger = logging.getLogger(__name__)


@dataclass
class ClosingWindowInfo:
    """Information about the closing window in a game.
    
    Uses the unified closing taxonomy from moments.closing.
    """
    
    is_active: bool = False
    closing_category: str = "NOT_CLOSING"  # ClosingCategory value
    window_start_index: int | None = None  # First event index in closing window
    window_end_index: int | None = None  # Last event index in closing window
    quarter: int = 0
    seconds_remaining_at_start: int = 0
    tier_at_start: int = 0
    margin_at_start: int = 0
    reason: str = ""  # Why closing mode activated or not
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "is_active": self.is_active,
            "closing_category": self.closing_category,
            "window_start_index": self.window_start_index,
            "window_end_index": self.window_end_index,
            "quarter": self.quarter,
            "seconds_remaining_at_start": self.seconds_remaining_at_start,
            "tier_at_start": self.tier_at_start,
            "margin_at_start": self.margin_at_start,
            "reason": self.reason,
        }
    
    @property
    def is_close_game(self) -> bool:
        """True if in close game closing (expansion mode)."""
        return self.closing_category == "CLOSE_GAME_CLOSING"
    
    @property
    def is_decided_game(self) -> bool:
        """True if in decided game closing (compression mode)."""
        return self.closing_category == "DECIDED_GAME_CLOSING"


@dataclass
class ClosingMomentAnnotation:
    """Annotation for a moment that was processed by closing expansion.
    
    Uses the unified closing taxonomy from moments.closing.
    """
    
    moment_id: str
    original_index: int
    is_in_closing_window: bool
    closing_category: str = "NOT_CLOSING"  # ClosingCategory value
    expansion_applied: bool = False
    reason: str = ""
    seconds_remaining: int = 0
    tier_at_moment: int = 0
    margin_at_moment: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_id": self.moment_id,
            "original_index": self.original_index,
            "is_in_closing_window": self.is_in_closing_window,
            "closing_category": self.closing_category,
            "expansion_applied": self.expansion_applied,
            "reason": self.reason,
            "seconds_remaining": self.seconds_remaining,
            "tier_at_moment": self.tier_at_moment,
            "margin_at_moment": self.margin_at_moment,
        }


@dataclass
class ClosingExpansionResult:
    """Result of closing expansion pass."""
    
    moments: list["Moment"] = field(default_factory=list)
    closing_window: ClosingWindowInfo = field(default_factory=ClosingWindowInfo)
    moments_in_closing: int = 0
    moments_expanded: int = 0
    moments_protected: int = 0
    annotations: list[ClosingMomentAnnotation] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "closing_window": self.closing_window.to_dict(),
            "moments_in_closing": self.moments_in_closing,
            "moments_expanded": self.moments_expanded,
            "moments_protected": self.moments_protected,
            "annotations": [a.to_dict() for a in self.annotations],
        }


def _parse_clock_to_seconds(clock: str) -> int:
    """Parse game clock string to seconds remaining.
    
    Handles formats like "2:30", "0:45.5", "12:00", etc.
    """
    if not clock:
        return 0
    
    try:
        # Remove any decimal portion for simplicity
        clock = clock.split(".")[0]
        
        if ":" in clock:
            parts = clock.split(":")
            minutes = int(parts[0])
            seconds = int(parts[1]) if len(parts) > 1 else 0
            return minutes * 60 + seconds
        else:
            return int(clock)
    except (ValueError, IndexError):
        return 0


def _get_event_closing_classification(
    event: dict[str, Any],
    thresholds: Sequence[int],
    sport: str | None = None,
) -> "tuple[int, int, int, int, str]":
    """Get closing classification for an event.
    
    Uses the unified closing taxonomy from moments.closing.
    SPORT-AGNOSTIC: Uses unified game structure.
    
    Returns:
        Tuple of (phase_number, seconds_remaining, tier, margin, closing_category_value)
    """
    from ..lead_ladder import compute_lead_state
    from ..moments.closing import classify_closing_situation, ClosingCategory
    from ..moments.game_structure import compute_game_phase_state
    
    # Use sport-agnostic phase state
    phase_state = compute_game_phase_state(event, sport)
    
    home_score = event.get("home_score", 0) or 0
    away_score = event.get("away_score", 0) or 0
    margin = abs(home_score - away_score)
    
    if thresholds:
        state = compute_lead_state(home_score, away_score, thresholds)
        tier = state.tier
        classification = classify_closing_situation(event, state, sport=sport)
        category = classification.category.value
    else:
        # Fallback: estimate tier based on point differential
        if margin <= 3:
            tier = 0
        elif margin <= 7:
            tier = 1
        elif margin <= 12:
            tier = 2
        else:
            tier = 3
        
        # Simplified classification using sport-agnostic phase state
        if phase_state.is_final_phase and phase_state.is_closing_window:
            if tier <= 1 or margin <= 6:
                category = ClosingCategory.CLOSE_GAME_CLOSING.value
            elif tier >= 2 and margin > 10:
                category = ClosingCategory.DECIDED_GAME_CLOSING.value
            else:
                category = ClosingCategory.NOT_CLOSING.value
        else:
            category = ClosingCategory.NOT_CLOSING.value
    
    return phase_state.phase_number, phase_state.remaining_seconds, tier, margin, category


def detect_closing_window(
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    config: ClosingConfig = DEFAULT_CLOSING_CONFIG,
    sport: str | None = None,
) -> ClosingWindowInfo:
    """Detect if a closing window exists in the game.
    
    Uses the unified closing taxonomy from moments.closing.
    SPORT-AGNOSTIC: Uses unified game structure for phase detection.
    Scans events to find where closing mode should activate.
    
    Args:
        events: Timeline events
        thresholds: Lead Ladder thresholds
        config: Closing configuration
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
    
    Returns:
        ClosingWindowInfo with window details including closing category
    """
    from ..moments.game_structure import compute_game_phase_state, get_phase_label
    
    info = ClosingWindowInfo()
    
    # Scan backwards from end to find closing window start
    window_start_idx: int | None = None
    window_start_phase: int = 0
    window_start_seconds: int = 0
    window_start_tier: int = 0
    window_start_margin: int = 0
    window_start_category: str = "NOT_CLOSING"
    
    for i in range(len(events) - 1, -1, -1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue
        
        # Use sport-agnostic phase state
        phase_state = compute_game_phase_state(event, sport)
        phase_num, seconds, tier, margin, category = _get_event_closing_classification(
            event, thresholds, sport
        )
        
        # Check if this event is in a potential closing window (sport-agnostic)
        is_final_phase = phase_state.is_final_phase
        is_final_minutes = seconds <= config.final_seconds_window
        is_close_game = category == "CLOSE_GAME_CLOSING"
        
        if is_final_phase and is_final_minutes:
            if is_close_game:
                # This is a valid closing window event (expansion mode)
                window_start_idx = i
                window_start_phase = phase_num
                window_start_seconds = seconds
                window_start_tier = tier
                window_start_margin = margin
                window_start_category = category
            elif category == "DECIDED_GAME_CLOSING":
                # Game is decided - compression mode, not expansion
                # Continue scanning to see if there was an earlier close window
                pass
            else:
                # Not in closing at all
                break
        elif is_final_phase and not is_final_minutes:
            # Before the final minutes window
            break
    
    if window_start_idx is not None:
        # Get phase label for logging
        sample_event = events[window_start_idx]
        phase_state = compute_game_phase_state(sample_event, sport)
        phase_label = get_phase_label(phase_state)
        
        info.is_active = True
        info.closing_category = window_start_category
        info.window_start_index = window_start_idx
        info.window_end_index = len(events) - 1
        info.quarter = window_start_phase
        info.seconds_remaining_at_start = window_start_seconds
        info.tier_at_start = window_start_tier
        info.margin_at_start = window_start_margin
        info.reason = (
            f"{phase_label} with {window_start_seconds}s remaining, "
            f"tier {window_start_tier}, margin {window_start_margin} "
            f"({window_start_category})"
        )
        
        logger.info(
            "closing_window_detected",
            extra={
                "window_start_index": window_start_idx,
                "window_end_index": len(events) - 1,
                "phase_label": phase_label,
                "phase_number": window_start_phase,
                "seconds_remaining": window_start_seconds,
                "tier": window_start_tier,
                "margin": window_start_margin,
                "closing_category": window_start_category,
                "sport": sport or "NBA",
            },
        )
    else:
        info.reason = "no_closing_window_found"
        logger.debug("closing_window_not_detected")
    
    return info


def _is_moment_in_closing_window(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    closing_window: ClosingWindowInfo,
) -> bool:
    """Check if a moment overlaps with the closing window."""
    if not closing_window.is_active:
        return False
    
    if closing_window.window_start_index is None:
        return False
    
    # Moment overlaps if its end_play is >= window start
    return moment.end_play >= closing_window.window_start_index


def apply_closing_expansion(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int] = (),
    config: ClosingConfig = DEFAULT_CLOSING_CONFIG,
    sport: str | None = None,
) -> ClosingExpansionResult:
    """Apply closing expansion to moments.
    
    When the game is close late, this pass:
    - Detects the closing window
    - Marks moments in the closing window as protected
    - Annotates moments for expansion (relaxed merge restrictions)
    
    SPORT-AGNOSTIC: Uses unified game structure for phase detection.
    
    This pass does NOT:
    - Reorder moments
    - Re-run selection
    - Change importance scores
    - Affect earlier phases
    
    Args:
        moments: Moments after chapter creation and quotas
        events: Timeline events
        thresholds: Lead Ladder thresholds
        config: Closing configuration
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
    
    Returns:
        ClosingExpansionResult with annotated moments
    """
    result = ClosingExpansionResult()
    
    if not moments:
        return result
    
    # Step 1: Detect closing window (sport-agnostic)
    closing_window = detect_closing_window(events, thresholds, config, sport)
    result.closing_window = closing_window
    
    if not closing_window.is_active:
        # No closing window - return moments unchanged
        result.moments = moments
        logger.info(
            "closing_expansion_skipped",
            extra={"reason": closing_window.reason},
        )
        return result
    
    # Step 2: Process moments and apply closing annotations
    output_moments: list["Moment"] = []
    closing_moment_count = 0
    
    for idx, moment in enumerate(moments):
        in_closing = _is_moment_in_closing_window(moment, events, closing_window)
        
        if in_closing:
            closing_moment_count += 1
            result.moments_in_closing += 1
            
            # Get closing classification at moment end (sport-agnostic)
            end_event = events[moment.end_play] if moment.end_play < len(events) else {}
            phase_num, seconds, tier, margin, category = _get_event_closing_classification(
                end_event, thresholds, sport
            )
            
            # Check if this moment type is protected
            type_value = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)
            is_protected = type_value in config.protected_closing_types
            
            if is_protected:
                result.moments_protected += 1
            
            # Check if we're within the cap
            within_cap = closing_moment_count <= config.max_closing_moments
            
            # Expansion only applies in CLOSE_GAME_CLOSING (not decided games)
            is_close_game = category == "CLOSE_GAME_CLOSING"
            
            # Determine if expansion should be applied
            expansion_applied = is_close_game and within_cap and (
                is_protected or
                config.allow_short_moments or
                moment.play_count >= config.min_closing_plays
            )
            
            if expansion_applied:
                result.moments_expanded += 1
            
            # Annotate the moment with unified closing category
            annotation = ClosingMomentAnnotation(
                moment_id=moment.id,
                original_index=idx,
                is_in_closing_window=True,
                closing_category=category,
                expansion_applied=expansion_applied,
                reason="protected_type" if is_protected else f"closing_{category.lower()}",
                seconds_remaining=seconds,
                tier_at_moment=tier,
                margin_at_moment=margin,
            )
            result.annotations.append(annotation)
            
            # Add closing expansion metadata to the moment (includes unified taxonomy)
            if not moment.importance_factors:
                moment.importance_factors = {}
            
            moment.importance_factors["closing_expansion"] = {
                "in_closing_window": True,
                "closing_category": category,
                "expansion_applied": expansion_applied,
                "is_protected": is_protected,
                "is_close_game": is_close_game,
                "seconds_remaining": seconds,
                "tier": tier,
                "margin": margin,
            }
            
            # Log individual moment annotation with unified category
            logger.debug(
                "closing_moment_annotated",
                extra={
                    "moment_id": moment.id,
                    "closing_category": category,
                    "expansion_applied": expansion_applied,
                    "is_protected": is_protected,
                    "seconds_remaining": seconds,
                    "tier": tier,
                    "margin": margin,
                },
            )
        else:
            # Not in closing window - mark as such but don't modify
            annotation = ClosingMomentAnnotation(
                moment_id=moment.id,
                original_index=idx,
                is_in_closing_window=False,
                closing_category="NOT_CLOSING",
                expansion_applied=False,
                reason="outside_closing_window",
            )
            result.annotations.append(annotation)
        
        output_moments.append(moment)
    
    # Step 3: Validate we haven't exceeded hard caps
    pre_expansion_closing_count = sum(
        1 for a in result.annotations if a.is_in_closing_window
    )
    
    if pre_expansion_closing_count > 0:
        expansion_ratio = result.moments_expanded / pre_expansion_closing_count
        if expansion_ratio > config.max_expansion_ratio:
            logger.warning(
                "closing_expansion_ratio_exceeded",
                extra={
                    "expansion_ratio": round(expansion_ratio, 2),
                    "max_allowed": config.max_expansion_ratio,
                    "expanded_count": result.moments_expanded,
                },
            )
    
    result.moments = output_moments
    
    logger.info(
        "closing_expansion_applied",
        extra={
            "closing_window_active": closing_window.is_active,
            "moments_in_closing": result.moments_in_closing,
            "moments_expanded": result.moments_expanded,
            "moments_protected": result.moments_protected,
            "total_moments": len(output_moments),
        },
    )
    
    return result


def should_allow_short_moment_in_closing(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
    closing_window: ClosingWindowInfo,
    config: ClosingConfig = DEFAULT_CLOSING_CONFIG,
) -> bool:
    """Check if a short moment (1-3 plays) should be allowed in closing.
    
    This is a helper function that can be called by other modules
    to check if merge restrictions should be relaxed.
    
    Args:
        moment: The moment to check
        events: Timeline events
        closing_window: Pre-computed closing window info
        config: Closing configuration
    
    Returns:
        True if short moment should be allowed
    """
    if not closing_window.is_active:
        return False
    
    if not config.allow_short_moments:
        return False
    
    if not _is_moment_in_closing_window(moment, events, closing_window):
        return False
    
    # Check if moment type is protected
    type_value = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)
    if type_value in config.protected_closing_types:
        return True
    
    # Check if moment meets minimum play count
    return moment.play_count >= config.min_closing_plays


def should_relax_flip_tie_density_in_closing(
    events: Sequence[dict[str, Any]],
    event_index: int,
    closing_window: ClosingWindowInfo,
    config: ClosingConfig = DEFAULT_CLOSING_CONFIG,
) -> bool:
    """Check if FLIP/TIE density restrictions should be relaxed.
    
    In the closing window, we allow multiple FLIP/TIE moments close together
    because each lead change is narratively significant.
    
    Args:
        events: Timeline events
        event_index: Index of the event to check
        closing_window: Pre-computed closing window info
        config: Closing configuration
    
    Returns:
        True if density restrictions should be relaxed
    """
    if not closing_window.is_active:
        return False
    
    if not config.relax_flip_tie_density:
        return False
    
    if closing_window.window_start_index is None:
        return False
    
    return event_index >= closing_window.window_start_index
