"""
Beat Classifier: Deterministic beat type assignment for chapters.

This module assigns EXACTLY ONE beat_type to EACH chapter based on:
- score delta
- time remaining
- basic stat deltas

DESIGN PRINCIPLES:
- Deterministic: Same input → same beats every run
- Conservative: When in doubt, use BACK_AND_FORTH
- Explainable: Each rule is documented inline
- Stable: No ML, no tuning, no historical inference beyond previous chapter

This layer exists only to help form story structure later.
It does NOT generate narrative.

LOCKED BEAT TAXONOMY (NBA v1):
- FAST_START
- MISSED_SHOT_FEST
- BACK_AND_FORTH
- EARLY_CONTROL
- RUN
- RESPONSE
- STALL
- CRUNCH_SETUP
- CLOSING_SEQUENCE
- OVERTIME

No new beats. No renaming. No synonyms. No compound beats.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .types import Chapter
from .running_stats import SectionDelta


# ============================================================================
# LOCKED BEAT TAXONOMY (NBA v1)
# ============================================================================

class BeatType(str, Enum):
    """Locked beat types for NBA v1.

    These are the ONLY valid beat types. No additions, renaming, or synonyms.
    """

    FAST_START = "FAST_START"
    MISSED_SHOT_FEST = "MISSED_SHOT_FEST"
    BACK_AND_FORTH = "BACK_AND_FORTH"
    EARLY_CONTROL = "EARLY_CONTROL"
    RUN = "RUN"
    RESPONSE = "RESPONSE"
    STALL = "STALL"
    CRUNCH_SETUP = "CRUNCH_SETUP"
    CLOSING_SEQUENCE = "CLOSING_SEQUENCE"
    OVERTIME = "OVERTIME"


# ============================================================================
# CHAPTER CONTEXT (INPUT)
# ============================================================================

@dataclass
class ChapterContext:
    """Context needed for beat classification.

    All the information about a chapter needed to assign a beat type.
    This is computed from chapter data + running stats.
    """

    # Chapter identity
    chapter_id: str
    chapter_index: int                       # 0-indexed position in game

    # Time context
    period: int | None                       # 1-4 for regulation, 5+ for OT
    time_remaining_seconds: int | None       # Seconds remaining in period
    is_overtime: bool                        # True if period > 4

    # Score context
    home_score: int
    away_score: int
    score_margin: int                        # abs(home_score - away_score)

    # Section stats (from SectionDelta)
    home_points_scored: int
    away_points_scored: int
    total_points_scored: int

    # Possession/play metrics
    total_plays: int
    possessions_estimate: int

    # Shot/rebound metrics (for MISSED_SHOT_FEST detection)
    total_fg_made: int
    total_fg_attempts: int | None            # May not be available
    total_rebounds: int | None               # May not be available

    # Run detection (unanswered points)
    home_unanswered_max: int                 # Max consecutive home points
    away_unanswered_max: int                 # Max consecutive away points
    max_unanswered: int                      # Max of either team

    # Previous chapter info (for RESPONSE detection)
    previous_beat_type: BeatType | None
    previous_scoring_team: str | None        # "home" or "away"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        return {
            "chapter_id": self.chapter_id,
            "chapter_index": self.chapter_index,
            "period": self.period,
            "time_remaining_seconds": self.time_remaining_seconds,
            "is_overtime": self.is_overtime,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "score_margin": self.score_margin,
            "home_points_scored": self.home_points_scored,
            "away_points_scored": self.away_points_scored,
            "total_points_scored": self.total_points_scored,
            "total_plays": self.total_plays,
            "possessions_estimate": self.possessions_estimate,
            "total_fg_made": self.total_fg_made,
            "max_unanswered": self.max_unanswered,
            "previous_beat_type": self.previous_beat_type.value if self.previous_beat_type else None,
        }


# ============================================================================
# CLASSIFICATION RESULT (OUTPUT)
# ============================================================================

@dataclass
class BeatClassification:
    """Result of beat classification for a single chapter.

    Contains:
    - The assigned beat type
    - The rule that triggered assignment
    - Debug information
    """

    chapter_id: str
    beat_type: BeatType
    triggered_rule: str                      # Human-readable rule name
    debug_info: dict[str, Any]               # Context used for decision

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API/debugging."""
        return {
            "chapter_id": self.chapter_id,
            "beat_type": self.beat_type.value,
            "triggered_rule": self.triggered_rule,
            "debug_info": self.debug_info,
        }


# ============================================================================
# HELPER: TIME PARSING
# ============================================================================

