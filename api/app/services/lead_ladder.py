"""
Lead Ladder: Game state tracking based on lead thresholds.

This module provides utilities for tracking game control based on the
Lead Ladder concept - a Fibonacci-inspired set of thresholds that define
meaningful separation levels between teams.

The Lead Ladder is used to:
1. Detect when game control changes (tier crossings)
2. Identify narrative boundaries for Moments
3. Track the story of how leads are built, cut, or flipped

IMPORTANT:
- This module contains PURE FUNCTIONS only (no database access)
- Thresholds must be provided by the caller (from compact_mode_thresholds.py)
- No hardcoded sport-specific values

Lead Ladder values are configured per sport:
- NBA / NCAAB: [3, 6, 10, 16] points
- NFL / NCAAF: [1, 2, 3, 5] possessions
- MLB: [1, 2, 3, 5] runs
- NHL: [1, 2, 3] goals
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from .compact_mode_thresholds import get_lead_tier


# =============================================================================
# ENUMS
# =============================================================================


class Leader(str, Enum):
    """Which team is currently leading."""
    HOME = "home"
    AWAY = "away"
    TIED = "tied"


class TierCrossingType(str, Enum):
    """
    Type of tier crossing that occurred.

    These are the primary signals for creating Moment boundaries.
    """
    TIER_UP = "tier_up"          # Lead increased to higher tier
    TIER_DOWN = "tier_down"      # Lead decreased to lower tier (cut)
    FLIP = "flip"                # Leader changed (always significant)
    TIE_REACHED = "tie_reached"  # Game returned to even
    TIE_BROKEN = "tie_broken"    # Tie was broken (someone took lead)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class LeadState:
    """
    Immutable snapshot of the current lead state.

    This captures everything needed to understand game control at a point in time.
    """
    home_score: int
    away_score: int
    margin: int           # Absolute difference (always >= 0)
    leader: Leader        # Who is ahead (or TIED)
    tier: int             # Current tier level (0 = small, higher = more decisive)
    tier_label: str       # Human-readable tier label

    @property
    def is_tied(self) -> bool:
        return self.leader == Leader.TIED

    @property
    def home_leading(self) -> bool:
        return self.leader == Leader.HOME

    @property
    def away_leading(self) -> bool:
        return self.leader == Leader.AWAY


@dataclass(frozen=True)
class TierCrossing:
    """
    Represents a tier crossing event (a potential Moment boundary).

    A tier crossing occurs when:
    - Lead tier increases (team extending control)
    - Lead tier decreases (opponent cutting into lead)
    - Leader changes (flip)
    - Tie is reached or broken
    """
    crossing_type: TierCrossingType
    prev_state: LeadState
    curr_state: LeadState

    @property
    def tier_delta(self) -> int:
        """Change in tier level (positive = tier up, negative = tier down)."""
        return self.curr_state.tier - self.prev_state.tier

    @property
    def is_significant(self) -> bool:
        """
        Whether this crossing is significant enough to create a Moment boundary.

        All crossings are potentially significant, but some are more so:
        - Flips are always significant
        - Large tier changes (2+) are more significant
        - Reaching/breaking tie is significant
        """
        if self.crossing_type in (
            TierCrossingType.FLIP,
            TierCrossingType.TIE_REACHED,
            TierCrossingType.TIE_BROKEN,
        ):
            return True
        return abs(self.tier_delta) >= 1


# =============================================================================
# PURE FUNCTIONS
# =============================================================================


def compute_lead_state(
    home_score: int,
    away_score: int,
    thresholds: Sequence[int],
) -> LeadState:
    """
    Compute the current lead state from scores and thresholds.

    This is a PURE FUNCTION - no side effects, no database access.

    Args:
        home_score: Home team's current score
        away_score: Away team's current score
        thresholds: Lead ladder thresholds for this sport, e.g. [3, 6, 10, 16]

    Returns:
        LeadState snapshot

    Example:
        >>> state = compute_lead_state(45, 38, [3, 6, 10, 16])
        >>> state.margin
        7
        >>> state.leader
        <Leader.HOME: 'home'>
        >>> state.tier
        2  # 7 >= 6 but < 10
    """
    margin = abs(home_score - away_score)

    if home_score > away_score:
        leader = Leader.HOME
    elif away_score > home_score:
        leader = Leader.AWAY
    else:
        leader = Leader.TIED

    tier = get_lead_tier(margin, thresholds)
    max_tier = len(thresholds)

    # Compute tier label
    if leader == Leader.TIED:
        tier_label = "tied"
    elif tier == 0:
        tier_label = "small"
    elif max_tier <= 1:
        tier_label = "meaningful"
    else:
        ratio = tier / max_tier
        if ratio <= 0.25:
            tier_label = "meaningful"
        elif ratio <= 0.5:
            tier_label = "comfortable"
        elif ratio <= 0.75:
            tier_label = "large"
        else:
            tier_label = "decisive"

    return LeadState(
        home_score=home_score,
        away_score=away_score,
        margin=margin,
        leader=leader,
        tier=tier,
        tier_label=tier_label,
    )


def detect_tier_crossing(
    prev_state: LeadState,
    curr_state: LeadState,
) -> TierCrossing | None:
    """
    Detect if a tier crossing occurred between two states.

    A tier crossing is a potential Moment boundary. This function
    identifies what type of crossing occurred (if any).

    This is a PURE FUNCTION - no side effects, no database access.

    Args:
        prev_state: LeadState before the play
        curr_state: LeadState after the play

    Returns:
        TierCrossing if a crossing occurred, None otherwise

    Example:
        >>> prev = compute_lead_state(40, 38, [3, 6, 10, 16])  # tier 0
        >>> curr = compute_lead_state(45, 38, [3, 6, 10, 16])  # tier 2
        >>> crossing = detect_tier_crossing(prev, curr)
        >>> crossing.crossing_type
        <TierCrossingType.TIER_UP: 'tier_up'>
    """
    # Check for leader change (FLIP)
    if prev_state.leader != curr_state.leader:
        # Tie reached
        if curr_state.leader == Leader.TIED:
            return TierCrossing(
                crossing_type=TierCrossingType.TIE_REACHED,
                prev_state=prev_state,
                curr_state=curr_state,
            )
        # Tie broken
        if prev_state.leader == Leader.TIED:
            return TierCrossing(
                crossing_type=TierCrossingType.TIE_BROKEN,
                prev_state=prev_state,
                curr_state=curr_state,
            )
        # Lead flip (leader changed from one team to the other)
        return TierCrossing(
            crossing_type=TierCrossingType.FLIP,
            prev_state=prev_state,
            curr_state=curr_state,
        )

    # No leader change - check for tier change
    tier_delta = curr_state.tier - prev_state.tier

    if tier_delta > 0:
        # Tier increased (lead built up)
        return TierCrossing(
            crossing_type=TierCrossingType.TIER_UP,
            prev_state=prev_state,
            curr_state=curr_state,
        )

    if tier_delta < 0:
        # Tier decreased (lead cut)
        return TierCrossing(
            crossing_type=TierCrossingType.TIER_DOWN,
            prev_state=prev_state,
            curr_state=curr_state,
        )

    # No crossing - tier and leader unchanged
    return None


def track_lead_states(
    score_sequence: Sequence[tuple[int, int]],
    thresholds: Sequence[int],
) -> list[LeadState]:
    """
    Track lead states through a sequence of scores.

    Useful for analyzing a game's lead progression.

    Args:
        score_sequence: List of (home_score, away_score) tuples
        thresholds: Lead ladder thresholds

    Returns:
        List of LeadState objects, one per score tuple

    Example:
        >>> scores = [(0, 0), (2, 0), (2, 3), (5, 3), (5, 6)]
        >>> states = track_lead_states(scores, [3, 6, 10, 16])
        >>> [s.leader.value for s in states]
        ['tied', 'home', 'away', 'home', 'away']
    """
    return [compute_lead_state(home, away, thresholds) for home, away in score_sequence]


def find_all_tier_crossings(
    score_sequence: Sequence[tuple[int, int]],
    thresholds: Sequence[int],
) -> list[tuple[int, TierCrossing]]:
    """
    Find all tier crossings in a sequence of scores.

    Args:
        score_sequence: List of (home_score, away_score) tuples
        thresholds: Lead ladder thresholds

    Returns:
        List of (index, TierCrossing) tuples for each crossing found

    Example:
        >>> scores = [(0, 0), (3, 0), (3, 3), (6, 3)]
        >>> crossings = find_all_tier_crossings(scores, [3, 6, 10, 16])
        >>> len(crossings)
        3  # tier_up at index 1, tie_reached at 2, tier_up at 3
    """
    if len(score_sequence) < 2:
        return []

    crossings: list[tuple[int, TierCrossing]] = []
    states = track_lead_states(score_sequence, thresholds)

    for i in range(1, len(states)):
        crossing = detect_tier_crossing(states[i - 1], states[i])
        if crossing is not None:
            crossings.append((i, crossing))

    return crossings
