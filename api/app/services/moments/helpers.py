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
    DEFAULT_CLOSING_SECONDS,
    DEFAULT_CLOSING_TIER,
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
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    return (home, away)


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
    
    When a GamePhaseContext is available, uses that for consistency.

    Args:
        event: Timeline event with quarter/period and game_clock
        sport: Sport identifier (optional, defaults to NBA)

    Returns:
        Float from 0.0 (game start) to 1.0 (end of regulation), >1.0 in OT
    """
    from .game_structure import compute_game_progress, get_current_phase_context
    
    # Use global context if available for consistency
    context = get_current_phase_context()
    if context is not None:
        # Get event index if available
        event_idx = event.get("_original_index")
        if event_idx is not None:
            # Need events list - fall back to direct computation
            pass
    
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


def is_closing_situation(
    event: dict[str, Any],
    lead_state: LeadState,
    closing_seconds: int = DEFAULT_CLOSING_SECONDS,
    closing_max_tier: int = DEFAULT_CLOSING_TIER,
) -> bool:
    """Check if we're in a closing situation (late game, close score).

    DEPRECATED: Use classify_closing_situation() from moments.closing for
    the unified closing taxonomy with explicit categories.

    This function returns True for CLOSE_GAME_CLOSING situations.
    For the full classification including DECIDED_GAME_CLOSING, use
    the new unified API.

    Closing is defined as:
    - Late in the game (configurable threshold)
    - Lead tier is at or below closing_max_tier

    Used to detect CLOSING_CONTROL moments (daggers).
    """
    from .closing import classify_closing_situation, ClosingCategory
    
    classification = classify_closing_situation(
        event=event,
        lead_state=lead_state,
        closing_window_seconds=closing_seconds,
        close_game_max_tier=closing_max_tier,
    )
    
    # Legacy behavior: return True for close game closing
    return classification.category == ClosingCategory.CLOSE_GAME_CLOSING


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
                player_data[player_name] = {}
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
) -> Moment:
    """Create a Moment and run the RESOLUTION PASS."""
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
    )
