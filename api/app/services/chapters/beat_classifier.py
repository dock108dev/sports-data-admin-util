"""
Beat Classifier: Deterministic beat type assignment for chapters.

This module assigns EXACTLY ONE beat_type to EACH chapter based on:
- score delta
- time remaining
- basic stat deltas

DESIGN PRINCIPLES:
- Deterministic: Same input -> same beats every run
- Conservative: When in doubt, use BACK_AND_FORTH
- Explainable: Each rule is documented inline
- Stable: No ML, no tuning, no historical inference beyond previous chapter

This layer exists only to help form story structure later.
It does NOT generate narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import Chapter
from .running_stats import SectionDelta

# Import from modular components
from .beat_types import (
    BeatType,
    BeatDescriptor,
    PRIMARY_BEATS,
    BEAT_PRIORITY,
    MISSED_SHOT_PPP_THRESHOLD,
    RUN_WINDOW_THRESHOLD,
    RUN_MARGIN_EXPANSION_THRESHOLD,
    BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD,
    BACK_AND_FORTH_TIES_THRESHOLD,
    EARLY_WINDOW_DURATION_SECONDS,
    FAST_START_MIN_COMBINED_POINTS,
    FAST_START_MAX_MARGIN,
    EARLY_CONTROL_MIN_LEAD,
    EARLY_CONTROL_MIN_SHARE_PCT,
    CRUNCH_SETUP_TIME_THRESHOLD,
    CRUNCH_SETUP_MARGIN_THRESHOLD,
    CLOSING_SEQUENCE_TIME_THRESHOLD,
    CLOSING_SEQUENCE_MARGIN_THRESHOLD,
)
from .run_windows import (
    RunWindow,
    detect_run_windows,
    get_qualifying_run_windows,
)
from .response_windows import (
    ResponseWindow,
    detect_response_windows,
    get_qualifying_response_windows,
)
from .back_and_forth_windows import (
    BackAndForthWindow,
    detect_back_and_forth_window,
    get_qualifying_back_and_forth_window,
)
from .early_windows import (
    EarlyWindowStats,
    SectionBeatOverride,
    compute_early_window_stats,
    detect_section_fast_start,
    detect_section_early_control,
    detect_opening_section_beat,
)


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
    chapter_index: int  # 0-indexed position in game

    # Time context
    period: int | None  # 1-4 for regulation, 5+ for OT
    time_remaining_seconds: int | None  # Seconds remaining in period
    is_overtime: bool  # True if period > 4

    # Score context
    home_score: int
    away_score: int
    score_margin: int  # abs(home_score - away_score)

    # Section stats (from SectionDelta)
    home_points_scored: int
    away_points_scored: int
    total_points_scored: int

    # Possession/play metrics
    total_plays: int
    possessions_estimate: int

    # Shot/rebound metrics (for descriptor detection)
    total_fg_made: int
    total_fg_attempts: int | None  # May not be available
    total_rebounds: int | None  # May not be available

    # Run window detection (Phase 2.2)
    qualifying_run_windows: list[RunWindow] = field(default_factory=list)
    has_qualifying_run: bool = False  # Convenience flag

    # Response window detection (Phase 2.3)
    qualifying_response_windows: list[ResponseWindow] = field(default_factory=list)
    has_qualifying_response: bool = False  # Convenience flag

    # Back-and-forth window detection (Phase 2.4)
    back_and_forth_window: BackAndForthWindow | None = None
    has_qualifying_back_and_forth: bool = False  # Convenience flag

    # Previous chapter info (for cross-chapter RESPONSE detection)
    previous_beat_type: BeatType | None = None
    previous_scoring_team: str | None = None  # "home" or "away"
    previous_run_windows: list[RunWindow] = field(default_factory=list)  # Phase 2.3

    def to_dict(self) -> dict[str, Any]:
        """Serialize for debugging."""
        result = {
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
            "has_qualifying_run": self.has_qualifying_run,
            "has_qualifying_response": self.has_qualifying_response,
            "has_qualifying_back_and_forth": self.has_qualifying_back_and_forth,
            "previous_beat_type": self.previous_beat_type.value
            if self.previous_beat_type
            else None,
        }
        if self.qualifying_run_windows:
            result["qualifying_run_windows"] = [
                w.to_dict() for w in self.qualifying_run_windows
            ]
        if self.qualifying_response_windows:
            result["qualifying_response_windows"] = [
                r.to_dict() for r in self.qualifying_response_windows
            ]
        if self.back_and_forth_window:
            result["back_and_forth_window"] = self.back_and_forth_window.to_dict()
        return result


# ============================================================================
# CLASSIFICATION RESULT (OUTPUT)
# ============================================================================


@dataclass
class BeatClassification:
    """Result of beat classification for a single chapter.

    Contains:
    - The assigned beat type (primary beat)
    - Descriptors (secondary context, may be empty)
    - The rule that triggered assignment
    - Debug information
    """

    chapter_id: str
    beat_type: BeatType
    triggered_rule: str  # Human-readable rule name
    debug_info: dict[str, Any]  # Context used for decision
    descriptors: set[BeatDescriptor] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API/debugging."""
        result = {
            "chapter_id": self.chapter_id,
            "beat_type": self.beat_type.value,
            "triggered_rule": self.triggered_rule,
            "debug_info": self.debug_info,
        }
        if self.descriptors:
            result["descriptors"] = [d.value for d in self.descriptors]
        return result


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
# CONTEXT BUILDER
# ============================================================================


