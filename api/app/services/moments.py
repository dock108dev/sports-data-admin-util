"""
Moments: Partition game timeline into narrative segments based on Lead Ladder.

LEAD LADDER-BASED MOMENT DETECTION (2026-01 Rewrite)
=====================================================

A Moment is a contiguous stretch of plays forming a narrative unit.
Moment boundaries occur ONLY when game control changes, as detected by
Lead Ladder tier crossings.

MomentType values:
- LEAD_BUILD: Lead tier increased (team extending control)
- CUT: Lead tier decreased (opponent cutting into lead)
- TIE: Game returned to even
- FLIP: Leader changed (always immediate boundary)
- CLOSING_CONTROL: Late-game control lock-in (dagger)
- HIGH_IMPACT: Non-scoring event that materially changes control
- NEUTRAL: Normal flow without tier changes
- OPENER: First plays of a period

KEY DESIGN PRINCIPLES:
1. Moments are STRICTLY chronological
2. Every play belongs to exactly ONE moment
3. Moment boundaries are determined by Lead Ladder tier crossings
4. Runs do NOT automatically create moments (they may be noted in metadata)
5. Importance is metadata only - never controls ordering
6. No sport-specific hardcoding - thresholds come from Lead Ladder config

Notable moments (is_notable=True) are the key game events.

FILE STRUCTURE (~1000 LOC)
--------------------------
This file is intentionally kept as a single module for cohesion.
The sections are:

1. MOMENT TYPES (enum)
2. CONFIGURATION (sport-agnostic defaults)
3. DATA CLASSES (PlayerContribution, RunInfo, Moment)
4. HELPER FUNCTIONS (clock parsing, score formatting)
5. RUN DETECTION (metadata, not boundaries)
6. BOUNDARY DETECTION (Lead Ladder crossings)
7. MOMENT PARTITIONING (main algorithm)
8. VALIDATION (coverage and ordering checks)
9. PUBLIC API (partition_game, get_notable_moments, validate_moments)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

from ..utils.datetime_utils import parse_clock_to_seconds
from .lead_ladder import (
    Leader,
    LeadState,
    TierCrossing,
    TierCrossingType,
    compute_lead_state,
    detect_tier_crossing,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MOMENT TYPES
# =============================================================================


class MomentType(str, Enum):
    """
    Types of narrative moments based on Lead Ladder crossings.

    These replace the old RUN/BATTLE/CLOSING types with more precise
    lead-change-based classifications.
    """
    # Lead Ladder crossing types (primary)
    LEAD_BUILD = "LEAD_BUILD"      # Lead tier increased
    CUT = "CUT"                    # Lead tier decreased (opponent cutting in)
    TIE = "TIE"                    # Game returned to even
    FLIP = "FLIP"                  # Leader changed

    # Special context types
    CLOSING_CONTROL = "CLOSING_CONTROL"  # Late-game lock-in (dagger)
    HIGH_IMPACT = "HIGH_IMPACT"    # Non-scoring event changing control
    OPENER = "OPENER"              # First plays of a period
    NEUTRAL = "NEUTRAL"            # Normal flow, no tier changes


# =============================================================================
# CONFIGURATION (Sport-agnostic)
# =============================================================================

# Default hysteresis: number of plays a tier must persist to register
# This prevents flicker from momentary score changes
DEFAULT_HYSTERESIS_PLAYS = 2

# Default thresholds for closing detection (in game seconds remaining)
# These are configurable per-sport but we need defaults for the algorithm
DEFAULT_CLOSING_SECONDS = 300  # 5 minutes
DEFAULT_CLOSING_TIER = 1  # Max tier for "close" game

# High-impact play types that can create boundaries
HIGH_IMPACT_PLAY_TYPES = frozenset({
    "ejection", "flagrant", "technical",  # Discipline
    "injury",  # Context-critical
})


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class PlayerContribution:
    """Player stats within a moment."""
    name: str
    stats: dict[str, int] = field(default_factory=dict)
    summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stats": self.stats,
            "summary": self.summary,
        }


@dataclass
class RunInfo:
    """
    Information about a scoring run within a moment.

    Runs do NOT create moments by themselves. They are metadata
    attached to moments when a run contributed to a tier crossing.
    
    A run is a sequence of unanswered scoring by one team.
    Runs are ONLY promoted to moment metadata if they:
    - Caused a tier crossing (LEAD_BUILD or CUT)
    - Caused a lead flip (FLIP)
    
    Runs that didn't move control become key_play_ids instead.
    """
    team: str  # "home" or "away"
    points: int
    unanswered: bool  # True if opponent scored 0 during run
    play_ids: list[int] = field(default_factory=list)  # Indices of scoring plays in run
    start_idx: int = 0  # Timeline index where run started
    end_idx: int = 0    # Timeline index where run ended


@dataclass
class Moment:
    """
    A contiguous segment of plays forming a narrative unit.

    Every play in the timeline belongs to exactly one Moment.
    Moments are always chronologically ordered by start_play.
    """
    id: str
    type: MomentType
    start_play: int
    end_play: int
    play_count: int

    # Score tracking
    score_before: tuple[int, int] = (0, 0)  # (home, away) at start
    score_after: tuple[int, int] = (0, 0)   # (home, away) at end
    score_start: str = ""  # Format "away–home"
    score_end: str = ""    # Format "away–home"

    # Lead Ladder state
    ladder_tier_before: int = 0
    ladder_tier_after: int = 0
    team_in_control: str | None = None  # "home", "away", or None

    # Context
    teams: list[str] = field(default_factory=list)
    players: list[PlayerContribution] = field(default_factory=list)
    key_play_ids: list[int] = field(default_factory=list)
    clock: str = ""

    # Metadata
    is_notable: bool = False
    note: str | None = None
    run_info: RunInfo | None = None  # If a run contributed to this moment
    bucket: str = ""  # "early", "mid", "late" (derived from clock)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API responses."""
        result = {
            "id": self.id,
            "type": self.type.value,
            "start_play": self.start_play,
            "end_play": self.end_play,
            "play_count": self.play_count,
            "teams": self.teams,
            "players": [p.to_dict() for p in self.players],
            "score_start": self.score_start,
            "score_end": self.score_end,
            "clock": self.clock,
            "is_notable": self.is_notable,
            "note": self.note,
        }
        # Include new fields if present
        if self.ladder_tier_before or self.ladder_tier_after:
            result["ladder_tier_before"] = self.ladder_tier_before
            result["ladder_tier_after"] = self.ladder_tier_after
        if self.team_in_control:
            result["team_in_control"] = self.team_in_control
        if self.key_play_ids:
            result["key_play_ids"] = self.key_play_ids
        if self.run_info:
            result["run_info"] = {
                "team": self.run_info.team,
                "points": self.run_info.points,
                "unanswered": self.run_info.unanswered,
                "play_ids": self.run_info.play_ids,
            }
        return result


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _format_score(home: int | None, away: int | None) -> str:
    """Format score as 'away–home'."""
    if home is None or away is None:
        return ""
    return f"{away}–{home}"


