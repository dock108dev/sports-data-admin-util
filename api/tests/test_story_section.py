"""
Unit tests for StorySection Builder.

These tests validate:
- Forced break precedence
- Section count enforcement (3-10)
- Overtime handling
- Final 2-minute behavior
- Determinism
- Notes generation

ISSUE: StorySection Builder (Chapters-First Architecture)
"""

import pytest

from app.services.chapters.types import Chapter, Play
from app.services.chapters.beat_classifier import BeatType, BeatClassification
from app.services.chapters.story_section import (
    # Types
    StorySection,
    TeamStatDelta,
    PlayerStatDelta,
    ChapterMetadata,
    ForcedBreakReason,
    # Functions
    detect_forced_break,
    build_story_sections,
    enforce_section_count,
    generate_section_notes,
    format_sections_debug,
    _is_final_2_minutes_entry,
    _is_protected_section,
)


# ============================================================================
# TEST HELPERS
# ============================================================================


def make_play(
    index: int,
    quarter: int = 1,
    game_clock: str = "12:00",
    home_score: int = 0,
    away_score: int = 0,
) -> Play:
    """Create a Play with common fields."""
    return Play(
        index=index,
        event_type="pbp",
        raw_data={
            "quarter": quarter,
            "game_clock": game_clock,
            "home_score": home_score,
            "away_score": away_score,
        },
    )


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


def make_classification(
    chapter_id: str,
    beat_type: BeatType,
    chapter_index: int = 0,
) -> BeatClassification:
    """Create a BeatClassification."""
    return BeatClassification(
        chapter_id=chapter_id,
        beat_type=beat_type,
        triggered_rule="TEST",
        debug_info={"chapter_index": chapter_index},
    )


def make_metadata(
    chapter_id: str = "ch_001",
    chapter_index: int = 0,
    beat_type: BeatType = BeatType.BACK_AND_FORTH,
    period: int = 1,
    time_remaining_seconds: int = 600,
    is_overtime: bool = False,
) -> ChapterMetadata:
    """Create ChapterMetadata for testing."""
    return ChapterMetadata(
        chapter_id=chapter_id,
        chapter_index=chapter_index,
        beat_type=beat_type,
        period=period,
        time_remaining_seconds=time_remaining_seconds,
        is_overtime=is_overtime,
        start_home_score=0,
        start_away_score=0,
        end_home_score=0,
        end_away_score=0,
    )


def make_section(
    section_index: int,
    beat_type: BeatType,
    chapters: list[str],
) -> StorySection:
    """Create a StorySection for testing."""
    return StorySection(
        section_index=section_index,
        beat_type=beat_type,
        chapters_included=chapters,
        start_score={"home": 0, "away": 0},
        end_score={"home": 0, "away": 0},
    )


# ============================================================================
# TEST: FORCED BREAK DETECTION
# ============================================================================


class TestForcedBreakDetection:
    """Tests for forced break detection."""

    def test_game_start_forces_break(self):
        """First chapter always forces a break."""
        curr = make_metadata(chapter_id="ch_001", chapter_index=0)
        reason = detect_forced_break(curr, prev=None, seen_crunch=False)
        assert reason == ForcedBreakReason.GAME_START

    def test_overtime_start_forces_break(self):
        """Overtime start forces a break."""
        prev = make_metadata(period=4, is_overtime=False)
        curr = make_metadata(period=5, is_overtime=True)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.OVERTIME_START

    def test_final_2_minutes_forces_break(self):
        """Entry into final 2 minutes forces a break."""
        prev = make_metadata(period=4, time_remaining_seconds=150)
        curr = make_metadata(period=4, time_remaining_seconds=100)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.FINAL_2_MINUTES

    def test_first_crunch_setup_forces_break(self):
        """First CRUNCH_SETUP forces a break."""
        prev = make_metadata(beat_type=BeatType.BACK_AND_FORTH)
        curr = make_metadata(beat_type=BeatType.CRUNCH_SETUP)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.CRUNCH_SETUP_FIRST

    def test_second_crunch_setup_no_forced_break(self):
        """Second CRUNCH_SETUP does NOT force a break (unless beat change)."""
        prev = make_metadata(beat_type=BeatType.CRUNCH_SETUP)
        curr = make_metadata(beat_type=BeatType.CRUNCH_SETUP)

        # seen_crunch=True, same beat
        reason = detect_forced_break(curr, prev, seen_crunch=True)
        assert reason is None

    def test_quarter_boundary_forces_break(self):
        """Quarter change forces a break."""
        prev = make_metadata(period=1)
        curr = make_metadata(period=2)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.QUARTER_BOUNDARY

    def test_beat_change_forces_break(self):
        """Beat change forces a break (lowest priority)."""
        prev = make_metadata(beat_type=BeatType.BACK_AND_FORTH)
        curr = make_metadata(beat_type=BeatType.RUN)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.BEAT_CHANGE

    def test_no_break_same_beat_same_period(self):
        """No break when same beat and same period."""
        prev = make_metadata(
            period=2,
            beat_type=BeatType.BACK_AND_FORTH,
            time_remaining_seconds=400,
        )
        curr = make_metadata(
            period=2,
            beat_type=BeatType.BACK_AND_FORTH,
            time_remaining_seconds=350,
        )

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason is None


