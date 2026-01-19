"""Recap moment generation for key game boundaries.

This module creates contextual summary moments at:
- Halftime (NBA, NHL)
- End of periods (NHL: P1/P2/P3, MLB: 5th/9th)
- End of game (all sports)
- End of overtime (all sports)

Recaps provide context about momentum, key runs, and late back-and-forths
to help users understand narrative shifts.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .types import Moment, MomentType, RecapContext
from ..lead_ladder import compute_lead_state, Leader

logger = logging.getLogger(__name__)


def generate_recap_moments(
    events: Sequence[dict[str, Any]],
    moments: list[Moment],
    sport: str | None,
    thresholds: Sequence[int],
) -> list[Moment]:
    """Generate recap moments at key game boundaries.
    
    Args:
        events: All game events
        moments: All existing moments
        sport: Sport identifier ("nba", "nhl", "mlb")
        thresholds: Lead ladder thresholds
    
    Returns:
        List of recap moments to insert
    """
    recap_moments: list[Moment] = []
    
    # Find period boundaries in the events
    period_boundaries = _find_period_boundaries(events)
    
    if not period_boundaries:
        return recap_moments
    
    # Generate recaps for each boundary
    for boundary in period_boundaries:
        should_create, recap_type = should_create_recap(
            quarter=boundary["quarter"],
            is_final=boundary["is_final"],
            is_overtime=boundary["is_overtime"],
            sport=sport,
        )
        
        if should_create and recap_type:
            # Extract context for this period
            recap_context = extract_recap_context(
                events=events,
                moments=moments,
                period_start_idx=boundary["period_start"],
                period_end_idx=boundary["period_end"],
                thresholds=thresholds,
            )
            
            # Create the recap moment
            recap_moment = create_recap_moment(
                recap_type=recap_type,
                recap_context=recap_context,
                period_start_idx=boundary["period_start"],
                period_end_idx=boundary["period_end"],
                events=events,
                moment_id=f"recap_{boundary['quarter']}",  # Will be renumbered
            )
            
            recap_moments.append(recap_moment)
            
            logger.debug(
                "recap_moment_created",
                extra={
                    "recap_type": recap_type.value,
                    "quarter": boundary["quarter"],
                    "momentum": recap_context.momentum_summary,
                },
            )
    
    return recap_moments


def _find_period_boundaries(
    events: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find period/quarter boundaries in the event stream.
    
    Returns:
        List of boundary dicts with:
        - quarter: Quarter/period/inning number
        - period_start: Start index of the period
        - period_end: End index of the period
        - is_final: True if this is the end of the game
        - is_overtime: True if this is an overtime period
    """
    boundaries: list[dict[str, Any]] = []
    
    current_quarter = None
    period_start = 0
    
    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue
        
        quarter = event.get("quarter")
        if quarter is None:
            continue
        
        # Detect quarter change
        if current_quarter is not None and quarter != current_quarter:
            # End of previous period
            boundaries.append({
                "quarter": current_quarter,
                "period_start": period_start,
                "period_end": i - 1,
                "is_final": False,
                "is_overtime": current_quarter > 4,  # Simplified OT detection
            })
            period_start = i
        
        current_quarter = quarter
    
    # Add final boundary (end of game)
    if current_quarter is not None:
        boundaries.append({
            "quarter": current_quarter,
            "period_start": period_start,
            "period_end": len(events) - 1,
            "is_final": True,
            "is_overtime": current_quarter > 4,
        })
    
    return boundaries