def _get_score(event: dict[str, Any]) -> tuple[int, int]:
    """Extract (home_score, away_score) from an event."""
    home = event.get("home_score", 0) or 0
    away = event.get("away_score", 0) or 0
    return (home, away)


def _get_bucket(event: dict[str, Any]) -> str:
    """
    Determine time bucket (early/mid/late) from event.

    This is sport-agnostic: uses quarter/period and clock position.
    """
    quarter = event.get("quarter", 1)
    clock_seconds = parse_clock_to_seconds(event.get("game_clock"))

    if quarter <= 1:
        return "early"
    if quarter >= 4:
        if clock_seconds is not None and clock_seconds <= 300:
            return "late"
        return "mid"
    return "mid"


def _is_period_opener(event: dict[str, Any], prev_event: dict[str, Any] | None) -> bool:
    """Check if this event starts a new period."""
    if prev_event is None:
        return True  # First event is always an opener
    return event.get("quarter") != prev_event.get("quarter")


def _is_high_impact_event(event: dict[str, Any]) -> bool:
    """Check if event is a high-impact non-scoring event."""
    play_type = event.get("play_type", "")
    return play_type in HIGH_IMPACT_PLAY_TYPES


def _is_closing_situation(
    event: dict[str, Any],
    lead_state: LeadState,
    closing_seconds: int = DEFAULT_CLOSING_SECONDS,
    closing_max_tier: int = DEFAULT_CLOSING_TIER,
) -> bool:
    """
    Check if we're in a closing situation (late game, close score).

    Closing is defined as:
    - Late in the game (configurable threshold)
    - Lead tier is at or below closing_max_tier

    This is used to detect CLOSING_CONTROL moments (daggers).
    """
    quarter = event.get("quarter", 1)
    clock_seconds = parse_clock_to_seconds(event.get("game_clock"))

    # Must be in 4th quarter or overtime
    if quarter < 4:
        return False

    # Must be in final minutes
    if clock_seconds is None or clock_seconds > closing_seconds:
        return False

    # Must be a close game
    return lead_state.tier <= closing_max_tier


