"""Helper functions for moment creation and processing.

This module contains utility functions used throughout the moment system:
- Score formatting and extraction
- Time bucket calculation
- Period detection
- Game progress calculation
- Early-game gating logic
- Moment creation and validation
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from ...utils.datetime_utils import parse_clock_to_seconds
from ..lead_ladder import Leader, LeadState, compute_lead_state
from ..moments_boundaries import BoundaryEvent

from .types import (
    Moment,
    MomentReason,
    MomentType,
    PlayerContribution,
)
from .config import (
    EARLY_GAME_PROGRESS_THRESHOLD,
    MID_GAME_PROGRESS_THRESHOLD,
    EARLY_GAME_MIN_TIER_FOR_IMMEDIATE,
    HIGH_IMPACT_PLAY_TYPES,
)

logger = logging.getLogger(__name__)


def format_score(home: int | None, away: int | None) -> str:
    """Format score as 'away–home'."""
    if home is None or away is None:
        return ""
    return f"{away}–{home}"


def get_score(event: dict[str, Any]) -> tuple[int, int]:
    """Extract (home_score, away_score) from an event."""
    # Ensure we use 0 as fallback if scores are explicitly None or 0
    home = event.get("home_score")
    away = event.get("away_score")
    
    # If both are 0, it might be a reset marker.
    # In that case, we should have carried it forward in normalization,
    # but as a safety, we return (0, 0) and let the caller handle it.
    return (home or 0, away or 0)


def get_bucket(event: dict[str, Any], sport: str | None = None) -> str:
    """Determine time bucket (early/mid/late) from event.

    SPORT-AGNOSTIC: Uses unified game structure.
    - "early": First ~35% of game
    - "mid": Middle portion
    - "late": Final phase with closing time remaining
    """
    from .game_structure import compute_game_phase_state
    
    phase_state = compute_game_phase_state(event, sport)
    
    if phase_state.game_progress <= 0.35:
        return "early"
    
    if phase_state.is_final_phase and phase_state.is_closing_window:
        return "late"
    
    if phase_state.is_late_game:
        return "late"
    
    return "mid"


def is_period_opener(event: dict[str, Any], prev_event: dict[str, Any] | None) -> bool:
    """Check if this event starts a new period."""
    if prev_event is None:
        return True
    return event.get("quarter") != prev_event.get("quarter")


def is_high_impact_event(event: dict[str, Any]) -> bool:
    """Check if event is a high-impact non-scoring event."""
    play_type = event.get("play_type", "")
    return play_type in HIGH_IMPACT_PLAY_TYPES


def get_game_progress(event: dict[str, Any], sport: str | None = None) -> float:
    """Calculate game progress (0.0 to 1.0) from event context.

    Uses quarter/period and game clock to determine how far into the game we are.
    Used for time-aware gating of FLIP/TIE triggers.

    SPORT-AGNOSTIC: Uses unified game structure.
    - NBA: 4 quarters × 12 min
    - NCAAB: 2 halves × 20 min
    - NHL: 3 periods × 20 min
    - NFL: 4 quarters × 15 min

    Args:
        event: Timeline event with quarter/period and game_clock
        sport: Sport identifier (optional, defaults to NBA)

    Returns:
        Float from 0.0 (game start) to 1.0 (end of regulation), >1.0 in OT
    """
    from .game_structure import compute_game_progress

    return compute_game_progress(event, sport)


def get_game_phase(game_progress: float) -> str:
    """Determine game phase from progress.

    SPORT-AGNOSTIC: Uses progress-based thresholds that work
    for any game structure.

    Returns:
        "early" - First ~35% of game
        "mid" - Middle portion (35% to 75%)
        "late" - Final stretch (75%+ or OT)
    """
    if game_progress <= EARLY_GAME_PROGRESS_THRESHOLD:
        return "early"
    elif game_progress <= MID_GAME_PROGRESS_THRESHOLD:
        return "mid"
    else:
        return "late"


def get_game_phase_from_event(event: dict[str, Any], sport: str | None = None) -> str:
    """Determine game phase from event.
    
    SPORT-AGNOSTIC: Uses unified game structure.

    Args:
        event: Timeline event with quarter/period and game_clock
        sport: Sport identifier

    Returns:
        "early", "mid", or "late"
    """
    from .game_structure import compute_game_phase_state
    
    phase_state = compute_game_phase_state(event, sport)
    return get_game_phase(phase_state.game_progress)


def should_gate_early_flip(
    event: dict[str, Any],
    curr_state: LeadState,
    prev_state: LeadState,
) -> bool:
    """Determine if a FLIP should be gated (require hysteresis) in early game.

    In early game, micro-flips (tier 0 to tier 0) are noise.
    Only significant flips (higher tier) bypass hysteresis.

    Returns:
        True if this FLIP should require hysteresis
        False if this FLIP is significant and can be immediate
    """
    game_progress = get_game_progress(event)
    phase = get_game_phase(game_progress)

    if phase == "late":
        return False

    if curr_state.tier >= EARLY_GAME_MIN_TIER_FOR_IMMEDIATE:
        return False

    if phase == "early":
        return True

    total_score = curr_state.home_score + curr_state.away_score
    if total_score > 30:
        return False

    return True


def should_gate_early_tie(
    event: dict[str, Any],
    prev_state: LeadState,
) -> bool:
    """Determine if a TIE should be gated (require hysteresis) in early game.

    In early game, ties at 2-2, 4-4, etc. are noise.
    Only ties that break significant leads matter.

    Returns:
        True if this TIE should require hysteresis
        False if this TIE is significant and can be immediate
    """
    game_progress = get_game_progress(event)
    phase = get_game_phase(game_progress)

    if phase == "late":
        return False

    if prev_state.tier >= EARLY_GAME_MIN_TIER_FOR_IMMEDIATE:
        return False

    if phase == "early":
        return True

    total_score = prev_state.home_score + prev_state.away_score
    if total_score > 40:
        return False

    return True


def extract_moment_context(
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    game_context: dict[str, str],
) -> tuple[list[str], str | None, list[PlayerContribution], list[int]]:
    """MOMENT RESOLUTION PASS: Deeply inspect plays to extract participants.

    Returns:
        - teams_involved: All teams with plays in this moment
        - primary_team: The team that drove the narrative
        - players: Top 1-3 players by impact
        - key_play_ids: Play indices for significant actions
    """
    teams_involved: set[str] = set()
    player_impact: dict[str, int] = {}
    player_data: dict[str, dict[str, int]] = {}
    team_impact: dict[str, int] = {}
    key_play_ids: list[int] = []

    start_score = None
    end_score = None

    for i in range(start_idx, end_idx + 1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue

        if start_score is None:
            start_score = (event.get("home_score", 0), event.get("away_score", 0))
        end_score = (event.get("home_score", 0), event.get("away_score", 0))

        team_abbrev = event.get("team_abbreviation")
        if team_abbrev:
            teams_involved.add(team_abbrev)

        player_name = event.get("player_name")
        description = (event.get("description") or "").lower()
        impact = 0

        if "made" in description:
            impact += 10
            if "three" in description or "3pt" in description:
                impact += 5
        if "assist" in description:
            impact += 5
        if "block" in description:
            impact += 7
        if "steal" in description:
            impact += 7
        if "rebound" in description:
            impact += 3

        if player_name:
            player_impact[player_name] = player_impact.get(player_name, 0) + impact
            if player_name not in player_data:
                player_data[player_name] = {
                    "points": 0,
                    "assists": 0,
                    "rebounds": 0,
                    "steals": 0,
                    "blocks": 0,
                }
            
            # Track actual stats from play descriptions
            if "made" in description:
                if "three" in description or "3pt" in description:
                    player_data[player_name]["points"] = player_data[player_name].get("points", 0) + 3
                elif "free throw" in description:
                    player_data[player_name]["points"] = player_data[player_name].get("points", 0) + 1
                else:
                    # Assume 2-pointer
                    player_data[player_name]["points"] = player_data[player_name].get("points", 0) + 2
            
            if "assist" in description:
                player_data[player_name]["assists"] = player_data[player_name].get("assists", 0) + 1
            
            if "rebound" in description:
                player_data[player_name]["rebounds"] = player_data[player_name].get("rebounds", 0) + 1
            
            if "steal" in description:
                player_data[player_name]["steals"] = player_data[player_name].get("steals", 0) + 1
            
            if "block" in description:
                player_data[player_name]["blocks"] = player_data[player_name].get("blocks", 0) + 1
            
            if impact > 0:
                key_play_ids.append(i)

        if team_abbrev and impact > 0:
            team_impact[team_abbrev] = team_impact.get(team_abbrev, 0) + impact

    # Build team name resolution map
    team_name_map: dict[str, str] = {}
    if game_context:
        home_abbrev = game_context.get("home_team_abbrev", "HOME")
        away_abbrev = game_context.get("away_team_abbrev", "AWAY")
        home_name = game_context.get("home_team_name", "Home")
        away_name = game_context.get("away_team_name", "Away")

        team_name_map[home_abbrev] = home_name
        team_name_map[away_abbrev] = away_name
        team_name_map["home"] = home_name
        team_name_map["away"] = away_name
        team_name_map["HOME"] = home_name
        team_name_map["AWAY"] = away_name

    # Resolve primary team by score delta
    primary_team = None
    if start_score and end_score:
        home_start = start_score[0] if start_score[0] is not None else 0
        away_start = start_score[1] if start_score[1] is not None else 0
        home_end = end_score[0] if end_score[0] is not None else 0
        away_end = end_score[1] if end_score[1] is not None else 0

        home_delta = home_end - home_start
        away_delta = away_end - away_start

        if home_delta > away_delta:
            primary_team = team_name_map.get("home", "home")
        elif away_delta > home_delta:
            primary_team = team_name_map.get("away", "away")
        elif team_impact:
            top_abbrev = max(team_impact.items(), key=lambda x: x[1])[0]
            primary_team = team_name_map.get(top_abbrev, top_abbrev)

    resolved_teams = [team_name_map.get(abbrev, abbrev) for abbrev in teams_involved]

    sorted_players = sorted(player_impact.items(), key=lambda x: x[1], reverse=True)[:3]
    players = [
        PlayerContribution(name=name, stats=player_data.get(name, {}))
        for name, _ in sorted_players
    ]

    return resolved_teams, primary_team, players, key_play_ids


def create_moment_reason(
    moment_type: MomentType,
    start_state: LeadState,
    end_state: LeadState,
    team_in_control: str | None,
) -> MomentReason:
    """Create a reason explaining WHY this moment exists."""
    trigger_map = {
        "FLIP": "flip",
        "TIE": "tie",
        "CLOSING_CONTROL": "closing_lock",
        "HIGH_IMPACT": "high_impact",
        "LEAD_BUILD": "tier_cross",
        "CUT": "tier_cross",
        "NEUTRAL": "stable",
    }
    type_str = moment_type.value if hasattr(moment_type, "value") else str(moment_type)
    trigger = trigger_map.get(type_str, "unknown")

    if trigger == "unknown":
        logger.error(f"moment_creation_failed: unknown_trigger_for_type_{type_str}")

    control_shift: str | None = None
    if start_state.leader != end_state.leader:
        if end_state.leader == Leader.HOME:
            control_shift = "home"
        elif end_state.leader == Leader.AWAY:
            control_shift = "away"

    if type_str == "FLIP":
        narrative_delta = "control changed"
    elif type_str == "TIE":
        narrative_delta = "tension ↑"
    elif type_str == "CLOSING_CONTROL":
        narrative_delta = "game locked"
    elif type_str == "LEAD_BUILD":
        tier_diff = end_state.tier - start_state.tier
        if tier_diff >= 2:
            narrative_delta = "control solidified"
        else:
            narrative_delta = "lead extended"
    elif type_str == "CUT":
        narrative_delta = "pressure relieved" if team_in_control else "momentum shift"
    elif type_str == "HIGH_IMPACT":
        narrative_delta = "context changed"
    else:
        narrative_delta = "stable flow"

    return MomentReason(
        trigger=trigger,
        control_shift=control_shift,
        narrative_delta=narrative_delta,
    )


def is_moment_notable(
    moment_type: MomentType,
    start_state: LeadState,
    end_state: LeadState,
    boundary: BoundaryEvent | None,
) -> bool:
    """Determine if a moment is notable (a key game event).

    Notable moments are those that significantly changed game control:
    - All FLIPs (leader changed)
    - All TIEs (game went to even)
    - CLOSING_CONTROL (daggers)
    - HIGH_IMPACT events
    - LEAD_BUILD with tier change >= 2
    - CUT with tier change >= 2
    """
    if moment_type in (
        MomentType.FLIP,
        MomentType.TIE,
        MomentType.CLOSING_CONTROL,
        MomentType.HIGH_IMPACT,
    ):
        return True

    if moment_type in (MomentType.LEAD_BUILD, MomentType.CUT):
        tier_change = abs(end_state.tier - start_state.tier)
        return tier_change >= 2

    return False


def create_moment(
    moment_id: int,
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    moment_type: MomentType,
    thresholds: Sequence[int],
    boundary: BoundaryEvent | None,
    score_before: tuple[int, int],
    game_context: dict[str, str] | None = None,
    phase_state: Any = None,  # PROMPT 2: GamePhaseState
    previous_moment: "Moment | None" = None,  # PROMPT 2: Previous moment for context
) -> Moment:
    """Create a Moment and run the RESOLUTION PASS.
    
    PROMPT 2 Enhancement: Now accepts phase_state and previous_moment
    to enable context-aware narrative generation.
    """
    start_event = events[start_idx]
    end_event = events[end_idx]

    score_after = get_score(end_event)

    start_state = compute_lead_state(score_before[0], score_before[1], thresholds)
    end_state = compute_lead_state(score_after[0], score_after[1], thresholds)

    if end_state.leader == Leader.HOME:
        team_in_control = "home"
    elif end_state.leader == Leader.AWAY:
        team_in_control = "away"
    else:
        team_in_control = None

    reason = create_moment_reason(moment_type, start_state, end_state, team_in_control)
    notable = is_moment_notable(moment_type, start_state, end_state, boundary)

    start_quarter = start_event.get("quarter", "?")
    end_quarter = end_event.get("quarter", "?")
    start_clock = start_event.get("game_clock", "")
    end_clock = end_event.get("game_clock", "")

    if start_quarter == end_quarter:
        clock = f"Q{start_quarter} {start_clock}–{end_clock}"
    else:
        clock = f"Q{start_quarter} {start_clock} – Q{end_quarter} {end_clock}"

    teams, primary_team, players, key_play_ids = extract_moment_context(
        events, start_idx, end_idx, game_context or {}
    )

    play_count = sum(
        1
        for i in range(start_idx, end_idx + 1)
        if events[i].get("event_type") == "pbp"
    )

    return Moment(
        id=f"m_{moment_id + 1:03d}",
        type=moment_type,
        start_play=start_idx,
        end_play=end_idx,
        play_count=play_count,
        score_before=score_before,
        score_after=score_after,
        score_start=format_score(score_before[0], score_before[1]),
        score_end=format_score(score_after[0], score_after[1]),
        ladder_tier_before=start_state.tier,
        ladder_tier_after=end_state.tier,
        team_in_control=team_in_control,
        teams=teams,
        primary_team=primary_team,
        players=players,
        key_play_ids=key_play_ids,
        clock=clock,
        reason=reason,
        is_notable=notable,
        note=boundary.note if boundary else None,
        bucket=get_bucket(start_event),
        phase_state=phase_state,  # PROMPT 2: Attach phase state
    )


def build_moment_context(
    moment: Moment,
    previous_moment: Moment | None,
    moments_history: list[Moment],
    phase_state: Any = None,
    parent_moment_id: str | None = None,
) -> "MomentContext":
    """Build narrative context for a moment.
    
    This provides memory and awareness for AI enrichment.
    These are SIGNALS, not rules - no behavior changes here.
    
    PROMPT 2: Phase 3 - Context Payload Construction
    
    Args:
        moment: The moment to build context for
        previous_moment: The immediately preceding moment (if any)
        moments_history: All moments created so far (for sliding window analysis)
        phase_state: GamePhaseState at the time of this moment
        parent_moment_id: If this moment was split from another
        
    Returns:
        MomentContext with all fields populated
    """
    from .types import MomentContext, MomentType
    
    context = MomentContext()
    
    # Phase awareness (from phase_state if available)
    if phase_state:
        context.phase_progress = phase_state.game_progress
        context.is_overtime = phase_state.is_overtime
        context.is_closing_window = phase_state.is_closing_window
        
        # Classify game phase
        if phase_state.game_progress < 0.35:
            context.game_phase = "opening"
        elif phase_state.game_progress > 0.75:
            context.game_phase = "closing"
        else:
            context.game_phase = "middle"
    else:
        # Fallback to bucket if no phase_state
        if moment.bucket == "early":
            context.game_phase = "opening"
        elif moment.bucket == "late":
            context.game_phase = "closing"
        else:
            context.game_phase = "middle"
    
    # Narrative continuity
    if previous_moment:
        context.previous_moment_type = previous_moment.type.value
        if previous_moment.reason:
            context.previous_narrative_delta = previous_moment.reason.narrative_delta
        
        # Is this a continuation of the previous narrative?
        # Same type OR same control direction
        if moment.type == previous_moment.type:
            context.is_continuation = True
        elif moment.team_in_control and previous_moment.team_in_control:
            context.is_continuation = (moment.team_in_control == previous_moment.team_in_control)
    
    context.parent_moment_id = parent_moment_id
    
    # Volatility context (sliding window of last 10 moments)
    recent_window = moments_history[-10:] if len(moments_history) >= 10 else moments_history
    
    flip_tie_types = {MomentType.FLIP, MomentType.TIE}
    context.recent_flip_tie_count = sum(
        1 for m in recent_window if m.type in flip_tie_types
    )
    
    # Classify volatility
    if context.recent_flip_tie_count >= 4:
        context.volatility_phase = "back_and_forth"
    elif context.recent_flip_tie_count >= 2:
        context.volatility_phase = "volatile"
    else:
        context.volatility_phase = "stable"
    
    # Control context
    context.controlling_team = moment.team_in_control
    
    # Count consecutive moments with same control
    control_duration = 0
    if moment.team_in_control:
        for m in reversed(moments_history):
            if m.team_in_control == moment.team_in_control:
                control_duration += 1
            else:
                break
    context.control_duration = control_duration
    
    # Tier stability (analyze tier changes in recent moments)
    if len(recent_window) >= 3:
        tier_changes = 0
        for i in range(1, len(recent_window)):
            if recent_window[i].ladder_tier_after != recent_window[i-1].ladder_tier_after:
                tier_changes += 1
        
        if tier_changes >= 4:
            context.tier_stability = "oscillating"
        elif tier_changes >= 2:
            context.tier_stability = "shifting"
        else:
            context.tier_stability = "stable"
    
    return context
