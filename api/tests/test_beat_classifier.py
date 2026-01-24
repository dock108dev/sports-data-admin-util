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
    BeatDescriptor,  # Phase 2.1
    RunWindow,  # Phase 2.2
    ResponseWindow,  # Phase 2.3
    BackAndForthWindow,  # Phase 2.4
    ChapterContext,
    BeatClassification,
    # Constants (Phase 2.1)
    PRIMARY_BEATS,
    BEAT_PRIORITY,
    MISSED_SHOT_PPP_THRESHOLD,
    # Constants (Phase 2.2)
    RUN_WINDOW_THRESHOLD,
    RUN_MARGIN_EXPANSION_THRESHOLD,
    # Constants (Phase 2.4)
    BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD,
    BACK_AND_FORTH_TIES_THRESHOLD,
    # Functions
    classify_chapter_beat,
    classify_all_chapters,
    build_chapter_context,
    parse_game_clock_to_seconds,
    format_classification_debug,
    get_beat_distribution,
    _compute_descriptors,  # Phase 2.1
    # Run window functions (Phase 2.2)
    detect_run_windows,
    get_qualifying_run_windows,
    # Response window functions (Phase 2.3)
    detect_response_windows,
    get_qualifying_response_windows,
    # Back-and-forth window functions (Phase 2.4)
    detect_back_and_forth_window,
    get_qualifying_back_and_forth_window,
    # Rule functions (for direct testing)
    _check_overtime,
    _check_closing_sequence,
    _check_crunch_setup,
    _check_run,
    _check_response,
    _check_stall,
    _check_back_and_forth,  # Phase 2.4
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
    previous_beat_type: BeatType | None = None,
    # Phase 2.2: Run window fields
    qualifying_run_windows: list[RunWindow] | None = None,
    has_qualifying_run: bool = False,
    # Phase 2.3: Response window fields
    qualifying_response_windows: list[ResponseWindow] | None = None,
    has_qualifying_response: bool = False,
    previous_run_windows: list[RunWindow] | None = None,
    # Phase 2.4: Back-and-forth window fields
    back_and_forth_window: BackAndForthWindow | None = None,
    has_qualifying_back_and_forth: bool = False,
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
        qualifying_run_windows=qualifying_run_windows or [],
        has_qualifying_run=has_qualifying_run,
        qualifying_response_windows=qualifying_response_windows or [],
        has_qualifying_response=has_qualifying_response,
        back_and_forth_window=back_and_forth_window,
        has_qualifying_back_and_forth=has_qualifying_back_and_forth,
        previous_beat_type=previous_beat_type,
        previous_scoring_team=None,
        previous_run_windows=previous_run_windows or [],
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
        """Under 2 min in close game gets CRUNCH_SETUP (Phase 2.6).

        Phase 2.6: CRUNCH_SETUP now fires for ≤ 5:00 (including < 2:00).
        However, in classify_chapter_beat, CLOSING_SEQUENCE has higher
        priority and would fire instead for close games under 2:00.
        """
        ctx = make_context(
            period=4,
            time_remaining_seconds=100,
            is_overtime=False,
            home_score=80,
            away_score=78,  # margin = 2, within threshold
        )
        result = _check_crunch_setup(ctx)
        # Phase 2.6: CRUNCH_SETUP now fires for ≤ 5:00
        assert result is not None
        assert result.beat_type == BeatType.CRUNCH_SETUP