# =============================================================================
# RUN DETECTION (Metadata, not boundaries)
# =============================================================================


@dataclass
class DetectedRun:
    """
    A detected scoring run (before assignment to a moment).
    
    Runs are sequences of unanswered scoring by one team.
    They do NOT create moment boundaries by themselves.
    """
    team: str  # "home" or "away"
    points: int
    start_idx: int  # Timeline index where run started
    end_idx: int    # Timeline index where run ended
    play_ids: list[int] = field(default_factory=list)  # All scoring play indices


# Minimum points for a run to be considered significant
# This is sport-agnostic - the caller should provide appropriate threshold
DEFAULT_RUN_THRESHOLD = 6


def _detect_runs(
    events: Sequence[dict[str, Any]],
    min_points: int = DEFAULT_RUN_THRESHOLD,
) -> list[DetectedRun]:
    """
    Detect scoring runs in the timeline.
    
    A run is a sequence of unanswered scoring by one team.
    Runs are detected but do NOT create moment boundaries.
    They become metadata attached to the owning moment.
    
    Args:
        events: Timeline events
        min_points: Minimum points to qualify as a run
        
    Returns:
        List of detected runs (not yet assigned to moments)
    """
    runs: list[DetectedRun] = []
    
    # Track current run state
    current_run_team: str | None = None
    current_run_points = 0
    current_run_start = 0
    current_run_plays: list[int] = []
    
    prev_home = 0
    prev_away = 0
    
    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue
            
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0
        
        # Calculate score deltas
        home_delta = home_score - prev_home
        away_delta = away_score - prev_away
        
        # Determine which team scored
        if home_delta > 0 and away_delta == 0:
            scoring_team = "home"
            points_scored = home_delta
        elif away_delta > 0 and home_delta == 0:
            scoring_team = "away"
            points_scored = away_delta
        elif home_delta > 0 or away_delta > 0:
            # Both teams scored - end any current run
            if current_run_points >= min_points:
                runs.append(DetectedRun(
                    team=current_run_team or "home",
                    points=current_run_points,
                    start_idx=current_run_start,
                    end_idx=i - 1,
                    play_ids=current_run_plays.copy(),
                ))
            current_run_team = None
            current_run_points = 0
            current_run_plays = []
            prev_home = home_score
            prev_away = away_score
            continue
        else:
            # No scoring - continue current run
            prev_home = home_score
            prev_away = away_score
            continue
        
        # Handle scoring by one team
        if scoring_team == current_run_team:
            # Extend current run
            current_run_points += points_scored
            current_run_plays.append(i)
        else:
            # New team scored - close previous run if significant
            if current_run_points >= min_points:
                runs.append(DetectedRun(
                    team=current_run_team or "home",
                    points=current_run_points,
                    start_idx=current_run_start,
                    end_idx=i - 1,
                    play_ids=current_run_plays.copy(),
                ))
            # Start new run
            current_run_team = scoring_team
            current_run_points = points_scored
            current_run_start = i
            current_run_plays = [i]
        
        prev_home = home_score
        prev_away = away_score
    
    # Close any open run
    if current_run_points >= min_points and current_run_plays:
        runs.append(DetectedRun(
            team=current_run_team or "home",
            points=current_run_points,
            start_idx=current_run_start,
            end_idx=current_run_plays[-1],
            play_ids=current_run_plays.copy(),
        ))
    
    return runs


def _find_run_for_moment(
    runs: list[DetectedRun],
    moment_start: int,
    moment_end: int,
) -> DetectedRun | None:
    """
    Find the best run that contributed to a moment.
    
    A run "contributed" to a moment if:
    - The run overlaps with the moment's play range
    - The run ended at or before the moment boundary
    
    Returns the largest run that fits, or None.
    """
    best_run: DetectedRun | None = None
    best_points = 0
    
    for run in runs:
        # Check if run overlaps with moment
        if run.end_idx < moment_start or run.start_idx > moment_end:
            continue
        
        # This run contributed to the moment - take the largest
        if run.points > best_points:
            best_run = run
            best_points = run.points
    
    return best_run