def should_create_recap(
    quarter: int,
    is_final: bool,
    is_overtime: bool,
    sport: str | None = None,
) -> tuple[bool, MomentType | None]:
    """Determine if a recap should be created at this boundary.
    
    Args:
        quarter: Current quarter/period/inning number
        is_final: True if this is the end of the game
        is_overtime: True if this is an overtime period
        sport: Sport identifier ("nba", "nhl", "mlb")
    
    Returns:
        (should_create, recap_type)
    """
    sport = (sport or "nba").lower()
    
    # Final game recap (all sports)
    if is_final:
        return True, MomentType.GAME_RECAP
    
    # Overtime recap (all sports)
    if is_overtime:
        return True, MomentType.OVERTIME_RECAP
    
    # Sport-specific recaps
    if sport == "nba":
        # Halftime only (after Q2)
        if quarter == 2:
            return True, MomentType.HALFTIME_RECAP
    
    elif sport == "nhl":
        # After each period (P1, P2, P3)
        if quarter in (1, 2, 3):
            if quarter == 2:
                return True, MomentType.HALFTIME_RECAP  # P2 is halftime-ish
            else:
                return True, MomentType.PERIOD_RECAP
    
    elif sport == "mlb":
        # After 5th inning and 9th inning
        if quarter == 5:
            return True, MomentType.PERIOD_RECAP  # Mid-game checkpoint
        elif quarter == 9:
            return True, MomentType.PERIOD_RECAP  # End of regulation
    
    return False, None


def extract_recap_context(
    events: Sequence[dict[str, Any]],
    moments: list[Moment],
    period_start_idx: int,
    period_end_idx: int,
    thresholds: Sequence[int],
) -> RecapContext:
    """Extract contextual data for a recap moment.
    
    Priority order (most to least important):
    1. Momentum summary (who finished strong)
    2. Key runs
    3. Largest lead
    4. Lead changes
    5. Running score
    6. Top performers
    7. Period score
    
    Args:
        events: All game events
        moments: All moments in the game (for detecting lead changes)
        period_start_idx: Start index of the period
        period_end_idx: End index of the period
        thresholds: Lead ladder thresholds
    
    Returns:
        RecapContext with extracted data
    """
    from .helpers import get_score
    from ..moments_runs import detect_runs
    
    context = RecapContext()
    
    # Get period events (all events in the period range)
    period_events = list(events[period_start_idx:period_end_idx + 1])
    pbp_events = [e for e in period_events if e.get("event_type") == "pbp"]
    
    logger.debug(
        "recap_context_extraction",
        extra={
            "period_start_idx": period_start_idx,
            "period_end_idx": period_end_idx,
            "total_events": len(period_events),
            "pbp_events": len(pbp_events),
        },
    )
    
    if not pbp_events:
        logger.warning("recap_no_pbp_events", extra={"period_start": period_start_idx, "period_end": period_end_idx})
        return context
    
    # Extract scores
    period_start_score = get_score(events[period_start_idx]) if period_start_idx < len(events) else (0, 0)
    period_end_score = get_score(events[period_end_idx]) if period_end_idx < len(events) else (0, 0)
    
    context.running_score = period_end_score
    context.period_score = (
        period_end_score[0] - period_start_score[0],
        period_end_score[1] - period_start_score[1],
    )
    
    # Priority 1: Momentum summary (who finished strong)
    context.momentum_summary, context.who_has_control = _analyze_momentum(
        pbp_events, moments, period_start_idx, period_end_idx, thresholds
    )
    
    # Priority 2: Key runs
    all_runs = detect_runs(events)
    period_runs = [r for r in all_runs 
                   if r.start_idx >= period_start_idx and r.end_idx <= period_end_idx]
    
    logger.debug(
        "recap_runs_detected",
        extra={
            "total_runs": len(all_runs),
            "period_runs": len(period_runs),
            "run_points": [r.points for r in period_runs],
        },
    )
    
    # Get top 3 runs by points
    top_runs = sorted(period_runs, key=lambda r: r.points, reverse=True)[:3]
    context.key_runs = [
        {
            "team": r.team,
            "points": r.points,
            "description": f"{r.points}-pt run",
        }
        for r in top_runs if r.points >= 6  # Only include significant runs
    ]
    
    # Priority 3: Largest lead
    context.largest_lead, context.largest_lead_team = _find_largest_lead(
        pbp_events, thresholds
    )
    
    # Priority 4: Lead changes
    period_moments = [m for m in moments 
                      if m.start_play >= period_start_idx and m.end_play <= period_end_idx]
    context.lead_changes_count = sum(
        1 for m in period_moments if m.type == MomentType.FLIP
    )
    
    # Priority 6: Top performers (simplified - would need full boxscore integration)
    # For now, leave empty - will be populated by boxscore integration layer
    
    return context