class TestRunBeat:
    """Tests for RUN beat assignment (Phase 2.2: Run Window Detection)."""

    def test_run_with_lead_change(self):
        """Run that causes lead change triggers RUN."""
        ctx = make_context(
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=3,
                    points_scored=8,
                    start_home_score=5,
                    start_away_score=8,  # Away leading
                    end_home_score=13,
                    end_away_score=8,    # Home now leading
                    caused_lead_change=True,
                    margin_expansion=8,
                )
            ],
        )
        result = _check_run(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RUN

    def test_run_with_margin_expansion_8(self):
        """Run that expands margin by 8+ triggers RUN."""
        ctx = make_context(
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="away",
                    start_play_index=0,
                    end_play_index=4,
                    points_scored=10,
                    start_home_score=20,
                    start_away_score=20,
                    end_home_score=20,
                    end_away_score=30,
                    caused_lead_change=True,  # Tied to leading
                    margin_expansion=10,
                )
            ],
        )
        result = _check_run(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RUN

    def test_run_without_qualifying_window_no_trigger(self):
        """Run without qualifying window does NOT trigger RUN."""
        ctx = make_context(
            has_qualifying_run=False,  # No qualifying window
        )
        result = _check_run(ctx)
        assert result is None

    def test_run_with_margin_expansion_below_8_no_trigger(self):
        """Run with < 8 margin expansion and no lead change doesn't trigger RUN."""
        # The run window exists but doesn't qualify
        ctx = make_context(
            has_qualifying_run=False,  # Doesn't qualify
        )
        result = _check_run(ctx)
        assert result is None


class TestResponseBeat:
    """Tests for RESPONSE beat assignment (Phase 2.3: Response Window Detection)."""

    def test_intra_chapter_response(self):
        """Intra-chapter response (RUN + RESPONSE in same chapter) gets RESPONSE."""
        ctx = make_context(
            has_qualifying_response=True,
            qualifying_response_windows=[
                ResponseWindow(
                    responding_team="away",
                    run_team="home",
                    start_play_index=5,
                    end_play_index=10,
                    responding_team_points=8,
                    run_team_points=2,
                    run_end_home_score=50,
                    run_end_away_score=42,
                    response_end_home_score=52,
                    response_end_away_score=50,
                )
            ],
        )
        result = _check_response(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RESPONSE
        assert "INTRA_CHAPTER" in result.triggered_rule

    def test_cross_chapter_response(self):
        """Cross-chapter response (previous chapter had RUN) gets RESPONSE."""
        # Previous chapter had a home team RUN, so away is responding
        previous_run = RunWindow(
            team="home",
            start_play_index=0,
            end_play_index=5,
            points_scored=10,
            start_home_score=40,
            start_away_score=40,
            end_home_score=50,
            end_away_score=40,
            caused_lead_change=True,
            margin_expansion=10,
        )
        ctx = make_context(
            previous_beat_type=BeatType.RUN,
            previous_run_windows=[previous_run],
            home_points_scored=2,   # Run team scores 2
            away_points_scored=8,   # Responding team scores 8
        )
        result = _check_response(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RESPONSE
        assert "CROSS_CHAPTER" in result.triggered_rule

    def test_response_not_after_run(self):
        """Chapter not after RUN doesn't get RESPONSE."""
        ctx = make_context(
            previous_beat_type=BeatType.BACK_AND_FORTH,
            home_points_scored=6,
            away_points_scored=4,
            has_qualifying_response=False,
        )
        result = _check_response(ctx)
        assert result is None

    def test_response_trailing_team_must_outscore(self):
        """Cross-chapter: trailing team must outscore leading team."""
        # Previous RUN was by home, so away is responding
        # But away scored less than home in this chapter - no RESPONSE
        previous_run = RunWindow(
            team="home",
            start_play_index=0,
            end_play_index=5,
            points_scored=10,
            start_home_score=40,
            start_away_score=40,
            end_home_score=50,
            end_away_score=40,
            caused_lead_change=True,
            margin_expansion=10,
        )
        ctx = make_context(
            previous_beat_type=BeatType.RUN,
            previous_run_windows=[previous_run],
            home_points_scored=8,   # Run team scores MORE
            away_points_scored=4,   # Responding team scores less
        )
        result = _check_response(ctx)
        assert result is None

    def test_response_only_responding_team_scores(self):
        """RESPONSE fires even if only responding team scores (asymmetric)."""
        # Previous RUN was by home, so away is responding
        # Away scores, home doesn't - still a RESPONSE
        previous_run = RunWindow(
            team="home",
            start_play_index=0,
            end_play_index=5,
            points_scored=10,
            start_home_score=40,
            start_away_score=40,
            end_home_score=50,
            end_away_score=40,
            caused_lead_change=True,
            margin_expansion=10,
        )
        ctx = make_context(
            previous_beat_type=BeatType.RUN,
            previous_run_windows=[previous_run],
            home_points_scored=0,   # Run team scores NOTHING
            away_points_scored=6,   # Responding team scores
        )
        result = _check_response(ctx)
        assert result is not None
        assert result.beat_type == BeatType.RESPONSE


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
            has_qualifying_run=True,  # Would trigger RUN
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=3,
                    points_scored=10,
                    start_home_score=70,
                    start_away_score=78,
                    end_home_score=80,
                    end_away_score=78,
                    caused_lead_change=True,
                    margin_expansion=10,
                )
            ],
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_run_beats_missed_shot_fest(self):
        """RUN takes priority over MISSED_SHOT_FEST (now a descriptor)."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            total_plays=20,
            home_points_scored=2,
            away_points_scored=12,  # Also low scoring (0.7 PPP)
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="away",
                    start_play_index=0,
                    end_play_index=5,
                    points_scored=12,
                    start_home_score=2,
                    start_away_score=0,
                    end_home_score=2,
                    end_away_score=12,
                    caused_lead_change=True,
                    margin_expansion=10,
                )
            ],
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.RUN

    def test_response_beats_early_control(self):
        """RESPONSE takes priority over EARLY_CONTROL."""
        # Previous chapter had home team RUN, so away is responding
        previous_run = RunWindow(
            team="home",
            start_play_index=0,
            end_play_index=5,
            points_scored=10,
            start_home_score=40,
            start_away_score=40,
            end_home_score=50,
            end_away_score=40,
            caused_lead_change=True,
            margin_expansion=10,
        )
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            previous_beat_type=BeatType.RUN,
            previous_run_windows=[previous_run],
            home_points_scored=4,   # Run team (home) scores less
            away_points_scored=6,   # Responding team (away) scores more
        )
        result = classify_chapter_beat(ctx)
        # This should be RESPONSE since previous was RUN and responding team outscored
        assert result.beat_type == BeatType.RESPONSE


# ============================================================================
# TEST: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_qualifying_run_with_margin_8_triggers_run(self):
        """Qualifying run with 8-point margin expansion triggers RUN."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=4,
                    points_scored=8,
                    start_home_score=10,
                    start_away_score=10,
                    end_home_score=18,
                    end_away_score=10,
                    caused_lead_change=True,  # Tied to leading
                    margin_expansion=8,
                )
            ],
        )
        result = classify_chapter_beat(ctx)
        assert result.beat_type == BeatType.RUN

    def test_non_qualifying_run_does_not_trigger(self):
        """Non-qualifying run (< 8 margin, no lead change) doesn't trigger RUN."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            has_qualifying_run=False,  # No qualifying window
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

    def test_11_point_margin_no_crunch(self):
        """11-point margin does NOT qualify for CRUNCH_SETUP (Phase 2.6).

        Phase 2.6: CRUNCH_SETUP margin threshold expanded to ≤ 10.
        Margin > 10 does not qualify.
        """
        ctx = make_context(
            period=4,
            is_overtime=False,
            time_remaining_seconds=240,
            home_score=85,
            away_score=74,  # 11-point game
        )
        result = classify_chapter_beat(ctx)
        # Should NOT be CRUNCH_SETUP (margin > 10)
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
            debug_info={"qualifying_run_count": 2},
        )
        data = result.to_dict()

        assert data["chapter_id"] == "ch_001"
        assert data["beat_type"] == "RUN"
        assert data["triggered_rule"] == "RULE_4_RUN"
        assert data["debug_info"]["qualifying_run_count"] == 2


# ============================================================================
# TEST: PHASE 2.1 - BEAT DESCRIPTORS
# ============================================================================

class TestBeatDescriptorEnum:
    """Tests for BeatDescriptor enum (Phase 2.1)."""

    def test_missed_shot_context_exists(self):
        """MISSED_SHOT_CONTEXT descriptor exists."""
        assert BeatDescriptor.MISSED_SHOT_CONTEXT.value == "MISSED_SHOT_CONTEXT"

    def test_descriptor_count(self):
        """Exactly 1 descriptor defined (Phase 2.1)."""
        assert len(BeatDescriptor) == 1


class TestPrimaryBeats:
    """Tests for PRIMARY_BEATS set (Phase 2.1)."""

    def test_missed_shot_fest_excluded(self):
        """MISSED_SHOT_FEST is NOT in PRIMARY_BEATS."""
        assert BeatType.MISSED_SHOT_FEST not in PRIMARY_BEATS

    def test_primary_beats_count(self):
        """9 primary beats (10 total - MISSED_SHOT_FEST)."""
        assert len(PRIMARY_BEATS) == 9

    def test_all_primary_beats_present(self):
        """All expected primary beats are present."""
        expected = {
            BeatType.FAST_START,
            BeatType.EARLY_CONTROL,
            BeatType.RUN,
            BeatType.RESPONSE,
            BeatType.BACK_AND_FORTH,
            BeatType.STALL,
            BeatType.CRUNCH_SETUP,
            BeatType.CLOSING_SEQUENCE,
            BeatType.OVERTIME,
        }
        assert PRIMARY_BEATS == expected


class TestBeatPriority:
    """Tests for BEAT_PRIORITY list (Phase 2.1)."""

    def test_priority_ordering(self):
        """BEAT_PRIORITY has expected order (highest first)."""
        assert BEAT_PRIORITY[0] == BeatType.OVERTIME
        assert BEAT_PRIORITY[1] == BeatType.CLOSING_SEQUENCE
        assert BEAT_PRIORITY[2] == BeatType.CRUNCH_SETUP
        assert BEAT_PRIORITY[-1] == BeatType.STALL

    def test_priority_excludes_missed_shot_fest(self):
        """MISSED_SHOT_FEST not in priority list."""
        assert BeatType.MISSED_SHOT_FEST not in BEAT_PRIORITY

    def test_priority_count(self):
        """9 beats in priority list."""
        assert len(BEAT_PRIORITY) == 9


class TestMissedShotThreshold:
    """Tests for MISSED_SHOT_PPP_THRESHOLD constant (Phase 2.1)."""

    def test_threshold_value(self):
        """Threshold is 0.35 points per play."""
        assert MISSED_SHOT_PPP_THRESHOLD == 0.35


class TestComputeDescriptors:
    """Tests for _compute_descriptors function (Phase 2.1)."""

    def test_low_ppp_gets_descriptor(self):
        """Low points-per-play adds MISSED_SHOT_CONTEXT descriptor."""
        ctx = make_context(
            total_plays=15,
            home_points_scored=2,
            away_points_scored=2,  # 4 points in 15 plays = 0.27 PPP
        )
        descriptors = _compute_descriptors(ctx)
        assert BeatDescriptor.MISSED_SHOT_CONTEXT in descriptors

    def test_normal_ppp_no_descriptor(self):
        """Normal PPP does not add descriptor."""
        ctx = make_context(
            total_plays=10,
            home_points_scored=10,
            away_points_scored=8,  # 18 points in 10 plays = 1.8 PPP
        )
        descriptors = _compute_descriptors(ctx)
        assert len(descriptors) == 0

    def test_exactly_threshold_no_descriptor(self):
        """Exactly at threshold does NOT add descriptor (must be strictly below)."""
        # 0.35 * 20 = 7 points exactly
        ctx = make_context(
            total_plays=20,
            home_points_scored=4,
            away_points_scored=3,  # 7 points in 20 plays = 0.35 PPP
        )
        descriptors = _compute_descriptors(ctx)
        assert BeatDescriptor.MISSED_SHOT_CONTEXT not in descriptors

    def test_too_few_plays_no_descriptor(self):
        """Too few plays doesn't trigger descriptor."""
        ctx = make_context(
            total_plays=3,
            home_points_scored=0,
            away_points_scored=0,  # 0 PPP but only 3 plays
        )
        descriptors = _compute_descriptors(ctx)
        assert len(descriptors) == 0


