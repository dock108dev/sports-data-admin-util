"""GENERATE_MOMENTS Stage Implementation.

This stage segments normalized PBP data into condensed moments using
deterministic, rule-based boundary detection, and selects which plays
must be explicitly narrated.

STORY CONTRACT ALIGNMENT
========================
This implementation adheres to the Story contract:
- Moments are derived DIRECTLY from PBP data
- No signals, momentum, or narrative abstractions
- No LLM/OpenAI calls
- Ordering is by play_index (canonical)
- Output contains NO narrative text

SEGMENTATION RULES (Task 1.1: Soft-Capped Moment Compression)
=============================================================
The system uses SOFT caps that prefer but don't force closure:

SOFT CAP: SOFT_CAP_PLAYS = 8 plays
- Prefer closing when reached
- Allow continuation if game flow is continuous

ABSOLUTE CAP: ABSOLUTE_MAX_PLAYS = 12 plays
- Hard limit, must close (safety valve)

HARD BREAK CONDITIONS (always close):
1. Period boundary (end/start of quarter)
2. Lead change
3. Would create >2 explicitly narrated plays
4. ABSOLUTE_MAX_PLAYS reached

SOFT BREAK CONDITIONS (prefer closing):
1. SOFT_CAP_PLAYS reached
2. Scoring play (but not lead change)
3. Turnover/possession change
4. Stoppage (timeout/review)
5. Second explicitly narrated play encountered

MERGE ELIGIBILITY (encourage continuing):
- No scoring in current moment
- Possession alternates normally
- Time delta below threshold

TARGET DISTRIBUTION:
- ~80% of moments ≤ 8 plays
- ~80% of moments with ≤ 1 explicitly narrated play
- ~25-40% reduction in moment count

EXPLICIT NARRATION SELECTION
============================
Each moment must identify at least one play for explicit narration.
Selection rules (in priority order):
1. Scoring plays: Any play where score changed from previous play
2. Notable plays: Plays with notable play_types (blocks, steals, etc.)
3. Fallback: Last play in the moment

Constraint: Maximum 2 explicitly narrated plays per moment.

GUARANTEES
==========
1. Full play coverage: Every play appears in exactly one moment
2. No overlap: No play_id appears in more than one moment
3. Correct ordering: Moments ordered by first play's play_index
4. Non-empty: Every moment has at least 1 play_id
5. Narration coverage: Every moment has at least 1 explicitly_narrated_play_id
6. Narration subset: explicitly_narrated_play_ids is a subset of play_ids
7. No cross-period moments: All plays in a moment are from the same period
8. Max narration: No moment has more than 2 explicitly_narrated_play_ids
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..models import StageInput, StageOutput

logger = logging.getLogger(__name__)


# =============================================================================
# MOMENT COMPRESSION CONFIGURATION (Task 1.1)
# =============================================================================
# These values are tunable without code changes.

# Soft cap: prefer closing at this point
SOFT_CAP_PLAYS = 8

# Absolute cap: must close (safety valve, should be rare)
ABSOLUTE_MAX_PLAYS = 12

# Maximum explicitly narrated plays per moment
MAX_EXPLICIT_PLAYS_PER_MOMENT = 2

# Target: prefer ≤1 explicit play per moment
PREFERRED_EXPLICIT_PLAYS = 1


class BoundaryType(str, Enum):
    """Classification of boundary decision type."""

    HARD = "HARD"  # Non-negotiable, must close
    SOFT = "SOFT"  # Prefer closing, but can continue if flow demands


class BoundaryReason(str, Enum):
    """Specific reason for moment boundary."""

    # Hard boundaries (always close)
    PERIOD_BOUNDARY = "PERIOD_BOUNDARY"
    LEAD_CHANGE = "LEAD_CHANGE"
    EXPLICIT_PLAY_OVERFLOW = "EXPLICIT_PLAY_OVERFLOW"
    ABSOLUTE_MAX_PLAYS = "ABSOLUTE_MAX_PLAYS"

    # Soft boundaries (prefer closing)
    SOFT_CAP_REACHED = "SOFT_CAP_REACHED"
    SCORING_PLAY = "SCORING_PLAY"
    POSSESSION_CHANGE = "POSSESSION_CHANGE"
    STOPPAGE = "STOPPAGE"
    SECOND_EXPLICIT_PLAY = "SECOND_EXPLICIT_PLAY"

    # End of input
    END_OF_INPUT = "END_OF_INPUT"

    @property
    def is_hard(self) -> bool:
        """Check if this is a hard (non-negotiable) boundary."""
        return self in {
            BoundaryReason.PERIOD_BOUNDARY,
            BoundaryReason.LEAD_CHANGE,
            BoundaryReason.EXPLICIT_PLAY_OVERFLOW,
            BoundaryReason.ABSOLUTE_MAX_PLAYS,
        }


@dataclass
class CompressionMetrics:
    """Instrumentation metrics for moment compression (Task 1.1).

    These metrics track distribution characteristics for validation.
    """

    total_moments: int = 0
    total_plays: int = 0
    plays_per_moment: list[int] = field(default_factory=list)
    explicit_plays_per_moment: list[int] = field(default_factory=list)
    boundary_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def pct_moments_under_soft_cap(self) -> float:
        """Percentage of moments with ≤ SOFT_CAP_PLAYS plays."""
        if not self.plays_per_moment:
            return 0.0
        under = sum(1 for p in self.plays_per_moment if p <= SOFT_CAP_PLAYS)
        return (under / len(self.plays_per_moment)) * 100

    @property
    def pct_moments_single_explicit(self) -> float:
        """Percentage of moments with ≤ 1 explicitly narrated play."""
        if not self.explicit_plays_per_moment:
            return 0.0
        single = sum(1 for e in self.explicit_plays_per_moment if e <= 1)
        return (single / len(self.explicit_plays_per_moment)) * 100

    @property
    def median_plays_per_moment(self) -> float:
        """Median plays per moment."""
        if not self.plays_per_moment:
            return 0.0
        sorted_plays = sorted(self.plays_per_moment)
        n = len(sorted_plays)
        if n % 2 == 0:
            return (sorted_plays[n // 2 - 1] + sorted_plays[n // 2]) / 2
        return float(sorted_plays[n // 2])

    @property
    def max_plays_observed(self) -> int:
        """Maximum plays in any moment."""
        return max(self.plays_per_moment) if self.plays_per_moment else 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "total_moments": self.total_moments,
            "total_plays": self.total_plays,
            "pct_moments_under_soft_cap": round(self.pct_moments_under_soft_cap, 1),
            "pct_moments_single_explicit": round(self.pct_moments_single_explicit, 1),
            "median_plays_per_moment": round(self.median_plays_per_moment, 1),
            "max_plays_observed": self.max_plays_observed,
            "avg_plays_per_moment": round(
                sum(self.plays_per_moment) / len(self.plays_per_moment), 1
            ) if self.plays_per_moment else 0,
            "boundary_reasons": self.boundary_reasons,
        }

# Play types that indicate stoppages (timeouts, reviews, etc.)
STOPPAGE_PLAY_TYPES = frozenset([
    "timeout",
    "full_timeout",
    "official_timeout",
    "tv_timeout",
    "20_second_timeout",
    "review",
    "instant_replay",
    "delay_of_game",
    "ejection",
])

# Play types that indicate possession change / turnover
TURNOVER_PLAY_TYPES = frozenset([
    "turnover",
    "steal",
    "lost_ball",
    "bad_pass",
    "out_of_bounds",
    "offensive_foul",
    "traveling",
    "travel",
    "double_dribble",
    "kicked_ball",
])

# Play types that are notable and should be narrated (non-scoring)
# These are plays that typically warrant explicit mention in game narrative
NOTABLE_PLAY_TYPES = frozenset([
    # Defensive plays
    "block",
    "blocked_shot",
    "steal",
    # Turnovers
    "turnover",
    "offensive_foul",
    # Rebounds (contested action)
    "offensive_rebound",
    "defensive_rebound",
    # Fast breaks / assists
    "assist",
    "fast_break",
    # Fouls
    "foul",
    "personal_foul",
    "shooting_foul",
    "technical_foul",
    "flagrant_foul",
    # Other notable events
    "jump_ball",
    "jumpball",
    "violation",
])


def _get_lead_state(home_score: int, away_score: int) -> str:
    """Determine the lead state from scores.

    Returns:
        'HOME' if home leads, 'AWAY' if away leads, 'TIE' if tied
    """
    if home_score > away_score:
        return "HOME"
    elif away_score > home_score:
        return "AWAY"
    return "TIE"


def _is_lead_change(
    prev_home: int,
    prev_away: int,
    curr_home: int,
    curr_away: int,
) -> bool:
    """Detect if a lead change occurred between two score states.

    A lead change is when the team with the lead switches.
    Going from tied to a lead is NOT a lead change.
    Going from a lead to tied is NOT a lead change.
    Going from HOME lead to AWAY lead IS a lead change.

    Args:
        prev_home: Previous home score
        prev_away: Previous away score
        curr_home: Current home score
        curr_away: Current away score

    Returns:
        True if a lead change occurred
    """
    prev_lead = _get_lead_state(prev_home, prev_away)
    curr_lead = _get_lead_state(curr_home, curr_away)

    # Lead change only if both states have a leader and they differ
    if prev_lead in ("HOME", "AWAY") and curr_lead in ("HOME", "AWAY"):
        return prev_lead != curr_lead

    return False


def _is_scoring_play(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if the current play resulted in a score change.

    A scoring play is detected when either home_score or away_score
    differs from the previous play's scores.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if score changed, False otherwise
    """
    if previous_event is None:
        # First play: scoring if scores are non-zero
        home = current_event.get("home_score") or 0
        away = current_event.get("away_score") or 0
        return home > 0 or away > 0

    prev_home = previous_event.get("home_score") or 0
    prev_away = previous_event.get("away_score") or 0
    curr_home = current_event.get("home_score") or 0
    curr_away = current_event.get("away_score") or 0

    return curr_home != prev_home or curr_away != prev_away