def _analyze_momentum(
    period_events: Sequence[dict[str, Any]],
    moments: list[Moment],
    period_start_idx: int,
    period_end_idx: int,
    thresholds: Sequence[int],
) -> tuple[str, str | None]:
    """Analyze momentum and control in the period.
    
    Returns:
        (momentum_summary, who_has_control)
    """
    from .helpers import get_score
    
    if not period_events:
        logger.warning("momentum_analysis_no_events")
        return "No scoring", None
    
    logger.debug(
        "momentum_analysis_starting",
        extra={
            "period_events_count": len(period_events),
            "period_start_idx": period_start_idx,
            "period_end_idx": period_end_idx,
        },
    )
    
    # Look at the last 10-15 plays to determine who finished strong
    lookback_window = min(15, len(period_events))
    recent_events = period_events[-lookback_window:]
    
    # Count scoring by each team in the recent window
    home_recent_points = 0
    away_recent_points = 0
    
    for i in range(1, len(recent_events)):
        prev_score = get_score(recent_events[i - 1])
        curr_score = get_score(recent_events[i])
        home_recent_points += curr_score[0] - prev_score[0]
        away_recent_points += curr_score[1] - prev_score[1]
    
    # Get final score and state
    final_score = get_score(period_events[-1])
    final_state = compute_lead_state(final_score[0], final_score[1], thresholds)
    
    # Determine control
    who_has_control = None
    if final_state.leader == Leader.HOME:
        who_has_control = "home"
    elif final_state.leader == Leader.AWAY:
        who_has_control = "away"
    
    # Determine momentum summary
    point_diff = abs(home_recent_points - away_recent_points)
    
    if point_diff <= 3:
        momentum_summary = "Back-and-forth battle"
    elif home_recent_points > away_recent_points:
        if final_state.leader == Leader.HOME:
            momentum_summary = "Home team finished strong"
        else:
            momentum_summary = "Home team surged late"
    else:
        if final_state.leader == Leader.AWAY:
            momentum_summary = "Away team finished strong"
        else:
            momentum_summary = "Away team surged late"
    
    # Check for late lead changes (indicates back-and-forth)
    recent_moments = [m for m in moments 
                      if m.end_play >= period_end_idx - lookback_window 
                      and m.end_play <= period_end_idx]
    late_flips = sum(1 for m in recent_moments if m.type == MomentType.FLIP)
    
    if late_flips >= 2:
        momentum_summary = "Multiple late lead changes"
    
    return momentum_summary, who_has_control


def _find_largest_lead(
    period_events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
) -> tuple[int, str | None]:
    """Find the largest lead in the period.
    
    Returns:
        (largest_lead, team_with_largest_lead)
    """
    from .helpers import get_score
    
    largest_lead = 0
    largest_lead_team = None
    
    for event in period_events:
        score = get_score(event)
        margin = abs(score[0] - score[1])
        
        if margin > largest_lead:
            largest_lead = margin
            if score[0] > score[1]:
                largest_lead_team = "home"
            else:
                largest_lead_team = "away"
    
    return largest_lead, largest_lead_team