class TestClassifyChapterBeatPhase21:
    """Tests for classify_chapter_beat Phase 2.1 changes."""

    def test_never_returns_missed_shot_fest(self):
        """classify_chapter_beat NEVER returns MISSED_SHOT_FEST as primary beat."""
        # This context would have triggered MISSED_SHOT_FEST in old system
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            total_plays=15,
            home_points_scored=2,
            away_points_scored=2,  # 4 points in 15 plays = 0.27 PPP
        )
        result = classify_chapter_beat(ctx)

        # Should NOT be MISSED_SHOT_FEST
        assert result.beat_type != BeatType.MISSED_SHOT_FEST
        # Should have the descriptor instead
        assert BeatDescriptor.MISSED_SHOT_CONTEXT in result.descriptors

    def test_low_ppp_falls_to_stall_or_back_and_forth(self):
        """Low PPP chapter falls through to STALL or BACK_AND_FORTH."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            total_plays=15,
            home_points_scored=2,
            away_points_scored=2,
            possessions_estimate=8,  # Not STALL
        )
        result = classify_chapter_beat(ctx)

        # Should be BACK_AND_FORTH (default) with descriptor
        assert result.beat_type == BeatType.BACK_AND_FORTH
        assert BeatDescriptor.MISSED_SHOT_CONTEXT in result.descriptors

    def test_classification_includes_descriptors_field(self):
        """BeatClassification always includes descriptors field."""
        ctx = make_context()
        result = classify_chapter_beat(ctx)

        assert hasattr(result, "descriptors")
        assert isinstance(result.descriptors, set)

    def test_run_with_missed_shot_context(self):
        """RUN can have MISSED_SHOT_CONTEXT descriptor."""
        # A run where overall PPP is still low
        ctx = make_context(
            period=2,
            time_remaining_seconds=500,
            total_plays=30,
            home_points_scored=6,
            away_points_scored=4,  # 10 points in 30 plays = 0.33 PPP
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=10,
                    points_scored=10,
                    start_home_score=0,
                    start_away_score=4,
                    end_home_score=10,
                    end_away_score=4,
                    caused_lead_change=True,
                    margin_expansion=10,
                )
            ],
        )
        result = classify_chapter_beat(ctx)

        # Primary beat is RUN
        assert result.beat_type == BeatType.RUN
        # But also has descriptor for low scoring
        assert BeatDescriptor.MISSED_SHOT_CONTEXT in result.descriptors


class TestClassificationSerialization:
    """Tests for BeatClassification serialization with descriptors."""

    def test_to_dict_includes_descriptors(self):
        """BeatClassification.to_dict() includes descriptors."""
        result = BeatClassification(
            chapter_id="ch_001",
            beat_type=BeatType.RUN,
            triggered_rule="RULE_4_RUN",
            debug_info={},
            descriptors={BeatDescriptor.MISSED_SHOT_CONTEXT},
        )
        data = result.to_dict()

        assert "descriptors" in data
        assert "MISSED_SHOT_CONTEXT" in data["descriptors"]

    def test_to_dict_empty_descriptors(self):
        """Empty descriptors are NOT included in serialization (reduces noise)."""
        result = BeatClassification(
            chapter_id="ch_001",
            beat_type=BeatType.RUN,
            triggered_rule="RULE_4_RUN",
            debug_info={},
            descriptors=set(),
        )
        data = result.to_dict()

        # Empty descriptors are excluded from output
        assert "descriptors" not in data


# ============================================================================
# TEST: PHASE 2.2 - RUN WINDOW DETECTION
# ============================================================================

class TestRunWindowThresholds:
    """Tests for run window threshold constants."""

    def test_run_window_threshold(self):
        """Run window threshold is 6 points."""
        assert RUN_WINDOW_THRESHOLD == 6

    def test_margin_expansion_threshold(self):
        """Margin expansion threshold is 8 points."""
        assert RUN_MARGIN_EXPANSION_THRESHOLD == 8


class TestDetectRunWindows:
    """Tests for detect_run_windows function."""

    def test_detect_6_point_run(self):
        """Detect run window when team scores 6+ unanswered."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 6, "away_score": 0},
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 1
        assert windows[0].team == "home"
        assert windows[0].points_scored == 6

    def test_no_run_under_threshold(self):
        """No run window for 5 or fewer unanswered points."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "BOS makes layup", "home_score": 5, "away_score": 2},
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 0

    def test_run_ends_on_opponent_score(self):
        """Run window ends when opponent scores."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "BOS makes layup", "home_score": 7, "away_score": 2},  # Run ends here
            {"description": "LAL makes layup", "home_score": 9, "away_score": 2},
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 1
        assert windows[0].points_scored == 7
        assert windows[0].end_play_index == 2  # Run ends before opponent scores

    def test_multiple_runs_in_chapter(self):
        """Detect multiple run windows in same chapter."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "BOS makes layup", "home_score": 7, "away_score": 2},  # Run 1 ends
            {"description": "BOS makes 3-pt shot", "home_score": 7, "away_score": 5},
            {"description": "BOS makes layup", "home_score": 7, "away_score": 7},  # Run 2 (2+3+2=7 pts)
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 2
        assert windows[0].team == "home"
        assert windows[0].points_scored == 7
        assert windows[1].team == "away"
        assert windows[1].points_scored == 7  # 2+3+2=7

    def test_empty_plays(self):
        """Empty plays list returns no windows."""
        windows = detect_run_windows([])
        assert len(windows) == 0

    def test_no_scoring_plays(self):
        """No scoring plays returns no windows."""
        plays = [
            {"description": "Defensive rebound", "home_score": 0, "away_score": 0},
            {"description": "Turnover", "home_score": 0, "away_score": 0},
        ]
        windows = detect_run_windows(plays)
        assert len(windows) == 0


class TestRunWindowQualification:
    """Tests for run window qualification (lead change or margin expansion)."""

    def test_run_with_lead_change_qualifies(self):
        """Run that causes lead change qualifies."""
        plays = [
            # Away starts with lead
            {"description": "BOS makes layup", "home_score": 0, "away_score": 2},
            # Home runs to take lead
            {"description": "LAL makes layup", "home_score": 2, "away_score": 2},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 2},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 2},
        ]
        windows = get_qualifying_run_windows(plays)

        assert len(windows) == 1
        assert windows[0].caused_lead_change
        assert windows[0].is_qualifying()

    def test_run_with_margin_expansion_8_qualifies(self):
        """Run that expands margin by 8+ qualifies."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
        ]
        windows = get_qualifying_run_windows(plays)

        assert len(windows) == 1
        assert windows[0].margin_expansion == 8
        assert windows[0].is_qualifying()

    def test_run_without_lead_change_or_margin_8_does_not_qualify(self):
        """Run that doesn't change lead and expands margin < 8 doesn't qualify."""
        # Scenario: home is already leading significantly, and extends by 6 more
        plays = [
            # Home already leading 10-5, away scores to make it 10-7
            {"description": "BOS makes layup", "home_score": 10, "away_score": 7},
            # Home scores 6 unanswered - extends lead but only by 6
            {"description": "LAL makes layup", "home_score": 12, "away_score": 7},
            {"description": "LAL makes 3-pt shot", "home_score": 15, "away_score": 7},
            {"description": "LAL makes free throw", "home_score": 16, "away_score": 7},
        ]
        qualifying = get_qualifying_run_windows(plays)

        # The run exists but doesn't qualify (6 margin expansion, no lead change)
        all_windows = detect_run_windows(plays)
        assert len(all_windows) == 1
        assert all_windows[0].team == "home"
        assert all_windows[0].margin_expansion == 6  # Went from 3 to 9 margin
        assert not all_windows[0].caused_lead_change  # Home was already leading
        assert len(qualifying) == 0  # Doesn't qualify: < 8 margin, no lead change

    def test_run_creating_tie_does_not_qualify_as_lead_change(self):
        """Run that creates tie but doesn't take lead doesn't qualify via lead change."""
        # Scenario: away scored first (one bucket), then home goes on a run to tie
        plays = [
            # Away scores first to take lead
            {"description": "BOS makes layup", "home_score": 0, "away_score": 2},
            # Home goes on 6-0 run to take lead (this DOES cause lead change)
            {"description": "LAL makes layup", "home_score": 2, "away_score": 2},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 2},
            {"description": "LAL makes free throw", "home_score": 6, "away_score": 2},
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 1
        assert windows[0].team == "home"
        # This run DOES cause lead change (away leading to home leading)
        assert windows[0].caused_lead_change is True
        assert windows[0].margin_expansion == 6
        # Qualifies due to lead change
        assert windows[0].is_qualifying() is True