def parse_game_clock_to_seconds(clock_str: str | None) -> int | None:
    """Parse game clock string to seconds remaining.

    Args:
        clock_str: Clock string like "12:00", "5:30", "0:45"

    Returns:
        Seconds remaining, or None if unparseable
    """
    if not clock_str:
        return None

    try:
        if ":" in clock_str:
            parts = clock_str.split(":")
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
    except (ValueError, IndexError):
        pass

    return None


# ============================================================================
# HELPER: UNANSWERED POINTS DETECTION
# ============================================================================

def compute_max_unanswered_points(plays: list[dict[str, Any]]) -> tuple[int, int]:
    """Compute maximum unanswered points for each team.

    Scans through plays looking for scoring runs by tracking score changes.

    Args:
        plays: List of play raw_data dicts

    Returns:
        Tuple of (home_max_unanswered, away_max_unanswered)
    """
    home_current = 0
    away_current = 0
    home_max = 0
    away_max = 0

    # Track previous scores to detect which team scored
    prev_home_score = 0
    prev_away_score = 0

    for play in plays:
        description = (play.get("description") or "").lower()

        # Skip non-scoring plays
        if "makes" not in description:
            continue

        # Get current scores
        home_score = play.get("home_score", 0) or 0
        away_score = play.get("away_score", 0) or 0

        # Calculate score changes
        home_delta = home_score - prev_home_score
        away_delta = away_score - prev_away_score

        # Determine which team scored based on score change
        if home_delta > 0 and away_delta == 0:
            # Home team scored
            away_current = 0  # Reset away run
            home_current += home_delta
            home_max = max(home_max, home_current)
        elif away_delta > 0 and home_delta == 0:
            # Away team scored
            home_current = 0  # Reset home run
            away_current += away_delta
            away_max = max(away_max, away_current)
        elif home_delta > 0 and away_delta > 0:
            # Both scores changed (unusual, but possible with corrections)
            # Reset both runs
            home_current = 0
            away_current = 0
        # If no change, skip

        # Update previous scores
        prev_home_score = home_score
        prev_away_score = away_score

    return home_max, away_max


# ============================================================================
# CONTEXT BUILDER
# ============================================================================

def build_chapter_context(
    chapter: Chapter,
    chapter_index: int,
    section_delta: SectionDelta | None,
    previous_result: BeatClassification | None,
    home_team_key: str | None = None,
    away_team_key: str | None = None,
) -> ChapterContext:
    """Build classification context from chapter and stats.

    Args:
        chapter: The chapter to classify
        chapter_index: 0-indexed position in game
        section_delta: Stats for this chapter (from running_stats)
        previous_result: Classification result of previous chapter
        home_team_key: Home team key for team identification
        away_team_key: Away team key for team identification

    Returns:
        ChapterContext ready for classification
    """
    # Extract period from chapter or plays
    period = chapter.period
    if period is None and chapter.plays:
        period = chapter.plays[0].raw_data.get("quarter")

    # Determine if overtime
    is_overtime = period is not None and period > 4

    # Extract time remaining from last play
    time_remaining_seconds = None
    if chapter.plays:
        last_play = chapter.plays[-1]
        clock_str = last_play.raw_data.get("game_clock")
        time_remaining_seconds = parse_game_clock_to_seconds(clock_str)

    # Extract scores from last play
    home_score = 0
    away_score = 0
    if chapter.plays:
        last_play = chapter.plays[-1]
        home_score = last_play.raw_data.get("home_score", 0) or 0
        away_score = last_play.raw_data.get("away_score", 0) or 0

    score_margin = abs(home_score - away_score)

    # Extract stats from section delta
    home_points_scored = 0
    away_points_scored = 0
    possessions_estimate = 0
    total_fg_made = 0

    if section_delta:
        # Get team stats
        for team_key, team_delta in section_delta.teams.items():
            if team_key == home_team_key:
                home_points_scored = team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate
            elif team_key == away_team_key:
                away_points_scored = team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate
            else:
                # Unknown team - add to whichever has less
                if home_points_scored <= away_points_scored:
                    home_points_scored += team_delta.points_scored
                else:
                    away_points_scored += team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate

        # Get player FG stats
        for player_delta in section_delta.players.values():
            total_fg_made += player_delta.fg_made

    total_points_scored = home_points_scored + away_points_scored
    total_plays = len(chapter.plays)

    # Compute unanswered points
    play_data = [p.raw_data for p in chapter.plays]
    home_unanswered, away_unanswered = compute_max_unanswered_points(play_data)
    max_unanswered = max(home_unanswered, away_unanswered)

    # Previous chapter info
    previous_beat_type = previous_result.beat_type if previous_result else None

    # Determine previous scoring team (simplified)
    previous_scoring_team = None
    if previous_result and section_delta:
        # This would need more context; for now, leave as None
        pass

    return ChapterContext(
        chapter_id=chapter.chapter_id,
        chapter_index=chapter_index,
        period=period,
        time_remaining_seconds=time_remaining_seconds,
        is_overtime=is_overtime,
        home_score=home_score,
        away_score=away_score,
        score_margin=score_margin,
        home_points_scored=home_points_scored,
        away_points_scored=away_points_scored,
        total_points_scored=total_points_scored,
        total_plays=total_plays,
        possessions_estimate=possessions_estimate,
        total_fg_made=total_fg_made,
        total_fg_attempts=None,  # Not tracked yet
        total_rebounds=None,     # Not tracked yet
        home_unanswered_max=home_unanswered,
        away_unanswered_max=away_unanswered,
        max_unanswered=max_unanswered,
        previous_beat_type=previous_beat_type,
        previous_scoring_team=previous_scoring_team,
    )


