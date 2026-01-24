"""
Game Quality Scoring: Deterministic qualitative score for story length targeting.

PURPOSE:
Game quality score is used ONLY to determine target story length.
It does NOT influence structure, beats, stats, or headers.

OUTPUT:
- game_quality_score ∈ { LOW, MEDIUM, HIGH }

DESIGN PRINCIPLES:
- Deterministic: Same input → same quality every run
- Conservative: When uncertain, bias MEDIUM
- Explainable: Easy to explain each signal's contribution
- No tuning, no ML, no learned weights, no narrative inference

CODEBASE REVIEW (documented):
- No overlapping quality scoring systems exist
- QualityStatus in pipeline/models.py is for data validation, unrelated
- importance_score and lead_change_count are in DISALLOWED_SIGNALS
- This module is the ONLY quality scoring path for story length

ISSUE: Game Quality Scoring (Chapters-First Architecture)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .beat_classifier import BeatType
from .story_section import StorySection


# ============================================================================
# QUALITY ENUM (LOCKED)
# ============================================================================


class GameQuality(str, Enum):
    """Game quality bucket for story length targeting.

    LOW = shorter story target
    MEDIUM = standard story target
    HIGH = longer story target
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# ============================================================================
# QUALITY SIGNALS (AUTHORITATIVE)
# ============================================================================


@dataclass
class QualitySignals:
    """Individual signal contributions to quality score.

    Each signal maps to a locked point value.
    This structure enables debug output and explainability.
    """

    # Signal: Lead changes (count each time leading team switches)
    # Points: +1 per lead change
    lead_changes: int = 0
    lead_changes_points: float = 0.0

    # Signal: Crunch presence (any section has beat_type == CRUNCH_SETUP)
    # Points: +2 if present
    has_crunch: bool = False
    crunch_points: float = 0.0

    # Signal: Overtime presence (any section has beat_type == OVERTIME)
    # Points: +3 if present
    has_overtime: bool = False
    overtime_points: float = 0.0

    # Signal: Final margin (abs(final_score_difference))
    # Points: +2 if margin <= 5, +1 if margin <= 12, +0 otherwise
    final_margin: int = 0
    margin_points: float = 0.0

    # Signal: Run/Response count (sections with RUN or RESPONSE beat_type)
    # Points: +0.5 per section
    run_response_count: int = 0
    run_response_points: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "lead_changes": self.lead_changes,
            "lead_changes_points": self.lead_changes_points,
            "has_crunch": self.has_crunch,
            "crunch_points": self.crunch_points,
            "has_overtime": self.has_overtime,
            "overtime_points": self.overtime_points,
            "final_margin": self.final_margin,
            "margin_points": self.margin_points,
            "run_response_count": self.run_response_count,
            "run_response_points": self.run_response_points,
        }