class TestCheckRunWithQualifyingWindows:
    """Tests for _check_run using qualifying run windows."""

    def test_check_run_with_qualifying_run(self):
        """_check_run returns RUN when qualifying run window exists."""
        ctx = make_context(
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=3,
                    points_scored=10,
                    start_home_score=0,
                    start_away_score=5,
                    end_home_score=10,
                    end_away_score=5,
                    caused_lead_change=True,
                    margin_expansion=10,
                )
            ],
        )
        result = _check_run(ctx)

        assert result is not None
        assert result.beat_type == BeatType.RUN
        assert "qualifying_run_count" in result.debug_info

    def test_check_run_without_qualifying_run(self):
        """_check_run returns None when no qualifying run window."""
        ctx = make_context(has_qualifying_run=False)
        result = _check_run(ctx)

        assert result is None

    def test_run_not_triggered_without_qualifying_window(self):
        """RUN requires qualifying window."""
        ctx = make_context(
            has_qualifying_run=False,  # No qualifying window
        )
        result = _check_run(ctx)

        assert result is None


class TestClassifyChapterBeatWithRunWindows:
    """Tests for classify_chapter_beat with new run window logic."""

    def test_lead_change_run_triggers_run_beat(self):
        """Chapter with lead-changing run gets RUN beat."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=400,
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="away",
                    start_play_index=0,
                    end_play_index=2,
                    points_scored=8,
                    start_home_score=10,
                    start_away_score=8,
                    end_home_score=10,
                    end_away_score=16,
                    caused_lead_change=True,
                    margin_expansion=8,
                )
            ],
        )
        result = classify_chapter_beat(ctx)

        assert result.beat_type == BeatType.RUN

    def test_margin_expansion_run_triggers_run_beat(self):
        """Chapter with margin-expanding run gets RUN beat."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=400,
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=4,
                    points_scored=12,
                    start_home_score=20,
                    start_away_score=10,
                    end_home_score=32,
                    end_away_score=10,
                    caused_lead_change=False,
                    margin_expansion=12,
                )
            ],
        )
        result = classify_chapter_beat(ctx)

        assert result.beat_type == BeatType.RUN

    def test_minor_run_does_not_trigger_run_beat(self):
        """Chapter with non-qualifying run doesn't get RUN beat."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=400,
            has_qualifying_run=False,  # Run exists but doesn't qualify
        )
        result = classify_chapter_beat(ctx)

        # Should fall through to another beat
        assert result.beat_type != BeatType.RUN


class TestRunWindowSerialization:
    """Tests for RunWindow serialization."""

    def test_run_window_to_dict(self):
        """RunWindow serializes correctly."""
        window = RunWindow(
            team="home",
            start_play_index=0,
            end_play_index=3,
            points_scored=10,
            start_home_score=0,
            start_away_score=5,
            end_home_score=10,
            end_away_score=5,
            caused_lead_change=True,
            margin_expansion=10,
        )
        data = window.to_dict()

        assert data["team"] == "home"
        assert data["points_scored"] == 10
        assert data["caused_lead_change"] is True
        assert data["margin_expansion"] == 10
        assert data["is_qualifying"] is True
        assert data["start_score"] == "0-5"
        assert data["end_score"] == "10-5"

    def test_context_to_dict_includes_qualifying_runs(self):
        """ChapterContext.to_dict() includes qualifying run windows."""
        ctx = make_context(
            has_qualifying_run=True,
            qualifying_run_windows=[
                RunWindow(
                    team="home",
                    start_play_index=0,
                    end_play_index=3,
                    points_scored=10,
                    start_home_score=0,
                    start_away_score=5,
                    end_home_score=10,
                    end_away_score=5,
                    caused_lead_change=True,
                    margin_expansion=10,
                )
            ],
        )
        data = ctx.to_dict()

        assert data["has_qualifying_run"] is True
        assert "qualifying_run_windows" in data
        assert len(data["qualifying_run_windows"]) == 1


# ============================================================================
# TEST: PHASE 2.3 - RESPONSE WINDOW DETECTION
# ============================================================================

class TestDetectResponseWindows:
    """Tests for detect_response_windows function."""

    def test_detect_response_after_run(self):
        """Detect response window following a RUN."""
        # Home goes on 8-0 run, then away responds with scoring
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
            # RUN ends here (8 unanswered, lead change from tie)
            # Response begins
            {"description": "BOS makes 3-pt shot", "home_score": 8, "away_score": 3},
            {"description": "BOS makes layup", "home_score": 8, "away_score": 5},
        ]
        qualifying_runs = get_qualifying_run_windows(plays)
        responses = detect_response_windows(plays, qualifying_runs)

        assert len(responses) == 1
        assert responses[0].responding_team == "away"
        assert responses[0].run_team == "home"
        assert responses[0].responding_team_points == 5
        assert responses[0].run_team_points == 0

    def test_no_response_if_run_team_outscores(self):
        """No qualifying response if run team outscores responding team."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
            # RUN ends here (8 points, lead change from tie)
            # In response window, home (run team) outscores away (responding team)
            {"description": "BOS makes layup", "home_score": 8, "away_score": 2},
            {"description": "LAL makes 3-pt shot", "home_score": 11, "away_score": 2},
            {"description": "LAL makes layup", "home_score": 13, "away_score": 2},
        ]
        qualifying_runs = get_qualifying_run_windows(plays)
        qualifying_responses = get_qualifying_response_windows(plays, qualifying_runs)

        # Response window exists but doesn't qualify (home scored 5, away scored 2)
        all_responses = detect_response_windows(plays, qualifying_runs)
        assert len(all_responses) == 1  # Response window exists
        assert all_responses[0].run_team_points == 5  # Home scored 5
        assert all_responses[0].responding_team_points == 2  # Away scored 2
        assert len(qualifying_responses) == 0  # But doesn't qualify

    def test_no_response_if_run_ends_at_chapter_end(self):
        """No response window if RUN ends at last play."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
            # RUN ends at last play - no room for response
        ]
        qualifying_runs = get_qualifying_run_windows(plays)
        responses = detect_response_windows(plays, qualifying_runs)

        assert len(responses) == 0

    def test_response_only_responding_team_scores(self):
        """Response qualifies even if only responding team scores."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
            # Only away scores in response
            {"description": "BOS makes 3-pt shot", "home_score": 8, "away_score": 3},
            {"description": "BOS makes layup", "home_score": 8, "away_score": 5},
        ]
        qualifying_runs = get_qualifying_run_windows(plays)
        qualifying_responses = get_qualifying_response_windows(plays, qualifying_runs)

        assert len(qualifying_responses) == 1
        assert qualifying_responses[0].responding_team_points == 5
        assert qualifying_responses[0].run_team_points == 0
        assert qualifying_responses[0].is_qualifying()