# ============================================================================
# BEAT CLASSIFICATION RULES (PRIORITY ORDER)
# ============================================================================

def _check_overtime(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 1: OVERTIME (FORCED)

    If chapter occurs during overtime, beat_type = OVERTIME.
    No further evaluation.
    """
    if ctx.is_overtime:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.OVERTIME,
            triggered_rule="RULE_1_OVERTIME",
            debug_info={"period": ctx.period, "is_overtime": True},
        )
    return None


def _check_closing_sequence(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 2: CLOSING_SEQUENCE

    If time_remaining <= 2:00 in regulation (not overtime),
    beat_type = CLOSING_SEQUENCE.

    Do NOT check score margin. Late is late.
    """
    # Must be regulation (period 4 or less)
    if ctx.is_overtime:
        return None

    # Must be Q4
    if ctx.period != 4:
        return None

    # Must have time data
    if ctx.time_remaining_seconds is None:
        return None

    # <= 2 minutes (120 seconds)
    if ctx.time_remaining_seconds <= 120:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.CLOSING_SEQUENCE,
            triggered_rule="RULE_2_CLOSING_SEQUENCE",
            debug_info={
                "period": ctx.period,
                "time_remaining_seconds": ctx.time_remaining_seconds,
                "threshold": 120,
            },
        )
    return None


def _check_crunch_setup(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 3: CRUNCH_SETUP

    If time_remaining <= 5:00 AND > 2:00 AND abs(score_margin) <= 5,
    beat_type = CRUNCH_SETUP.

    This beat marks tightening games. Do NOT infer drama.
    """
    # Must be regulation Q4
    if ctx.is_overtime:
        return None

    if ctx.period != 4:
        return None

    if ctx.time_remaining_seconds is None:
        return None

    # Time window: > 2:00 (120s) AND <= 5:00 (300s)
    if ctx.time_remaining_seconds > 300 or ctx.time_remaining_seconds <= 120:
        return None

    # Score margin <= 5
    if ctx.score_margin > 5:
        return None

    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.CRUNCH_SETUP,
        triggered_rule="RULE_3_CRUNCH_SETUP",
        debug_info={
            "period": ctx.period,
            "time_remaining_seconds": ctx.time_remaining_seconds,
            "score_margin": ctx.score_margin,
        },
    )


def _check_run(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 4: RUN

    If within this chapter one team scores >= 8 unanswered points,
    beat_type = RUN.

    Ignore pace, shooting %, or time.
    This is purely a scoring swing detector.
    """
    RUN_THRESHOLD = 8

    if ctx.max_unanswered >= RUN_THRESHOLD:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.RUN,
            triggered_rule="RULE_4_RUN",
            debug_info={
                "max_unanswered": ctx.max_unanswered,
                "home_unanswered_max": ctx.home_unanswered_max,
                "away_unanswered_max": ctx.away_unanswered_max,
                "threshold": RUN_THRESHOLD,
            },
        )
    return None