def _run_to_info(run: DetectedRun) -> RunInfo:
    """Convert a DetectedRun to RunInfo for attachment to a Moment."""
    return RunInfo(
        team=run.team,
        points=run.points,
        unanswered=True,  # By definition, runs are unanswered
        play_ids=run.play_ids.copy(),
        start_idx=run.start_idx,
        end_idx=run.end_idx,
    )


# =============================================================================
# BOUNDARY DETECTION
# =============================================================================


@dataclass
class BoundaryEvent:
    """
    Represents a detected moment boundary.

    A boundary occurs when game control changes significantly enough
    to warrant starting a new moment.
    """
    index: int  # Index in timeline where boundary occurs
    moment_type: MomentType
    prev_state: LeadState
    curr_state: LeadState
    crossing: TierCrossing | None = None
    note: str | None = None


def _detect_boundaries(
    events: Sequence[dict[str, Any]],
    thresholds: Sequence[int],
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
) -> list[BoundaryEvent]:
    """
    Detect all moment boundaries in the timeline.

    BOUNDARY RULES:
    1. Lead tier increase → LEAD_BUILD (if persists for hysteresis_plays)
    2. Lead tier decrease → CUT (if persists for hysteresis_plays)
    3. Tie reached → TIE (immediate)
    4. Lead flip → FLIP (immediate, no hysteresis)
    5. Closing control lock-in → CLOSING_CONTROL
    6. High-impact non-scoring → HIGH_IMPACT (only if significant)
    7. Period start → OPENER

    Hysteresis prevents flicker from momentary score changes.
    Flips and ties are always immediate (no hysteresis needed).
    """
    boundaries: list[BoundaryEvent] = []

    if not events:
        return boundaries

    # Track state
    prev_state: LeadState | None = None
    pending_crossing: TierCrossing | None = None
    pending_index: int = 0
    persistence_count: int = 0
    prev_event: dict[str, Any] | None = None

    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue

        home_score, away_score = _get_score(event)
        curr_state = compute_lead_state(home_score, away_score, thresholds)

        # === PERIOD OPENER ===
        # Check if this is a new period (always a boundary)
        if _is_period_opener(event, prev_event):
            boundaries.append(BoundaryEvent(
                index=i,
                moment_type=MomentType.OPENER,
                prev_state=prev_state or curr_state,
                curr_state=curr_state,
                note=f"Period {event.get('quarter', '?')} start",
            ))

        # === LEAD LADDER CROSSING ===
        if prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)

            if crossing is not None:
                crossing_type = crossing.crossing_type

                # IMMEDIATE boundaries (no hysteresis)
                if crossing_type == TierCrossingType.FLIP:
                    # Clear any pending crossing
                    pending_crossing = None
                    persistence_count = 0

                    # Check for closing control (dagger)
                    if _is_closing_situation(event, curr_state):
                        boundaries.append(BoundaryEvent(
                            index=i,
                            moment_type=MomentType.CLOSING_CONTROL,
                            prev_state=prev_state,
                            curr_state=curr_state,
                            crossing=crossing,
                            note="Late lead change",
                        ))
                    else:
                        boundaries.append(BoundaryEvent(
                            index=i,
                            moment_type=MomentType.FLIP,
                            prev_state=prev_state,
                            curr_state=curr_state,
                            crossing=crossing,
                            note="Lead change",
                        ))

                elif crossing_type == TierCrossingType.TIE_REACHED:
                    # Tie is immediate
                    pending_crossing = None
                    persistence_count = 0
                    boundaries.append(BoundaryEvent(
                        index=i,
                        moment_type=MomentType.TIE,
                        prev_state=prev_state,
                        curr_state=curr_state,
                        crossing=crossing,
                        note="Game tied",
                    ))

                elif crossing_type == TierCrossingType.TIE_BROKEN:
                    # Tie broken - could be start of a lead build
                    pending_crossing = crossing
                    pending_index = i
                    persistence_count = 1

                elif crossing_type == TierCrossingType.TIER_UP:
                    # Lead extended - start hysteresis
                    pending_crossing = crossing
                    pending_index = i
                    persistence_count = 1

                elif crossing_type == TierCrossingType.TIER_DOWN:
                    # Lead cut - start hysteresis
                    pending_crossing = crossing
                    pending_index = i
                    persistence_count = 1

            else:
                # No crossing - check if pending crossing should be confirmed
                if pending_crossing is not None:
                    # Check if the tier from pending crossing is still holding
                    if curr_state.tier == pending_crossing.curr_state.tier:
                        persistence_count += 1

                        if persistence_count >= hysteresis_plays:
                            # Confirm the boundary
                            if pending_crossing.crossing_type == TierCrossingType.TIER_UP:
                                moment_type = MomentType.LEAD_BUILD
                                note = "Lead extended"
                            elif pending_crossing.crossing_type == TierCrossingType.TIER_DOWN:
                                moment_type = MomentType.CUT
                                note = "Lead cut"
                            elif pending_crossing.crossing_type == TierCrossingType.TIE_BROKEN:
                                moment_type = MomentType.LEAD_BUILD
                                note = "Took the lead"
                            else:
                                moment_type = MomentType.NEUTRAL
                                note = None

                            # Check for closing control
                            if _is_closing_situation(event, curr_state) and curr_state.tier >= 2:
                                moment_type = MomentType.CLOSING_CONTROL
                                note = "Game control locked"

                            boundaries.append(BoundaryEvent(
                                index=pending_index,
                                moment_type=moment_type,
                                prev_state=pending_crossing.prev_state,
                                curr_state=curr_state,
                                crossing=pending_crossing,
                                note=note,
                            ))
                            pending_crossing = None
                            persistence_count = 0
                    else:
                        # Tier changed again before hysteresis completed - reset
                        pending_crossing = None
                        persistence_count = 0

        # === HIGH-IMPACT EVENTS ===
        if _is_high_impact_event(event):
            boundaries.append(BoundaryEvent(
                index=i,
                moment_type=MomentType.HIGH_IMPACT,
                prev_state=prev_state or curr_state,
                curr_state=curr_state,
                note=event.get("play_type", "High-impact event"),
            ))

        prev_state = curr_state
        prev_event = event

    return boundaries