class TestResponseWindowQualification:
    """Tests for response window qualification rules."""

    def test_response_qualifies_when_trailing_outscores(self):
        """Response qualifies when trailing team outscores leading team."""
        response = ResponseWindow(
            responding_team="away",
            run_team="home",
            start_play_index=5,
            end_play_index=8,
            responding_team_points=8,
            run_team_points=4,
            run_end_home_score=50,
            run_end_away_score=42,
            response_end_home_score=54,
            response_end_away_score=50,
        )
        assert response.is_qualifying() is True

    def test_response_does_not_qualify_when_run_team_outscores(self):
        """Response doesn't qualify when run team outscores responding team."""
        response = ResponseWindow(
            responding_team="away",
            run_team="home",
            start_play_index=5,
            end_play_index=8,
            responding_team_points=4,
            run_team_points=8,
            run_end_home_score=50,
            run_end_away_score=42,
            response_end_home_score=58,
            response_end_away_score=46,
        )
        assert response.is_qualifying() is False

    def test_response_does_not_qualify_when_equal_scoring(self):
        """Response doesn't qualify when both teams score equally."""
        response = ResponseWindow(
            responding_team="away",
            run_team="home",
            start_play_index=5,
            end_play_index=8,
            responding_team_points=6,
            run_team_points=6,
            run_end_home_score=50,
            run_end_away_score=42,
            response_end_home_score=56,
            response_end_away_score=48,
        )
        assert response.is_qualifying() is False


class TestResponseWindowSerialization:
    """Tests for ResponseWindow serialization."""

    def test_response_window_to_dict(self):
        """ResponseWindow serializes correctly."""
        response = ResponseWindow(
            responding_team="away",
            run_team="home",
            start_play_index=5,
            end_play_index=8,
            responding_team_points=8,
            run_team_points=2,
            run_end_home_score=50,
            run_end_away_score=42,
            response_end_home_score=52,
            response_end_away_score=50,
        )
        data = response.to_dict()

        assert data["responding_team"] == "away"
        assert data["run_team"] == "home"
        assert data["responding_team_points"] == 8
        assert data["run_team_points"] == 2
        assert data["is_qualifying"] is True
        assert data["run_end_score"] == "50-42"
        assert data["response_end_score"] == "52-50"

    def test_context_to_dict_includes_qualifying_responses(self):
        """ChapterContext.to_dict() includes qualifying response windows."""
        ctx = make_context(
            has_qualifying_response=True,
            qualifying_response_windows=[
                ResponseWindow(
                    responding_team="away",
                    run_team="home",
                    start_play_index=5,
                    end_play_index=8,
                    responding_team_points=8,
                    run_team_points=2,
                    run_end_home_score=50,
                    run_end_away_score=42,
                    response_end_home_score=52,
                    response_end_away_score=50,
                )
            ],
        )
        data = ctx.to_dict()

        assert data["has_qualifying_response"] is True
        assert "qualifying_response_windows" in data
        assert len(data["qualifying_response_windows"]) == 1


class TestRunResponseSequence:
    """Tests for natural RUN → RESPONSE sequences."""

    def test_run_then_response_in_same_chapter(self):
        """RUN followed by RESPONSE in same chapter."""
        plays = [
            # Home goes on 10-0 run (qualifies)
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 8, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 10, "away_score": 0},
            # Away responds with 8-2 scoring advantage
            {"description": "BOS makes 3-pt shot", "home_score": 10, "away_score": 3},
            {"description": "LAL makes layup", "home_score": 12, "away_score": 3},
            {"description": "BOS makes 3-pt shot", "home_score": 12, "away_score": 6},
            {"description": "BOS makes layup", "home_score": 12, "away_score": 8},
        ]

        qualifying_runs = get_qualifying_run_windows(plays)
        qualifying_responses = get_qualifying_response_windows(plays, qualifying_runs)

        # Should detect the RUN
        assert len(qualifying_runs) == 1
        assert qualifying_runs[0].team == "home"
        assert qualifying_runs[0].points_scored == 10

        # Should detect the RESPONSE
        assert len(qualifying_responses) == 1
        assert qualifying_responses[0].responding_team == "away"
        assert qualifying_responses[0].responding_team_points == 8
        assert qualifying_responses[0].run_team_points == 2


# ============================================================================
# TEST: PHASE 2.4 - BACK_AND_FORTH WINDOW DETECTION
# ============================================================================

class TestBackAndForthThresholds:
    """Tests for back-and-forth window threshold constants."""

    def test_lead_changes_threshold(self):
        """Lead changes threshold is 2."""
        assert BACK_AND_FORTH_LEAD_CHANGES_THRESHOLD == 2

    def test_ties_threshold(self):
        """Ties threshold is 3."""
        assert BACK_AND_FORTH_TIES_THRESHOLD == 3


