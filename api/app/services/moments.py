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
# MOMENT BUDGET (HARD CONSTRAINT)
# =============================================================================
# If you exceed these, the system is broken.
# These are NOT guidelines - they are enforcement limits.

MOMENT_BUDGET: dict[str, int] = {
    "NBA": 30,
    "NCAAB": 32,
    "NFL": 22,
    "NHL": 28,
    "MLB": 26,
}
DEFAULT_MOMENT_BUDGET = 30

# Per-quarter/period limits prevent "chaotic quarter" bloat
# A quarter with 10+ moments is narratively confusing
QUARTER_MOMENT_LIMIT = 7  # Max moments per quarter/period

# Moment types that can NEVER be merged (dramatic moments)
PROTECTED_TYPES = frozenset({
    MomentType.FLIP,
    MomentType.CLOSING_CONTROL,
    MomentType.HIGH_IMPACT,
})

# Moment types that should always be merged when consecutive
ALWAYS_MERGE_TYPES = frozenset({
    MomentType.NEUTRAL,
    MomentType.LEAD_BUILD,
    MomentType.CUT,
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
class MomentReason:
    """
    Explains WHY a moment exists.
    
    Every moment must have a reason. If you can't populate this,
    the moment should not exist.
    """
    trigger: str  # "tier_cross" | "flip" | "tie" | "closing_lock" | "high_impact" | "opener"
    control_shift: str | None  # "home" | "away" | None
    narrative_delta: str  # "tension ↑" | "control gained" | "pressure relieved" | etc.
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "control_shift": self.control_shift,
            "narrative_delta": self.narrative_delta,
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
    
    A moment only exists when something meaningfully changes.
    If nothing meaningful changed, extend the current moment.
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

    # WHY THIS MOMENT EXISTS - mandatory for narrative clarity
    reason: MomentReason | None = None
    
    # Metadata
    is_notable: bool = False
    note: str | None = None
    run_info: RunInfo | None = None  # If a run contributed to this moment
    bucket: str = ""  # "early", "mid", "late" (derived from clock)

    # AI-generated content (populated by enrich_game_moments)
    headline: str = ""   # max 60 chars, SportsCenter-style
    summary: str = ""    # max 150 chars, captures momentum/pressure

    @property
    def display_weight(self) -> str:
        """How prominent to render this moment: high, medium, low."""
        if self.type in (MomentType.FLIP, MomentType.TIE, MomentType.HIGH_IMPACT):
            return "high"
        if self.type in (MomentType.CLOSING_CONTROL, MomentType.LEAD_BUILD):
            return "medium"
        if self.type in (MomentType.CUT,):
            return "medium"
        return "low"  # NEUTRAL, OPENER

    @property
    def display_icon(self) -> str:
        """Suggested icon for this moment type."""
        icons = {
            MomentType.FLIP: "swap",
            MomentType.TIE: "equals",
            MomentType.LEAD_BUILD: "trending-up",
            MomentType.CUT: "trending-down",
            MomentType.CLOSING_CONTROL: "lock",
            MomentType.HIGH_IMPACT: "zap",
            MomentType.OPENER: "play",
            MomentType.NEUTRAL: "minus",
        }
        return icons.get(self.type, "circle")

    @property
    def display_color_hint(self) -> str:
        """Color intent: tension, positive, negative, neutral."""
        if self.type in (MomentType.FLIP, MomentType.TIE):
            return "tension"
        if self.type == MomentType.CLOSING_CONTROL:
            return "positive"
        if self.type == MomentType.HIGH_IMPACT:
            return "highlight"
        if self.type in (MomentType.LEAD_BUILD, MomentType.CUT):
            # Depends on who's in control vs home/away preference
            # For now, neutral - frontend can decide based on team_in_control
            return "neutral"
        return "neutral"

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
            "ladder_tier_before": self.ladder_tier_before,
            "ladder_tier_after": self.ladder_tier_after,
            "team_in_control": self.team_in_control,
            "key_play_ids": self.key_play_ids,
            # AI-generated content
            "headline": self.headline,
            "summary": self.summary,
            # Display hints (frontend doesn't need to guess)
            "display_weight": self.display_weight,
            "display_icon": self.display_icon,
            "display_color_hint": self.display_color_hint,
        }
        # Reason is critical for AI and narrative
        if self.reason:
            result["reason"] = self.reason.to_dict()
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


# =============================================================================
# MOMENT MERGING (Critical for budget enforcement)
# =============================================================================


def _can_merge_moments(m1: Moment, m2: Moment) -> bool:
    """
    Determine if two adjacent moments can be merged.
    
    MERGE RULES (from spec):
    - Same MomentType → ALWAYS merge
    - Same team_in_control → MERGE (unless protected type)
    - No intervening FLIP, TIE, or CLOSING_CONTROL
    
    Protected types (FLIP, CLOSING_CONTROL, HIGH_IMPACT) are NEVER merged.
    """
    # Never merge protected types
    if m1.type in PROTECTED_TYPES or m2.type in PROTECTED_TYPES:
        return False
    
    # Always merge same type + same control
    if m1.type == m2.type:
        return True
    
    # Merge NEUTRAL with anything except protected
    if m1.type == MomentType.NEUTRAL or m2.type == MomentType.NEUTRAL:
        return True
    
    # Merge consecutive LEAD_BUILD or CUT if same control
    if m1.type in ALWAYS_MERGE_TYPES and m2.type in ALWAYS_MERGE_TYPES:
        if m1.team_in_control == m2.team_in_control:
            return True
    
    # Don't merge TIE with other types (TIE is a narrative pivot)
    if m1.type == MomentType.TIE or m2.type == MomentType.TIE:
        return False
    
    # OPENER can merge with following NEUTRAL/LEAD_BUILD
    if m1.type == MomentType.OPENER and m2.type in {MomentType.NEUTRAL, MomentType.LEAD_BUILD}:
        return True
    
    return False


def _merge_two_moments(m1: Moment, m2: Moment) -> Moment:
    """
    Merge two adjacent moments into one.
    
    The resulting moment:
    - Spans from m1.start_play to m2.end_play
    - Takes the more significant type
    - Combines key_play_ids
    - Takes the final control state
    """
    # Determine the dominant type (more significant)
    type_priority = {
        MomentType.FLIP: 10,
        MomentType.CLOSING_CONTROL: 9,
        MomentType.HIGH_IMPACT: 8,
        MomentType.TIE: 7,
        MomentType.CUT: 6,
        MomentType.LEAD_BUILD: 5,
        MomentType.OPENER: 3,
        MomentType.NEUTRAL: 1,
    }
    
    if type_priority.get(m2.type, 0) > type_priority.get(m1.type, 0):
        dominant_type = m2.type
        dominant_reason = m2.reason
    else:
        dominant_type = m1.type
        dominant_reason = m1.reason
    
    # Combine key plays
    combined_key_plays = list(set(m1.key_play_ids + m2.key_play_ids))
    combined_key_plays.sort()
    
    # Build merged reason if needed
    if dominant_reason is None and m1.reason:
        dominant_reason = m1.reason
    
    merged = Moment(
        id=m1.id,  # Will be renumbered later
        type=dominant_type,
        start_play=m1.start_play,
        end_play=m2.end_play,
        play_count=m2.end_play - m1.start_play + 1,
        score_before=m1.score_before,
        score_after=m2.score_after,
        score_start=m1.score_start,
        score_end=m2.score_end,
        ladder_tier_before=m1.ladder_tier_before,
        ladder_tier_after=m2.ladder_tier_after,
        team_in_control=m2.team_in_control,
        teams=list(set(m1.teams + m2.teams)),
        players=m1.players + m2.players,  # Combine player contributions
        key_play_ids=combined_key_plays,
        clock=f"{m1.clock.split('–')[0]}–{m2.clock.split('–')[-1]}" if m1.clock and m2.clock else m1.clock or m2.clock,
        reason=dominant_reason,
        is_notable=m1.is_notable or m2.is_notable,
        note=m2.note or m1.note,
        run_info=m2.run_info or m1.run_info,
        bucket=m2.bucket or m1.bucket,
    )
    
    return merged


def _merge_consecutive_moments(moments: list[Moment]) -> list[Moment]:
    """
    Merge consecutive same-type moments aggressively.
    
    This is the PRIMARY mechanism for reducing moment count.
    
    These should NEVER be separate moments:
    - LEAD_BUILD → LEAD_BUILD
    - CUT → CUT  
    - NEUTRAL → NEUTRAL
    
    If control didn't change, the moment didn't change.
    """
    if len(moments) <= 1:
        return moments
    
    merged: list[Moment] = [moments[0]]
    
    for current in moments[1:]:
        prev = merged[-1]
        
        if _can_merge_moments(prev, current):
            # Merge into previous
            merged[-1] = _merge_two_moments(prev, current)
        else:
            merged.append(current)
    
    return merged


def _get_quarter_for_play(play_idx: int, events: Sequence[dict[str, Any]]) -> int | None:
    """Get quarter number for a play index."""
    if play_idx < 0 or play_idx >= len(events):
        return None
    event = events[play_idx]
    return event.get("quarter")


def _enforce_quarter_limits(
    moments: list[Moment], 
    events: Sequence[dict[str, Any]],
) -> list[Moment]:
    """
    Enforce per-quarter moment limits to prevent chaotic quarters.
    
    A quarter with 10+ moments is narratively confusing.
    This merges excess moments within each quarter.
    """
    if not moments:
        return moments
    
    # Group moments by quarter
    quarter_moments: dict[int, list[int]] = {}  # quarter -> list of moment indices
    for i, m in enumerate(moments):
        q = _get_quarter_for_play(m.start_play, events)
        if q is not None:
            if q not in quarter_moments:
                quarter_moments[q] = []
            quarter_moments[q].append(i)
    
    # Find quarters over limit
    to_merge: set[int] = set()  # moment indices to merge with previous
    for q, indices in quarter_moments.items():
        if len(indices) > QUARTER_MOMENT_LIMIT:
            excess = len(indices) - QUARTER_MOMENT_LIMIT
            # Mark the least important moments for merging
            # Prefer merging NEUTRAL, LEAD_BUILD, CUT in that order
            scored = []
            for idx in indices[1:]:  # Skip first moment in quarter
                m = moments[idx]
                if m.type == MomentType.NEUTRAL:
                    priority = 0
                elif m.type in (MomentType.LEAD_BUILD, MomentType.CUT):
                    priority = 1
                elif m.type == MomentType.OPENER:
                    priority = 2
                elif m.type == MomentType.TIE:
                    priority = 3
                else:
                    priority = 4  # Protected types
                scored.append((priority, m.play_count, idx))
            
            # Sort by priority (lowest first) then play_count (lowest first)
            scored.sort(key=lambda x: (x[0], x[1]))
            
            # Mark top 'excess' for merging
            for _, _, idx in scored[:excess]:
                to_merge.add(idx)
    
    if not to_merge:
        return moments
    
    # Merge marked moments into previous
    result = []
    for i, m in enumerate(moments):
        if i in to_merge and result:
            # Merge into previous
            result[-1] = _merge_two_moments(result[-1], m)
        else:
            result.append(m)
    
    if len(result) < len(moments):
        logger.info(
            "quarter_limits_enforced",
            extra={
                "original_count": len(moments),
                "final_count": len(result),
                "merged_count": len(moments) - len(result),
            },
        )
    
    return result


def _enforce_budget(moments: list[Moment], budget: int) -> list[Moment]:
    """
    Force moments under budget. This is a HARD CLAMP.
    
    Priority for merging (least important first):
    1. Consecutive NEUTRAL moments
    2. Consecutive LEAD_BUILD moments  
    3. Consecutive CUT moments
    4. OPENER + following moment
    5. (HARD CLAMP) Any consecutive same-type moments
    6. (HARD CLAMP) Any consecutive moments (last resort)
    
    The budget IS enforced. No exceptions.
    """
    if len(moments) <= budget:
        return moments
    
    initial_count = len(moments)
    
    # Phase 1: Soft merges (preferred)
    iterations = 0
    max_iterations = 20
    
    while len(moments) > budget and iterations < max_iterations:
        iterations += 1
        merged = False
        
        # First pass: merge any remaining NEUTRAL sequences
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.NEUTRAL and moments[i + 1].type == MomentType.NEUTRAL:
                moments[i] = _merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break
        
        if merged or len(moments) <= budget:
            continue
        
        # Second pass: merge LEAD_BUILD sequences
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.LEAD_BUILD and moments[i + 1].type == MomentType.LEAD_BUILD:
                moments[i] = _merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break
        
        if merged or len(moments) <= budget:
            continue
        
        # Third pass: merge CUT sequences
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.CUT and moments[i + 1].type == MomentType.CUT:
                moments[i] = _merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break
        
        if merged or len(moments) <= budget:
            continue
        
        # Fourth pass: merge OPENER with following non-protected moment
        for i in range(len(moments) - 1):
            if i >= len(moments) - 1:
                break
            if moments[i].type == MomentType.OPENER and moments[i + 1].type not in PROTECTED_TYPES:
                moments[i] = _merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break
        
        if not merged:
            break  # Move to hard clamp phase
    
    # Phase 2: HARD CLAMP - merge any consecutive same-type moments
    while len(moments) > budget:
        merged = False
        for i in range(len(moments) - 2):  # Don't merge the last moment
            if moments[i].type == moments[i + 1].type:
                moments[i] = _merge_two_moments(moments[i], moments[i + 1])
                moments.pop(i + 1)
                merged = True
                break
        if not merged:
            break
    
    # Phase 3: NUCLEAR OPTION - merge any consecutive moments
    while len(moments) > budget:
        # Find the smallest moment to absorb
        if len(moments) <= 2:
            break
        
        # Merge the moment with fewest plays into its neighbor
        min_plays = float('inf')
        merge_idx = 1  # Default to second moment
        for i in range(1, len(moments) - 1):  # Skip first and last
            if moments[i].play_count < min_plays:
                min_plays = moments[i].play_count
                merge_idx = i
        
        # Merge into previous
        moments[merge_idx - 1] = _merge_two_moments(moments[merge_idx - 1], moments[merge_idx])
        moments.pop(merge_idx)
    
    if len(moments) < initial_count:
        logger.info(
            "budget_enforced",
            extra={
                "initial_count": initial_count,
                "final_count": len(moments),
                "budget": budget,
                "hard_clamp_used": len(moments) != initial_count,
            },
        )
    
    return moments


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
    4. Moment count stays within sport-specific budget
    5. Every moment has a reason for existing

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

    # AGGRESSIVE MERGE: Collapse consecutive same-type moments
    pre_merge_count = len(moments)
    moments = _merge_consecutive_moments(moments)
    
    # PER-QUARTER ENFORCEMENT: Prevent chaotic quarters
    moments = _enforce_quarter_limits(moments, events)
    
    # BUDGET ENFORCEMENT: If still over budget, merge more aggressively
    sport = summary.get("sport", "NBA") if isinstance(summary, dict) else "NBA"
    budget = MOMENT_BUDGET.get(sport, DEFAULT_MOMENT_BUDGET)
    if len(moments) > budget:
        moments = _enforce_budget(moments, budget)

    # Re-validate coverage after merging
    _validate_moment_coverage(moments, pbp_indices)

    # Renumber moment IDs after merging
    for i, m in enumerate(moments):
        m.id = f"m_{i + 1:03d}"

    logger.info(
        "partition_game_complete",
        extra={
            "pre_merge_count": pre_merge_count,
            "post_merge_count": len(moments),
            "merge_reduction_pct": round((1 - len(moments) / pre_merge_count) * 100, 1) if pre_merge_count > 0 else 0,
            "budget": budget,
            "within_budget": len(moments) <= budget,
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


def _create_moment_reason(
    moment_type: MomentType,
    start_state: LeadState,
    end_state: LeadState,
    team_in_control: str | None,
) -> MomentReason:
    """
    Create a reason explaining WHY this moment exists.
    
    Every moment must have a reason. If you can't explain it, don't create it.
    """
    # Determine trigger
    trigger_map = {
        MomentType.FLIP: "flip",
        MomentType.TIE: "tie",
        MomentType.CLOSING_CONTROL: "closing_lock",
        MomentType.HIGH_IMPACT: "high_impact",
        MomentType.OPENER: "opener",
        MomentType.LEAD_BUILD: "tier_cross",
        MomentType.CUT: "tier_cross",
        MomentType.NEUTRAL: "stable",
    }
    trigger = trigger_map.get(moment_type, "unknown")
    
    # Determine control shift
    control_shift: str | None = None
    if start_state.leader != end_state.leader:
        if end_state.leader == Leader.HOME:
            control_shift = "home"
        elif end_state.leader == Leader.AWAY:
            control_shift = "away"
    
    # Determine narrative delta
    if moment_type == MomentType.FLIP:
        narrative_delta = "control changed"
    elif moment_type == MomentType.TIE:
        narrative_delta = "tension ↑"
    elif moment_type == MomentType.CLOSING_CONTROL:
        narrative_delta = "game locked"
    elif moment_type == MomentType.LEAD_BUILD:
        tier_diff = end_state.tier - start_state.tier
        if tier_diff >= 2:
            narrative_delta = "control solidified"
        else:
            narrative_delta = "lead extended"
    elif moment_type == MomentType.CUT:
        narrative_delta = "pressure relieved" if team_in_control else "momentum shift"
    elif moment_type == MomentType.HIGH_IMPACT:
        narrative_delta = "context changed"
    elif moment_type == MomentType.OPENER:
        narrative_delta = "period started"
    else:
        narrative_delta = "stable flow"
    
    return MomentReason(
        trigger=trigger,
        control_shift=control_shift,
        narrative_delta=narrative_delta,
    )


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

    # Create reason for this moment's existence
    reason = _create_moment_reason(moment_type, start_state, end_state, team_in_control)

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
        reason=reason,
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