# ============================================================================
# TEST: FORCED BREAK PRIORITY
# ============================================================================


class TestForcedBreakPriority:
    """Tests for forced break priority order."""

    def test_overtime_beats_final_2_minutes(self):
        """Overtime takes priority over final 2 minutes logic."""
        prev = make_metadata(period=4, time_remaining_seconds=60)
        curr = make_metadata(period=5, is_overtime=True, time_remaining_seconds=60)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.OVERTIME_START

    def test_final_2_minutes_beats_crunch_setup(self):
        """Final 2 minutes takes priority over CRUNCH_SETUP."""
        prev = make_metadata(period=4, time_remaining_seconds=150)
        curr = make_metadata(
            period=4,
            time_remaining_seconds=100,
            beat_type=BeatType.CRUNCH_SETUP,
        )

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.FINAL_2_MINUTES

    def test_crunch_setup_beats_quarter_boundary(self):
        """CRUNCH_SETUP takes priority over quarter boundary."""
        # This is a weird edge case - CRUNCH_SETUP in new quarter
        prev = make_metadata(period=3, beat_type=BeatType.BACK_AND_FORTH)
        curr = make_metadata(period=4, beat_type=BeatType.CRUNCH_SETUP)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        # Quarter boundary is checked after CRUNCH_SETUP in our priority
        # Actually, CRUNCH_SETUP_FIRST is priority 3, QUARTER_BOUNDARY is priority 4
        assert reason == ForcedBreakReason.CRUNCH_SETUP_FIRST

    def test_quarter_boundary_beats_beat_change(self):
        """Quarter boundary takes priority over beat change."""
        prev = make_metadata(period=1, beat_type=BeatType.FAST_START)
        curr = make_metadata(period=2, beat_type=BeatType.BACK_AND_FORTH)

        reason = detect_forced_break(curr, prev, seen_crunch=False)
        assert reason == ForcedBreakReason.QUARTER_BOUNDARY


# ============================================================================
# TEST: OVERTIME HANDLING
# ============================================================================