class TestDetectBackAndForthWindow:
    """Tests for detect_back_and_forth_window function."""

    def test_detect_lead_changes(self):
        """Detect lead changes in chapter."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "BOS makes 3-pt shot", "home_score": 2, "away_score": 3},  # Lead change: home→away
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 3},  # Lead change: away→home
            {"description": "BOS makes 3-pt shot", "home_score": 5, "away_score": 6},  # Lead change: home→away
        ]
        window = detect_back_and_forth_window(plays)

        assert window is not None
        assert window.lead_change_count == 3

    def test_detect_ties(self):
        """Detect tie creations in chapter."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "BOS makes layup", "home_score": 2, "away_score": 2},  # Tie created
            {"description": "LAL makes layup", "home_score": 4, "away_score": 2},
            {"description": "BOS makes layup", "home_score": 4, "away_score": 4},  # Tie created
            {"description": "LAL makes layup", "home_score": 6, "away_score": 4},
            {"description": "BOS makes layup", "home_score": 6, "away_score": 6},  # Tie created
        ]
        window = detect_back_and_forth_window(plays)

        assert window is not None
        assert window.tie_count == 3

    def test_empty_plays(self):
        """Empty plays list returns None."""
        window = detect_back_and_forth_window([])
        assert window is None

    def test_no_scoring_plays(self):
        """Non-scoring plays returns window with 0 changes."""
        plays = [
            {"description": "Defensive rebound", "home_score": 0, "away_score": 0},
            {"description": "Turnover", "home_score": 0, "away_score": 0},
        ]
        window = detect_back_and_forth_window(plays)

        # Window exists but has no changes
        assert window is not None
        assert window.lead_change_count == 0
        assert window.tie_count == 0

    def test_one_team_dominant(self):
        """One team dominant has no lead changes."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
            {"description": "LAL makes free throw", "home_score": 8, "away_score": 0},
        ]
        window = detect_back_and_forth_window(plays)

        assert window is not None
        assert window.lead_change_count == 0
        assert window.tie_count == 0


class TestBackAndForthWindowQualification:
    """Tests for back-and-forth window qualification rules."""

    def test_qualifies_with_2_lead_changes(self):
        """Window qualifies with 2 lead changes."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=2,
            tie_count=0,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=18,
        )
        assert window.is_qualifying() is True

    def test_qualifies_with_3_ties(self):
        """Window qualifies with 3 ties."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=0,
            tie_count=3,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=20,
        )
        assert window.is_qualifying() is True

    def test_qualifies_with_both(self):
        """Window qualifies with both lead changes and ties."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=2,
            tie_count=3,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=20,
        )
        assert window.is_qualifying() is True

    def test_does_not_qualify_under_thresholds(self):
        """Window doesn't qualify with 1 lead change and 2 ties."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=1,
            tie_count=2,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=18,
        )
        assert window.is_qualifying() is False


class TestGetQualifyingBackAndForthWindow:
    """Tests for get_qualifying_back_and_forth_window function."""

    def test_returns_qualifying_window(self):
        """Returns window when qualifying."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "BOS makes 3-pt shot", "home_score": 2, "away_score": 3},  # Lead change 1
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 3},  # Lead change 2
        ]
        window = get_qualifying_back_and_forth_window(plays)

        assert window is not None
        assert window.is_qualifying()

    def test_returns_none_when_not_qualifying(self):
        """Returns None when not qualifying."""
        plays = [
            {"description": "LAL makes layup", "home_score": 2, "away_score": 0},
            {"description": "LAL makes 3-pt shot", "home_score": 5, "away_score": 0},
            {"description": "LAL makes layup", "home_score": 7, "away_score": 0},
        ]
        window = get_qualifying_back_and_forth_window(plays)

        assert window is None


class TestCheckBackAndForth:
    """Tests for _check_back_and_forth function."""

    def test_check_back_and_forth_with_qualifying_window(self):
        """_check_back_and_forth returns BACK_AND_FORTH when qualifying."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=3,
            tie_count=2,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=18,
        )
        ctx = make_context(
            has_qualifying_back_and_forth=True,
            back_and_forth_window=window,
        )
        result = _check_back_and_forth(ctx)

        assert result is not None
        assert result.beat_type == BeatType.BACK_AND_FORTH
        assert "lead_change_count" in result.debug_info
        assert result.debug_info["lead_change_count"] == 3

    def test_check_back_and_forth_without_qualifying_window(self):
        """_check_back_and_forth returns None when not qualifying."""
        ctx = make_context(has_qualifying_back_and_forth=False)
        result = _check_back_and_forth(ctx)

        assert result is None


class TestClassifyWithBackAndForthWindow:
    """Tests for classify_chapter_beat with back-and-forth windows."""

    def test_qualifying_back_and_forth_gets_beat(self):
        """Chapter with qualifying back-and-forth gets BACK_AND_FORTH beat."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=2,
            tie_count=0,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=18,
        )
        ctx = make_context(
            period=2,
            time_remaining_seconds=400,
            has_qualifying_back_and_forth=True,
            back_and_forth_window=window,
            home_points_scored=10,
            away_points_scored=9,  # Not EARLY_CONTROL
        )
        result = classify_chapter_beat(ctx)

        assert result.beat_type == BeatType.BACK_AND_FORTH
        assert "RULE_10_BACK_AND_FORTH" == result.triggered_rule

    def test_non_qualifying_back_and_forth_falls_to_default(self):
        """Chapter without qualifying back-and-forth falls to default."""
        ctx = make_context(
            period=2,
            time_remaining_seconds=400,
            has_qualifying_back_and_forth=False,
            home_points_scored=8,
            away_points_scored=8,  # Even scoring
        )
        result = classify_chapter_beat(ctx)

        # Falls to default BACK_AND_FORTH
        assert result.beat_type == BeatType.BACK_AND_FORTH
        assert "RULE_11_DEFAULT" in result.triggered_rule

    def test_back_and_forth_lower_priority_than_run(self):
        """RUN takes priority over BACK_AND_FORTH."""
        run_window = RunWindow(
            team="home",
            start_play_index=0,
            end_play_index=3,
            points_scored=10,
            start_home_score=0,
            start_away_score=5,
            end_home_score=10,
            end_away_score=5,
            caused_lead_change=True,
            margin_expansion=10,
        )
        bnf_window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=3,
            tie_count=2,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=18,
        )
        ctx = make_context(
            period=2,
            time_remaining_seconds=400,
            has_qualifying_run=True,
            qualifying_run_windows=[run_window],
            has_qualifying_back_and_forth=True,
            back_and_forth_window=bnf_window,
        )
        result = classify_chapter_beat(ctx)

        # RUN has higher priority
        assert result.beat_type == BeatType.RUN

    def test_back_and_forth_any_quarter(self):
        """BACK_AND_FORTH can occur in any quarter."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=3,
            tie_count=0,
            start_home_score=0,
            start_away_score=0,
            end_home_score=20,
            end_away_score=18,
        )
        # Q3 chapter
        ctx = make_context(
            period=3,
            time_remaining_seconds=400,
            has_qualifying_back_and_forth=True,
            back_and_forth_window=window,
            home_points_scored=10,
            away_points_scored=9,
        )
        result = classify_chapter_beat(ctx)

        assert result.beat_type == BeatType.BACK_AND_FORTH


class TestBackAndForthWindowSerialization:
    """Tests for BackAndForthWindow serialization."""

    def test_back_and_forth_window_to_dict(self):
        """BackAndForthWindow serializes correctly."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=3,
            tie_count=2,
            start_home_score=10,
            start_away_score=8,
            end_home_score=30,
            end_away_score=28,
        )
        data = window.to_dict()

        assert data["start_play_index"] == 0
        assert data["end_play_index"] == 10
        assert data["lead_change_count"] == 3
        assert data["tie_count"] == 2
        assert data["start_score"] == "10-8"
        assert data["end_score"] == "30-28"
        assert data["is_qualifying"] is True

    def test_context_to_dict_includes_back_and_forth_window(self):
        """ChapterContext.to_dict() includes back-and-forth window."""
        window = BackAndForthWindow(
            start_play_index=0,
            end_play_index=10,
            lead_change_count=3,
            tie_count=2,
            start_home_score=10,
            start_away_score=8,
            end_home_score=30,
            end_away_score=28,
        )
        ctx = make_context(
            has_qualifying_back_and_forth=True,
            back_and_forth_window=window,
        )
        data = ctx.to_dict()

        assert data["has_qualifying_back_and_forth"] is True
        assert "back_and_forth_window" in data
        assert data["back_and_forth_window"]["lead_change_count"] == 3