@dataclass
class QualityScoreResult:
    """Result of game quality scoring.

    Contains:
    - The final quality bucket (LOW/MEDIUM/HIGH)
    - The numeric score used to determine bucket
    - The individual signal contributions
    """

    quality: GameQuality
    numeric_score: float
    signals: QualitySignals

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging and logging."""
        return {
            "quality": self.quality.value,
            "numeric_score": self.numeric_score,
            "signals": self.signals.to_dict(),
        }


# ============================================================================
# POINT ASSIGNMENT (LOCKED - NO TUNING)
# ============================================================================

# Lead change points: +1 per change
POINTS_PER_LEAD_CHANGE = 1.0

# Crunch presence: +2 if any section has CRUNCH_SETUP
POINTS_CRUNCH_PRESENT = 2.0

# Overtime presence: +3 if any section has OVERTIME
POINTS_OVERTIME_PRESENT = 3.0

# Final margin thresholds and points
MARGIN_THRESHOLD_CLOSE = 5  # <= 5 points = very close game
MARGIN_THRESHOLD_COMPETITIVE = 12  # <= 12 points = competitive game
POINTS_MARGIN_CLOSE = 2.0  # +2 for margin <= 5
POINTS_MARGIN_COMPETITIVE = 1.0  # +1 for margin <= 12 (but > 5)

# Run/Response points: +0.5 per section
POINTS_PER_RUN_RESPONSE = 0.5


# ============================================================================
# QUALITY BUCKETS (LOCKED - NO TUNING)
# ============================================================================

# Bucket thresholds (score falls on boundary = round DOWN)
BUCKET_MEDIUM_THRESHOLD = 3.0  # score >= 3 = MEDIUM
BUCKET_HIGH_THRESHOLD = 6.0  # score >= 6 = HIGH


# ============================================================================
# LEAD CHANGE COUNTER
# ============================================================================


def count_lead_changes(score_history: list[dict[str, int]]) -> int:
    """Count the number of lead changes in a game.

    A lead change occurs when the leading team switches.
    Ties do not count as lead changes.

    Args:
        score_history: List of score snapshots with "home" and "away" keys.
                       Must be in chronological order.
                       Example: [{"home": 0, "away": 0}, {"home": 2, "away": 0}, ...]

    Returns:
        Number of lead changes (int >= 0)
    """
    if not score_history:
        return 0

    lead_changes = 0
    current_leader: str | None = None  # "home", "away", or None (tied)

    for score in score_history:
        home = score.get("home", 0) or 0
        away = score.get("away", 0) or 0

        # Determine current leader
        if home > away:
            new_leader = "home"
        elif away > home:
            new_leader = "away"
        else:
            new_leader = None  # Tied

        # Count lead change only when leader SWITCHES (not from/to tie)
        # A lead change requires going from one team leading to the other
        if (
            current_leader is not None
            and new_leader is not None
            and current_leader != new_leader
        ):
            lead_changes += 1

        # Update current leader (even if tied)
        if new_leader is not None:
            current_leader = new_leader

    return lead_changes


# ============================================================================
# SIGNAL EXTRACTION FROM SECTIONS
# ============================================================================


def _has_beat_type(sections: list[StorySection], beat_type: BeatType) -> bool:
    """Check if any section has the given beat type."""
    return any(section.beat_type == beat_type for section in sections)


def _count_beat_types(sections: list[StorySection], beat_types: set[BeatType]) -> int:
    """Count sections with any of the given beat types."""
    return sum(1 for section in sections if section.beat_type in beat_types)


# ============================================================================
# QUALITY SCORE COMPUTATION
# ============================================================================


def compute_quality_score(
    sections: list[StorySection],
    final_home_score: int,
    final_away_score: int,
    score_history: list[dict[str, int]] | None = None,
) -> QualityScoreResult:
    """Compute game quality score for story length targeting.

    This is the ONLY quality scoring path. Uses ONLY these signals:
    - Lead changes (from score_history)
    - Crunch presence (from sections)
    - Overtime presence (from sections)
    - Final margin (from final scores)
    - Run/Response count (from sections)

    Args:
        sections: List of StorySections with beat_type labels
        final_home_score: Final home team score
        final_away_score: Final away team score
        score_history: Optional list of score snapshots for lead change counting.
                       If None, lead changes will be 0.

    Returns:
        QualityScoreResult with quality bucket, numeric score, and signal breakdown
    """
    signals = QualitySignals()

    # -------------------------------------------------------------------------
    # Signal 1: Lead Changes
    # Points: +1 per lead change
    # -------------------------------------------------------------------------
    if score_history:
        signals.lead_changes = count_lead_changes(score_history)
    else:
        signals.lead_changes = 0
    signals.lead_changes_points = signals.lead_changes * POINTS_PER_LEAD_CHANGE

    # -------------------------------------------------------------------------
    # Signal 2: Crunch Presence
    # Points: +2 if any section has CRUNCH_SETUP
    # Reuses existing beat_type labels (no re-detection)
    # -------------------------------------------------------------------------
    signals.has_crunch = _has_beat_type(sections, BeatType.CRUNCH_SETUP)
    signals.crunch_points = POINTS_CRUNCH_PRESENT if signals.has_crunch else 0.0

    # -------------------------------------------------------------------------
    # Signal 3: Overtime Presence
    # Points: +3 if any section has OVERTIME
    # Reuses existing beat_type labels (no re-detection)
    # -------------------------------------------------------------------------
    signals.has_overtime = _has_beat_type(sections, BeatType.OVERTIME)
    signals.overtime_points = POINTS_OVERTIME_PRESENT if signals.has_overtime else 0.0

    # -------------------------------------------------------------------------
    # Signal 4: Final Margin
    # Points: +2 if <= 5, +1 if <= 12 (but > 5), +0 otherwise
    # -------------------------------------------------------------------------
    signals.final_margin = abs(final_home_score - final_away_score)

    if signals.final_margin <= MARGIN_THRESHOLD_CLOSE:
        # Very close game: +2 points
        signals.margin_points = POINTS_MARGIN_CLOSE
    elif signals.final_margin <= MARGIN_THRESHOLD_COMPETITIVE:
        # Competitive game: +1 point
        signals.margin_points = POINTS_MARGIN_COMPETITIVE
    else:
        # Blowout: +0 points
        signals.margin_points = 0.0

    # -------------------------------------------------------------------------
    # Signal 5: Run/Response Count
    # Points: +0.5 per RUN or RESPONSE section
    # Reuses existing beat_type labels (no re-detection)
    # -------------------------------------------------------------------------
    run_response_beats = {BeatType.RUN, BeatType.RESPONSE}
    signals.run_response_count = _count_beat_types(sections, run_response_beats)
    signals.run_response_points = signals.run_response_count * POINTS_PER_RUN_RESPONSE

    # -------------------------------------------------------------------------
    # Sum all points
    # -------------------------------------------------------------------------
    numeric_score = (
        signals.lead_changes_points
        + signals.crunch_points
        + signals.overtime_points
        + signals.margin_points
        + signals.run_response_points
    )

    # -------------------------------------------------------------------------
    # Determine bucket (boundary = round DOWN)
    # LOW: score < 3
    # MEDIUM: 3 <= score < 6
    # HIGH: score >= 6
    # -------------------------------------------------------------------------
    if numeric_score >= BUCKET_HIGH_THRESHOLD:
        quality = GameQuality.HIGH
    elif numeric_score >= BUCKET_MEDIUM_THRESHOLD:
        quality = GameQuality.MEDIUM
    else:
        quality = GameQuality.LOW

    return QualityScoreResult(
        quality=quality,
        numeric_score=numeric_score,
        signals=signals,
    )


# ============================================================================
# DEBUG OUTPUT
# ============================================================================


def format_quality_debug(result: QualityScoreResult) -> str:
    """Format quality score result for debugging.

    Shows each signal contribution, final score, and bucket.

    Args:
        result: QualityScoreResult to format

    Returns:
        Human-readable debug string
    """
    signals = result.signals
    lines = [
        "Game Quality Score Breakdown:",
        "=" * 50,
        "",
        "Signal Contributions:",
        f"  Lead Changes:    {signals.lead_changes:3d}  × {POINTS_PER_LEAD_CHANGE} = {signals.lead_changes_points:5.1f}",
        f"  Crunch Present:  {'Yes' if signals.has_crunch else 'No':>3}  → {signals.crunch_points:5.1f}",
        f"  Overtime:        {'Yes' if signals.has_overtime else 'No':>3}  → {signals.overtime_points:5.1f}",
        f"  Final Margin:    {signals.final_margin:3d}  → {signals.margin_points:5.1f}",
        f"  Run/Response:    {signals.run_response_count:3d}  × {POINTS_PER_RUN_RESPONSE} = {signals.run_response_points:5.1f}",
        "",
        "-" * 50,
        f"  TOTAL SCORE:           {result.numeric_score:5.1f}",
        "",
        "Bucket Thresholds:",
        f"  LOW:    score < {BUCKET_MEDIUM_THRESHOLD}",
        f"  MEDIUM: {BUCKET_MEDIUM_THRESHOLD} <= score < {BUCKET_HIGH_THRESHOLD}",
        f"  HIGH:   score >= {BUCKET_HIGH_THRESHOLD}",
        "",
        f"FINAL QUALITY: {result.quality.value}",
        "=" * 50,
    ]

    return "\n".join(lines)
