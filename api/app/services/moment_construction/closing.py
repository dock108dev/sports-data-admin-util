"""Closing expansion for late-game narrative detail.

POST-SELECTION EXPANSION PASS:
This module implements a post-selection pass that:
- Adds detail in true close endings (close_closing)
- Compresses decided endings (decided_closing)
- Respects narrative distance gating (prevents flip spam)

UNIFIED CLOSING TAXONOMY:
This module uses the unified closing classification from moments.closing:
- CLOSE_GAME_CLOSING: tier <= 1 OR margin <= possession threshold → EXPAND
- DECIDED_GAME_CLOSING: tier >= 2 AND margin > safe margin → COMPRESS

EXPANSION RULES (close_closing):
- Allows up to N additional moments in the last X seconds
- Enforces narrative distance: min Y seconds between FLIP/TIE (final-minute override)
- Prefers: run-based momentum, high-impact plays, final-minute lead changes

COMPRESSION RULES (decided_closing):
- Suppresses CUT moments unless margin crosses threat threshold
- Does not create "comeback beats" unless game becomes close_closing

SAFETY RULES:
- Only one CUT/comeback beat per team unless tier drops >= 2 tiers
- False-drama suppression applies to inserted moments
- Narrative distance gating prevents consecutive FLIP/TIE spam
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
class ExpansionCandidate:
    """A candidate moment for insertion in closing expansion."""
    
    event_index: int
    candidate_type: str  # "run", "high_impact", "final_minute_flip", "tier_change"
    priority: int  # Lower = higher priority
    score: float  # Quality score for ranking
    
    # Context
    seconds_remaining: int = 0
    tier_at_event: int = 0
    margin_at_event: int = 0
    closing_category: str = "NOT_CLOSING"
    
    # Run-specific
    run_points: int = 0
    run_team: str | None = None
    
    # Lead change specific
    is_flip: bool = False
    is_tie: bool = False
    
    # Distance from last similar moment
    seconds_since_last_flip_tie: int | None = None
    plays_since_last_flip_tie: int | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event_index": self.event_index,
            "candidate_type": self.candidate_type,
            "priority": self.priority,
            "score": self.score,
            "seconds_remaining": self.seconds_remaining,
            "tier_at_event": self.tier_at_event,
            "margin_at_event": self.margin_at_event,
            "closing_category": self.closing_category,
            "run_points": self.run_points,
            "run_team": self.run_team,
            "is_flip": self.is_flip,
            "is_tie": self.is_tie,
            "seconds_since_last_flip_tie": self.seconds_since_last_flip_tie,
        }


@dataclass
class ExpansionDecision:
    """Decision record for a candidate moment."""
    
    candidate: ExpansionCandidate
    inserted: bool
    reason: str  # Why inserted or skipped
    suppressed_by_density: bool = False
    suppressed_by_false_drama: bool = False
    suppressed_by_comeback_limit: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event_index": self.candidate.event_index,
            "candidate_type": self.candidate.candidate_type,
            "inserted": self.inserted,
            "reason": self.reason,
            "suppressed_by_density": self.suppressed_by_density,
            "suppressed_by_false_drama": self.suppressed_by_false_drama,
            "suppressed_by_comeback_limit": self.suppressed_by_comeback_limit,
        }


@dataclass
class ClosingExpansionResult:
    """Result of closing expansion pass."""
    
    moments: list["Moment"] = field(default_factory=list)
    closing_window: ClosingWindowInfo = field(default_factory=ClosingWindowInfo)
    moments_in_closing: int = 0
    moments_inserted: int = 0  # New moments inserted
    moments_removed: int = 0  # Moments removed (decided_closing compression)
    moments_protected: int = 0
    annotations: list[ClosingMomentAnnotation] = field(default_factory=list)
    expansion_decisions: list[ExpansionDecision] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "closing_window": self.closing_window.to_dict(),
            "moments_in_closing": self.moments_in_closing,
            "moments_inserted": self.moments_inserted,
            "moments_removed": self.moments_removed,
            "moments_protected": self.moments_protected,
            "annotations": [a.to_dict() for a in self.annotations],
            "expansion_decisions": [d.to_dict() for d in self.expansion_decisions],
            "inserted_by_type": {
                d.candidate.candidate_type: sum(
                    1 for dec in self.expansion_decisions
                    if dec.candidate.candidate_type == d.candidate.candidate_type and dec.inserted
                )
                for d in self.expansion_decisions
            },
            "suppressed_by_reason": {
                "density": sum(1 for d in self.expansion_decisions if d.suppressed_by_density),
                "false_drama": sum(1 for d in self.expansion_decisions if d.suppressed_by_false_drama),
                "comeback_limit": sum(1 for d in self.expansion_decisions if d.suppressed_by_comeback_limit),
            },
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


def _find_expansion_candidates(
    events: Sequence[dict[str, Any]],
    closing_window: ClosingWindowInfo,
    thresholds: Sequence[int],
    config: ClosingConfig,
    sport: str | None = None,
) -> list[ExpansionCandidate]:
    """Find candidate events for closing expansion.
    
    Candidates include:
    - Scoring runs >= run_expansion_min_points
    - High-impact events
    - Final-minute lead changes (FLIP/TIE)
    - Significant tier changes
    
    Returns candidates sorted by priority (lower = higher priority).
    """
    from ..lead_ladder import compute_lead_state, detect_tier_crossing
    from ..boundary_helpers import is_high_impact_event, get_seconds_remaining
    from ..moments_runs import detect_runs
    
    if not closing_window.is_active or closing_window.window_start_index is None:
        return []
    
    candidates: list[ExpansionCandidate] = []
    window_start = closing_window.window_start_index
    window_end = len(events) - 1
    
    # Track previous state for tier change detection
    prev_state = None
    prev_index = None
    
    # Detect runs in the closing window
    all_runs = detect_runs(events)
    closing_runs = [
        r for r in all_runs
        if r.start_idx >= window_start
        and r.end_idx <= window_end
        and r.points >= config.run_expansion_min_points
    ]
    
    for run in closing_runs:
        if run.end_idx < len(events):
            run_event = events[run.end_idx]
            phase_num, seconds, tier, margin, category = _get_event_closing_classification(
                run_event, thresholds, sport
            )
            
            # Only consider runs in close_closing
            if category == "CLOSE_GAME_CLOSING":
                candidates.append(ExpansionCandidate(
                    event_index=run.start_idx,
                    candidate_type="run",
                    priority=1,  # High priority
                    score=run.points * 10.0,  # More points = higher score
                    seconds_remaining=seconds,
                    tier_at_event=tier,
                    margin_at_event=margin,
                    closing_category=category,
                    run_points=run.points,
                    run_team=run.team,
                ))
    
    # Scan events for other candidates
    # Track state for tier change detection
    prev_state = None
    
    for i in range(window_start, min(window_end + 1, len(events))):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue
        
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        curr_state = compute_lead_state(home_score, away_score, thresholds)
        
        phase_num, seconds, tier, margin, category = _get_event_closing_classification(
            event, thresholds, sport
        )
        
        # Only consider events in close_closing
        if category != "CLOSE_GAME_CLOSING":
            prev_state = curr_state
            continue
        
        # Skip if outside expansion window
        if seconds > config.expansion_window_seconds:
            prev_state = curr_state
            continue
        
        # Candidate 1: High-impact events
        if is_high_impact_event(event):
            candidates.append(ExpansionCandidate(
                event_index=i,
                candidate_type="high_impact",
                priority=0,  # Highest priority
                score=100.0,
                seconds_remaining=seconds,
                tier_at_event=tier,
                margin_at_event=margin,
                closing_category=category,
            ))
        
        # Candidate 2: Final-minute lead changes
        if seconds <= config.final_minute_override_seconds and prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)
            if crossing:
                crossing_type = crossing.crossing_type.value
                is_flip = crossing_type == "FLIP"
                is_tie = crossing_type in ("TIE_REACHED", "TIE_BROKEN")
                
                if is_flip or is_tie:
                    candidates.append(ExpansionCandidate(
                        event_index=i,
                        candidate_type="final_minute_flip" if is_flip else "final_minute_tie",
                        priority=2,  # High priority for final minute
                        score=90.0 - seconds,  # Closer to end = higher score
                        seconds_remaining=seconds,
                        tier_at_event=tier,
                        margin_at_event=margin,
                        closing_category=category,
                        is_flip=is_flip,
                        is_tie=is_tie,
                    ))
        
        # Candidate 3: Significant tier changes (outside final minute but still in expansion window)
        if prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)
            if crossing:
                tier_delta = abs(curr_state.tier - prev_state.tier)
                if tier_delta >= 2:  # Significant tier change
                    candidates.append(ExpansionCandidate(
                        event_index=i,
                        candidate_type="tier_change",
                        priority=3,  # Medium priority
                        score=50.0 + (tier_delta * 10.0),
                        seconds_remaining=seconds,
                        tier_at_event=tier,
                        margin_at_event=margin,
                        closing_category=category,
                    ))
        
        prev_state = curr_state
    
    # Sort by priority, then by score (descending)
    candidates.sort(key=lambda c: (c.priority, -c.score))
    
    return candidates


def _check_narrative_distance(
    candidate: ExpansionCandidate,
    last_flip_tie_index: int | None,
    last_flip_tie_clock: str | None,
    events: Sequence[dict[str, Any]],
    config: ClosingConfig,
) -> tuple[bool, str]:
    """Check if candidate meets narrative distance requirements.
    
    Returns (allowed, reason).
    """
    from ...utils.datetime_utils import parse_clock_to_seconds
    
    # Final-minute override (always allowed)
    if candidate.seconds_remaining <= config.final_minute_override_seconds:
        return True, "final_minute_override"
    
    # Non-FLIP/TIE candidates don't need distance check
    if candidate.candidate_type not in ("final_minute_flip", "final_minute_tie", "tier_change"):
        return True, "not_flip_tie"
    
    # Only check distance for FLIP/TIE candidates
    if candidate.candidate_type not in ("final_minute_flip", "final_minute_tie"):
        return True, "not_flip_tie_type"
    
    if last_flip_tie_index is None:
        return True, "first_in_closing"
    
    # Check time distance
    if last_flip_tie_clock is not None and candidate.event_index < len(events):
        try:
            candidate_clock = events[candidate.event_index].get("game_clock", "12:00") or "12:00"
            last_seconds = parse_clock_to_seconds(last_flip_tie_clock)
            candidate_seconds = parse_clock_to_seconds(candidate_clock)
            
            # Clock counts down, so if last_seconds > candidate_seconds, time has passed
            # But we need to handle quarter boundaries - for simplicity, use absolute difference
            # This is conservative (may allow some that are too close)
            seconds_since = abs(last_seconds - candidate_seconds)
            
            # If clocks are very different, might be different quarters - allow
            if seconds_since > 600:  # More than 10 minutes apart
                return True, "different_quarter"
            
            if seconds_since < config.min_seconds_between_flip_tie:
                candidate.seconds_since_last_flip_tie = seconds_since
                return False, f"within_distance_{seconds_since}s"
            
            candidate.seconds_since_last_flip_tie = seconds_since
        except (ValueError, TypeError):
            pass
    
    return True, "outside_distance_window"


def _check_comeback_limit(
    candidate: ExpansionCandidate,
    events: Sequence[dict[str, Any]],
    existing_moments: list["Moment"],
    inserted_moments: list["Moment"],
    thresholds: Sequence[int],
    config: ClosingConfig,
) -> tuple[bool, str]:
    """Check if candidate violates comeback beat limit.
    
    Safety rule: Only one CUT/comeback-style beat per team unless:
    - margin crosses down by >= 2 tiers AND
    - game becomes close_closing
    
    Returns (allowed, reason).
    """
    from ..lead_ladder import compute_lead_state, Leader
    
    # Only applies to CUT-like moments (runs or tier decreases)
    if candidate.candidate_type not in ("run", "tier_change"):
        return True, "not_comeback_type"
    
    # Check if this represents a tier decrease (comeback)
    if candidate.event_index >= len(events):
        return True, "invalid_index"
    
    event = events[candidate.event_index]
    home_score = event.get("home_score", 0) or 0
    away_score = event.get("away_score", 0) or 0
    
    # Get previous event to check tier change
    if candidate.event_index > 0:
        prev_event = events[candidate.event_index - 1]
        prev_home = prev_event.get("home_score", 0) or 0
        prev_away = prev_event.get("away_score", 0) or 0
        
        prev_state = compute_lead_state(prev_home, prev_away, thresholds)
        curr_state = compute_lead_state(home_score, away_score, thresholds)
        
        # Check if tier decreased (comeback)
        if curr_state.tier < prev_state.tier:
            tier_delta = prev_state.tier - curr_state.tier
            
            # Determine which team is making the comeback (the one that was trailing)
            # If home was leading and tier decreased, away is making comeback
            # If away was leading and tier decreased, home is making comeback
            if prev_state.leader == Leader.HOME:
                comeback_team = "away"
            elif prev_state.leader == Leader.AWAY:
                comeback_team = "home"
            else:
                # Was tied - can't determine comeback team
                return True, "was_tied"
            
            # Count existing comeback beats for this team in closing window
            # Check both existing moments and inserted moments
            comeback_count = 0
            all_moments = existing_moments + inserted_moments
            
            for moment in all_moments:
                if moment.type.value == "CUT":
                    # Check if this moment is in closing and represents a comeback
                    # We can't perfectly determine which team, so we count all CUTs
                    # This is conservative but safe
                    if (moment.end_play >= candidate.event_index - 50 and
                        moment.end_play < candidate.event_index):
                        comeback_count += 1
            
            # Allow if tier delta >= threshold (significant comeback)
            if tier_delta >= config.comeback_tier_threshold:
                return True, f"significant_tier_drop_{tier_delta}"
            
            # Allow if this is the first comeback
            if comeback_count < config.max_comeback_beats_per_team:
                return True, f"within_limit_{comeback_count}"
            
            # Check if game becomes close_closing after this change
            # (margin crosses below threat threshold)
            margin_after = abs(home_score - away_score)
            if margin_after <= config.threat_margin_threshold:
                return True, f"game_becomes_threatened_margin_{margin_after}"
            
            return False, f"comeback_limit_exceeded_{comeback_count}"
    
    return True, "no_tier_decrease"


def apply_closing_expansion(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int] = (),
    config: ClosingConfig = DEFAULT_CLOSING_CONFIG,
    sport: str | None = None,
) -> ClosingExpansionResult:
    """Apply closing expansion pass to moments.
    
    POST-SELECTION EXPANSION:
    - Adds detail in true close endings (close_closing)
    - Compresses decided endings (decided_closing)
    - Respects narrative distance gating
    
    Uses unified closing taxonomy from moments.closing:
    - CLOSE_GAME_CLOSING: tier <= 1 OR margin <= possession threshold → EXPAND
    - DECIDED_GAME_CLOSING: tier >= 2 AND margin > safe margin → COMPRESS
    
    SAFETY RULES:
    - Narrative distance gating prevents FLIP spam
    - Comeback limit prevents multiple "they're coming back!" beats
    - False-drama suppression applies to inserted moments
    
    Args:
        moments: Selected moments (after Phase 2)
        events: Timeline events
        thresholds: Lead Ladder thresholds
        config: Closing configuration
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
    
    Returns:
        ClosingExpansionResult with expanded/compressed moments and diagnostics
    """
    from ..moments import Moment, MomentType, MomentReason
    from ..moments.helpers import create_moment, get_score
    from ..lead_ladder import compute_lead_state, detect_tier_crossing, Leader
    from ..boundary_helpers import is_late_false_drama, is_high_impact_event
    from ..moments_runs import run_to_info, DetectedRun
    
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
    
    # Step 2: Classify closing category
    is_close_game = closing_window.is_close_game
    is_decided_game = closing_window.is_decided_game
    
    # Step 3: Handle DECIDED_GAME_CLOSING (compression)
    if is_decided_game:
        output_moments: list["Moment"] = []
        removed_count = 0
        
        for moment in moments:
            in_closing = _is_moment_in_closing_window(moment, events, closing_window)
            
            type_value = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)
            if in_closing and type_value == "CUT":
                # Check if this CUT should be suppressed
                if moment.end_play < len(events):
                    end_event = events[moment.end_play]
                    home_score, away_score = get_score(end_event)
                    curr_state = compute_lead_state(home_score, away_score, thresholds)
                    
                    # Get state before moment
                    if moment.start_play > 0:
                        start_event = events[moment.start_play - 1]
                        prev_home, prev_away = get_score(start_event)
                        prev_state = compute_lead_state(prev_home, prev_away, thresholds)
                    else:
                        prev_state = curr_state
                    
                    # Check false drama
                    false_drama = is_late_false_drama(
                        event=end_event,
                        prev_state=prev_state,
                        curr_state=curr_state,
                        crossing_type="TIER_DOWN",
                        sport=sport,
                    )
                    
                    # Check if margin crosses threat threshold
                    margin_after = abs(home_score - away_score)
                    crosses_threat = margin_after <= config.threat_margin_threshold
                    
                    if false_drama.suppressed and not crosses_threat:
                        # Suppress this CUT moment
                        removed_count += 1
                        logger.info(
                            "closing_cut_suppressed",
                            extra={
                                "moment_id": moment.id,
                                "margin_after": margin_after,
                                "tier_after": curr_state.tier,
                                "suppressed_reason": false_drama.suppressed_reason,
                            },
                        )
                        continue
            
            output_moments.append(moment)
        
        result.moments = output_moments
        result.moments_removed = removed_count
        
        logger.info(
            "closing_compression_applied",
            extra={
                "moments_removed": removed_count,
                "final_count": len(output_moments),
            },
        )
        
        return result
    
    # Step 4: Handle CLOSE_GAME_CLOSING (expansion)
    # Find candidate events for expansion
    candidates = _find_expansion_candidates(
        events, closing_window, thresholds, config, sport
    )
    
    if not candidates:
        # No candidates - return moments unchanged
        result.moments = moments
        logger.info("closing_expansion_no_candidates")
        return result
    
    # Step 5: Evaluate candidates and apply filters
    inserted_moments: list["Moment"] = []
    last_flip_tie_index: int | None = None
    last_flip_tie_clock: str | None = None
    comeback_counts: dict[str, int] = {"home": 0, "away": 0}
    
    # Track existing moments in closing for distance calculation
    # Find the most recent FLIP/TIE in the closing window
    existing_closing_moments = [
        m for m in moments
        if _is_moment_in_closing_window(m, events, closing_window)
    ]
    
    # Find the most recent FLIP/TIE (scan backwards from end)
    for existing in reversed(existing_closing_moments):
        existing_type = existing.type.value if hasattr(existing.type, 'value') else str(existing.type)
        if existing_type in ("FLIP", "TIE"):
            if existing.end_play < len(events):
                last_flip_tie_index = existing.end_play
                last_flip_tie_clock = events[existing.end_play].get("game_clock")
                break
    
    for candidate in candidates[:config.max_additional_moments]:
        decision = ExpansionDecision(
            candidate=candidate,
            inserted=False,
            reason="pending_evaluation",
        )
        
        # Filter 1: Narrative distance gating
        allowed, distance_reason = _check_narrative_distance(
            candidate, last_flip_tie_index, last_flip_tie_clock, events, config
        )
        
        if not allowed:
            decision.reason = f"suppressed_by_density_{distance_reason}"
            decision.suppressed_by_density = True
            result.expansion_decisions.append(decision)
            logger.debug(
                "expansion_candidate_suppressed_density",
                extra={
                    "event_index": candidate.event_index,
                    "candidate_type": candidate.candidate_type,
                    "reason": distance_reason,
                },
            )
            continue
        
        # Filter 2: False-drama suppression (for CUT-like candidates)
        if candidate.candidate_type in ("run", "tier_change"):
            if candidate.event_index < len(events):
                event = events[candidate.event_index]
                home_score, away_score = get_score(event)
                curr_state = compute_lead_state(home_score, away_score, thresholds)
                
                # Check if this represents a tier decrease
                if candidate.event_index > 0:
                    prev_event = events[candidate.event_index - 1]
                    prev_home, prev_away = get_score(prev_event)
                    prev_state = compute_lead_state(prev_home, prev_away, thresholds)
                    
                    if curr_state.tier < prev_state.tier:
                        false_drama = is_late_false_drama(
                            event=event,
                            prev_state=prev_state,
                            curr_state=curr_state,
                            crossing_type="TIER_DOWN",
                            sport=sport,
                        )
                        
                        if false_drama.suppressed:
                            decision.reason = f"suppressed_by_false_drama_{false_drama.suppressed_reason}"
                            decision.suppressed_by_false_drama = True
                            result.expansion_decisions.append(decision)
                            logger.debug(
                                "expansion_candidate_suppressed_false_drama",
                                extra={
                                    "event_index": candidate.event_index,
                                    "margin_after": false_drama.margin_after,
                                    "tier_after": curr_state.tier,
                                },
                            )
                            continue
        
        # Filter 3: Comeback limit
        allowed, comeback_reason = _check_comeback_limit(
            candidate, events, moments, inserted_moments, thresholds, config
        )
        
        if not allowed:
            decision.reason = f"suppressed_by_comeback_limit_{comeback_reason}"
            decision.suppressed_by_comeback_limit = True
            result.expansion_decisions.append(decision)
            logger.debug(
                "expansion_candidate_suppressed_comeback",
                extra={
                    "event_index": candidate.event_index,
                    "reason": comeback_reason,
                },
            )
            continue
        
        # Candidate passed all filters - create moment
        try:
            # Determine moment type based on candidate
            if candidate.is_flip:
                moment_type = MomentType.FLIP
            elif candidate.is_tie:
                moment_type = MomentType.TIE
            elif candidate.candidate_type == "high_impact":
                moment_type = MomentType.HIGH_IMPACT
            elif candidate.candidate_type == "run":
                moment_type = MomentType.MOMENTUM_SHIFT
            else:
                # Default to NEUTRAL for other cases
                moment_type = MomentType.NEUTRAL
            
            # Find end index (next moment start or end of window)
            end_idx = candidate.event_index
            if candidate.event_index < len(events) - 1:
                # Try to find a natural end point (next scoring play, timeout, etc.)
                for j in range(candidate.event_index + 1, min(candidate.event_index + 10, len(events))):
                    next_event = events[j]
                    if next_event.get("event_type") == "pbp":
                        # Check if this is a natural break
                        if (next_event.get("points_scored", 0) or 0) > 0:
                            end_idx = j
                            break
                        if "timeout" in (next_event.get("play_type", "") or "").lower():
                            end_idx = j
                            break
                else:
                    end_idx = min(candidate.event_index + 5, len(events) - 1)
            
            # Get scores
            if candidate.event_index > 0:
                score_before = get_score(events[candidate.event_index - 1])
            else:
                score_before = (0, 0)
            score_after = get_score(events[end_idx])
            
            # Create the moment with unique ID
            # Use a temporary ID that will be renumbered later
            temp_id = f"closing_exp_{candidate.event_index}"
            
            new_moment = create_moment(
                moment_id=0,  # Will be renumbered
                events=events,
                start_idx=candidate.event_index,
                end_idx=end_idx,
                moment_type=moment_type,
                thresholds=thresholds,
                boundary=None,
                score_before=score_before,
                game_context={},
            )
            
            # Set temporary ID for tracking
            new_moment.id = temp_id
            
            # Override reason to indicate closing expansion
            if new_moment.reason:
                new_moment.reason.trigger = "closing_expansion"
                new_moment.reason.narrative_delta = f"closing_{candidate.candidate_type}"
            else:
                new_moment.reason = MomentReason(
                    trigger="closing_expansion",
                    control_shift=None,
                    narrative_delta=f"closing_{candidate.candidate_type}",
                )
            
            # Add diagnostics
            new_moment.importance_factors = {
                "closing_expansion_inserted": True,
                "candidate_type": candidate.candidate_type,
                "seconds_remaining": candidate.seconds_remaining,
                "closing_category": candidate.closing_category,
                "inserted_reason": distance_reason,
            }
            
            if candidate.run_points > 0:
                # Attach run info if applicable
                run = DetectedRun(
                    team=candidate.run_team or "home",
                    points=candidate.run_points,
                    start_idx=candidate.event_index,
                    end_idx=end_idx,
                )
                new_moment.run_info = run_to_info(run)
            
            inserted_moments.append(new_moment)
            decision.inserted = True
            decision.reason = f"inserted_{candidate.candidate_type}"
            
            # Update tracking for narrative distance
            if candidate.is_flip or candidate.is_tie:
                last_flip_tie_index = candidate.event_index
                if candidate.event_index < len(events):
                    last_flip_tie_clock = events[candidate.event_index].get("game_clock", "12:00") or "12:00"
                    candidate.seconds_since_last_flip_tie = 0  # This is the new last one
            
            result.moments_inserted += 1
            
            logger.info(
                "closing_moment_inserted",
                extra={
                    "moment_id": new_moment.id,
                    "candidate_type": candidate.candidate_type,
                    "event_index": candidate.event_index,
                    "seconds_remaining": candidate.seconds_remaining,
                    "moment_type": moment_type.value,
                },
            )
            
        except Exception as e:
            logger.error(
                "closing_expansion_insertion_failed",
                extra={
                    "event_index": candidate.event_index,
                    "candidate_type": candidate.candidate_type,
                    "error": str(e),
                },
            )
            decision.reason = f"insertion_failed_{str(e)}"
        
        result.expansion_decisions.append(decision)
    
    # Step 6: Merge inserted moments with existing moments
    all_moments = list(moments) + inserted_moments
    all_moments.sort(key=lambda m: m.start_play)
    
    # Step 7: Renumber all moments to ensure unique IDs
    for i, moment in enumerate(all_moments):
        moment.id = f"m_{i + 1:03d}"
    
    # Step 8: Count moments in closing and annotate
    for idx, moment in enumerate(all_moments):
        in_closing = _is_moment_in_closing_window(moment, events, closing_window)
        
        if in_closing:
            result.moments_in_closing += 1
            
            # Get closing classification at moment end
            if moment.end_play < len(events):
                end_event = events[moment.end_play]
                phase_num, seconds, tier, margin, category = _get_event_closing_classification(
                    end_event, thresholds, sport
                )
                
                type_value = moment.type.value if hasattr(moment.type, 'value') else str(moment.type)
                is_protected = type_value in config.protected_closing_types
                
                if is_protected:
                    result.moments_protected += 1
                
                # Annotate the moment
                annotation = ClosingMomentAnnotation(
                    moment_id=moment.id,
                    original_index=idx,
                    is_in_closing_window=True,
                    closing_category=category,
                    expansion_applied=moment.id.startswith("closing_exp_"),
                    reason="inserted" if moment.id.startswith("closing_exp_") else "existing",
                    seconds_remaining=seconds,
                    tier_at_moment=tier,
                    margin_at_moment=margin,
                )
                result.annotations.append(annotation)
            else:
                annotation = ClosingMomentAnnotation(
                    moment_id=moment.id,
                    original_index=idx,
                    is_in_closing_window=True,
                    closing_category="UNKNOWN",
                    expansion_applied=moment.id.startswith("closing_exp_"),
                    reason="invalid_end_play",
                )
                result.annotations.append(annotation)
        else:
            annotation = ClosingMomentAnnotation(
                moment_id=moment.id,
                original_index=idx,
                is_in_closing_window=False,
                closing_category="NOT_CLOSING",
                expansion_applied=False,
                reason="outside_closing_window",
            )
            result.annotations.append(annotation)
    
    result.moments = all_moments
    
    logger.info(
        "closing_expansion_applied",
        extra={
            "closing_window_active": closing_window.is_active,
            "closing_category": closing_window.closing_category,
            "candidates_found": len(candidates),
            "moments_inserted": result.moments_inserted,
            "moments_in_closing": result.moments_in_closing,
            "suppressed_by_density": sum(1 for d in result.expansion_decisions if d.suppressed_by_density),
            "suppressed_by_false_drama": sum(1 for d in result.expansion_decisions if d.suppressed_by_false_drama),
            "suppressed_by_comeback": sum(1 for d in result.expansion_decisions if d.suppressed_by_comeback_limit),
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