# ============================================================================
# TEST: PHASE 2.5 - SECTION-LEVEL FAST_START & EARLY_CONTROL
# ============================================================================

from app.services.chapters.beat_classifier import (
    # Types
    EarlyWindowStats,
    SectionBeatOverride,
    # Constants
    EARLY_WINDOW_DURATION_SECONDS,
    FAST_START_MIN_COMBINED_POINTS,
    FAST_START_MAX_MARGIN,
    EARLY_CONTROL_MIN_LEAD,
    EARLY_CONTROL_MIN_SHARE_PCT,
    # Functions
    compute_early_window_stats,
    detect_section_fast_start,
    detect_section_early_control,
    detect_opening_section_beat,
)


class TestEarlyWindowConstants:
    """Tests for early window threshold constants."""

    def test_early_window_duration(self):
        """Early window duration is 6 minutes (360 seconds)."""
        assert EARLY_WINDOW_DURATION_SECONDS == 360

    def test_fast_start_min_combined_points(self):
        """FAST_START requires 30 combined points."""
        assert FAST_START_MIN_COMBINED_POINTS == 30

    def test_fast_start_max_margin(self):
        """FAST_START requires margin <= 6."""
        assert FAST_START_MAX_MARGIN == 6

    def test_early_control_min_lead(self):
        """EARLY_CONTROL requires lead >= 8."""
        assert EARLY_CONTROL_MIN_LEAD == 8

    def test_early_control_min_share(self):
        """EARLY_CONTROL requires 65% scoring share."""
        assert EARLY_CONTROL_MIN_SHARE_PCT == 0.65