def build_chapter_context(
    chapter: Chapter,
    chapter_index: int,
    section_delta: SectionDelta | None,
    previous_result: BeatClassification | None,
    home_team_key: str | None = None,
    away_team_key: str | None = None,
    previous_context: ChapterContext | None = None,
) -> ChapterContext:
    """Build classification context from chapter and stats.

    Args:
        chapter: The chapter to classify
        chapter_index: 0-indexed position in game
        section_delta: Stats for this chapter (from running_stats)
        previous_result: Classification result of previous chapter
        home_team_key: Home team key for team identification
        away_team_key: Away team key for team identification
        previous_context: Previous chapter's context (for cross-chapter RESPONSE)

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
        for team_key, team_delta in section_delta.teams.items():
            if team_key == home_team_key:
                home_points_scored = team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate
            elif team_key == away_team_key:
                away_points_scored = team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate
            else:
                if home_points_scored <= away_points_scored:
                    home_points_scored += team_delta.points_scored
                else:
                    away_points_scored += team_delta.points_scored
                possessions_estimate += team_delta.possessions_estimate

        for player_delta in section_delta.players.values():
            total_fg_made += player_delta.fg_made

    total_points_scored = home_points_scored + away_points_scored
    total_plays = len(chapter.plays)

    # Extract play data for window detection
    play_data = [p.raw_data for p in chapter.plays]

    # Compute qualifying run windows (Phase 2.2)
    qualifying_runs = get_qualifying_run_windows(play_data)
    has_qualifying_run = len(qualifying_runs) > 0

    # Compute qualifying response windows (Phase 2.3)
    qualifying_responses = get_qualifying_response_windows(play_data, qualifying_runs)
    has_qualifying_response = len(qualifying_responses) > 0

    # Compute back-and-forth window (Phase 2.4)
    back_and_forth_window = get_qualifying_back_and_forth_window(play_data)
    has_qualifying_back_and_forth = back_and_forth_window is not None

    # Previous chapter info
    previous_beat_type = previous_result.beat_type if previous_result else None
    previous_run_windows: list[RunWindow] = []

    if previous_context is not None:
        previous_run_windows = previous_context.qualifying_run_windows

    previous_scoring_team = None

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
        total_fg_attempts=None,
        total_rebounds=None,
        qualifying_run_windows=qualifying_runs,
        has_qualifying_run=has_qualifying_run,
        qualifying_response_windows=qualifying_responses,
        has_qualifying_response=has_qualifying_response,
        back_and_forth_window=back_and_forth_window,
        has_qualifying_back_and_forth=has_qualifying_back_and_forth,
        previous_beat_type=previous_beat_type,
        previous_scoring_team=previous_scoring_team,
        previous_run_windows=previous_run_windows,
    )


# ============================================================================
# BEAT CLASSIFICATION RULES (PRIORITY ORDER)
# ============================================================================


def _check_overtime(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 1: OVERTIME (FORCED)"""
    if ctx.is_overtime:
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.OVERTIME,
            triggered_rule="RULE_1_OVERTIME",
            debug_info={"period": ctx.period, "is_overtime": True},
        )
    return None