def _is_lead_change_play(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if this play caused a lead change.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if a lead change occurred
    """
    if previous_event is None:
        return False

    prev_home = previous_event.get("home_score") or 0
    prev_away = previous_event.get("away_score") or 0
    curr_home = current_event.get("home_score") or 0
    curr_away = current_event.get("away_score") or 0

    return _is_lead_change(prev_home, prev_away, curr_home, curr_away)


def _is_turnover_play(event: dict[str, Any]) -> bool:
    """Detect if this play is a turnover/possession change.

    Args:
        event: The normalized PBP event

    Returns:
        True if this is a turnover play
    """
    play_type = (event.get("play_type") or "").lower().replace(" ", "_")
    description = (event.get("description") or "").lower()

    # Check explicit play_type
    if play_type in TURNOVER_PLAY_TYPES:
        return True

    # Check description for turnover indicators
    turnover_keywords = ["turnover", "steal", "lost ball", "bad pass", "traveling"]
    if any(kw in description for kw in turnover_keywords):
        return True

    return False


def _is_period_boundary(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
) -> bool:
    """Detect if this play starts a new period.

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)

    Returns:
        True if period changed, False otherwise
    """
    if previous_event is None:
        return False

    prev_quarter = previous_event.get("quarter") or 1
    curr_quarter = current_event.get("quarter") or 1

    return curr_quarter != prev_quarter


def _is_stoppage_play(event: dict[str, Any]) -> bool:
    """Detect if this play is a stoppage (timeout, review, etc.).

    Args:
        event: The normalized PBP event

    Returns:
        True if this is a stoppage play, False otherwise
    """
    play_type = (event.get("play_type") or "").lower().replace(" ", "_")
    description = (event.get("description") or "").lower()

    # Check explicit play_type
    if play_type in STOPPAGE_PLAY_TYPES:
        return True

    # Check description for timeout indicators
    if "timeout" in description:
        return True

    return False


def _should_start_new_moment(
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    current_moment_size: int,
) -> bool:
    """Determine if we should start a new moment before this play.

    BOUNDARY RULES (in priority order):
    1. Period boundary: Always start new moment at period change
    2. Hard maximum: Start new moment if current would exceed SOFT_CAP_PLAYS
    3. After scoring: Previous play was a scoring play
    4. After stoppage: Previous play was a timeout/review

    Args:
        current_event: The current normalized PBP event
        previous_event: The previous event (None for first play)
        current_moment_size: Number of plays in current moment

    Returns:
        True if a new moment should start, False otherwise
    """
    # First play always starts first moment
    if previous_event is None:
        return True

    # Rule 1: Period boundary - always start new moment
    if _is_period_boundary(current_event, previous_event):
        return True

    # Rule 2: Hard maximum exceeded
    if current_moment_size >= SOFT_CAP_PLAYS:
        return True

    # Rule 3: Previous play was a scoring play
    if _is_scoring_play(previous_event, None):
        # We need the play before previous to check if previous was scoring
        # This is handled by tracking in the main loop
        pass

    # Rule 4: Previous play was a stoppage
    if _is_stoppage_play(previous_event):
        return True

    return False


def _get_score_before_moment(
    events: list[dict[str, Any]],
    moment_start_index: int,
) -> tuple[int, int]:
    """Get the score state BEFORE the first play of a moment.

    The score_before is the score after the play immediately preceding
    the first play of this moment. For the first moment, it's [0, 0].

    Args:
        events: All normalized PBP events
        moment_start_index: Index of first play in this moment

    Returns:
        Tuple of (home_score, away_score) before the moment
    """
    if moment_start_index == 0:
        return (0, 0)

    prev_event = events[moment_start_index - 1]
    home = prev_event.get("home_score") or 0
    away = prev_event.get("away_score") or 0
    return (home, away)


def _get_score_after_moment(last_event: dict[str, Any]) -> tuple[int, int]:
    """Get the score state AFTER the last play of a moment.

    Args:
        last_event: The last PBP event in the moment

    Returns:
        Tuple of (home_score, away_score) after the moment
    """
    home = last_event.get("home_score") or 0
    away = last_event.get("away_score") or 0
    return (home, away)


def _is_notable_play(event: dict[str, Any]) -> bool:
    """Check if a play has a notable play_type.

    Args:
        event: The normalized PBP event

    Returns:
        True if the play_type is in NOTABLE_PLAY_TYPES
    """
    play_type = (event.get("play_type") or "").lower().replace(" ", "_")
    return play_type in NOTABLE_PLAY_TYPES


def _select_explicitly_narrated_plays(
    moment_plays: list[dict[str, Any]],
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> list[int]:
    """Select which plays in a moment must be explicitly narrated.

    SELECTION RULES (deterministic, based on PBP facts only):

    1. SCORING PLAYS: Any play where score differs from the previous play.
       These are the most concrete, verifiable events.

    2. NOTABLE PLAYS: If no scoring plays, select plays with notable
       play_types (blocks, steals, turnovers, etc.).

    3. FALLBACK: If no scoring or notable plays, select the last play.
       Every moment must have at least one narrated play.

    CONSTRAINT (Task 1.1):
    - Maximum MAX_EXPLICIT_PLAYS_PER_MOMENT (2) plays can be narrated
    - If more candidates exist, prefer scoring plays, then most recent

    Args:
        moment_plays: List of PBP events in this moment
        all_events: All PBP events (for score comparison)
        moment_start_idx: Index of first play in all_events

    Returns:
        List of play_index values that must be explicitly narrated.
        Guaranteed to be non-empty, subset of play_ids, and ≤ MAX_EXPLICIT_PLAYS_PER_MOMENT.
    """
    scoring_ids: list[int] = []
    notable_ids: list[int] = []

    # RULE 1: Identify scoring plays
    for i, play in enumerate(moment_plays):
        # Get the previous event (could be from previous moment or this moment)
        global_idx = moment_start_idx + i
        if global_idx == 0:
            # First play of game - scoring if scores > 0
            home = play.get("home_score") or 0
            away = play.get("away_score") or 0
            if home > 0 or away > 0:
                scoring_ids.append(play["play_index"])
        else:
            prev_event = all_events[global_idx - 1]
            if _is_scoring_play(play, prev_event):
                scoring_ids.append(play["play_index"])

    # RULE 2: Identify notable plays (blocks, steals, etc.)
    for play in moment_plays:
        if _is_notable_play(play):
            notable_ids.append(play["play_index"])

    # Build candidate list: scoring plays first, then notable plays
    candidates = scoring_ids + [nid for nid in notable_ids if nid not in scoring_ids]

    # If we have candidates, cap at MAX_EXPLICIT_PLAYS_PER_MOMENT
    if candidates:
        # Prefer keeping scoring plays, take most recent if we must cap
        if len(candidates) > MAX_EXPLICIT_PLAYS_PER_MOMENT:
            # Keep the most significant ones (scoring plays preferred)
            if len(scoring_ids) >= MAX_EXPLICIT_PLAYS_PER_MOMENT:
                # Take last N scoring plays (most recent scoring events)
                candidates = scoring_ids[-MAX_EXPLICIT_PLAYS_PER_MOMENT:]
            else:
                # Take all scoring + remaining from notable up to cap
                candidates = candidates[-MAX_EXPLICIT_PLAYS_PER_MOMENT:]
        return candidates

    # RULE 3: Fallback - select the last play
    return [moment_plays[-1]["play_index"]]


def _count_explicit_plays_if_added(
    moment_plays: list[dict[str, Any]],
    new_play: dict[str, Any],
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> int:
    """Count how many explicit plays would result if we add new_play to moment.

    This is used to check if adding a play would exceed MAX_EXPLICIT_PLAYS_PER_MOMENT.

    Args:
        moment_plays: Current plays in the moment
        new_play: Play we're considering adding
        all_events: All PBP events
        moment_start_idx: Index of first play in all_events

    Returns:
        Number of explicitly narrated plays that would result
    """
    # Build hypothetical moment
    hypothetical_plays = moment_plays + [new_play]
    narrated = _select_explicitly_narrated_plays(
        hypothetical_plays, all_events, moment_start_idx
    )
    return len(narrated)


def _should_force_close_moment(
    current_moment_plays: list[dict[str, Any]],
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> tuple[bool, BoundaryReason | None]:
    """Check if a HARD boundary condition requires closing the moment.

    HARD conditions are non-negotiable and always force closure.

    Args:
        current_moment_plays: Plays currently in the moment (including current)
        current_event: The current event just added
        previous_event: The previous event (None for first play)
        all_events: All events for explicit play counting
        moment_start_idx: Start index of current moment

    Returns:
        (should_close, reason) tuple
    """
    # HARD: Absolute max plays reached (safety valve)
    if len(current_moment_plays) >= ABSOLUTE_MAX_PLAYS:
        return True, BoundaryReason.ABSOLUTE_MAX_PLAYS

    # HARD: Lead change occurred
    if previous_event and _is_lead_change_play(current_event, previous_event):
        return True, BoundaryReason.LEAD_CHANGE

    # HARD: Would create >2 explicitly narrated plays
    # Check what the explicit play count would be
    narrated = _select_explicitly_narrated_plays(
        current_moment_plays, all_events, moment_start_idx
    )
    if len(narrated) > MAX_EXPLICIT_PLAYS_PER_MOMENT:
        return True, BoundaryReason.EXPLICIT_PLAY_OVERFLOW

    return False, None


def _should_prefer_close_moment(
    current_moment_plays: list[dict[str, Any]],
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    all_events: list[dict[str, Any]],
    moment_start_idx: int,
) -> tuple[bool, BoundaryReason | None]:
    """Check if a SOFT boundary condition suggests closing the moment.

    SOFT conditions prefer closing but can be overridden by merge eligibility.

    Args:
        current_moment_plays: Plays currently in the moment (including current)
        current_event: The current event just added
        previous_event: The previous event (None for first play)
        all_events: All events for explicit play counting
        moment_start_idx: Start index of current moment

    Returns:
        (should_close, reason) tuple
    """
    # SOFT: Soft cap reached
    if len(current_moment_plays) >= SOFT_CAP_PLAYS:
        return True, BoundaryReason.SOFT_CAP_REACHED

    # SOFT: Scoring play (but not lead change, that's HARD)
    if previous_event and _is_scoring_play(current_event, previous_event):
        return True, BoundaryReason.SCORING_PLAY

    # SOFT: Stoppage play
    if _is_stoppage_play(current_event):
        return True, BoundaryReason.STOPPAGE

    # SOFT: Turnover / possession change
    if _is_turnover_play(current_event):
        return True, BoundaryReason.POSSESSION_CHANGE

    # SOFT: Second explicitly narrated play encountered
    narrated = _select_explicitly_narrated_plays(
        current_moment_plays, all_events, moment_start_idx
    )
    if len(narrated) > PREFERRED_EXPLICIT_PLAYS:
        return True, BoundaryReason.SECOND_EXPLICIT_PLAY

    return False, None


def _is_merge_eligible(
    current_moment_plays: list[dict[str, Any]],
    current_event: dict[str, Any],
    previous_event: dict[str, Any] | None,
    next_event: dict[str, Any] | None,
) -> bool:
    """Check if game flow suggests we should continue merging plays.

    Merge eligibility can override SOFT (but not HARD) boundary conditions.

    Conditions for merge eligibility:
    - No scoring has occurred in the current moment
    - Game flow appears continuous (not fragmented)

    Args:
        current_moment_plays: Plays currently in the moment
        current_event: The current event
        previous_event: The previous event
        next_event: The next event (for lookahead)

    Returns:
        True if merge should be encouraged
    """
    # Don't encourage merge if moment is already getting large
    if len(current_moment_plays) >= SOFT_CAP_PLAYS:
        return False

    # Check if any scoring has occurred in this moment
    if len(current_moment_plays) > 1:
        for j in range(1, len(current_moment_plays)):
            prev = current_moment_plays[j - 1]
            curr = current_moment_plays[j]
            if _is_scoring_play(curr, prev):
                # Scoring occurred, don't encourage merge
                return False

    # If next event is in the same period and game is flowing, encourage merge
    if next_event:
        curr_period = current_event.get("quarter") or 1
        next_period = next_event.get("quarter") or 1
        if curr_period == next_period:
            # Same period, game is flowing
            return True

    return False


def _segment_plays_into_moments(
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], CompressionMetrics]:
    """Segment PBP events into condensed moments using soft-capped compression.

    ALGORITHM (Task 1.1: Soft-Capped Moment Compression):
    1. Iterate through events in play_index order (already sorted)
    2. Accumulate plays into current moment
    3. Check HARD boundary conditions (must close)
    4. Check SOFT boundary conditions (prefer close)
    5. Check merge eligibility (can override soft conditions)
    6. Close moment when appropriate

    HARD BOUNDARIES (always close):
    - Period change (start new moment BEFORE the play)
    - Lead change
    - >2 explicitly narrated plays would result
    - ABSOLUTE_MAX_PLAYS reached

    SOFT BOUNDARIES (prefer closing):
    - SOFT_CAP_PLAYS reached
    - Scoring play
    - Stoppage play
    - Turnover
    - Second explicit play

    MERGE ELIGIBILITY (can override soft):
    - No scoring in current moment
    - Continuous game flow

    Args:
        events: Normalized PBP events, ordered by play_index

    Returns:
        Tuple of (moments list, compression metrics)

    Raises:
        ValueError: If any guarantee is violated
    """
    if not events:
        return [], CompressionMetrics()

    moments: list[dict[str, Any]] = []
    current_moment_plays: list[dict[str, Any]] = []
    current_moment_start_idx = 0
    metrics = CompressionMetrics(total_plays=len(events))

    # Track all play_ids for coverage verification
    all_play_ids: set[int] = set()
    assigned_play_ids: set[int] = set()

    def finalize_current_moment(reason: BoundaryReason) -> None:
        """Helper to finalize and record the current moment."""
        nonlocal current_moment_plays, current_moment_start_idx

        if not current_moment_plays:
            return

        moment = _finalize_moment(events, current_moment_plays, current_moment_start_idx)
        moments.append(moment)

        # Track metrics
        play_count = len(moment["play_ids"])
        explicit_count = len(moment["explicitly_narrated_play_ids"])
        metrics.plays_per_moment.append(play_count)
        metrics.explicit_plays_per_moment.append(explicit_count)
        metrics.boundary_reasons[reason.value] = (
            metrics.boundary_reasons.get(reason.value, 0) + 1
        )

        for p in current_moment_plays:
            assigned_play_ids.add(p["play_index"])

        current_moment_plays = []

    for i, event in enumerate(events):
        play_index = event.get("play_index")
        if play_index is None:
            raise ValueError(f"Event at position {i} missing play_index")

        all_play_ids.add(play_index)

        previous_event = events[i - 1] if i > 0 else None
        next_event = events[i + 1] if i + 1 < len(events) else None

        # HARD: Period boundary - close current and start new moment BEFORE this play
        if previous_event and _is_period_boundary(event, previous_event):
            if current_moment_plays:
                finalize_current_moment(BoundaryReason.PERIOD_BOUNDARY)
            current_moment_start_idx = i

        # Add current play to moment
        current_moment_plays.append(event)

        # Last play always ends moment
        if i == len(events) - 1:
            finalize_current_moment(BoundaryReason.END_OF_INPUT)
            continue

        # Check HARD boundary conditions (must close)
        should_close_hard, hard_reason = _should_force_close_moment(
            current_moment_plays,
            event,
            previous_event,
            events,
            current_moment_start_idx,
        )
        if should_close_hard and hard_reason:
            finalize_current_moment(hard_reason)
            current_moment_start_idx = i + 1
            continue

        # Check SOFT boundary conditions (prefer close)
        should_close_soft, soft_reason = _should_prefer_close_moment(
            current_moment_plays,
            event,
            previous_event,
            events,
            current_moment_start_idx,
        )

        if should_close_soft and soft_reason:
            # Check if merge eligibility overrides the soft condition
            merge_eligible = _is_merge_eligible(
                current_moment_plays,
                event,
                previous_event,
                next_event,
            )

            # Only override soft conditions if:
            # 1. Merge is eligible
            # 2. We haven't hit soft cap yet
            # 3. The soft reason isn't critical (scoring allowed to override merge)
            should_override = (
                merge_eligible
                and len(current_moment_plays) < SOFT_CAP_PLAYS
                and soft_reason not in {
                    BoundaryReason.SCORING_PLAY,  # Don't override scoring
                    BoundaryReason.SOFT_CAP_REACHED,  # Don't override cap
                }
            )

            if not should_override:
                finalize_current_moment(soft_reason)
                current_moment_start_idx = i + 1

    # Ensure all plays are assigned
    if current_moment_plays:
        finalize_current_moment(BoundaryReason.END_OF_INPUT)

    # Update metrics
    metrics.total_moments = len(moments)

    # VERIFICATION: Full coverage
    if all_play_ids != assigned_play_ids:
        missing = all_play_ids - assigned_play_ids
        extra = assigned_play_ids - all_play_ids
        raise ValueError(
            f"Play coverage violation. Missing: {missing}, Extra: {extra}"
        )

    # VERIFICATION: Non-empty moments and narration
    for idx, moment in enumerate(moments):
        if not moment["play_ids"]:
            raise ValueError(f"Moment {idx} has no play_ids")

        if not moment.get("explicitly_narrated_play_ids"):
            raise ValueError(f"Moment {idx} has no explicitly_narrated_play_ids")

        # VERIFICATION: Narrated plays are subset of play_ids
        play_ids_set = set(moment["play_ids"])
        narrated_set = set(moment["explicitly_narrated_play_ids"])
        if not narrated_set.issubset(play_ids_set):
            invalid = narrated_set - play_ids_set
            raise ValueError(
                f"Moment {idx} has narrated play_ids not in play_ids: {invalid}"
            )

        # VERIFICATION: Max narration constraint (Task 1.1)
        if len(narrated_set) > MAX_EXPLICIT_PLAYS_PER_MOMENT:
            raise ValueError(
                f"Moment {idx} has {len(narrated_set)} narrated plays, "
                f"exceeds max of {MAX_EXPLICIT_PLAYS_PER_MOMENT}"
            )

    # VERIFICATION: Correct ordering
    prev_first_play = -1
    for idx, moment in enumerate(moments):
        first_play = moment["play_ids"][0]
        if first_play <= prev_first_play:
            raise ValueError(
                f"Moment ordering violation at index {idx}: "
                f"first_play {first_play} <= previous {prev_first_play}"
            )
        prev_first_play = first_play

    # Note: Cross-period moments are prevented by period boundary being a HARD break
    # during moment generation, so no post-hoc verification is needed.

    return moments, metrics


def _finalize_moment(
    all_events: list[dict[str, Any]],
    moment_plays: list[dict[str, Any]],
    moment_start_idx: int,
) -> dict[str, Any]:
    """Finalize a moment with all required metadata.

    Args:
        all_events: All PBP events (for score_before lookup)
        moment_plays: Plays in this moment
        moment_start_idx: Index of first play in all_events

    Returns:
        Moment dict matching required output shape
    """
    first_play = moment_plays[0]
    last_play = moment_plays[-1]

    # Extract play_ids in order
    play_ids = [p["play_index"] for p in moment_plays]

    # Select plays that must be explicitly narrated
    explicitly_narrated_play_ids = _select_explicitly_narrated_plays(
        moment_plays, all_events, moment_start_idx
    )

    # Period from first play
    period = first_play.get("quarter") or 1

    # Clock values (may be null)
    start_clock = first_play.get("game_clock")
    end_clock = last_play.get("game_clock")

    # Score states
    score_before = list(_get_score_before_moment(all_events, moment_start_idx))
    score_after = list(_get_score_after_moment(last_play))

    return {
        "play_ids": play_ids,
        "explicitly_narrated_play_ids": explicitly_narrated_play_ids,
        "period": period,
        "start_clock": start_clock,
        "end_clock": end_clock,
        "score_before": score_before,
        "score_after": score_after,
    }


async def execute_generate_moments(stage_input: StageInput) -> StageOutput:
    """Execute the GENERATE_MOMENTS stage.

    Reads normalized PBP from previous stage output and segments
    plays into condensed moments using soft-capped compression rules.

    NO NARRATIVE TEXT IS GENERATED.
    NO LLM/OPENAI CALLS ARE MADE.

    Task 1.1: Soft-Capped Moment Compression
    - Target: ~80% of moments ≤ 8 plays
    - Target: ~80% of moments with ≤ 1 explicit play
    - Target: ~25-40% reduction in moment count

    Args:
        stage_input: Input containing previous_output with pbp_events

    Returns:
        StageOutput with moments list and compression metrics

    Raises:
        ValueError: If input is invalid or guarantees are violated
    """
    output = StageOutput(data={})
    game_id = stage_input.game_id

    output.add_log(f"Starting GENERATE_MOMENTS for game {game_id}")

    # Get normalized PBP from previous stage output
    previous_output = stage_input.previous_output
    if not previous_output:
        raise ValueError("GENERATE_MOMENTS requires previous stage output")

    pbp_events = previous_output.get("pbp_events")
    if not pbp_events:
        raise ValueError("No pbp_events in previous stage output")

    output.add_log(f"Processing {len(pbp_events)} PBP events")

    # Verify events are ordered by play_index
    prev_index = -1
    for i, event in enumerate(pbp_events):
        play_index = event.get("play_index")
        if play_index is None:
            raise ValueError(f"Event at position {i} missing play_index")
        if play_index <= prev_index:
            raise ValueError(
                f"Events not ordered by play_index at position {i}: "
                f"{play_index} <= {prev_index}"
            )
        prev_index = play_index

    output.add_log("Verified play_index ordering")

    # Segment plays into moments with soft-capped compression
    moments, metrics = _segment_plays_into_moments(pbp_events)

    output.add_log(f"Segmented into {len(moments)} moments")

    # Log compression metrics (Task 1.1 instrumentation)
    output.add_log(
        f"Compression metrics: "
        f"{metrics.pct_moments_under_soft_cap:.1f}% ≤ {SOFT_CAP_PLAYS} plays, "
        f"{metrics.pct_moments_single_explicit:.1f}% with ≤ 1 explicit play"
    )
    output.add_log(
        f"Moment sizes: median={metrics.median_plays_per_moment:.1f}, "
        f"max={metrics.max_plays_observed}"
    )

    # Log moment size distribution for reviewability
    sizes = [len(m["play_ids"]) for m in moments]
    if sizes:
        avg_size = sum(sizes) / len(sizes)
        min_size = min(sizes)
        max_size = max(sizes)
        output.add_log(
            f"Moment sizes: min={min_size}, max={max_size}, avg={avg_size:.1f}"
        )

    # Count scoring moments for verification
    scoring_moments = sum(
        1 for m in moments if m["score_before"] != m["score_after"]
    )
    output.add_log(f"Scoring moments: {scoring_moments}")

    # Log explicitly narrated play statistics
    narrated_counts = [len(m["explicitly_narrated_play_ids"]) for m in moments]
    total_narrated = sum(narrated_counts)
    total_plays = sum(sizes)
    narration_pct = (total_narrated / total_plays * 100) if total_plays > 0 else 0
    output.add_log(
        f"Narrated plays: {total_narrated}/{total_plays} ({narration_pct:.1f}%)"
    )
    if narrated_counts:
        output.add_log(
            f"Narrated per moment: min={min(narrated_counts)}, max={max(narrated_counts)}, "
            f"avg={sum(narrated_counts)/len(narrated_counts):.1f}"
        )

    # Log boundary reason distribution (Task 1.1 instrumentation)
    if metrics.boundary_reasons:
        reason_summary = ", ".join(
            f"{k}={v}" for k, v in sorted(metrics.boundary_reasons.items())
        )
        output.add_log(f"Boundary reasons: {reason_summary}")

    # Warn if distribution targets are not met
    if metrics.pct_moments_under_soft_cap < 80:
        output.add_log(
            f"WARNING: Only {metrics.pct_moments_under_soft_cap:.1f}% of moments "
            f"have ≤ {SOFT_CAP_PLAYS} plays (target: 80%)",
            level="warning",
        )
    if metrics.pct_moments_single_explicit < 80:
        output.add_log(
            f"WARNING: Only {metrics.pct_moments_single_explicit:.1f}% of moments "
            f"have ≤ 1 explicit play (target: 80%)",
            level="warning",
        )

    # Output includes moments and compression metrics for monitoring
    output.data = {
        "moments": moments,
        # Task 1.1: Compression metrics for monitoring and validation
        "compression_metrics": metrics.to_dict(),
    }

    output.add_log("GENERATE_MOMENTS completed successfully")

    return output