def create_recap_moment(
    recap_type: MomentType,
    recap_context: RecapContext,
    period_start_idx: int,
    period_end_idx: int,
    events: Sequence[dict[str, Any]],
    moment_id: str,
) -> Moment:
    """Create a recap moment with context.
    
    Args:
        recap_type: Type of recap (HALFTIME_RECAP, PERIOD_RECAP, etc.)
        recap_context: Extracted context data
        period_start_idx: Start index of the period
        period_end_idx: End index of the period
        events: All game events
        moment_id: ID for the moment
    
    Returns:
        Recap moment
    """
    from .helpers import get_score
    from .types import MomentReason
    
    # Get scores
    score_before = get_score(events[period_start_idx]) if period_start_idx < len(events) else (0, 0)
    score_after = get_score(events[period_end_idx]) if period_end_idx < len(events) else (0, 0)
    
    # Create reason
    reason = MomentReason(
        trigger="recap",
        control_shift=recap_context.who_has_control,
        narrative_delta=recap_context.momentum_summary,
    )
    
    # Generate headline and summary
    headline, summary = _generate_recap_narrative(recap_type, recap_context)
    
    # Format scores for display (away-home format)
    score_start_str = f"{score_before[1]}–{score_before[0]}"
    score_end_str = f"{score_after[1]}–{score_after[0]}"
    
    # Determine teams and primary team from recap context
    teams = []
    primary_team = None
    if recap_context.who_has_control:
        primary_team = recap_context.who_has_control
        teams = ["home", "away"]
    
    # Get clock info from events
    clock_str = ""
    if period_start_idx < len(events) and period_end_idx < len(events):
        start_event = events[period_start_idx]
        end_event = events[period_end_idx]
        start_q = start_event.get("quarter", "?")
        end_q = end_event.get("quarter", "?")
        if start_q == end_q:
            clock_str = f"Q{start_q} Recap"
        else:
            clock_str = f"Q{start_q}–Q{end_q} Recap"
    
    # Recap moments don't own plays - they're contextual summaries
    # Set start_play = end_play to make them "zero-width" boundary markers
    # This ensures they don't overlap with regular moments in coverage validation
    moment = Moment(
        id=moment_id,
        type=recap_type,
        start_play=period_end_idx,  # Point to the last play of the period
        end_play=period_end_idx,    # Same as start - zero width
        play_count=0,  # Recap doesn't own plays
        score_before=score_before,
        score_after=score_after,
        score_start=score_start_str,
        score_end=score_end_str,
        teams=teams,
        primary_team=primary_team,
        clock=clock_str,
        recap_context=recap_context,
        reason=reason,
        headline=headline,
        summary=summary,
        is_notable=True,  # Recaps are always notable
        is_recap=True,  # Flag for validation to skip
    )
    
    return moment


def _generate_recap_narrative(
    recap_type: MomentType,
    context: RecapContext,
) -> tuple[str, str]:
    """Generate headline and summary for recap.
    
    Returns:
        (headline, summary)
    """
    # Headline (max 60 chars)
    if recap_type == MomentType.HALFTIME_RECAP:
        headline = f"Halftime: {context.running_score[1]}-{context.running_score[0]}"
    elif recap_type == MomentType.GAME_RECAP:
        headline = f"Final: {context.running_score[1]}-{context.running_score[0]}"
    elif recap_type == MomentType.OVERTIME_RECAP:
        headline = f"OT Recap: {context.running_score[1]}-{context.running_score[0]}"
    else:
        headline = f"Period Recap: {context.running_score[1]}-{context.running_score[0]}"
    
    # Summary (max 150 chars) - prioritize momentum and key runs
    summary_parts = []
    
    # Priority 1: Momentum
    if context.momentum_summary:
        summary_parts.append(context.momentum_summary)
    
    # Priority 2: Key runs
    if context.key_runs:
        run_desc = context.key_runs[0]
        summary_parts.append(f"{run_desc['points']}-pt run")
    
    # Priority 4: Lead changes
    if context.lead_changes_count > 0:
        summary_parts.append(f"{context.lead_changes_count} lead change{'s' if context.lead_changes_count > 1 else ''}")
    
    summary = ". ".join(summary_parts)
    if len(summary) > 150:
        summary = summary[:147] + "..."
    
    return headline, summary