def _check_closing_sequence(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 2: CLOSING_SEQUENCE (Phase 2.6)"""
    if ctx.is_overtime:
        return None
    if ctx.period != 4:
        return None
    if ctx.time_remaining_seconds is None:
        return None
    if ctx.time_remaining_seconds > CLOSING_SEQUENCE_TIME_THRESHOLD:
        return None
    if ctx.score_margin > CLOSING_SEQUENCE_MARGIN_THRESHOLD:
        return None

    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.CLOSING_SEQUENCE,
        triggered_rule="RULE_2_CLOSING_SEQUENCE",
        debug_info={
            "period": ctx.period,
            "time_remaining_seconds": ctx.time_remaining_seconds,
            "time_threshold": CLOSING_SEQUENCE_TIME_THRESHOLD,
            "score_margin": ctx.score_margin,
            "margin_threshold": CLOSING_SEQUENCE_MARGIN_THRESHOLD,
        },
    )


def _check_crunch_setup(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 3: CRUNCH_SETUP (Phase 2.6)"""
    if ctx.is_overtime:
        return None
    if ctx.period != 4:
        return None
    if ctx.time_remaining_seconds is None:
        return None
    if ctx.time_remaining_seconds > CRUNCH_SETUP_TIME_THRESHOLD:
        return None
    if ctx.score_margin > CRUNCH_SETUP_MARGIN_THRESHOLD:
        return None

    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.CRUNCH_SETUP,
        triggered_rule="RULE_3_CRUNCH_SETUP",
        debug_info={
            "period": ctx.period,
            "time_remaining_seconds": ctx.time_remaining_seconds,
            "time_threshold": CRUNCH_SETUP_TIME_THRESHOLD,
            "score_margin": ctx.score_margin,
            "margin_threshold": CRUNCH_SETUP_MARGIN_THRESHOLD,
        },
    )


def _check_run(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 4: RUN (Phase 2.2 - Run Window Detection)"""
    if ctx.has_qualifying_run:
        best_run = max(ctx.qualifying_run_windows, key=lambda r: r.points_scored)
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.RUN,
            triggered_rule="RULE_4_RUN",
            debug_info={
                "qualifying_run_count": len(ctx.qualifying_run_windows),
                "best_run_team": best_run.team,
                "best_run_points": best_run.points_scored,
                "best_run_caused_lead_change": best_run.caused_lead_change,
                "best_run_margin_expansion": best_run.margin_expansion,
                "run_window_threshold": RUN_WINDOW_THRESHOLD,
                "margin_expansion_threshold": RUN_MARGIN_EXPANSION_THRESHOLD,
            },
        )
    return None


def _check_response(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 5: RESPONSE (Phase 2.3 - Response Window Detection)"""
    # Check 1: Intra-chapter response
    if ctx.has_qualifying_response:
        best_response = max(
            ctx.qualifying_response_windows,
            key=lambda r: r.responding_team_points - r.run_team_points,
        )
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.RESPONSE,
            triggered_rule="RULE_5_RESPONSE_INTRA_CHAPTER",
            debug_info={
                "response_type": "intra_chapter",
                "responding_team": best_response.responding_team,
                "responding_team_points": best_response.responding_team_points,
                "run_team_points": best_response.run_team_points,
                "point_differential": best_response.responding_team_points
                - best_response.run_team_points,
            },
        )

    # Check 2: Cross-chapter response
    if ctx.previous_beat_type == BeatType.RUN and ctx.previous_run_windows:
        last_run = ctx.previous_run_windows[-1]
        responding_team = "away" if last_run.team == "home" else "home"

        if responding_team == "home":
            responding_points = ctx.home_points_scored
            run_team_points = ctx.away_points_scored
        else:
            responding_points = ctx.away_points_scored
            run_team_points = ctx.home_points_scored

        if responding_points > run_team_points:
            return BeatClassification(
                chapter_id=ctx.chapter_id,
                beat_type=BeatType.RESPONSE,
                triggered_rule="RULE_5_RESPONSE_CROSS_CHAPTER",
                debug_info={
                    "response_type": "cross_chapter",
                    "previous_beat_type": ctx.previous_beat_type.value,
                    "responding_team": responding_team,
                    "responding_team_points": responding_points,
                    "run_team_points": run_team_points,
                    "point_differential": responding_points - run_team_points,
                },
            )

    return None