def _check_response(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 5: RESPONSE

    If previous chapter beat_type == RUN AND scoring swings back toward
    the other team AND abs(score_margin) decreases,
    beat_type = RESPONSE.

    This must be a direct follow-up. Do NOT search further back.
    """
    # Previous must be RUN
    if ctx.previous_beat_type != BeatType.RUN:
        return None

    # Must have some scoring
    if ctx.total_points_scored == 0:
        return None

    # For a proper response check, we'd need to compare margins
    # between chapters. For now, simplified: if previous was RUN
    # and this chapter has the other team scoring more.

    # Simple heuristic: if the team that wasn't running is scoring more now
    if ctx.home_unanswered_max > 0 or ctx.away_unanswered_max > 0:
        # One team is building a response
        # A "response" means the OTHER team is now scoring
        # We don't have enough context to know which team was running
        # So we use a simpler check: both teams scored, or margin decreased
        if ctx.home_points_scored > 0 and ctx.away_points_scored > 0:
            return BeatClassification(
                chapter_id=ctx.chapter_id,
                beat_type=BeatType.RESPONSE,
                triggered_rule="RULE_5_RESPONSE",
                debug_info={
                    "previous_beat_type": ctx.previous_beat_type.value,
                    "home_points": ctx.home_points_scored,
                    "away_points": ctx.away_points_scored,
                },
            )

    return None


def _check_missed_shot_fest(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 6: MISSED_SHOT_FEST

    If high volume of missed shots AND rebounds dominate possessions
    AND points_scored is low relative to plays.

    Threshold: > 60% of plays are non-scoring (misses/rebounds).
    Simplified: low points per play.
    """
    # Need at least some plays
    if ctx.total_plays < 5:
        return None

    # Low scoring threshold: less than 0.5 points per play
    # A typical play might generate 1-2 points if it's a score
    points_per_play = ctx.total_points_scored / ctx.total_plays

    # Very low scoring: less than 0.4 points per play
    # (e.g., 4 points in 10 plays = 0.4 PPP)
    MISS_FEST_THRESHOLD = 0.4

    if points_per_play < MISS_FEST_THRESHOLD:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.MISSED_SHOT_FEST,
            triggered_rule="RULE_6_MISSED_SHOT_FEST",
            debug_info={
                "total_plays": ctx.total_plays,
                "total_points_scored": ctx.total_points_scored,
                "points_per_play": points_per_play,
                "threshold": MISS_FEST_THRESHOLD,
            },
        )
    return None


def _check_stall(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 7: STALL

    If low scoring, few possessions, AND no clear run, response, or miss fest.

    This is a neutral "nothing is happening" beat.
    Use sparingly, but deterministically.
    """
    # Already checked RUN, RESPONSE, MISSED_SHOT_FEST
    # STALL is for low-action chapters

    # Few plays (< 5) AND low scoring (< 4 points)
    if ctx.total_plays < 5 and ctx.total_points_scored < 4:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.STALL,
            triggered_rule="RULE_7_STALL",
            debug_info={
                "total_plays": ctx.total_plays,
                "total_points_scored": ctx.total_points_scored,
            },
        )

    # Low possessions estimate AND low scoring
    if ctx.possessions_estimate < 3 and ctx.total_points_scored < 4:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.STALL,
            triggered_rule="RULE_7_STALL",
            debug_info={
                "possessions_estimate": ctx.possessions_estimate,
                "total_points_scored": ctx.total_points_scored,
            },
        )

    return None


def _check_fast_start(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 8: FAST_START

    If chapter occurs in Q1 AND time_remaining > 8:00 AND pace is high.

    This only applies early. Do NOT reuse later.
    """
    # Must be Q1
    if ctx.period != 1:
        return None

    # Must be early in Q1 (> 8:00 = 480 seconds)
    if ctx.time_remaining_seconds is None:
        return None

    if ctx.time_remaining_seconds <= 480:
        return None

    # High pace: many plays or many points
    # Threshold: >= 6 plays or >= 6 points
    HIGH_PACE_PLAYS = 6
    HIGH_PACE_POINTS = 6

    if ctx.total_plays >= HIGH_PACE_PLAYS or ctx.total_points_scored >= HIGH_PACE_POINTS:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.FAST_START,
            triggered_rule="RULE_8_FAST_START",
            debug_info={
                "period": ctx.period,
                "time_remaining_seconds": ctx.time_remaining_seconds,
                "total_plays": ctx.total_plays,
                "total_points_scored": ctx.total_points_scored,
            },
        )
    return None