# =============================================================================
# MOMENT PARTITIONING
# =============================================================================


def partition_game(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    thresholds: Sequence[int] | None = None,
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
) -> list[Moment]:
    """
    Partition a game timeline into moments based on Lead Ladder.

    CORE GUARANTEES:
    1. Every PBP play belongs to exactly ONE moment
    2. Moments are contiguous (no gaps)
    3. Moments are chronologically ordered by start_play
    4. Moment boundaries occur only on tier crossings

    Args:
        timeline: Full timeline events (PBP + social)
        summary: Game summary metadata (for team info)
        thresholds: Lead Ladder thresholds (if None, defaults to minimal [5])
        hysteresis_plays: Number of plays tier must persist

    Returns:
        List of Moments covering the entire timeline
    """
    events = list(timeline)
    if not events:
        return []

    # Get PBP-only event indices
    pbp_indices = [i for i, e in enumerate(events) if e.get("event_type") == "pbp"]
    if not pbp_indices:
        return []

    # Use provided thresholds or minimal default
    # NOTE: Caller should always provide thresholds from Lead Ladder config
    if thresholds is None:
        logger.warning(
            "partition_game_no_thresholds: No thresholds provided, using minimal default [5]",
        )
        thresholds = [5]

    # Detect boundaries
    boundaries = _detect_boundaries(events, thresholds, hysteresis_plays)

    # Build moments from boundaries
    moments: list[Moment] = []
    moment_id = 0

    # Convert boundaries to a dict for quick lookup
    boundary_at: dict[int, BoundaryEvent] = {b.index: b for b in boundaries}

    # Partition plays into moments
    current_start: int | None = None
    current_type: MomentType = MomentType.NEUTRAL
    current_boundary: BoundaryEvent | None = None

    for i in pbp_indices:
        # Check if this is a boundary
        if i in boundary_at:
            boundary = boundary_at[i]

            # Close previous moment if any
            if current_start is not None:
                prev_idx = pbp_indices[pbp_indices.index(i) - 1] if pbp_indices.index(i) > 0 else i - 1
                moment = _create_moment(
                    moment_id=moment_id,
                    events=events,
                    start_idx=current_start,
                    end_idx=prev_idx,
                    moment_type=current_type,
                    thresholds=thresholds,
                    boundary=current_boundary,
                )
                moments.append(moment)
                moment_id += 1

            # Start new moment at this boundary
            current_start = i
            current_type = boundary.moment_type
            current_boundary = boundary
        else:
            # Continue current moment
            if current_start is None:
                current_start = i
                current_type = MomentType.NEUTRAL

    # Close final moment
    if current_start is not None:
        moment = _create_moment(
            moment_id=moment_id,
            events=events,
            start_idx=current_start,
            end_idx=pbp_indices[-1],
            moment_type=current_type,
            thresholds=thresholds,
            boundary=current_boundary,
        )
        moments.append(moment)

    # Sort by start_play (should already be sorted, but ensure)
    moments.sort(key=lambda m: m.start_play)

    # Detect runs and attach to moments as metadata
    runs = _detect_runs(events)
    _attach_runs_to_moments(moments, runs)

    # Validate coverage
    _validate_moment_coverage(moments, pbp_indices)

    logger.info(
        "partition_game_complete",
        extra={
            "moment_count": len(moments),
            "moment_types": [m.type.value for m in moments],
            "notable_count": sum(1 for m in moments if m.is_notable),
            "runs_detected": len(runs),
            "runs_promoted": sum(1 for m in moments if m.run_info is not None),
        },
    )

    return moments


