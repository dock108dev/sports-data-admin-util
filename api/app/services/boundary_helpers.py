"""Boundary detection helper functions.

Low-level helpers for game state analysis, gating, and density checks.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .lead_ladder import LeadState
from .boundary_types import (
    DensityGateDecision,
    LateFalseDramaDecision,
    DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS,
    DEFAULT_FLIP_TIE_DENSITY_WINDOW_SECONDS,
    DENSITY_GATE_LATE_GAME_PROGRESS,
    CLOSING_FINAL_SEQUENCE_SECONDS,
    CLOSING_RUN_OVERRIDE_POINTS,
    CLOSING_ONE_POSSESSION_THRESHOLD,
    CLOSING_FIRST_FLIP_TIE_ALWAYS_ALLOW,
    LATE_GAME_SAFE_MARGIN,
    LATE_GAME_SAFE_TIER,
    LATE_GAME_MAX_SECONDS,
    LATE_GAME_MIN_QUARTER,
)

logger = logging.getLogger(__name__)


def get_canonical_pbp_indices(
    events: Sequence[dict[str, Any]],
    require_description: bool = True,
) -> list[int]:
    """
    Filter the timeline to find only real, narrative-relevant PBP plays.

    PHASE 1.4: This function now expects score-normalized events.
    Score normalization happens BEFORE boundary detection.

    A "canonical" play is:
    1. event_type == "pbp"
    2. Has home_score and away_score (not None)
    3. Optionally has a description (for narrative value)
    4. DOES advance the narrative (score changes or unique description)

    This creates a clean stream of plays for hysteresis counting.
    """
    indices: list[int] = []

    prev_home: int | None = None
    prev_away: int | None = None

    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue

        home = event.get("home_score")
        away = event.get("away_score")

        # Must have scores
        if home is None or away is None:
            continue

        # Optionally require description for narrative relevance
        if require_description and not event.get("description"):
            continue

        # Convert to int for comparison
        home_int = int(home)
        away_int = int(away)

        # Check if this advances the narrative
        score_changed = (prev_home is None or prev_away is None
                         or home_int != prev_home or away_int != prev_away)

        # For non-scoring plays, we still include them if they have descriptions
        # (they represent game flow even without score changes)
        if score_changed or event.get("description"):
            indices.append(i)

            # Use actual values for comparison to avoid None issues
            home_for_compare = home_int
            away_for_compare = away_int

            prev_home = home_for_compare
            prev_away = away_for_compare

    return indices


def get_score(event: dict[str, Any]) -> tuple[int, int]:
    """Extract (home_score, away_score) from an event."""
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    return home, away


def get_game_progress(event: dict[str, Any]) -> float:
    """
    Estimate game progress as 0.0 to 1.0.

    Uses quarter and clock to compute rough progress.
    Default assumptions for NBA-style games (4 quarters, 12 min each).
    """
    from ..utils.datetime_utils import parse_clock_to_seconds

    quarter = event.get("quarter", 1) or 1
    clock = event.get("game_clock", "12:00")

    # Handle OT
    if quarter > 4:
        return 1.0

    # Parse clock
    try:
        seconds = parse_clock_to_seconds(clock)
    except (ValueError, TypeError):
        seconds = 720  # Default to start of quarter

    # Each quarter is 12 minutes = 720 seconds
    quarter_duration = 720.0
    total_game_seconds = quarter_duration * 4

    # Calculate progress
    completed_quarters = (quarter - 1) * quarter_duration
    quarter_elapsed = quarter_duration - seconds
    total_elapsed = completed_quarters + quarter_elapsed

    return min(1.0, total_elapsed / total_game_seconds)


def is_closing_situation(
    event: dict[str, Any],
    curr_state: LeadState,
    sport: str | None = None,
) -> bool:
    """
    Check if this is a decided closing situation (late game with safe lead).

    UNIFIED CLOSING TAXONOMY (SPORT-AGNOSTIC):
    This function returns True for DECIDED_GAME_CLOSING situations,
    which triggers CLOSING_CONTROL instead of regular tier crossing.

    Works across all sports:
    - NBA: Q4 or OT with safe lead
    - NCAAB: 2nd half or OT with safe lead
    - NHL: 3rd period or OT with safe lead
    - NFL: Q4 or OT with safe lead

    For the full closing classification including CLOSE_GAME_CLOSING,
    use classify_closing_situation() from moments.closing.
    """
    from .moments.closing import classify_closing_situation

    classification = classify_closing_situation(event, curr_state, sport=sport)

    # CLOSING_CONTROL triggers on decided game closing
    return classification.is_decided_game


def is_high_impact_event(event: dict[str, Any]) -> bool:
    """Check if event is high-impact (ejection, injury, etc.)."""
    play_type = (event.get("play_type") or "").lower()
    description = (event.get("description") or "").lower()

    high_impact_markers = ["ejection", "ejected", "injury", "injured", "flagrant"]

    return any(m in play_type or m in description for m in high_impact_markers)


def should_gate_early_flip(
    event: dict[str, Any],
    curr_state: LeadState,
    prev_state: LeadState,
) -> bool:
    """
    Determine if an early-game FLIP should be gated (require hysteresis).

    PHASE 1 SUPPRESSION RULE:
    - In Q1, tier-0 flips require confirmation
    - Flips at higher tiers or later in the game are immediate

    Returns True if the flip should be gated (delayed pending confirmation).
    """
    game_progress = get_game_progress(event)

    # First 15% of game = early game
    if game_progress > 0.15:
        return False

    # Only gate tier-0 flips (very close games)
    if curr_state.tier > 0 or prev_state.tier > 0:
        return False

    return True


def should_gate_early_tie(
    event: dict[str, Any],
    prev_state: LeadState,
) -> bool:
    """
    Determine if an early-game TIE should be gated (require hysteresis).

    PHASE 1 SUPPRESSION RULE:
    - In Q1, ties from tier-0 require confirmation
    - Ties from higher tiers (dramatic comebacks) are immediate

    Returns True if the tie should be gated (delayed pending confirmation).
    """
    game_progress = get_game_progress(event)

    # First 15% of game = early game
    if game_progress > 0.15:
        return False

    # Only gate if coming from tier-0 (low significance)
    if prev_state.tier > 0:
        return False

    return True


def get_seconds_remaining(event: dict[str, Any]) -> int:
    """Get seconds remaining in the current quarter from an event."""
    from ..utils.datetime_utils import parse_clock_to_seconds

    clock = event.get("game_clock", "12:00") or "12:00"

    try:
        return parse_clock_to_seconds(clock)
    except (ValueError, TypeError):
        return 720  # Default to start of quarter


def is_late_false_drama(
    event: dict[str, Any],
    prev_state: LeadState,
    curr_state: LeadState,
    crossing_type: str,
    sport: str | None = None,
    safe_margin: int = LATE_GAME_SAFE_MARGIN,
    safe_tier: int = LATE_GAME_SAFE_TIER,
    max_seconds: int = LATE_GAME_MAX_SECONDS,
    min_quarter: int = LATE_GAME_MIN_QUARTER,
) -> LateFalseDramaDecision:
    """
    Check if a TIER_DOWN/CUT boundary should be suppressed as "late false drama".

    UNIFIED CLOSING TAXONOMY (SPORT-AGNOSTIC):
    This function uses the unified closing classification. A boundary is
    suppressed when it occurs in DECIDED_GAME_CLOSING situations.

    Works across all sports:
    - NBA: Q4 or OT
    - NCAAB: 2nd half or OT
    - NHL: 3rd period or OT
    - NFL: Q4 or OT

    In decided game closing:
    - CUT/TIER_DOWN boundaries are suppressed
    - The game is functionally decided
    - Cuts don't threaten the outcome

    Args:
        event: Current timeline event
        prev_state: Lead state before the crossing
        curr_state: Lead state after the crossing
        crossing_type: "TIER_DOWN" or "CUT" or "RUN"
        sport: Sport identifier (NBA, NCAAB, NHL, NFL)
        safe_margin: Minimum margin to consider "safe" (default 10)
        safe_tier: Minimum tier to consider "safe" (default 2)
        max_seconds: Maximum seconds remaining for late-game check (default 150)
        min_quarter: Minimum quarter for late-game check (default 4)

    Returns:
        LateFalseDramaDecision with suppression decision and diagnostics
    """
    from .moments.closing import classify_closing_situation, should_suppress_cut_boundary
    from .moments.game_structure import compute_game_phase_state, get_phase_label

    # Compute sport-agnostic phase state
    phase_state = compute_game_phase_state(event, sport)

    # Calculate margins
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    margin_after = abs(home - away)

    # Estimate margin before (from prev_state or by reversing the change)
    margin_before = prev_state.margin if hasattr(prev_state, 'margin') else margin_after

    # Build base decision record with sport-agnostic phase info
    decision = LateFalseDramaDecision(
        event_index=event.get("_original_index", 0),
        crossing_type=crossing_type,
        suppressed=False,
        suppressed_reason="outcome_threatening",
        phase_number=phase_state.phase_number,
        phase_label=get_phase_label(phase_state),
        is_final_phase=phase_state.is_final_phase,
        is_overtime=phase_state.is_overtime,
        seconds_remaining=phase_state.remaining_seconds,
        margin_before=margin_before,
        margin_after=margin_after,
        tier_before=prev_state.tier,
        tier_after=curr_state.tier,
    )

    # Use unified closing classification (sport-agnostic)
    classification = classify_closing_situation(event, curr_state, sport=sport)

    # Check if we should suppress based on unified taxonomy
    if should_suppress_cut_boundary(classification):
        decision.suppressed = True
        decision.suppressed_reason = f"late_false_drama_{classification.category.value}"

        logger.debug(
            "late_false_drama_detected",
            extra={
                "event_index": decision.event_index,
                "crossing_type": crossing_type,
                "closing_category": classification.category.value,
                "phase_label": decision.phase_label,
                "is_final_phase": decision.is_final_phase,
                "seconds_remaining": decision.seconds_remaining,
                "margin_after": margin_after,
                "tier_after": curr_state.tier,
                "sport": sport or "NBA",
                "reason": classification.reason,
            },
        )
    else:
        # Not suppressed - record why
        if not classification.is_closing:
            decision.suppressed_reason = f"not_closing_{classification.reason}"
        elif classification.is_close_game:
            decision.suppressed_reason = "close_game_closing"
        else:
            decision.suppressed_reason = "outcome_threatening"

    return decision


def should_density_gate_flip_tie(
    event: dict[str, Any],
    curr_state: LeadState,
    crossing_type: str,
    current_canonical_pos: int,
    last_flip_tie_canonical_pos: int | None,
    last_flip_tie_index: int | None,
    density_window_plays: int = DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS,
    density_window_seconds: int = DEFAULT_FLIP_TIE_DENSITY_WINDOW_SECONDS,
    last_flip_tie_clock: str | None = None,
    is_first_flip_tie_in_closing: bool = False,
    preceding_run_points: int = 0,
    preceding_run_team: str | None = None,
) -> DensityGateDecision:
    """
    Determine if a FLIP or TIE should be suppressed due to narrative distance gating.

    NARRATIVE DISTANCE GATING:
    This replaces the previous blanket "override_late_close" that disabled all gating
    in close late-game situations. Now we use narrative distance (plays + time) and
    grant overrides only for specific, explainable conditions.

    A FLIP/TIE is suppressed if:
    1. A previous FLIP/TIE boundary was emitted within:
       - density_window_plays canonical plays, OR
       - density_window_seconds game time
    2. AND the current event does NOT qualify for an override

    Override-worthy conditions (must be explainable):
    - FIRST_IN_CLOSING: First FLIP/TIE in the closing window (always allowed)
    - FINAL_SEQUENCE: Game time <= 60 seconds remaining (true final sequence)
    - AFTER_RUN: Lead change after a scoring run >= N points
    - ONE_POSSESSION: Lead change with margin <= one possession threshold

    Args:
        event: Current timeline event
        curr_state: Current lead state
        crossing_type: "FLIP" or "TIE"
        current_canonical_pos: Position in canonical PBP stream (0-indexed)
        last_flip_tie_canonical_pos: Position of last FLIP/TIE boundary (or None)
        last_flip_tie_index: Timeline index of last FLIP/TIE boundary (or None)
        density_window_plays: Min plays between FLIP/TIE boundaries
        density_window_seconds: Min seconds between FLIP/TIE boundaries
        last_flip_tie_clock: Game clock string of last accepted FLIP/TIE (for time distance)
        is_first_flip_tie_in_closing: Whether this is the first FLIP/TIE in closing window
        preceding_run_points: Points scored in a run preceding this event
        preceding_run_team: Team that scored the preceding run

    Returns:
        DensityGateDecision with suppression decision and full diagnostics
    """
    from ..utils.datetime_utils import parse_clock_to_seconds

    event_index = event.get("_original_index", 0)
    game_progress = get_game_progress(event)
    current_clock = event.get("game_clock", "12:00") or "12:00"
    seconds_remaining = get_seconds_remaining(event)
    quarter = event.get("quarter", 1) or 1

    # Calculate margin
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    margin = abs(home - away)

    # Determine if we're in the closing window (late Q4 or OT)
    is_in_closing_window = (
        game_progress >= DENSITY_GATE_LATE_GAME_PROGRESS or quarter > 4
    )

    # Build base decision record with full diagnostics
    decision = DensityGateDecision(
        event_index=event_index,
        crossing_type=crossing_type,
        density_gate_applied=False,
        reason="no_recent_boundary",
        last_flip_tie_index=last_flip_tie_index,
        last_flip_tie_canonical_pos=last_flip_tie_canonical_pos,
        current_canonical_pos=current_canonical_pos,
        window_size_plays=density_window_plays,
        window_size_seconds=density_window_seconds,
        last_flip_tie_clock=last_flip_tie_clock,
        current_clock=current_clock,
        game_progress=game_progress,
        seconds_remaining=seconds_remaining,
        tier_at_event=curr_state.tier,
        margin_at_event=margin,
        is_in_closing_window=is_in_closing_window,
        is_first_in_closing=is_first_flip_tie_in_closing,
        override_qualified=False,
        override_reason=None,
        preceding_run_points=preceding_run_points,
        preceding_run_team=preceding_run_team,
    )

    # === CASE 1: No previous FLIP/TIE boundary ===
    if last_flip_tie_canonical_pos is None:
        decision.reason = "no_recent_boundary"
        return decision

    # === Calculate narrative distance ===
    plays_since_last = current_canonical_pos - last_flip_tie_canonical_pos
    decision.plays_since_last = plays_since_last

    # Calculate time distance if we have the last clock
    seconds_since_last: int | None = None
    if last_flip_tie_clock is not None:
        try:
            last_seconds = parse_clock_to_seconds(last_flip_tie_clock)
            current_seconds = parse_clock_to_seconds(current_clock)
            
            # Clock counts down within a quarter, so last_seconds >= current_seconds
            # indicates elapsed time within the same quarter/period.
            if last_seconds >= current_seconds:
                seconds_since_last = last_seconds - current_seconds
            else:
                # Clock increased (e.g., 2:00 in Q3 -> 11:00 in Q4 after quarter reset).
                # This implies a quarter/period boundary crossed.
                # To avoid underestimating elapsed time across quarters, treat this as
                # being outside the time window so it won't be suppressed on time grounds.
                seconds_since_last = density_window_seconds
            
            decision.seconds_since_last = seconds_since_last
        except (ValueError, TypeError):
            seconds_since_last = None

    # === CASE 2: Outside BOTH distance windows ===
    outside_plays_window = plays_since_last >= density_window_plays
    outside_seconds_window = (
        seconds_since_last is None or seconds_since_last >= density_window_seconds
    )

    if outside_plays_window and outside_seconds_window:
        decision.reason = "outside_both_windows"
        return decision

    if outside_plays_window:
        decision.reason = "outside_plays_window"
        return decision

    # === CASE 3: Within distance window - evaluate override conditions ===

    # Override 1: First FLIP/TIE in closing window
    if is_first_flip_tie_in_closing and CLOSING_FIRST_FLIP_TIE_ALWAYS_ALLOW:
        decision.override_qualified = True
        decision.override_reason = "first_in_closing"
        decision.reason = "override_first_in_closing"
        logger.debug(
            "density_gate_override_first_in_closing",
            extra={
                "event_index": event_index,
                "crossing_type": crossing_type,
                "plays_since_last": plays_since_last,
                "seconds_since_last": seconds_since_last,
            },
        )
        return decision

    # Override 2: True final sequence (very late in game)
    if seconds_remaining <= CLOSING_FINAL_SEQUENCE_SECONDS and is_in_closing_window:
        decision.override_qualified = True
        decision.override_reason = "final_sequence"
        decision.reason = f"override_final_sequence_{seconds_remaining}s"
        logger.debug(
            "density_gate_override_final_sequence",
            extra={
                "event_index": event_index,
                "crossing_type": crossing_type,
                "seconds_remaining": seconds_remaining,
                "plays_since_last": plays_since_last,
            },
        )
        return decision

    # Override 3: After a significant scoring run
    if preceding_run_points >= CLOSING_RUN_OVERRIDE_POINTS:
        decision.override_qualified = True
        decision.override_reason = f"after_run_{preceding_run_points}pts"
        decision.reason = f"override_after_{preceding_run_points}pt_run"
        logger.debug(
            "density_gate_override_after_run",
            extra={
                "event_index": event_index,
                "crossing_type": crossing_type,
                "run_points": preceding_run_points,
                "run_team": preceding_run_team,
                "plays_since_last": plays_since_last,
            },
        )
        return decision

    # Override 4: One-possession game (only for FLIPs, not TIEs)
    if (
        crossing_type == "FLIP"
        and margin <= CLOSING_ONE_POSSESSION_THRESHOLD
        and is_in_closing_window
    ):
        decision.override_qualified = True
        decision.override_reason = f"one_possession_margin_{margin}"
        decision.reason = f"override_one_possession_flip"
        logger.debug(
            "density_gate_override_one_possession",
            extra={
                "event_index": event_index,
                "crossing_type": crossing_type,
                "margin": margin,
                "plays_since_last": plays_since_last,
            },
        )
        return decision

    # === CASE 4: Within window, no override - SUPPRESS ===
    decision.density_gate_applied = True
    if seconds_since_last is not None and seconds_since_last < density_window_seconds:
        decision.reason = (
            f"within_window_{plays_since_last}plays_{seconds_since_last}s"
        )
    else:
        decision.reason = f"within_window_{plays_since_last}plays"

    logger.debug(
        "density_gate_suppressed",
        extra={
            "event_index": event_index,
            "crossing_type": crossing_type,
            "plays_since_last": plays_since_last,
            "seconds_since_last": seconds_since_last,
            "is_in_closing_window": is_in_closing_window,
            "margin": margin,
            "seconds_remaining": seconds_remaining,
            "last_flip_tie_index": last_flip_tie_index,
        },
    )

    return decision
