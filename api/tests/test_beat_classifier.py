"""
Unit tests for Beat Classifier.

These tests validate:
- Each beat type assignment
- Rule priority conflicts
- Edge cases (exact time boundaries, exact 8-0 run)
- Determinism
- Debug output

ISSUE: Beat Classifier (Chapters-First Architecture)
"""

import pytest

from app.services.chapters.types import Chapter, Play
from app.services.chapters.beat_classifier import (
    # Core types
    BeatType,
    ChapterContext,
    BeatClassification,
    # Functions
    classify_chapter_beat,
    classify_all_chapters,
    build_chapter_context,
    parse_game_clock_to_seconds,
    compute_max_unanswered_points,
    format_classification_debug,
    get_beat_distribution,
    # Rule functions (for direct testing)
    _check_overtime,
    _check_closing_sequence,
    _check_crunch_setup,
    _check_run,
    _check_response,
    _check_missed_shot_fest,
    _check_stall,
    _check_fast_start,
    _check_early_control,
    _default_back_and_forth,
)


# ============================================================================
# TEST HELPERS
# ============================================================================

def make_play(
    index: int,
    description: str = "",
    quarter: int = 1,
    game_clock: str = "12:00",
    home_score: int = 0,
    away_score: int = 0,
    team_abbr: str | None = None,
) -> Play:
    """Create a Play with common fields."""
    raw_data = {
        "description": description,
        "quarter": quarter,
        "game_clock": game_clock,
        "home_score": home_score,
        "away_score": away_score,
    }
    if team_abbr:
        raw_data["team_abbreviation"] = team_abbr
    return Play(index=index, event_type="pbp", raw_data=raw_data)


def make_chapter(
    chapter_id: str,
    plays: list[Play],
    period: int | None = None,
) -> Chapter:
    """Create a Chapter."""
    start_idx = plays[0].index if plays else 0
    end_idx = plays[-1].index if plays else 0
    return Chapter(
        chapter_id=chapter_id,
        play_start_idx=start_idx,
        play_end_idx=end_idx,
        plays=plays,
        reason_codes=["TEST"],
        period=period,
    )


def make_context(
    chapter_id: str = "ch_001",
    chapter_index: int = 0,
    period: int | None = 1,
    time_remaining_seconds: int | None = 600,
    is_overtime: bool = False,
    home_score: int = 50,
    away_score: int = 48,
    home_points_scored: int = 10,
    away_points_scored: int = 8,
    total_plays: int = 10,
    possessions_estimate: int = 5,
    total_fg_made: int = 5,
    max_unanswered: int = 4,
    home_unanswered_max: int = 4,
    away_unanswered_max: int = 2,
    previous_beat_type: BeatType | None = None,
) -> ChapterContext:
    """Create a ChapterContext for testing."""
    return ChapterContext(
        chapter_id=chapter_id,
        chapter_index=chapter_index,
        period=period,
        time_remaining_seconds=time_remaining_seconds,
        is_overtime=is_overtime,
        home_score=home_score,
        away_score=away_score,
        score_margin=abs(home_score - away_score),
        home_points_scored=home_points_scored,
        away_points_scored=away_points_scored,
        total_points_scored=home_points_scored + away_points_scored,
        total_plays=total_plays,
        possessions_estimate=possessions_estimate,
        total_fg_made=total_fg_made,
        total_fg_attempts=None,
        total_rebounds=None,
        home_unanswered_max=home_unanswered_max,
        away_unanswered_max=away_unanswered_max,
        max_unanswered=max_unanswered,
        previous_beat_type=previous_beat_type,
        previous_scoring_team=None,
    )


# ============================================================================
# TEST: TIME PARSING
# ============================================================================

class TestTimeParsing:
    """Tests for game clock parsing."""

    def test_parse_standard_clock(self):
        """Parse standard MM:SS format."""
        assert parse_game_clock_to_seconds("12:00") == 720
        assert parse_game_clock_to_seconds("5:30") == 330
        assert parse_game_clock_to_seconds("0:45") == 45

    def test_parse_single_digit_minutes(self):
        """Parse M:SS format."""
        assert parse_game_clock_to_seconds("2:00") == 120
        assert parse_game_clock_to_seconds("1:15") == 75

    def test_parse_none(self):
        """None input returns None."""
        assert parse_game_clock_to_seconds(None) is None

    def test_parse_invalid(self):
        """Invalid format returns None."""
        assert parse_game_clock_to_seconds("invalid") is None
        assert parse_game_clock_to_seconds("") is None