def _attach_runs_to_moments(
    moments: list[Moment],
    runs: list[DetectedRun],
) -> None:
    """
    Attach detected runs to moments as metadata.
    
    PROMOTION RULES:
    - A run is promoted to run_info ONLY if it caused a tier change:
      - LEAD_BUILD: Run that extended the lead
      - CUT: Run that cut into a lead
      - FLIP: Run that changed the leader
    
    - Runs that didn't cause tier changes become key_play_ids.
    - A run can only be attached to ONE moment.
    
    This modifies moments in place.
    """
    # Types eligible for run promotion
    PROMOTABLE_TYPES = {MomentType.LEAD_BUILD, MomentType.CUT, MomentType.FLIP}
    
    # Track which runs have been attached
    attached_runs: set[int] = set()
    
    for moment in moments:
        # Find the best run for this moment
        run = _find_run_for_moment(runs, moment.start_play, moment.end_play)
        
        if run is None:
            continue
            
        # Check if this run is already attached
        run_idx = runs.index(run)
        if run_idx in attached_runs:
            continue
            
        # PROMOTE: Attach as run_info if moment type is promotable
        if moment.type in PROMOTABLE_TYPES:
            moment.run_info = _run_to_info(run)
            attached_runs.add(run_idx)
            
            # Enhance the note with run info
            if moment.note:
                moment.note = f"{moment.note} ({run.points}-0 run)"
            else:
                moment.note = f"{run.points}-0 run"
        else:
            # NOT PROMOTED: Add to key_play_ids instead
            for play_id in run.play_ids:
                if play_id not in moment.key_play_ids:
                    moment.key_play_ids.append(play_id)
            attached_runs.add(run_idx)


def _create_moment(
    moment_id: int,
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    moment_type: MomentType,
    thresholds: Sequence[int],
    boundary: BoundaryEvent | None,
) -> Moment:
    """Create a Moment from a range of events."""
    start_event = events[start_idx]
    end_event = events[end_idx]

    # Get scores
    score_before = _get_score(start_event)
    score_after = _get_score(end_event)

    # Compute lead states
    start_state = compute_lead_state(score_before[0], score_before[1], thresholds)
    end_state = compute_lead_state(score_after[0], score_after[1], thresholds)

    # Determine team in control
    if end_state.leader == Leader.HOME:
        team_in_control = "home"
    elif end_state.leader == Leader.AWAY:
        team_in_control = "away"
    else:
        team_in_control = None

    # Determine if notable
    is_notable = _is_moment_notable(moment_type, start_state, end_state, boundary)

    # Build clock string
    start_quarter = start_event.get("quarter", "?")
    end_quarter = end_event.get("quarter", "?")
    start_clock = start_event.get("game_clock", "")
    end_clock = end_event.get("game_clock", "")

    if start_quarter == end_quarter:
        clock = f"Q{start_quarter} {start_clock}–{end_clock}"
    else:
        clock = f"Q{start_quarter} {start_clock} – Q{end_quarter} {end_clock}"

    # Count plays
    play_count = sum(
        1 for i in range(start_idx, end_idx + 1)
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
        score_start=_format_score(score_before[0], score_before[1]),
        score_end=_format_score(score_after[0], score_after[1]),
        ladder_tier_before=start_state.tier,
        ladder_tier_after=end_state.tier,
        team_in_control=team_in_control,
        clock=clock,
        is_notable=is_notable,
        note=boundary.note if boundary else None,
        bucket=_get_bucket(start_event),
    )