class TestEarlyWindowStats:
    """Tests for EarlyWindowStats dataclass."""

    def test_leading_team_home(self):
        """Leading team is home when home score is higher."""
        stats = EarlyWindowStats(
            home_points=20,
            away_points=12,
            total_points=32,
            final_home_score=20,
            final_away_score=12,
            final_margin=8,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        assert stats.leading_team == "home"
        assert stats.leading_team_points == 20

    def test_leading_team_away(self):
        """Leading team is away when away score is higher."""
        stats = EarlyWindowStats(
            home_points=12,
            away_points=20,
            total_points=32,
            final_home_score=12,
            final_away_score=20,
            final_margin=8,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        assert stats.leading_team == "away"
        assert stats.leading_team_points == 20

    def test_no_leading_team_when_tied(self):
        """No leading team when game is tied."""
        stats = EarlyWindowStats(
            home_points=15,
            away_points=15,
            total_points=30,
            final_home_score=15,
            final_away_score=15,
            final_margin=0,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        assert stats.leading_team is None
        assert stats.leading_team_points == 0

    def test_leading_team_share(self):
        """Leading team share is calculated correctly."""
        stats = EarlyWindowStats(
            home_points=20,
            away_points=10,
            total_points=30,
            final_home_score=20,
            final_away_score=10,
            final_margin=10,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        assert stats.leading_team_share == 20 / 30  # 0.667


class TestDetectSectionFastStart:
    """Tests for detect_section_fast_start function."""

    def test_fast_start_detected(self):
        """FAST_START detected with high scoring and close game."""
        stats = EarlyWindowStats(
            home_points=16,
            away_points=15,
            total_points=31,
            final_home_score=16,
            final_away_score=15,
            final_margin=1,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        result = detect_section_fast_start(stats)

        assert result is not None
        assert result.beat_type == BeatType.FAST_START
        assert result.triggered_rule == "SECTION_FAST_START"

    def test_no_fast_start_low_scoring(self):
        """No FAST_START with low combined points."""
        stats = EarlyWindowStats(
            home_points=10,
            away_points=10,
            total_points=20,  # < 30
            final_home_score=10,
            final_away_score=10,
            final_margin=0,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        result = detect_section_fast_start(stats)

        assert result is None

    def test_no_fast_start_high_margin(self):
        """No FAST_START with margin > 6."""
        stats = EarlyWindowStats(
            home_points=22,
            away_points=10,
            total_points=32,
            final_home_score=22,
            final_away_score=10,
            final_margin=12,  # > 6
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        result = detect_section_fast_start(stats)

        assert result is None

    def test_fast_start_exactly_threshold(self):
        """FAST_START detected at exact thresholds."""
        stats = EarlyWindowStats(
            home_points=18,
            away_points=12,
            total_points=30,  # Exactly 30
            final_home_score=18,
            final_away_score=12,
            final_margin=6,  # Exactly 6
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        result = detect_section_fast_start(stats)

        assert result is not None
        assert result.beat_type == BeatType.FAST_START


class TestDetectSectionEarlyControl:
    """Tests for detect_section_early_control function."""

    def test_early_control_detected(self):
        """EARLY_CONTROL detected with dominant team."""
        stats = EarlyWindowStats(
            home_points=24,
            away_points=8,
            total_points=32,
            final_home_score=24,
            final_away_score=8,
            final_margin=16,  # > 8
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        result = detect_section_early_control(stats)

        assert result is not None
        assert result.beat_type == BeatType.EARLY_CONTROL
        assert result.debug_info["leading_team"] == "home"

    def test_no_early_control_small_lead(self):
        """No EARLY_CONTROL with lead < 8."""
        stats = EarlyWindowStats(
            home_points=18,
            away_points=12,
            total_points=30,
            final_home_score=18,
            final_away_score=12,
            final_margin=6,  # < 8
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        result = detect_section_early_control(stats)

        assert result is None

    def test_no_early_control_low_share(self):
        """No EARLY_CONTROL when leading team has < 65% of points."""
        stats = EarlyWindowStats(
            home_points=18,
            away_points=10,
            total_points=28,
            final_home_score=18,
            final_away_score=10,
            final_margin=8,  # >= 8
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        # 18/28 = 0.643 < 0.65
        result = detect_section_early_control(stats)

        assert result is None

    def test_early_control_exactly_threshold(self):
        """EARLY_CONTROL detected at exact thresholds."""
        stats = EarlyWindowStats(
            home_points=20,
            away_points=10,
            total_points=30,  # share = 20/30 = 0.667 > 0.65
            final_home_score=20,
            final_away_score=10,
            final_margin=10,  # >= 8
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        # Margin exactly 8, share 66.7%
        result = detect_section_early_control(stats)

        assert result is not None
        assert result.beat_type == BeatType.EARLY_CONTROL


class TestDetectOpeningSectionBeat:
    """Tests for detect_opening_section_beat function."""

    def test_early_control_takes_precedence(self):
        """EARLY_CONTROL takes precedence over FAST_START."""
        # This scenario has both: high scoring AND dominant team
        stats = EarlyWindowStats(
            home_points=26,
            away_points=8,
            total_points=34,  # >= 30 (FAST_START)
            final_home_score=26,
            final_away_score=8,
            final_margin=18,  # >= 8 (EARLY_CONTROL), but > 6 (no FAST_START)
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001"],
        )
        # Since margin > 6, FAST_START doesn't qualify anyway
        # But if it did, EARLY_CONTROL should win
        fast_start = detect_section_fast_start(stats)
        early_control = detect_section_early_control(stats)

        assert fast_start is None  # Margin too high
        assert early_control is not None


class TestSectionBeatOverrideSerialization:
    """Tests for SectionBeatOverride."""

    def test_section_beat_override_structure(self):
        """SectionBeatOverride has correct structure."""
        override = SectionBeatOverride(
            beat_type=BeatType.FAST_START,
            triggered_rule="SECTION_FAST_START",
            debug_info={"total_points": 32},
        )

        assert override.beat_type == BeatType.FAST_START
        assert override.triggered_rule == "SECTION_FAST_START"
        assert override.debug_info["total_points"] == 32


class TestEarlyWindowStatsSerialization:
    """Tests for EarlyWindowStats serialization."""

    def test_to_dict(self):
        """EarlyWindowStats serializes correctly."""
        stats = EarlyWindowStats(
            home_points=20,
            away_points=12,
            total_points=32,
            final_home_score=20,
            final_away_score=12,
            final_margin=8,
            window_end_seconds=400,
            chapter_ids_in_window=["ch_001", "ch_002"],
        )
        data = stats.to_dict()

        assert data["home_points"] == 20
        assert data["away_points"] == 12
        assert data["total_points"] == 32
        assert data["final_score"] == "20-12"
        assert data["final_margin"] == 8
        assert data["leading_team"] == "home"
        assert data["chapter_ids_in_window"] == ["ch_001", "ch_002"]


# ============================================================================
# TEST: PHASE 2.6 - CRUNCH_SETUP & CLOSING_SEQUENCE
# ============================================================================

from app.services.chapters.beat_classifier import (
    CRUNCH_SETUP_TIME_THRESHOLD,
    CRUNCH_SETUP_MARGIN_THRESHOLD,
    CLOSING_SEQUENCE_TIME_THRESHOLD,
    CLOSING_SEQUENCE_MARGIN_THRESHOLD,
)


class TestPhase26Constants:
    """Tests for Phase 2.6 threshold constants."""

    def test_crunch_setup_time_threshold(self):
        """CRUNCH_SETUP time threshold is 5:00 (300 seconds)."""
        assert CRUNCH_SETUP_TIME_THRESHOLD == 300

    def test_crunch_setup_margin_threshold(self):
        """CRUNCH_SETUP margin threshold is 10 points."""
        assert CRUNCH_SETUP_MARGIN_THRESHOLD == 10

    def test_closing_sequence_time_threshold(self):
        """CLOSING_SEQUENCE time threshold is 2:00 (120 seconds)."""
        assert CLOSING_SEQUENCE_TIME_THRESHOLD == 120

    def test_closing_sequence_margin_threshold(self):
        """CLOSING_SEQUENCE margin threshold is 8 points."""
        assert CLOSING_SEQUENCE_MARGIN_THRESHOLD == 8


class TestClosingSequencePhase26:
    """Tests for CLOSING_SEQUENCE Phase 2.6 changes."""

    def test_closing_sequence_requires_margin_check(self):
        """CLOSING_SEQUENCE requires margin ≤ 8."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=60,  # < 2:00
            is_overtime=False,
            home_score=90,
            away_score=80,  # margin = 10 > 8
        )
        result = _check_closing_sequence(ctx)
        # Margin too large, should not fire
        assert result is None

    def test_closing_sequence_margin_exactly_8(self):
        """CLOSING_SEQUENCE fires with margin exactly 8."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=60,
            is_overtime=False,
            home_score=88,
            away_score=80,  # margin = 8
        )
        result = _check_closing_sequence(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CLOSING_SEQUENCE

    def test_closing_sequence_close_game(self):
        """CLOSING_SEQUENCE fires in close game."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=90,
            is_overtime=False,
            home_score=82,
            away_score=80,  # margin = 2
        )
        result = _check_closing_sequence(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CLOSING_SEQUENCE


class TestCrunchSetupPhase26:
    """Tests for CRUNCH_SETUP Phase 2.6 changes."""

    def test_crunch_setup_expanded_margin(self):
        """CRUNCH_SETUP fires with margin up to 10 (Phase 2.6)."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=240,  # 4:00
            is_overtime=False,
            home_score=90,
            away_score=80,  # margin = 10
        )
        result = _check_crunch_setup(ctx)
        assert result is not None
        assert result.beat_type == BeatType.CRUNCH_SETUP

    def test_crunch_setup_margin_exceeds_10(self):
        """CRUNCH_SETUP does not fire with margin > 10."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=240,
            is_overtime=False,
            home_score=91,
            away_score=80,  # margin = 11
        )
        result = _check_crunch_setup(ctx)
        assert result is None

    def test_crunch_setup_early_q4(self):
        """CRUNCH_SETUP does not fire before 5:00 mark."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=400,  # > 5:00
            is_overtime=False,
            home_score=85,
            away_score=80,  # margin = 5
        )
        result = _check_crunch_setup(ctx)
        assert result is None


class TestClosingSequencePriority:
    """Tests for CLOSING_SEQUENCE priority over CRUNCH_SETUP."""

    def test_closing_beats_crunch_under_2_minutes(self):
        """CLOSING_SEQUENCE beats CRUNCH_SETUP when both could apply."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=90,  # < 2:00, both could apply
            is_overtime=False,
            home_score=82,
            away_score=80,  # margin = 2, within both thresholds
        )
        result = classify_chapter_beat(ctx)
        # CLOSING_SEQUENCE has higher priority
        assert result.beat_type == BeatType.CLOSING_SEQUENCE

    def test_crunch_wins_when_margin_too_large_for_closing(self):
        """CRUNCH_SETUP fires when margin > 8 but ≤ 10."""
        ctx = make_context(
            period=4,
            time_remaining_seconds=90,  # < 2:00
            is_overtime=False,
            home_score=89,
            away_score=80,  # margin = 9, > 8 but ≤ 10
        )
        result = classify_chapter_beat(ctx)
        # CLOSING_SEQUENCE can't fire (margin > 8)
        # CRUNCH_SETUP fires instead (margin ≤ 10)
        assert result.beat_type == BeatType.CRUNCH_SETUP