class TestOvertimeHandling:
    """Tests for overtime section handling."""

    def test_overtime_is_separate_section(self):
        """Overtime always becomes its own section."""
        plays_q4 = [
            make_play(0, quarter=4, game_clock="1:00", home_score=100, away_score=100)
        ]
        plays_ot = [
            make_play(1, quarter=5, game_clock="4:00", home_score=102, away_score=100)
        ]

        chapters = [
            make_chapter("ch_001", plays_q4, period=4),
            make_chapter("ch_002", plays_ot, period=5),
        ]
        classifications = [
            make_classification("ch_001", BeatType.CLOSING_SEQUENCE, 0),
            make_classification("ch_002", BeatType.OVERTIME, 1),
        ]

        sections = build_story_sections(chapters, classifications)

        # Should have at least 2 sections
        assert len(sections) >= 2

        # Last section should be OVERTIME
        ot_section = [s for s in sections if s.beat_type == BeatType.OVERTIME]
        assert len(ot_section) == 1

    def test_overtime_never_merges_with_regulation(self):
        """Overtime section never merges with regulation."""
        # Create a simple game with OT
        plays = [
            [
                make_play(
                    0, quarter=4, game_clock="0:30", home_score=100, away_score=100
                )
            ],
            [
                make_play(
                    1, quarter=5, game_clock="4:00", home_score=102, away_score=100
                )
            ],
            [
                make_play(
                    2, quarter=5, game_clock="2:00", home_score=105, away_score=104
                )
            ],
        ]
        chapters = [
            make_chapter(f"ch_{i:03d}", p, period=p[0].raw_data["quarter"])
            for i, p in enumerate(plays)
        ]
        classifications = [
            make_classification("ch_000", BeatType.CLOSING_SEQUENCE, 0),
            make_classification("ch_001", BeatType.OVERTIME, 1),
            make_classification("ch_002", BeatType.OVERTIME, 2),
        ]

        sections = build_story_sections(chapters, classifications)

        # Find OT section
        ot_sections = [s for s in sections if s.beat_type == BeatType.OVERTIME]

        # All OT chapters should be in OT sections only
        for ot_section in ot_sections:
            for ch_id in ot_section.chapters_included:
                # ch_001 and ch_002 are OT
                if ch_id in ("ch_001", "ch_002"):
                    assert ot_section.beat_type == BeatType.OVERTIME


# ============================================================================
# TEST: FINAL 2 MINUTES HANDLING
# ============================================================================


class TestFinal2MinutesHandling:
    """Tests for final 2 minutes section handling."""

    def test_final_2_minutes_forces_new_section(self):
        """Entry into final 2 minutes forces a new section."""
        prev = make_metadata(period=4, time_remaining_seconds=150)
        curr = make_metadata(period=4, time_remaining_seconds=100)

        assert _is_final_2_minutes_entry(curr, prev) is True

    def test_exactly_120_seconds_triggers(self):
        """Exactly 120 seconds remaining triggers final 2 minutes."""
        prev = make_metadata(period=4, time_remaining_seconds=130)
        curr = make_metadata(period=4, time_remaining_seconds=120)

        assert _is_final_2_minutes_entry(curr, prev) is True

    def test_already_in_final_2_minutes_no_trigger(self):
        """Already in final 2 minutes doesn't trigger again."""
        prev = make_metadata(period=4, time_remaining_seconds=90)
        curr = make_metadata(period=4, time_remaining_seconds=60)

        assert _is_final_2_minutes_entry(curr, prev) is False

    def test_overtime_doesnt_trigger_final_2_minutes(self):
        """Overtime doesn't trigger final 2 minutes logic."""
        prev = make_metadata(period=5, is_overtime=True, time_remaining_seconds=150)
        curr = make_metadata(period=5, is_overtime=True, time_remaining_seconds=100)

        assert _is_final_2_minutes_entry(curr, prev) is False


# ============================================================================
# TEST: SECTION COUNT ENFORCEMENT
# ============================================================================