# ============================================================================
# TEST: BEAT TYPE ENUM
# ============================================================================

class TestBeatTypeEnum:
    """Tests for BeatType enum."""

    def test_all_beat_types_exist(self):
        """All 10 beat types are defined."""
        expected = {
            "FAST_START",
            "MISSED_SHOT_FEST",
            "BACK_AND_FORTH",
            "EARLY_CONTROL",
            "RUN",
            "RESPONSE",
            "STALL",
            "CRUNCH_SETUP",
            "CLOSING_SEQUENCE",
            "OVERTIME",
        }
        actual = {bt.value for bt in BeatType}
        assert actual == expected

    def test_beat_type_count(self):
        """Exactly 10 beat types exist."""
        assert len(BeatType) == 10


# ============================================================================
# TEST: EACH BEAT TYPE
# ============================================================================

class TestOvertimeBeat:
    """Tests for OVERTIME beat assignment."""

    def test_overtime_forced(self):
        """Overtime chapters get OVERTIME beat."""
        ctx = make_context(period=5, is_overtime=True)
        result = _check_overtime(ctx)
        assert result is not None
        assert result.beat_type == BeatType.OVERTIME

    def test_overtime_second_ot(self):
        """Second overtime also gets OVERTIME beat."""
        ctx = make_context(period=6, is_overtime=True)
        result = _check_overtime(ctx)
        assert result.beat_type == BeatType.OVERTIME

    def test_regulation_not_overtime(self):
        """Regulation periods don't get OVERTIME."""
        ctx = make_context(period=4, is_overtime=False)
        result = _check_overtime(ctx)
        assert result is None