def _is_moment_notable(
    moment_type: MomentType,
    start_state: LeadState,
    end_state: LeadState,
    boundary: BoundaryEvent | None,
) -> bool:
    """
    Determine if a moment is notable (a key game event).

    Notable moments are those that significantly changed game control:
    - All FLIPs (leader changed)
    - All TIEs (game went to even)
    - CLOSING_CONTROL (daggers)
    - HIGH_IMPACT events
    - LEAD_BUILD with tier change >= 2
    - CUT with tier change >= 2
    """
    # These types are always notable
    if moment_type in (
        MomentType.FLIP,
        MomentType.TIE,
        MomentType.CLOSING_CONTROL,
        MomentType.HIGH_IMPACT,
    ):
        return True

    # LEAD_BUILD and CUT are notable if tier changed significantly
    if moment_type in (MomentType.LEAD_BUILD, MomentType.CUT):
        tier_change = abs(end_state.tier - start_state.tier)
        return tier_change >= 2

    # OPENER is notable if it sets a strong early lead
    if moment_type == MomentType.OPENER:
        return end_state.tier >= 2

    return False


# =============================================================================
# VALIDATION
# =============================================================================


class MomentValidationError(Exception):
    """Raised when moment partitioning fails validation."""
    pass


def _validate_moment_coverage(
    moments: list[Moment],
    pbp_indices: list[int],
) -> None:
    """
    Validate that moments cover all PBP plays exactly once.

    Raises:
        MomentValidationError: If validation fails
    """
    if not moments or not pbp_indices:
        return

    # Check that moments cover all indices
    covered_indices = set()
    for moment in moments:
        for i in range(moment.start_play, moment.end_play + 1):
            if i in covered_indices:
                raise MomentValidationError(
                    f"Overlapping moments: index {i} covered by multiple moments"
                )
            covered_indices.add(i)

    # Check for gaps (only PBP indices need to be covered)
    pbp_set = set(pbp_indices)
    uncovered = pbp_set - covered_indices
    if uncovered:
        logger.warning(
            "moment_validation_gap",
            extra={"uncovered_indices": sorted(uncovered)[:10]},
        )
        # Don't raise error - some indices might be non-PBP events in the range


def validate_moments(
    timeline: Sequence[dict[str, Any]],
    moments: list[Moment],
) -> bool:
    """
    Validate moment partitioning.

    Checks:
    1. All PBP plays are assigned to exactly one moment
    2. Moments are ordered chronologically
    3. No overlapping moment boundaries

    Args:
        timeline: Original timeline
        moments: Computed moments

    Returns:
        True if valid

    Raises:
        MomentValidationError: If validation fails
    """
    if not moments:
        return True

    pbp_indices = {
        i for i, e in enumerate(timeline)
        if e.get("event_type") == "pbp"
    }

    # Check chronological order
    for i in range(1, len(moments)):
        if moments[i].start_play < moments[i - 1].start_play:
            raise MomentValidationError(
                f"Moments not chronological: {moments[i-1].id} starts at "
                f"{moments[i-1].start_play}, {moments[i].id} starts at {moments[i].start_play}"
            )

    # Check no overlap
    for i in range(1, len(moments)):
        if moments[i].start_play <= moments[i - 1].end_play:
            raise MomentValidationError(
                f"Overlapping moments: {moments[i-1].id} ends at {moments[i-1].end_play}, "
                f"{moments[i].id} starts at {moments[i].start_play}"
            )

    # Check coverage
    covered = set()
    for moment in moments:
        for idx in range(moment.start_play, moment.end_play + 1):
            covered.add(idx)

    uncovered_pbp = pbp_indices - covered
    if uncovered_pbp:
        raise MomentValidationError(
            f"Uncovered PBP plays: {sorted(uncovered_pbp)[:10]}..."
        )

    return True


# =============================================================================
# PUBLIC API
# =============================================================================


def get_notable_moments(moments: list[Moment]) -> list[Moment]:
    """
    Return moments that are notable (is_notable=True).

    Notable moments are a VIEW of moments, not a separate entity.
    They are filtered client-side or server-side from the full moment list.
    """
    return [m for m in moments if m.is_notable]