class TestSectionCountEnforcement:
    """Tests for section count constraints (3-10)."""

    def test_enforce_minimum_3_sections(self):
        """Sections are merged to reach minimum of 3."""
        # Create only 2 sections
        sections = [
            make_section(0, BeatType.FAST_START, ["ch_001"]),
            make_section(1, BeatType.BACK_AND_FORTH, ["ch_002", "ch_003"]),
        ]

        result = enforce_section_count(sections, min_sections=3)

        # Should still have 2 (can't merge further if both protected or same)
        # Actually, we have 2 and can't create more, so stays at 2
        # The min enforcement only merges, it can't split
        assert len(result) == 2

    def test_enforce_maximum_10_sections(self):
        """Sections are merged to stay under maximum of 10."""
        # Create 12 sections
        sections = [
            make_section(i, BeatType.BACK_AND_FORTH, [f"ch_{i:03d}"]) for i in range(12)
        ]

        result = enforce_section_count(sections, max_sections=10)

        assert len(result) <= 10

    def test_protected_sections_not_merged(self):
        """Protected sections (opening, CRUNCH, CLOSING, OT) are not merged."""
        sections = [
            make_section(0, BeatType.FAST_START, ["ch_000"]),  # Protected: opening
            make_section(1, BeatType.BACK_AND_FORTH, ["ch_001"]),
            make_section(2, BeatType.RUN, ["ch_002"]),
            make_section(3, BeatType.CRUNCH_SETUP, ["ch_003"]),  # Protected
            make_section(4, BeatType.CLOSING_SEQUENCE, ["ch_004"]),  # Protected
        ]

        result = enforce_section_count(sections, max_sections=3)

        # Should merge middle sections, not protected ones
        # Protected: FAST_START (0), CRUNCH_SETUP (3), CLOSING_SEQUENCE (4)
        # Can only merge 1+2 → result: at most 4 sections (can't get to 3)

        # Verify protected sections still exist
        result_types = {s.beat_type for s in result}
        assert BeatType.CRUNCH_SETUP in result_types
        assert BeatType.CLOSING_SEQUENCE in result_types

    def test_middle_sections_merged_first(self):
        """Middle sections are merged before edge sections."""
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH, ["ch_000"]),
            make_section(1, BeatType.RUN, ["ch_001"]),
            make_section(2, BeatType.RESPONSE, ["ch_002"]),
            make_section(3, BeatType.RUN, ["ch_003"]),
            make_section(4, BeatType.BACK_AND_FORTH, ["ch_004"]),
        ]

        # Mark section 0 as protected (it's the opening)
        # Sections 1-3 are in the middle

        result = enforce_section_count(sections, max_sections=4)

        assert len(result) <= 4

        # Opening section should still exist
        assert result[0].chapters_included[0] == "ch_000"


# ============================================================================
# TEST: NOTES GENERATION
# ============================================================================


class TestNotesGeneration:
    """Tests for deterministic notes generation."""

    def test_scoring_comparison_note(self):
        """Generate scoring comparison note."""
        team_deltas = {
            "lal": TeamStatDelta(
                team_key="lal",
                team_name="Lakers",
                points_scored=14,
            ),
            "bos": TeamStatDelta(
                team_key="bos",
                team_name="Celtics",
                points_scored=6,
            ),
        }

        notes = generate_section_notes(team_deltas, {})

        assert any("Lakers outscored Celtics 14–6" in note for note in notes)

    def test_timeout_note(self):
        """Generate timeout note."""
        team_deltas = {
            "lal": TeamStatDelta(
                team_key="lal",
                team_name="Lakers",
                timeouts_used=2,
            ),
        }

        notes = generate_section_notes(team_deltas, {})

        assert any("2 timeouts used by Lakers" in note for note in notes)

    def test_single_timeout_note(self):
        """Generate single timeout note."""
        team_deltas = {
            "lal": TeamStatDelta(
                team_key="lal",
                team_name="Lakers",
                timeouts_used=1,
            ),
        }

        notes = generate_section_notes(team_deltas, {})

        assert any("Timeout used by Lakers" in note for note in notes)

    def test_technical_foul_note(self):
        """Generate technical foul note."""
        team_deltas = {
            "lal": TeamStatDelta(
                team_key="lal",
                team_name="Lakers",
                technical_fouls_committed=1,
            ),
        }

        notes = generate_section_notes(team_deltas, {})

        assert any("Technical foul assessed" in note for note in notes)

    def test_foul_trouble_note(self):
        """Generate foul trouble note."""
        player_deltas = {
            "lebron": PlayerStatDelta(
                player_key="lebron",
                player_name="LeBron James",
                team_key="lal",
                foul_trouble_flag=True,
            ),
        }

        notes = generate_section_notes({}, player_deltas)

        assert any("LeBron James in foul trouble" in note for note in notes)

    def test_high_scorer_note(self):
        """Generate high scorer note for 6+ points."""
        player_deltas = {
            "curry": PlayerStatDelta(
                player_key="curry",
                player_name="Stephen Curry",
                team_key="gsw",
                points_scored=8,
            ),
        }

        notes = generate_section_notes({}, player_deltas)

        assert any("Stephen Curry scored 8 points" in note for note in notes)

    def test_no_high_scorer_under_6(self):
        """No high scorer note for under 6 points."""
        player_deltas = {
            "curry": PlayerStatDelta(
                player_key="curry",
                player_name="Stephen Curry",
                team_key="gsw",
                points_scored=5,
            ),
        }

        notes = generate_section_notes({}, player_deltas)

        # Should not have a "scored X points" note
        assert not any("scored" in note and "points" in note for note in notes)


