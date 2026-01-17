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
from .moments_runs import (
    DetectedRun,
    RunInfo,
    detect_runs,
    find_run_for_moment,
    run_to_info,
)
from .moments_merging import (
    is_valid_moment,
    merge_invalid_moments,
    merge_consecutive_moments,
    enforce_quarter_limits,
    enforce_budget,
)
from .moments_validation import (
    MomentValidationError,
    validate_score_continuity,
    assert_moment_continuity,
    validate_moment_coverage,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MOMENT TYPES
# =============================================================================


class MomentType(str, Enum):
    """
    Types of narrative moments based on Lead Ladder crossings.
    """
    # Lead Ladder crossing types (primary)
    LEAD_BUILD = "LEAD_BUILD"      # Lead tier increased
    CUT = "CUT"                    # Lead tier decreased (opponent cutting in)
    TIE = "TIE"                    # Game returned to even
    FLIP = "FLIP"                  # Leader changed

    # Special context types
    CLOSING_CONTROL = "CLOSING_CONTROL"  # Late-game lock-in (dagger)
    HIGH_IMPACT = "HIGH_IMPACT"    # Non-scoring event changing control
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

    # Context (RESOLVED DURING RESOLUTION PASS)
    teams: list[str] = field(default_factory=list)
    primary_team: str | None = None  # "home" or "away"
    players: list[PlayerContribution] = field(default_factory=list)
    key_play_ids: list[int] = field(default_factory=list)
    clock: str = ""

    # WHY THIS MOMENT EXISTS
    reason: MomentReason | None = None
    
    # Metadata
    is_notable: bool = False
    is_period_start: bool = False # Flag for period boundaries
    note: str | None = None
    run_info: RunInfo | None = None  # If a run contributed to this moment
    bucket: str = ""  # "early", "mid", "late" (derived from clock)

    # AI-generated content (populated by enrich_game_moments)
    headline: str = ""   # max 60 chars
    summary: str = ""    # max 150 chars

    @property
    def display_weight(self) -> str:
        """How prominent to render this moment: high, medium, low."""
        if self.type in (MomentType.FLIP, MomentType.TIE, MomentType.HIGH_IMPACT):
            return "high"
        if self.type in (MomentType.CLOSING_CONTROL, MomentType.LEAD_BUILD):
            return "medium"
        if self.type in (MomentType.CUT,):
            return "medium"
        return "low"  # NEUTRAL

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
            "primary_team": self.primary_team,
            "players": [p.to_dict() for p in self.players],
            "score_start": self.score_start,
            "score_end": self.score_end,
            "clock": self.clock,
            "is_notable": self.is_notable,
            "is_period_start": self.is_period_start,
            "note": self.note,
            "ladder_tier_before": self.ladder_tier_before,
            "ladder_tier_after": self.ladder_tier_after,
            "team_in_control": self.team_in_control,
            "key_play_ids": self.key_play_ids,
            "headline": self.headline,
            "summary": self.summary,
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
# NOTE: Run detection logic has been extracted to moments_runs.py
# Functions: detect_runs(), find_run_for_moment(), run_to_info()
# This keeps the core partitioning algorithm focused while allowing
# independent testing and maintenance of run detection logic.


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


def get_canonical_pbp_indices(events: Sequence[dict[str, Any]]) -> list[int]:
    """
    Filter the timeline to find only real, narrative-relevant PBP plays.

    Excludes:
    - Non-PBP events
    - Empty descriptions
    - Period start/end markers
    - Score resets (0-0 mid-game)
    - Boundary bookkeeping rows
    """
    indices = []
    has_seen_scoring = False

    for i, event in enumerate(events):
        if event.get("event_type") != "pbp":
            continue

        description = (event.get("description") or "").strip()
        description_lower = description.lower()

        # 1. Filter by description content
        if not description:
            continue
        if any(marker in description_lower for marker in [
            "start of", "end of", "beginning of", "start period", "end period",
            "jump ball", "timeout", "coaches challenge"
        ]):
            # Keep jump balls at start of game/period? No, they don't change score/tier
            continue

        # 2. Filter by score resets
        home_score = event.get("home_score", 0) or 0
        away_score = event.get("away_score", 0) or 0

        if home_score > 0 or away_score > 0:
            has_seen_scoring = True

        if home_score == 0 and away_score == 0 and has_seen_scoring:
            # This is a score reset mid-game - ignore it
            continue

        # 3. Filter boundary markers at 0:00 that aren't plays
        clock = event.get("game_clock", "")
        if clock == "0:00" or clock == "0:00.0":
            # If it's a 0:00 row with no score change from previous, it's likely a marker
            # We'll check this by comparing with last added index if any
            if indices:
                prev_event = events[indices[-1]]
                if (prev_event.get("home_score") == home_score and
                    prev_event.get("away_score") == away_score and
                    "made" not in description_lower and "miss" not in description_lower):
                    continue

        indices.append(i)

    return indices


def _detect_boundaries(
    events: Sequence[dict[str, Any]],
    pbp_indices: list[int],
    thresholds: Sequence[int],
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
) -> list[BoundaryEvent]:
    """
    Detect all moment boundaries using the canonical PBP stream.

    MOMENTS MUST HAVE CAUSAL TRIGGERS:
    - tier_up / tier_down
    - tie / flip
    - closing_lock
    - high_impact_event

    OPENER is no longer a moment type.
    """
    boundaries: list[BoundaryEvent] = []

    if not pbp_indices:
        return boundaries

    # Track state
    prev_state: LeadState | None = None
    pending_crossing: TierCrossing | None = None
    pending_index: int = 0
    persistence_count: int = 0
    # prev_event removed - period start is metadata during partitioning

    for i in pbp_indices:
        event = events[i]
        home_score, away_score = _get_score(event)
        curr_state = compute_lead_state(home_score, away_score, thresholds)

        # === LEAD LADDER CROSSING ===
        if prev_state is not None:
            crossing = detect_tier_crossing(prev_state, curr_state)

            if crossing is not None:
                crossing_type = crossing.crossing_type

                # IMMEDIATE boundaries (no hysteresis)
                if crossing_type == TierCrossingType.FLIP:
                    pending_crossing = None
                    persistence_count = 0

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

                elif crossing_type in (TierCrossingType.TIE_BROKEN, TierCrossingType.TIER_UP, TierCrossingType.TIER_DOWN):
                    pending_crossing = crossing
                    pending_index = i
                    persistence_count = 1

            else:
                # No crossing - check if pending crossing should be confirmed
                if pending_crossing is not None:
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

    return boundaries


# =============================================================================
# MOMENT PARTITIONING
# =============================================================================


# =============================================================================
# MOMENT MERGING (Critical for budget enforcement)
# =============================================================================
# NOTE: Merging logic has been extracted to moments_merging.py

# BACK-AND-FORTH DETECTION AND MEGA-MOMENT SPLITTING
# =============================================================================


def _detect_back_and_forth_phase(
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    thresholds: Sequence[int],
) -> bool:
    """
    Detect if a moment represents a back-and-forth phase.
    
    Criteria:
    - Multiple small lead changes within the moment
    - Score stays within tier 0-1 (close game)
    - No sustained runs (no 8+ point unanswered runs)
    
    Returns True if this is a volatile back-and-forth sequence.
    """
    if end_idx - start_idx < 20:  # Too short to be back-and-forth
        return False
    
    lead_changes = 0
    ties = 0
    max_tier = 0
    prev_leader = None
    prev_score = None
    max_run_length = 0
    current_run_length = 0
    last_scoring_team = None
    
    for i in range(start_idx, end_idx + 1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue
        
        home_score = event.get("home_score") or 0
        away_score = event.get("away_score") or 0
        
        if prev_score is not None:
            # Check for scoring
            if home_score > prev_score[0] or away_score > prev_score[1]:
                scoring_team = "home" if home_score > prev_score[0] else "away"
                
                # Track runs
                if scoring_team == last_scoring_team:
                    current_run_length += 1
                    max_run_length = max(max_run_length, current_run_length)
                else:
                    current_run_length = 1
                    last_scoring_team = scoring_team
        
        # Compute lead state
        state = compute_lead_state(home_score, away_score, thresholds)
        max_tier = max(max_tier, state.tier)
        
        # Track lead changes
        if prev_leader is not None and state.leader != prev_leader and state.leader != Leader.TIED:
            lead_changes += 1
        
        # Track ties
        if state.leader == Leader.TIED and (prev_leader is None or prev_leader != Leader.TIED):
            ties += 1
        
        prev_leader = state.leader
        prev_score = (home_score, away_score)
    
    # Back-and-forth criteria:
    # - At least 3 lead changes OR 3 ties
    # - Stays within tier 0-1 (close game)
    # - No sustained run of 8+ consecutive scores
    is_volatile = (lead_changes >= 3 or ties >= 3)
    is_close = max_tier <= 1
    no_sustained_run = max_run_length < 8
    
    return is_volatile and is_close and no_sustained_run


def _find_quarter_boundaries(
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
) -> list[int]:
    """
    Find quarter boundary indices within a moment.
    
    Returns indices where the quarter changes.
    """
    boundaries = []
    prev_quarter = None
    
    for i in range(start_idx, end_idx + 1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue
        
        quarter = event.get("quarter")
        if prev_quarter is not None and quarter != prev_quarter:
            boundaries.append(i)
        prev_quarter = quarter
    
    return boundaries


def _split_mega_moment(
    moment: Moment,
    events: list[dict[str, Any]],
    thresholds: Sequence[int],
    game_context: dict[str, str],
    max_plays: int = 50,
) -> list[Moment]:
    """
    Split a mega-moment into smaller chunks at natural break points.
    
    Break points (in priority order):
    1. Quarter boundaries
    2. Every max_plays if no quarter boundaries available
    
    Preserves score continuity and moment IDs.
    """
    # Check if moment is actually a mega-moment
    if moment.play_count <= max_plays:
        return [moment]
    
    # Find quarter boundaries within this moment
    quarter_boundaries = _find_quarter_boundaries(events, moment.start_play, moment.end_play)
    
    # If no quarter boundaries, split at regular intervals
    if not quarter_boundaries:
        # Split into chunks of max_plays
        split_points = []
        current = moment.start_play + max_plays
        while current < moment.end_play:
            split_points.append(current)
            current += max_plays
    else:
        split_points = quarter_boundaries
    
    # Create sub-moments
    sub_moments = []
    current_start = moment.start_play
    moment_id_counter = 0
    
    # Get initial score before the moment starts
    if current_start > 0:
        current_score_before = _get_score(events[current_start - 1])
    else:
        current_score_before = (0, 0)
    
    for split_idx in split_points:
        if split_idx <= current_start:
            continue
        
        # Score before is the score AFTER the previous sub-moment
        score_before = current_score_before
        
        # Find the last valid score before the split point
        # (skip quarter boundary events which have None scores)
        end_idx_for_sub = split_idx - 1
        score_after = _get_score(events[end_idx_for_sub])
        
        # If score is (0, 0), try to find the last valid score before this
        if score_after == (0, 0) and end_idx_for_sub > current_start:
            for j in range(end_idx_for_sub - 1, current_start - 1, -1):
                temp_score = _get_score(events[j])
                if temp_score != (0, 0):
                    score_after = temp_score
                    end_idx_for_sub = j
                    break
        
        start_state = compute_lead_state(score_before[0], score_before[1], thresholds)
        end_state = compute_lead_state(score_after[0], score_after[1], thresholds)
        
        # Inherit type from parent or determine from states
        if start_state.leader != end_state.leader:
            sub_type = MomentType.FLIP if end_state.leader != Leader.TIED else MomentType.TIE
        elif end_state.tier > start_state.tier:
            sub_type = MomentType.LEAD_BUILD
        elif end_state.tier < start_state.tier:
            sub_type = MomentType.CUT
        else:
            sub_type = MomentType.NEUTRAL
        
        # Create sub-moment
        sub_moment = _create_moment(
            moment_id=moment_id_counter,
            events=events,
            start_idx=current_start,
            end_idx=end_idx_for_sub,
            moment_type=sub_type,
            thresholds=thresholds,
            boundary=None,
            score_before=score_before,
            game_context=game_context,
        )
        
        # Preserve some metadata from parent
        sub_moment.id = f"{moment.id}_sub{moment_id_counter}"
        sub_moments.append(sub_moment)
        
        # Update for next iteration - skip the quarter boundary event
        current_start = split_idx
        current_score_before = score_after  # Score after this sub-moment becomes score before next
        moment_id_counter += 1
    
    # Create final sub-moment
    if current_start <= moment.end_play:
        score_before = current_score_before
        
        sub_moment = _create_moment(
            moment_id=moment_id_counter,
            events=events,
            start_idx=current_start,
            end_idx=moment.end_play,
            moment_type=moment.type,  # Last chunk keeps original type
            thresholds=thresholds,
            boundary=None,
            score_before=score_before,
            game_context=game_context,
        )
        
        sub_moment.id = f"{moment.id}_sub{moment_id_counter}"
        sub_moments.append(sub_moment)
    
    logger.info(
        "mega_moment_split",
        extra={
            "original_id": moment.id,
            "original_plays": moment.play_count,
            "sub_moments": len(sub_moments),
            "split_points": len(split_points),
        },
    )
    
    return sub_moments


# =============================================================================
# MOMENT PARTITIONING
# =============================================================================


def partition_game(
    timeline: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    thresholds: Sequence[int] | None = None,
    hysteresis_plays: int = DEFAULT_HYSTERESIS_PLAYS,
    game_context: dict[str, str] | None = None,
) -> list[Moment]:
    """
    Partition a game timeline into moments based on Lead Ladder.

    CORE GUARANTEES:
    1. Every CANONICAL PBP play belongs to exactly ONE moment
    2. Moments are contiguous (no gaps in canonical stream)
    3. Moments are chronologically ordered by start_play
    4. Moment count stays within sport-specific budget
    5. Every moment has a reason for existing
    6. Score continuity is preserved
    7. Participants are RESOLVED and FROZEN on the moment
    
    Args:
        timeline: Full timeline events (PBP + social)
        summary: Game summary metadata
        thresholds: Lead Ladder tier thresholds
        hysteresis_plays: Number of plays to confirm tier changes
        game_context: Team names and abbreviations for resolution
    """
    events = list(timeline)
    if not events:
        return []
    
    # Store game context for later use
    _game_context = game_context or {}

    # 1. Get CANONICAL PBP event indices (filter out junk)
    pbp_indices = get_canonical_pbp_indices(events)
    if not pbp_indices:
        logger.warning("partition_game_no_canonical_pbp", extra={"timeline_len": len(events)})
        return []

    # Use provided thresholds or minimal default
    if thresholds is None:
        logger.warning(
            "partition_game_no_thresholds: No thresholds provided, using minimal default [5]",
        )
        thresholds = [5]

    # 2. Detect boundaries using canonical stream
    boundaries = _detect_boundaries(events, pbp_indices, thresholds, hysteresis_plays)

    # Build moments from boundaries
    moments: list[Moment] = []
    moment_id = 0

    # Convert boundaries to a dict for quick lookup
    boundary_at: dict[int, BoundaryEvent] = {b.index: b for b in boundaries}

    # Partition plays into moments
    current_start: int | None = None
    current_type: MomentType = MomentType.NEUTRAL
    current_boundary: BoundaryEvent | None = None
    current_is_period_start = False

    moment_start_score = (0, 0)
    current_score = (0, 0) # Score after previous play
    prev_event: dict[str, Any] | None = None

    for idx, i in enumerate(pbp_indices):
        event = events[i]
        
        # Check if this play is a period opener
        is_opener = _is_period_opener(event, prev_event)
        if is_opener:
            current_is_period_start = True

        # Check if this is a boundary
        if i in boundary_at:
            boundary = boundary_at[i]

            # Close previous moment if any
            if current_start is not None:
                prev_idx = pbp_indices[idx - 1]
                moment = _create_moment(
                    moment_id=moment_id,
                    events=events,
                    start_idx=current_start,
                    end_idx=prev_idx,
                    moment_type=current_type,
                    thresholds=thresholds,
                    boundary=current_boundary,
                    score_before=moment_start_score,
                    game_context=_game_context,
                )
                moment.is_period_start = current_is_period_start
                moments.append(moment)
                moment_id += 1

                # Reset metadata for next moment
                moment_start_score = current_score
                current_is_period_start = is_opener # If the boundary IS the opener

            # Start new moment at this boundary
            current_start = i
            current_type = boundary.moment_type
            current_boundary = boundary
        else:
            # Continue current moment
            if current_start is None:
                current_start = i
                current_type = MomentType.NEUTRAL
                current_is_period_start = is_opener

        # Track what the score is after THIS play
        current_score = _get_score(event)
        prev_event = event

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
            score_before=moment_start_score,
            game_context=_game_context,
        )
        moment.is_period_start = current_is_period_start
        moments.append(moment)

    # Detect runs and attach to moments as metadata
    runs = detect_runs(events)  # From moments_runs module
    _attach_runs_to_moments(moments, runs)

    # AGGRESSIVE MERGE: Collapse consecutive same-type moments
    pre_merge_count = len(moments)
    moments = merge_consecutive_moments(moments)  # From moments_merging module

    # PER-QUARTER ENFORCEMENT: Prevent chaotic quarters
    moments = enforce_quarter_limits(moments, events)  # From moments_merging module

    # VALIDITY ENFORCEMENT: Merge invalid moments (Hard Gate)
    moments = merge_invalid_moments(moments)  # From moments_merging module

    # MEGA-MOMENT SPLITTING: Break up oversized moments created by merging
    # This happens AFTER merging to split the resulting mega-moments
    split_moments = []
    mega_moment_count = 0
    for moment in moments:
        # Check if this is a mega-moment that should be split
        if moment.play_count > 50 and moment.type in (MomentType.NEUTRAL, MomentType.CUT, MomentType.LEAD_BUILD):
            mega_moment_count += 1
            logger.info(
                "mega_moment_detected",
                extra={
                    "moment_id": moment.id,
                    "type": moment.type.value,
                    "play_count": moment.play_count,
                    "score_range": f"{moment.score_start} → {moment.score_end}",
                },
            )
            
            # Check if it's a back-and-forth phase
            is_back_and_forth = _detect_back_and_forth_phase(
                events, moment.start_play, moment.end_play, thresholds
            )
            
            logger.info(
                "back_and_forth_check",
                extra={
                    "moment_id": moment.id,
                    "is_back_and_forth": is_back_and_forth,
                },
            )
            
            if is_back_and_forth:
                # Split at quarter boundaries or regular intervals
                sub_moments = _split_mega_moment(
                    moment, events, thresholds, _game_context, max_plays=40
                )
                split_moments.extend(sub_moments)
                
                # Reclassify as NEUTRAL back-and-forth if appropriate
                for sub in sub_moments:
                    if sub.type in (MomentType.CUT, MomentType.LEAD_BUILD) and sub.play_count > 20:
                        sub.type = MomentType.NEUTRAL
                        if sub.reason:
                            sub.reason.narrative_delta = "back and forth"
            else:
                # Not back-and-forth, but still too large - split at quarter boundaries only
                quarter_boundaries = _find_quarter_boundaries(events, moment.start_play, moment.end_play)
                logger.info(
                    "quarter_boundaries_found",
                    extra={
                        "moment_id": moment.id,
                        "boundary_count": len(quarter_boundaries),
                    },
                )
                if quarter_boundaries:
                    sub_moments = _split_mega_moment(
                        moment, events, thresholds, _game_context, max_plays=100  # More lenient
                    )
                    split_moments.extend(sub_moments)
                else:
                    split_moments.append(moment)
        else:
            split_moments.append(moment)
    
    if mega_moment_count > 0:
        logger.info(
            "mega_moment_splitting_complete",
            extra={
                "mega_moments_detected": mega_moment_count,
                "moments_before": len(moments),
                "moments_after": len(split_moments),
            },
        )
    
    moments = split_moments

    # BUDGET ENFORCEMENT: If still over budget, merge more aggressively
    sport = summary.get("sport", "NBA") if isinstance(summary, dict) else "NBA"
    budget = MOMENT_BUDGET.get(sport, DEFAULT_MOMENT_BUDGET)
    if len(moments) > budget:
        moments = enforce_budget(moments, budget)  # From moments_merging module

    # Re-validate coverage after merging
    validate_moment_coverage(moments, pbp_indices)  # From moments_validation module

    # Validate score continuity
    validate_score_continuity(moments)  # From moments_validation module

    # CONTINUITY VALIDATION: Log issues but don't crash
    assert_moment_continuity(moments, is_valid_moment)  # From moments_validation module

    # Renumber moment IDs after merging
    for i, m in enumerate(moments):
        m.id = f"m_{i + 1:03d}"

    logger.info(
        "partition_game_complete",
        extra={
            "pre_merge_count": pre_merge_count,
            "post_merge_count": len(moments),
            "budget": budget,
            "within_budget": len(moments) <= budget,
            "notable_count": sum(1 for m in moments if m.is_notable),
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
        run = find_run_for_moment(runs, moment.start_play, moment.end_play)  # From moments_runs module
        
        if run is None:
            continue
            
        # Check if this run is already attached
        run_idx = runs.index(run)
        if run_idx in attached_runs:
            continue
            
        # PROMOTE: Attach as run_info if moment type is promotable
        if moment.type in PROMOTABLE_TYPES:
            moment.run_info = run_to_info(run)  # From moments_runs module
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


def _extract_moment_context(
    events: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    game_context: dict[str, str],
) -> tuple[list[str], str | None, list[PlayerContribution], list[int]]:
    """
    MOMENT RESOLUTION PASS: Deeply inspect plays to extract participants.
    
    Returns:
        - teams_involved: All teams with plays in this moment (resolved to full names)
        - primary_team: The team that drove the narrative (resolved to full name)
        - players: Top 1-3 players by impact
        - key_play_ids: Play indices for significant actions
    """
    teams_involved = set()
    player_impact: dict[str, int] = {} # player -> impact score
    player_data: dict[str, dict[str, int]] = {}
    team_impact: dict[str, int] = {} # team_abbrev -> impact score
    key_play_ids = []

    # Track score deltas to determine which team drove the narrative
    start_score = None
    end_score = None

    for i in range(start_idx, end_idx + 1):
        event = events[i]
        if event.get("event_type") != "pbp":
            continue

        # Capture score range
        if start_score is None:
            start_score = (event.get("home_score", 0), event.get("away_score", 0))
        end_score = (event.get("home_score", 0), event.get("away_score", 0))

        team_abbrev = event.get("team_abbreviation")
        if team_abbrev:
            teams_involved.add(team_abbrev)
        
        # Extract stats/impact
        player_name = event.get("player_name")
        description = (event.get("description") or "").lower()
        impact = 0

        if "made" in description:
            impact += 10
            if "three" in description or "3pt" in description:
                impact += 5
        if "assist" in description: impact += 5
        if "block" in description: impact += 7
        if "steal" in description: impact += 7
        if "rebound" in description: impact += 3
        
        if player_name:
            player_impact[player_name] = player_impact.get(player_name, 0) + impact
            if player_name not in player_data:
                player_data[player_name] = {}
            if impact > 0:
                key_play_ids.append(i)

        # Track team impact
        if team_abbrev and impact > 0:
            team_impact[team_abbrev] = team_impact.get(team_abbrev, 0) + impact

    # Build team name resolution map
    team_name_map = {}
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

    # Resolve primary team by score delta if possible
    primary_team = None
    if start_score and end_score:
        # Handle None values in scores
        home_start = start_score[0] if start_score[0] is not None else 0
        away_start = start_score[1] if start_score[1] is not None else 0
        home_end = end_score[0] if end_score[0] is not None else 0
        away_end = end_score[1] if end_score[1] is not None else 0
        
        home_delta = home_end - home_start
        away_delta = away_end - away_start
        
        # Primary team is the one that scored more in this moment
        if home_delta > away_delta:
            primary_team = team_name_map.get("home", "home")
        elif away_delta > home_delta:
            primary_team = team_name_map.get("away", "away")
        # If tied, use impact score
        elif team_impact:
            top_abbrev = max(team_impact.items(), key=lambda x: x[1])[0]
            primary_team = team_name_map.get(top_abbrev, top_abbrev)

    # Resolve team names
    resolved_teams = [team_name_map.get(abbrev, abbrev) for abbrev in teams_involved]

    # Resolve players
    sorted_players = sorted(player_impact.items(), key=lambda x: x[1], reverse=True)[:3]
    players = [
        PlayerContribution(name=name, stats=player_data.get(name, {}))
        for name, _ in sorted_players
    ]

    return resolved_teams, primary_team, players, key_play_ids


def _create_moment_reason(
    moment_type: MomentType,
    start_state: LeadState,
    end_state: LeadState,
    team_in_control: str | None,
) -> MomentReason:
    """
    Create a reason explaining WHY this moment exists.
    """
    # Determine trigger - MUST be one of the allowed causal triggers
    trigger_map = {
        "FLIP": "flip",
        "TIE": "tie",
        "CLOSING_CONTROL": "closing_lock",
        "HIGH_IMPACT": "high_impact",
        "LEAD_BUILD": "tier_cross",
        "CUT": "tier_cross",
        "NEUTRAL": "stable",
    }
    type_str = moment_type.value if hasattr(moment_type, 'value') else str(moment_type)
    trigger = trigger_map.get(type_str, "unknown")

    if trigger == "unknown":
        logger.error(f"moment_creation_failed: unknown_trigger_for_type_{type_str}")

    # Determine control shift
    control_shift: str | None = None
    if start_state.leader != end_state.leader:
        if end_state.leader == Leader.HOME:
            control_shift = "home"
        elif end_state.leader == Leader.AWAY:
            control_shift = "away"

    # Determine narrative delta
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


def _create_moment(
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
    """
    Create a Moment and run the RESOLUTION PASS.
    """
    start_event = events[start_idx]
    end_event = events[end_idx]

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

    # RESOLUTION PASS: Extract factual context from events
    teams, primary_team, players, key_play_ids = _extract_moment_context(
        events, start_idx, end_idx, game_context or {}
    )

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
        teams=teams,
        primary_team=primary_team,
        players=players,
        key_play_ids=key_play_ids,
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

    return False


# =============================================================================
# VALIDATION
# =============================================================================


class MomentValidationError(Exception):
    """Raised when moment partitioning fails validation."""
    pass


def _validate_score_continuity(moments: list[Moment]) -> None:
    """
    Validate that moment scores are continuous (no resets).

    Logs warnings for score discontinuities but doesn't fail the build.
    """
    if len(moments) <= 1:
        return

    for i in range(1, len(moments)):
        prev_moment = moments[i - 1]
        curr_moment = moments[i]

        if prev_moment.score_after != curr_moment.score_before:
            logger.error(
                "moment_score_discontinuity",
                extra={
                    "prev_moment_id": prev_moment.id,
                    "curr_moment_id": curr_moment.id,
                    "prev_end": prev_moment.score_after,
                    "curr_start": curr_moment.score_before,
                    "prev_end_play": prev_moment.end_play,
                    "curr_start_play": curr_moment.start_play,
                },
            )


def _assert_moment_continuity(moments: list[Moment]) -> None:
    """
    CONTINUITY VALIDATION: Log issues but don't crash during debugging.

    During development, log problems but allow pipeline to continue.
    TODO: Make this crash the pipeline once all issues are resolved.
    """
    if not moments:
        logger.error("no_moments_generated")
        return  # Don't crash for now

    # Check play coverage (no gaps, no overlaps)
    covered_plays = set()
    overlaps = []
    for moment in moments:
        for play_idx in range(moment.start_play, moment.end_play + 1):
            if play_idx in covered_plays:
                overlaps.append(f"Play {play_idx} in {moment.id}")
            covered_plays.add(play_idx)

    if overlaps:
        logger.error("play_overlaps_detected", extra={"overlaps": overlaps[:10]})

    # Check score continuity between adjacent moments
    discontinuities = []
    for i in range(1, len(moments)):
        prev_moment = moments[i - 1]
        curr_moment = moments[i]

        if prev_moment.score_after != curr_moment.score_before:
            discontinuities.append({
                "prev_id": prev_moment.id,
                "curr_id": curr_moment.id,
                "prev_end": prev_moment.score_after,
                "curr_start": curr_moment.score_before,
            })

    if discontinuities:
        logger.error("score_discontinuities_detected", extra={"discontinuities": discontinuities})

    # Check that no moments are invalid after merging
    invalid_moments = [m for m in moments if not is_valid_moment(m)]
    if invalid_moments:
        invalid_info = [{"id": m.id, "type": m.type.value, "score": f"{m.score_before}→{m.score_after}"} for m in invalid_moments]
        logger.error("invalid_moments_remaining", extra={"invalid_moments": invalid_info})

    # Check for single-play moments that aren't high-impact
    problematic_micro = []
    for moment in moments:
        if (moment.play_count == 1 and
            moment.type not in (MomentType.FLIP, MomentType.TIE, MomentType.HIGH_IMPACT)):
            problematic_micro.append({
                "id": moment.id,
                "type": moment.type.value,
                "trigger": moment.reason.trigger if moment.reason else None
            })

    if problematic_micro:
        logger.error("problematic_micro_moments", extra={"micro_moments": problematic_micro})

    # For now, log all issues but don't crash the pipeline
    total_issues = len(overlaps) + len(discontinuities) + len(invalid_moments) + len(problematic_micro)
    if total_issues > 0:
        logger.warning(
            "moment_continuity_issues_detected",
            extra={
                "total_issues": total_issues,
                "overlaps": len(overlaps),
                "discontinuities": len(discontinuities),
                "invalid_moments": len(invalid_moments),
                "micro_moments": len(problematic_micro),
                "note": "Pipeline continuing despite issues - fix these problems"
            }
        )


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