def _check_stall(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 7: STALL"""
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


def _check_back_and_forth(ctx: ChapterContext) -> BeatClassification | None:
    """RULE 10: BACK_AND_FORTH (Phase 2.4 - Window Detection)"""
    if ctx.has_qualifying_back_and_forth and ctx.back_and_forth_window:
        window = ctx.back_and_forth_window
        return BeatClassification(
            chapter_id=ctx.chapter_id,
            beat_type=BeatType.BACK_AND_FORTH,
            triggered_rule="RULE_10_BACK_AND_FORTH",
            debug_info={
                "lead_change_count": window.lead_change_count,
                "tie_count": window.tie_count,
                "lead_changes_threshold": BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD,
                "ties_threshold": BACK_AND_FORTH_TIES_THRESHOLD,
                "start_score": f"{window.start_home_score}-{window.start_away_score}",
                "end_score": f"{window.end_home_score}-{window.end_away_score}",
            },
        )
    return None


def _default_back_and_forth(ctx: ChapterContext) -> BeatClassification:
    """RULE 11: BACK_AND_FORTH (DEFAULT)"""
    return BeatClassification(
        chapter_id=ctx.chapter_id,
        beat_type=BeatType.BACK_AND_FORTH,
        triggered_rule="RULE_11_DEFAULT_BACK_AND_FORTH",
        debug_info={"reason": "No other rule matched"},
    )


# ============================================================================
# MAIN CLASSIFICATION FUNCTION
# ============================================================================


def _compute_descriptors(ctx: ChapterContext) -> set[BeatDescriptor]:
    """Compute descriptors for a chapter."""
    descriptors: set[BeatDescriptor] = set()

    if ctx.total_plays >= 5:
        points_per_play = ctx.total_points_scored / ctx.total_plays
        if points_per_play < MISSED_SHOT_PPP_THRESHOLD:
            descriptors.add(BeatDescriptor.MISSED_SHOT_CONTEXT)

    return descriptors


def classify_chapter_beat(ctx: ChapterContext) -> BeatClassification:
    """Classify a single chapter's beat type.

    Applies rules in priority order (top wins):
    1. OVERTIME (forced)
    2. CLOSING_SEQUENCE
    3. CRUNCH_SETUP
    4. RUN
    5. RESPONSE
    6. STALL
    7. BACK_AND_FORTH (window-based)
    8. BACK_AND_FORTH (default)

    Args:
        ctx: ChapterContext with all classification inputs

    Returns:
        BeatClassification with exactly one beat_type and optional descriptors
    """
    result = _check_overtime(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_closing_sequence(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_crunch_setup(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_run(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_response(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_stall(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _check_back_and_forth(ctx)
    if result:
        result.descriptors = _compute_descriptors(ctx)
        return result

    result = _default_back_and_forth(ctx)
    result.descriptors = _compute_descriptors(ctx)
    return result


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
    contexts: list[ChapterContext] = []

    for i, chapter in enumerate(chapters):
        delta = (
            section_deltas[i] if section_deltas and i < len(section_deltas) else None
        )

        previous_result = results[-1] if results else None
        previous_context = contexts[-1] if contexts else None

        ctx = build_chapter_context(
            chapter=chapter,
            chapter_index=i,
            section_delta=delta,
            previous_result=previous_result,
            home_team_key=home_team_key,
            away_team_key=away_team_key,
            previous_context=previous_context,
        )
        contexts.append(ctx)

        result = classify_chapter_beat(ctx)
        results.append(result)

    return results


# ============================================================================
# DEBUG OUTPUT
# ============================================================================


def format_classification_debug(results: list[BeatClassification]) -> str:
    """Format classification results for debug output."""
    lines = ["Beat Classification Results:", "=" * 50]

    for result in results:
        line = f"{result.chapter_id}: {result.beat_type.value} (via {result.triggered_rule})"
        if result.descriptors:
            descriptors_str = ", ".join(d.value for d in result.descriptors)
            line += f" [descriptors: {descriptors_str}]"
        lines.append(line)

    return "\n".join(lines)


def get_beat_distribution(results: list[BeatClassification]) -> dict[str, int]:
    """Get distribution of beat types."""
    distribution: dict[str, int] = {}

    for result in results:
        beat = result.beat_type.value
        distribution[beat] = distribution.get(beat, 0) + 1

    return distribution