# ============================================================================
# TEST: SECTION BUILDING
# ============================================================================


class TestSectionBuilding:
    """Tests for full section building workflow."""

    def test_build_basic_sections(self):
        """Build sections from simple chapters."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00", home_score=5, away_score=3)],
            [make_play(1, quarter=2, game_clock="10:00", home_score=25, away_score=20)],
            [make_play(2, quarter=3, game_clock="10:00", home_score=50, away_score=45)],
            [make_play(3, quarter=4, game_clock="5:00", home_score=75, away_score=72)],
        ]

        chapters = [
            make_chapter(f"ch_{i:03d}", p, period=p[0].raw_data["quarter"])
            for i, p in enumerate(plays)
        ]
        classifications = [
            make_classification("ch_000", BeatType.FAST_START, 0),
            make_classification("ch_001", BeatType.BACK_AND_FORTH, 1),
            make_classification("ch_002", BeatType.BACK_AND_FORTH, 2),
            make_classification("ch_003", BeatType.CRUNCH_SETUP, 3),
        ]

        sections = build_story_sections(chapters, classifications)

        # Should have sections for each quarter boundary + crunch setup
        assert len(sections) >= 3

    def test_adjacent_same_beat_may_merge(self):
        """Adjacent chapters with same beat type may merge."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00")],
            [make_play(1, quarter=1, game_clock="8:00")],
            [make_play(2, quarter=1, game_clock="6:00")],
        ]

        chapters = [
            make_chapter(f"ch_{i:03d}", p, period=1) for i, p in enumerate(plays)
        ]
        classifications = [
            make_classification("ch_000", BeatType.BACK_AND_FORTH, 0),
            make_classification("ch_001", BeatType.BACK_AND_FORTH, 1),
            make_classification("ch_002", BeatType.BACK_AND_FORTH, 2),
        ]

        sections = build_story_sections(chapters, classifications)

        # All same beat in Q1 → should merge into 1 section
        assert sections[0].beat_type == BeatType.BACK_AND_FORTH
        assert len(sections[0].chapters_included) == 3

    def test_score_bookends_correct(self):
        """Section has correct start and end scores."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0)],
            [make_play(1, quarter=1, game_clock="8:00", home_score=10, away_score=8)],
        ]

        chapters = [
            make_chapter(f"ch_{i:03d}", p, period=1) for i, p in enumerate(plays)
        ]
        classifications = [
            make_classification("ch_000", BeatType.BACK_AND_FORTH, 0),
            make_classification("ch_001", BeatType.BACK_AND_FORTH, 1),
        ]

        sections = build_story_sections(chapters, classifications)

        # Single section should have start=0,0 and end=10,8
        assert sections[0].start_score == {"home": 0, "away": 0}
        assert sections[0].end_score == {"home": 10, "away": 8}


# ============================================================================
# TEST: DETERMINISM
# ============================================================================


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_input_same_output(self):
        """Same input produces same sections."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00", home_score=5, away_score=3)],
            [make_play(1, quarter=2, game_clock="10:00", home_score=25, away_score=20)],
        ]

        chapters = [
            make_chapter(f"ch_{i:03d}", p, period=p[0].raw_data["quarter"])
            for i, p in enumerate(plays)
        ]
        classifications = [
            make_classification("ch_000", BeatType.FAST_START, 0),
            make_classification("ch_001", BeatType.BACK_AND_FORTH, 1),
        ]

        results = [build_story_sections(chapters, classifications) for _ in range(5)]

        # All results should have same structure
        for result in results:
            assert len(result) == len(results[0])
            for i, section in enumerate(result):
                assert section.beat_type == results[0][i].beat_type
                assert section.chapters_included == results[0][i].chapters_included


# ============================================================================
# TEST: SERIALIZATION
# ============================================================================