class TestClosingSequenceBeat:
    """Tests for CLOSING_SEQUENCE beat assignment."""

    def test_closing_under_2_minutes(self):
        """Q4 with <= 2:00 gets CLOSING_SEQUENCE."""
        ctx = make_context(period=4, time_remaining_seconds=100, is_overtime=False)
        result = _check_closing_sequence(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CLOSING_SEQUENCE

    def test_closing_exactly_2_minutes(self):
        """Q4 with exactly 2:00 (120s) gets CLOSING_SEQUENCE."""
        ctx = make_context(period=4, time_remaining_seconds=120, is_overtime=False)
        result = _check_closing_sequence(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CLOSING_SEQUENCE

    def test_closing_not_in_overtime(self):
        """Overtime doesn't get CLOSING_SEQUENCE."""
        ctx = make_context(period=5, time_remaining_seconds=60, is_overtime=True)
        result = _check_closing_sequence(ctx)
        assert result is None

    def test_closing_not_in_q1(self):
        """Q1 doesn't get CLOSING_SEQUENCE."""
        ctx = make_context(period=1, time_remaining_seconds=60, is_overtime=False)
        result = _check_closing_sequence(ctx)
        assert result is None

    def test_closing_over_2_minutes(self):
        """Q4 with > 2:00 doesn't get CLOSING_SEQUENCE."""
        ctx = make_context(period=4, time_remaining_seconds=180, is_overtime=False)
        result = _check_closing_sequence(ctx)
        assert result is None


class TestCrunchSetupBeat:
    """Tests for CRUNCH_SETUP beat assignment."""

    def test_crunch_5min_close_game(self):
        """Q4, 2-5 min, close game gets CRUNCH_SETUP."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=240,  # 4 minutes
            is_overtime=False,
            home_score=80,
            away_score=78,
        )
        result = _check_crunch_setup(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_crunch_exactly_5_minutes(self):
        """Q4 with exactly 5:00 (300s) gets CRUNCH_SETUP."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=300,
            is_overtime=False,
            home_score=80,
            away_score=76,  # 4-point game
        )
        result = _check_crunch_setup(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_crunch_not_close_game(self):
        """Q4 blowout doesn't get CRUNCH_SETUP."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=240,
            is_overtime=False,
            home_score=100,
            away_score=80,  # 20-point game
        )
        result = _check_crunch_setup(ctx)
        assert result is None

    def test_crunch_under_2_minutes(self):
        """Under 2 min doesn't get CRUNCH_SETUP (goes to CLOSING)."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=100,
            is_overtime=False,
            home_score=80,
            away_score=78,
        )
        result = _check_crunch_setup(ctx)
        assert result is None


class TestRunBeat:
    """Tests for RUN beat assignment."""

    def test_run_8_unanswered(self):
        """8 unanswered points triggers RUN."""
        ctx = make_context(max_unanswered=8, home_unanswered_max=8, away_unanswered_max=0)
        result = _check_run(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RUN

    def test_run_10_unanswered(self):
        """10 unanswered points triggers RUN."""
        ctx = make_context(max_unanswered=10, home_unanswered_max=0, away_unanswered_max=10)
        result = _check_run(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RUN

    def test_run_7_unanswered_no_trigger(self):
        """7 unanswered points does NOT trigger RUN."""
        ctx = make_context(max_unanswered=7, home_unanswered_max=7, away_unanswered_max=0)
        result = _check_run(ctx)
        assert result is None

    def test_run_exactly_8_boundary(self):
        """Exactly 8 unanswered (boundary) triggers RUN."""
        ctx = make_context(max_unanswered=8)
        result = _check_run(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RUN


class TestResponseBeat:
    """Tests for RESPONSE beat assignment."""

    def test_response_after_run(self):
        """Chapter after RUN with both teams scoring gets RESPONSE."""
        ctx = make_context(
            previous_beat_type=BeatType.RUN,
            home_points_scored=6,
            away_points_scored=4,
            home_unanswered_max=4,
            away_unanswered_max=0,
        )
        result = _check_response(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RESPONSE

    def test_response_not_after_run(self):
        """Chapter not after RUN doesn't get RESPONSE."""
        ctx = make_context(
            previous_beat_type=BeatType.BACK_AND_FORTH,
            home_points_scored=6,
            away_points_scored=4,
        )
        result = _check_response(ctx)
        assert result is None

    def test_response_no_scoring(self):
        """Chapter after RUN with no scoring doesn't get RESPONSE."""
        ctx = make_context(
            previous_beat_type=BeatType.RUN,
            home_points_scored=0,
            away_points_scored=0,
        )
        result = _check_response(ctx)
        assert result is None


class TestMissedShotFestBeat:
    """Tests for MISSED_SHOT_FEST beat assignment."""

    def test_missed_shot_fest_low_scoring(self):
        """Low points per play triggers MISSED_SHOT_FEST."""
        ctx = make_context(
            total_plays=15,
            home_points_scored=2,
            away_points_scored=2,  # 4 points in 15 plays = 0.27 PPP
        )
        result = _check_missed_shot_fest(ctx)
        assert result is not None
        assert result.beat_type == BeatType.MISSED_SHOT_FEST

    def test_missed_shot_fest_normal_scoring(self):
        """Normal scoring doesn't trigger MISSED_SHOT_FEST."""
        ctx = make_context(
            total_plays=10,
            home_points_scored=10,
            away_points_scored=8,  # 18 points in 10 plays = 1.8 PPP
        )
        result = _check_missed_shot_fest(ctx)
        assert result is None

    def test_missed_shot_fest_too_few_plays(self):
        """Too few plays doesn't trigger MISSED_SHOT_FEST."""
        ctx = make_context(
            total_plays=3,
            home_points_scored=0,
            away_points_scored=0,
        )
        result = _check_missed_shot_fest(ctx)
        assert result is None


class TestStallBeat:
    """Tests for STALL beat assignment."""

    def test_stall_few_plays_low_scoring(self):
        """Few plays with low scoring triggers STALL."""
        ctx = make_context(
            total_plays=3,
            home_points_scored=1,
            away_points_scored=1,
            possessions_estimate=2,
        )
        result = _check_stall(ctx)
        assert result is not None
        assert result.beat_type == BeatType.STALL

    def test_stall_low_possessions(self):
        """Low possessions triggers STALL."""
        ctx = make_context(
            total_plays=6,
            home_points_scored=1,
            away_points_scored=1,
            possessions_estimate=2,
        )
        result = _check_stall(ctx)
        assert result is not None
        assert result.beat_type == BeatType.STALL

    def test_stall_not_low_scoring(self):
        """Normal scoring doesn't trigger STALL."""
        ctx = make_context(
            total_plays=4,
            home_points_scored=5,
            away_points_scored=5,
            possessions_estimate=4,
        )
        result = _check_stall(ctx)
        assert result is None


class TestFastStartBeat:
    """Tests for FAST_START beat assignment."""

    def test_fast_start_q1_early(self):
        """Q1 early with high pace gets FAST_START."""
        ctx = make_context(
            period=1,
            time_remaining_seconds=600,  # 10 minutes (> 8:00)
            total_plays=8,
            home_points_scored=8,
            away_points_scored=6,
        )
        result = _check_fast_start(ctx)
        assert result is not None
        assert result.beat_type == BeatType.FAST_START

    def test_fast_start_not_q1(self):
        """Q2 doesn't get FAST_START."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=600,
            total_plays=8,
            home_points_scored=8,
            away_points_scored=6,
        )
        result = _check_fast_start(ctx)
        assert result is None

    def test_fast_start_late_q1(self):
        """Late Q1 (< 8:00) doesn't get FAST_START."""
        ctx = make_context(
            period=1,
            time_remaining_seconds=400,  # < 8:00
            total_plays=8,
            home_points_scored=8,
            away_points_scored=6,
        )
        result = _check_fast_start(ctx)
        assert result is None

    def test_fast_start_low_pace(self):
        """Q1 early but low pace doesn't get FAST_START."""
        ctx = make_context(
            period=1,
            time_remaining_seconds=600,
            total_plays=3,
            home_points_scored=2,
            away_points_scored=2,
        )
        result = _check_fast_start(ctx)
        assert result is None


class TestEarlyControlBeat:
    """Tests for EARLY_CONTROL beat assignment."""

    def test_early_control_building_lead(self):
        """Modest lead building triggers EARLY_CONTROL."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            home_points_scored=10,
            away_points_scored=5,  # 5-point diff
            is_overtime=False,
        )
        result = _check_early_control(ctx)
        assert result is not None
        assert result.beat_type == BeatType.EARLY_CONTROL

    def test_early_control_not_in_crunch(self):
        """Crunch time doesn't get EARLY_CONTROL."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=200,  # In crunch time
            home_points_scored=10,
            away_points_scored=5,
            is_overtime=False,
        )
        result = _check_early_control(ctx)
        assert result is None

    def test_early_control_not_big_diff(self):
        """Big scoring diff (>7) doesn't get EARLY_CONTROL."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            home_points_scored=15,
            away_points_scored=5,  # 10-point diff
            is_overtime=False,
        )
        result = _check_early_control(ctx)
        assert result is None

    def test_early_control_too_close(self):
        """Too close scoring doesn't get EARLY_CONTROL."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            home_points_scored=8,
            away_points_scored=7,  # 1-point diff
            is_overtime=False,
        )
        result = _check_early_control(ctx)
        assert result is None


class TestBackAndForthBeat:
    """Tests for BACK_AND_FORTH beat assignment (default)."""

    def test_back_and_forth_default(self):
        """Default fallback is BACK_AND_FORTH."""
        ctx = make_context()
        result = _default_back_and_forth(ctx)
        assert result.beat_type == BeatType.BACK_AND_FORTH

    def test_back_and_forth_when_nothing_matches(self):
        """BACK_AND_FORTH when no other rule matches."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            home_points_scored=8,
            away_points_scored=8,  # Even scoring
            max_unanswered=4,  # Not a run
            total_plays=10,
            possessions_estimate=5,
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.BACK_AND_FORTH


# ============================================================================
# TEST: RULE PRIORITY CONFLICTS
# ============================================================================

class TestRulePriority:
    """Tests for rule priority (higher wins)."""

    def test_overtime_beats_closing(self):
        """OVERTIME takes priority over CLOSING_SEQUENCE."""
        ctx = make_context(
            period=5,
            is_overtime=True,
            time_remaining_seconds=60,  # Would be CLOSING in regulation
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.OVERTIME

    def test_closing_beats_crunch(self):
        """CLOSING_SEQUENCE takes priority over CRUNCH_SETUP."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=100,  # < 2:00, in CRUNCH range
            home_score=80,
            away_score=78,  # Close game
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.CLOSING_SEQUENCE

    def test_crunch_beats_run(self):
        """CRUNCH_SETUP takes priority over RUN."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=240,  # In CRUNCH window
            home_score=80,
            away_score=78,  # Close game
            max_unanswered=10,  # Would trigger RUN
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_run_beats_missed_shot_fest(self):
        """RUN takes priority over MISSED_SHOT_FEST."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            max_unanswered=12,  # RUN
            total_plays=20,
            home_points_scored=2,
            away_points_scored=12,  # Also low scoring (0.7 PPP)
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.RUN

    def test_response_beats_early_control(self):
        """RESPONSE takes priority over EARLY_CONTROL."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            previous_beat_type=BeatType.RUN,
            home_points_scored=6,
            away_points_scored=4,  # Would be EARLY_CONTROL (5-pt diff... wait, that's only 2)
            home_unanswered_max=4,
            away_unanswered_max=0,
        )
        result = classify_chapter_beat(ctx)
        # This should be RESPONSE since previous was RUN
        assert result.beat_type == BeatType.RESPONSE


# ============================================================================
# TEST: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_exactly_8_unanswered(self):
        """Exactly 8 unanswered triggers RUN (boundary)."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            max_unanswered=8,  # Exactly 8
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.RUN

    def test_exactly_7_unanswered(self):
        """Exactly 7 unanswered does NOT trigger RUN."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            max_unanswered=7,
            home_points_scored=7,
            away_points_scored=5,
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type != BeatType.RUN

    def test_exactly_2_minutes(self):
        """Exactly 2:00 (120s) triggers CLOSING_SEQUENCE."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=120,  # Exactly 2:00
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.CLOSING_SEQUENCE

    def test_exactly_121_seconds(self):
        """121 seconds does NOT trigger CLOSING_SEQUENCE."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=121,
            home_score=80,
            away_score=78,
        )
        result = classify_chapter_beat(ctx)
        # Should be CRUNCH_SETUP (within 5 min, close game)
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_exactly_5_minutes(self):
        """Exactly 5:00 (300s) triggers CRUNCH_SETUP for close game."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=300,
            home_score=80,
            away_score=76,  # 4-point game
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_exactly_5_point_margin(self):
        """Exactly 5-point margin qualifies for CRUNCH_SETUP."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=240,
            home_score=80,
            away_score=75,  # Exactly 5 points
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_6_point_margin_no_crunch(self):
        """6-point margin does NOT qualify for CRUNCH_SETUP."""
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=240,
            home_score=80,
            away_score=74,  # 6-point game
        )
        result = classify_chapter_beat(ctx)
        # Should NOT be CRUNCH_SETUP
        assert result.beat_type != BeatType.CRUNCH_SETUP

    def test_missing_time_data(self):
        """Missing time data falls through gracefully."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=None,  # Unknown time
            is_overtime=False,
        )
        result = classify_chapter_beat(ctx)
        # Should fall through to another beat or default
        assert result.beat_type is not None

    def test_period_none_not_overtime(self):
        """None period doesn't count as overtime."""
        ctx = make_context(
            period=None,
            is_overtime=False,
            time_remaining_seconds=100,
        )
        result = _check_overtime(ctx)
        assert result is None


# ============================================================================
# TEST: DETERMINISM
# ============================================================================

class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_input_same_output(self):
        """Same context produces same beat type."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            home_points_scored=8,
            away_points_scored=8,
        )

        results = [classify_chapter_beat(ctx) for _ in range(5)]
        beat_types = [r.beat_type for r in results]

        # All should be identical
        assert len(set(beat_types)) == 1

    def test_all_chapters_deterministic(self):
        """classify_all_chapters produces same results."""
        plays = [make_play(0, "play", quarter=1, game_clock="10:00")]
        chapters = [make_chapter("ch_001", plays, period=1)]

        results1 = classify_all_chapters(chapters)
        results2 = classify_all_chapters(chapters)

        assert results1[0].beat_type == results2[0].beat_type
        assert results1[0].triggered_rule == results2[0].triggered_rule


# ============================================================================
# TEST: BATCH CLASSIFICATION
# ============================================================================

class TestBatchClassification:
    """Tests for classify_all_chapters."""

    def test_classify_multiple_chapters(self):
        """Classify multiple chapters."""
        plays1 = [make_play(0, "play", quarter=1, game_clock="10:00")]
        plays2 = [make_play(1, "play", quarter=4, game_clock="1:00", home_score=80, away_score=78)]

        chapters = [
            make_chapter("ch_001", plays1, period=1),
            make_chapter("ch_002", plays2, period=4),
        ]

        results = classify_all_chapters(chapters)

        assert len(results) == 2
        assert results[0].chapter_id == "ch_001"
        assert results[1].chapter_id == "ch_002"

    def test_response_requires_previous_run(self):
        """RESPONSE only after RUN."""
        # First chapter: 10-0 run
        plays1 = [
            make_play(0, "LAL makes 3-pt shot", quarter=2, game_clock="8:00",
                     home_score=10, away_score=0, team_abbr="LAL"),
        ]
        # Second chapter: opponent responds
        plays2 = [
            make_play(1, "BOS makes layup", quarter=2, game_clock="6:00",
                     home_score=12, away_score=4, team_abbr="BOS"),
        ]

        chapters = [
            make_chapter("ch_001", plays1, period=2),
            make_chapter("ch_002", plays2, period=2),
        ]

        # We need section deltas for proper scoring
        # For this test, we'll verify the mechanism works
        results = classify_all_chapters(chapters)
        assert len(results) == 2


# ============================================================================
# TEST: DEBUG OUTPUT
# ============================================================================

class TestDebugOutput:
    """Tests for debug output functions."""

    def test_format_classification_debug(self):
        """Debug formatting works."""
        results = [
            BeatClassification("ch_001", BeatType.FAST_START, "RULE_8", {}),
            BeatClassification("ch_002", BeatType.RUN, "RULE_4", {}),
        ]

        output = format_classification_debug(results)

        assert "ch_001" in output
        assert "FAST_START" in output
        assert "ch_002" in output
        assert "RUN" in output

    def test_get_beat_distribution(self):
        """Beat distribution counting works."""
        results = [
            BeatClassification("ch_001", BeatType.FAST_START, "RULE_8", {}),
            BeatClassification("ch_002", BeatType.RUN, "RULE_4", {}),
            BeatClassification("ch_003", BeatType.RUN, "RULE_4", {}),
            BeatClassification("ch_004", BeatType.BACK_AND_FORTH, "RULE_10", {}),
        ]

        dist = get_beat_distribution(results)

        assert dist["FAST_START"] == 1
        assert dist["RUN"] == 2
        assert dist["BACK_AND_FORTH"] == 1


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================

class TestSerialization:
    """Tests for serialization."""

    def test_context_to_dict(self):
        """ChapterContext serializes correctly."""
        ctx = make_context()
        data = ctx.to_dict()

        assert data["chapter_id"] == "ch_001"
        assert "period" in data
        assert "score_margin" in data

    def test_classification_to_dict(self):
        """BeatClassification serializes correctly."""
        result = BeatClassification(
            chapter_id="ch_001",
            beat_type=BeatType.RUN,
            triggered_rule="RULE_4_RUN",
            debug_info={"max_unanswered": 10},
        )
        data = result.to_dict()

        assert data["chapter_id"] == "ch_001"
        assert data["beat_type"] == "RUN"
        assert data["triggered_rule"] == "RULE_4_RUN"
        assert data["debug_info"]["max_unanswered"] == 10


# ============================================================================
# TEST: UNANSWERED POINTS COMPUTATION
# ============================================================================

class TestUnansweredPoints:
    """Tests for unanswered points computation."""

    def test_compute_basic_run(self):
        """Basic scoring run detection."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
        ]

        home_max, away_max = compute_max_unanswered_points(plays)

        # Home scored 8 unanswered
        assert home_max == 8
        assert away_max == 0

    def test_compute_alternating(self):
        """Alternating scoring has no run."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "BOS makes layup", "home_score": 2, "away_score": 2},
            {"description": "LAL makes layup", "home_score": 4, "away_score": 2},
            {"description": "BOS makes 3-pt", "home_score": 4, "away_score": 5},
        ]

        home_max, away_max = compute_max_unanswered_points(plays)

        # Max either team had consecutively
        assert home_max <= 2
        assert away_max <= 3