def _check_early_control(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 9: EARLY_CONTROL

    If one team builds a modest but steady lead AND no run threshold is met
    AND occurs outside crunch time.

    This describes gradual separation, not dominance.
    """
    # Must be outside crunch time
    if ctx.period == 4 and ctx.time_remaining_seconds is not None:
        if ctx.time_remaining_seconds <= 300:  # 5 minutes
            return None

    # Skip if overtime
    if ctx.is_overtime:
        return None

    # One team must have scored more (margin building)
    point_diff = abs(ctx.home_points_scored - ctx.away_points_scored)

    # Modest lead: 3-7 point difference in this chapter
    # AND a clear leader (not 50-50)
    if point_diff >= 3 and point_diff <= 7:
        # One team outscored the other meaningfully
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.EARLY_CONTROL,
            triggered_rule="RULE_9_EARLY_CONTROL",
            debug_info={
                "home_points_scored": ctx.home_points_scored,
                "away_points_scored": ctx.away_points_scored,
                "point_diff": point_diff,
                "score_margin": ctx.score_margin,
            },
        )
    return None


def _default_back_and_forth(ctx: ChapterContext) -> BeatClassification:
    """RULE 10: BACK_AND_FORTH (DEFAULT)

    If none of the above rules apply, beat_type = BACK_AND_FORTH.

    This is the safe fallback. If unsure, use this.
    """
    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.BACK_AND_FORTH,
        triggered_rule="RULE_10_DEFAULT_BACK_AND_FORTH",
        debug_info={"reason": "No other rule matched"},
    )


# ============================================================================
# MAIN CLASSIFICATION FUNCTION
# ============================================================================

def classify_chapter_beat(ctx: ChapterContext) -> BeatClassification:
    """Classify a single chapter's beat type.

    Applies rules in priority order (top wins):
    1. OVERTIME (forced)
    2. CLOSING_SEQUENCE
    3. CRUNCH_SETUP
    4. RUN
    5. RESPONSE
    6. MISSED_SHOT_FEST
    7. STALL
    8. FAST_START
    9. EARLY_CONTROL
    10. BACK_AND_FORTH (default)

    Args:
        ctx: ChapterContext with all classification inputs

    Returns:
        BeatClassification with exactly one beat_type
    """
    # Apply rules in priority order
    result = _check_overtime(ctx)
    if result:
        return result

    result = _check_closing_sequence(ctx)
    if result:
        return result

    result = _check_crunch_setup(ctx)
    if result:
        return result

    result = _check_run(ctx)
    if result:
        return result

    result = _check_response(ctx)
    if result:
        return result

    result = _check_missed_shot_fest(ctx)
    if result:
        return result

    result = _check_stall(ctx)
    if result:
        return result

    result = _check_fast_start(ctx)
    if result:
        return result

    result = _check_early_control(ctx)
    if result:
        return result

    # Default fallback
    return _default_back_and_forth(ctx)


# ============================================================================
# BATCH CLASSIFICATION
# ============================================================================

def classify_all_chapters(
    chapters: list[Chapter],
    section_deltas: list[SectionDelta] | None = None,
    home_team_key: str | None = None,
    away_team_key: str | None = None,
) -> list[BeatClassification]:
    """Classify beat types for all chapters in a game.

    Args:
        chapters: List of chapters in chronological order
        section_deltas: List of SectionDeltas (one per chapter)
        home_team_key: Home team key for identification
        away_team_key: Away team key for identification

    Returns:
        List of BeatClassification, one per chapter
    """
    results: list[BeatClassification] = []

    for i, chapter in enumerate(chapters):
        # Get corresponding section delta
        delta = section_deltas[i] if section_deltas and i < len(section_deltas) else None

        # Get previous result (for RESPONSE detection)
        previous_result = results[-1] if results else None

        # Build context
        ctx = build_chapter_context(
            chapter=chapter,
            chapter_index=i,
            section_delta=delta,
            previous_result=previous_result,
            home_team_key=home_team_key,
            away_team_key=away_team_key,
        )

        # Classify
        result = classify_chapter_beat(ctx)
        results.append(result)

    return results


# ============================================================================
# DEBUG OUTPUT
# ============================================================================

def format_classification_debug(results: list[BeatClassification]) -> str:
    """Format classification results for debug output.

    Args:
        results: List of BeatClassification

    Returns:
        Human-readable debug string
    """
    lines = ["Beat Classification Results:", "=" * 50]

    for result in results:
        lines.append(
            f"{result.chapter_id}: {result.beat_type.value} "
            f"(via {result.triggered_rule})"
        )

    return "\n".join(lines)


def get_beat_distribution(results: list[BeatClassification]) -> dict[str, int]:
    """Get distribution of beat types.

    Args:
        results: List of BeatClassification

    Returns:
        Dict of beat_type -> count
    """
    distribution: dict[str, int] = {}

    for result in results:
        beat = result.beat_type.value
        distribution[beat] = distribution.get(beat, 0) + 1

    return distribution