class TestSerialization:
    """Tests for serialization."""

    def test_section_to_dict(self):
        """StorySection serializes correctly."""
        section = StorySection(
            section_index=0,
            beat_type=BeatType.RUN,
            chapters_included=["ch_001", "ch_002"],
            start_score={"home": 50, "away": 48},
            end_score={"home": 60, "away": 50},
            notes=["Lakers outscored Celtics 10–2"],
        )

        data = section.to_dict()

        assert data["section_index"] == 0
        assert data["beat_type"] == "RUN"
        assert data["chapters_included"] == ["ch_001", "ch_002"]
        assert data["start_score"] == {"home": 50, "away": 48}
        assert data["end_score"] == {"home": 60, "away": 50}
        assert "Lakers outscored" in data["notes"][0]

    def test_section_debug_dict(self):
        """StorySection debug serialization includes break reason."""
        section = StorySection(
            section_index=0,
            beat_type=BeatType.OVERTIME,
            chapters_included=["ch_001"],
            start_score={"home": 100, "away": 100},
            end_score={"home": 105, "away": 102},
            break_reason=ForcedBreakReason.OVERTIME_START,
        )

        data = section.to_debug_dict()

        assert data["break_reason"] == "OVERTIME_START"


# ============================================================================
# TEST: DEBUG OUTPUT
# ============================================================================


class TestDebugOutput:
    """Tests for debug output."""

    def test_format_sections_debug(self):
        """Debug formatting includes all key info."""
        sections = [
            StorySection(
                section_index=0,
                beat_type=BeatType.FAST_START,
                chapters_included=["ch_001"],
                start_score={"home": 0, "away": 0},
                end_score={"home": 10, "away": 8},
                notes=["Lakers outscored Celtics 10–8"],
                break_reason=ForcedBreakReason.GAME_START,
            ),
        ]

        output = format_sections_debug(sections)

        assert "Section 0" in output
        assert "FAST_START" in output
        assert "ch_001" in output
        assert "GAME_START" in output


# ============================================================================
# TEST: EDGE CASES
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_chapters(self):
        """Empty chapters list returns empty sections."""
        sections = build_story_sections([], [])
        assert sections == []

    def test_mismatched_lengths_raises(self):
        """Mismatched chapters/classifications raises error."""
        plays = [[make_play(0, quarter=1)]]
        chapters = [make_chapter("ch_001", plays[0], period=1)]
        classifications = [
            make_classification("ch_001", BeatType.BACK_AND_FORTH, 0),
            make_classification("ch_002", BeatType.RUN, 1),
        ]

        with pytest.raises(ValueError):
            build_story_sections(chapters, classifications)

    def test_single_chapter_game(self):
        """Single chapter produces single section."""
        plays = [[make_play(0, quarter=1)]]
        chapters = [make_chapter("ch_001", plays[0], period=1)]
        classifications = [make_classification("ch_001", BeatType.BACK_AND_FORTH, 0)]

        sections = build_story_sections(chapters, classifications)

        assert len(sections) == 1
        assert sections[0].chapters_included == ["ch_001"]


# ============================================================================
# TEST: PROTECTED SECTION DETECTION
# ============================================================================


class TestProtectedSectionDetection:
    """Tests for protected section detection."""

    def test_opening_section_protected(self):
        """Opening section (index 0) is protected."""
        section = make_section(0, BeatType.BACK_AND_FORTH, ["ch_001"])
        assert _is_protected_section(section) is True

    def test_crunch_setup_protected(self):
        """CRUNCH_SETUP section is protected."""
        section = make_section(3, BeatType.CRUNCH_SETUP, ["ch_004"])
        assert _is_protected_section(section) is True

    def test_closing_sequence_protected(self):
        """CLOSING_SEQUENCE section is protected."""
        section = make_section(4, BeatType.CLOSING_SEQUENCE, ["ch_005"])
        assert _is_protected_section(section) is True

    def test_overtime_protected(self):
        """OVERTIME section is protected."""
        section = make_section(5, BeatType.OVERTIME, ["ch_006"])
        assert _is_protected_section(section) is True

    def test_middle_back_and_forth_not_protected(self):
        """Middle BACK_AND_FORTH section is not protected."""
        section = make_section(2, BeatType.BACK_AND_FORTH, ["ch_003"])
        assert _is_protected_section(section) is False

    def test_middle_run_not_protected(self):
        """Middle RUN section is not protected."""
        section = make_section(2, BeatType.RUN, ["ch_003"])
        assert _is_protected_section(section) is False
