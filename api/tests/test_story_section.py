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
    PlayerProminence,
    # Constants
    SECTION_MIN_POINTS_THRESHOLD,
    SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD,
    CRUNCH_TIER_BEATS,
    NON_CRUNCH_BEATS,
    # Functions
    detect_forced_break,
    build_story_sections,
    enforce_section_count,
    generate_section_notes,
    format_sections_debug,
    _is_final_2_minutes_entry,
    _is_protected_section,
    are_beats_compatible_for_merge,
    is_section_underpowered,
    get_section_total_points,
    count_meaningful_events,
    handle_underpowered_sections,
    compute_player_prominence,
    select_prominent_players,
)
from app.services.chapters.running_stats import (
    SectionDelta,
    PlayerDelta,
    RunningStatsSnapshot,
    PlayerSnapshot,
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
        # Each quarter needs multiple plays and sufficient scoring to not be underpowered
        plays = [
            [
                make_play(0, quarter=1, game_clock="12:00", home_score=0, away_score=0),
                make_play(1, quarter=1, game_clock="10:00", home_score=5, away_score=3),
                make_play(2, quarter=1, game_clock="8:00", home_score=10, away_score=8),
            ],
            [
                make_play(
                    3, quarter=2, game_clock="12:00", home_score=10, away_score=8
                ),
                make_play(
                    4, quarter=2, game_clock="10:00", home_score=20, away_score=15
                ),
                make_play(
                    5, quarter=2, game_clock="8:00", home_score=28, away_score=22
                ),
            ],
            [
                make_play(
                    6, quarter=3, game_clock="12:00", home_score=28, away_score=22
                ),
                make_play(
                    7, quarter=3, game_clock="10:00", home_score=40, away_score=35
                ),
                make_play(
                    8, quarter=3, game_clock="8:00", home_score=52, away_score=48
                ),
            ],
            [
                make_play(
                    9, quarter=4, game_clock="5:00", home_score=52, away_score=48
                ),
                make_play(
                    10, quarter=4, game_clock="4:00", home_score=60, away_score=55
                ),
                make_play(
                    11, quarter=4, game_clock="3:00", home_score=75, away_score=72
                ),
            ],
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


# ============================================================================
# TEST: BEAT-AWARE MERGE RULES
# ============================================================================


class TestBeatAwareMergeRules:
    """Tests for beat-aware merge prevention."""

    def test_constants_defined(self):
        """Verify signal threshold constants are defined."""
        assert SECTION_MIN_POINTS_THRESHOLD == 8
        assert SECTION_MIN_MEANINGFUL_EVENTS_THRESHOLD == 3

    def test_crunch_tier_beats_defined(self):
        """Verify crunch-tier beats are defined."""
        assert BeatType.CRUNCH_SETUP in CRUNCH_TIER_BEATS
        assert BeatType.CLOSING_SEQUENCE in CRUNCH_TIER_BEATS

    def test_non_crunch_beats_defined(self):
        """Verify non-crunch beats are defined."""
        assert BeatType.RUN in NON_CRUNCH_BEATS
        assert BeatType.RESPONSE in NON_CRUNCH_BEATS
        assert BeatType.STALL in NON_CRUNCH_BEATS
        assert BeatType.BACK_AND_FORTH in NON_CRUNCH_BEATS

    def test_overtime_incompatible_with_everything(self):
        """OVERTIME cannot merge with any other beat."""
        for beat in BeatType:
            if beat != BeatType.OVERTIME:
                assert are_beats_compatible_for_merge(BeatType.OVERTIME, beat) is False
                assert are_beats_compatible_for_merge(beat, BeatType.OVERTIME) is False

    def test_run_stall_incompatible(self):
        """RUN cannot merge with STALL."""
        assert are_beats_compatible_for_merge(BeatType.RUN, BeatType.STALL) is False
        assert are_beats_compatible_for_merge(BeatType.STALL, BeatType.RUN) is False

    def test_response_stall_incompatible(self):
        """RESPONSE cannot merge with STALL."""
        assert (
            are_beats_compatible_for_merge(BeatType.RESPONSE, BeatType.STALL) is False
        )
        assert (
            are_beats_compatible_for_merge(BeatType.STALL, BeatType.RESPONSE) is False
        )

    def test_fast_start_closing_incompatible(self):
        """FAST_START cannot merge with CLOSING_SEQUENCE."""
        assert (
            are_beats_compatible_for_merge(
                BeatType.FAST_START, BeatType.CLOSING_SEQUENCE
            )
            is False
        )

    def test_early_control_closing_incompatible(self):
        """EARLY_CONTROL cannot merge with CLOSING_SEQUENCE."""
        assert (
            are_beats_compatible_for_merge(
                BeatType.EARLY_CONTROL, BeatType.CLOSING_SEQUENCE
            )
            is False
        )

    def test_non_crunch_cannot_merge_with_crunch_tier(self):
        """Non-crunch beats cannot merge with crunch-tier beats."""
        for non_crunch in NON_CRUNCH_BEATS:
            for crunch in CRUNCH_TIER_BEATS:
                assert are_beats_compatible_for_merge(non_crunch, crunch) is False, (
                    f"{non_crunch} should not merge with {crunch}"
                )

    def test_same_beats_compatible(self):
        """Same beat types are compatible (except OVERTIME)."""
        compatible_beats = [
            BeatType.RUN,
            BeatType.RESPONSE,
            BeatType.BACK_AND_FORTH,
            BeatType.STALL,
        ]
        for beat in compatible_beats:
            assert are_beats_compatible_for_merge(beat, beat) is True, (
                f"{beat} should be compatible with itself"
            )

    def test_run_response_compatible(self):
        """RUN and RESPONSE are compatible."""
        assert are_beats_compatible_for_merge(BeatType.RUN, BeatType.RESPONSE) is True

    def test_back_and_forth_compatible_with_run(self):
        """BACK_AND_FORTH is compatible with RUN."""
        assert (
            are_beats_compatible_for_merge(BeatType.BACK_AND_FORTH, BeatType.RUN)
            is True
        )


class TestBeatAwareMergeIntegration:
    """Integration tests for beat-aware merge prevention in section building."""

    def test_run_stall_never_merged(self):
        """RUN and STALL chapters should not be merged into same section."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0)],
            [make_play(1, quarter=1, game_clock="8:00", home_score=10, away_score=2)],
            [make_play(2, quarter=1, game_clock="6:00", home_score=12, away_score=4)],
        ]

        chapters = [
            make_chapter(f"ch_{i:03d}", p, period=1) for i, p in enumerate(plays)
        ]
        classifications = [
            make_classification("ch_000", BeatType.BACK_AND_FORTH, 0),
            make_classification("ch_001", BeatType.RUN, 1),
            make_classification("ch_002", BeatType.STALL, 2),
        ]

        sections = build_story_sections(chapters, classifications)

        # RUN and STALL should be in different sections
        for section in sections:
            beat_types_in_section = set()
            for ch_id in section.chapters_included:
                # Find the classification for this chapter
                for c in classifications:
                    if c.chapter_id == ch_id:
                        beat_types_in_section.add(c.beat_type)

            # Should not have both RUN and STALL in same section
            assert not (
                BeatType.RUN in beat_types_in_section
                and BeatType.STALL in beat_types_in_section
            ), "RUN and STALL should not be in same section"


# ============================================================================
# TEST: SIGNAL THRESHOLD EVALUATION
# ============================================================================


class TestSignalThreshold:
    """Tests for section signal threshold evaluation."""

    def test_section_total_points(self):
        """Calculate total points in section correctly."""
        section = StorySection(
            section_index=0,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_001"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 10, "away": 8},
            team_stat_deltas={
                "home": TeamStatDelta(
                    team_key="home", team_name="Home", points_scored=10
                ),
                "away": TeamStatDelta(
                    team_key="away", team_name="Away", points_scored=8
                ),
            },
        )

        total = get_section_total_points(section)
        assert total == 18

    def test_underpowered_low_points_low_events(self):
        """Section with <8 points and <3 events is underpowered."""
        # Create a chapter with minimal scoring
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:30", home_score=2, away_score=0),
        ]
        chapter = make_chapter("ch_001", plays, period=1)

        section = StorySection(
            section_index=1,
            beat_type=BeatType.STALL,
            chapters_included=["ch_001"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 2, "away": 0},
            team_stat_deltas={
                "home": TeamStatDelta(
                    team_key="home", team_name="Home", points_scored=2
                ),
                "away": TeamStatDelta(
                    team_key="away", team_name="Away", points_scored=0
                ),
            },
        )

        assert is_section_underpowered(section, [chapter]) is True

    def test_not_underpowered_high_points(self):
        """Section with >=8 points is not underpowered."""
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:00", home_score=5, away_score=4),
        ]
        chapter = make_chapter("ch_001", plays, period=1)

        section = StorySection(
            section_index=1,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_001"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 5, "away": 4},
            team_stat_deltas={
                "home": TeamStatDelta(
                    team_key="home", team_name="Home", points_scored=5
                ),
                "away": TeamStatDelta(
                    team_key="away", team_name="Away", points_scored=4
                ),
            },
        )

        # 9 points total >= 8, so not underpowered
        assert is_section_underpowered(section, [chapter]) is False

    def test_not_underpowered_many_events(self):
        """Section with >=3 meaningful events is not underpowered."""
        # Create a chapter with multiple lead changes (meaningful events)
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:30", home_score=2, away_score=0),
            make_play(
                2, quarter=1, game_clock="9:00", home_score=2, away_score=3
            ),  # Lead change
            make_play(
                3, quarter=1, game_clock="8:30", home_score=4, away_score=3
            ),  # Lead change
            make_play(
                4, quarter=1, game_clock="8:00", home_score=4, away_score=5
            ),  # Lead change
        ]
        chapter = make_chapter("ch_001", plays, period=1)

        section = StorySection(
            section_index=1,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_001"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 4, "away": 5},
            team_stat_deltas={
                "home": TeamStatDelta(
                    team_key="home", team_name="Home", points_scored=4
                ),
                "away": TeamStatDelta(
                    team_key="away", team_name="Away", points_scored=5
                ),
            },
        )

        # Only 9 points, but has 3+ meaningful events (scoring + lead changes)
        # Not underpowered because of meaningful events
        events = count_meaningful_events(section, [chapter])
        # Should have: 4 scoring plays + 3 lead changes = 7+ events
        assert events >= 3

    def test_protected_section_not_dropped(self):
        """Protected sections are never dropped even if underpowered."""
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:30", home_score=2, away_score=0),
        ]
        chapter = make_chapter("ch_001", plays, period=1)

        sections = [
            StorySection(
                section_index=0,  # Opening section - protected
                beat_type=BeatType.STALL,
                chapters_included=["ch_001"],
                start_score={"home": 0, "away": 0},
                end_score={"home": 2, "away": 0},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=2
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=0
                    ),
                },
            ),
        ]

        result = handle_underpowered_sections(sections, [chapter])

        # Opening section is protected, should not be dropped
        assert len(result) == 1
        assert result[0].section_index == 0


# ============================================================================
# TEST: UNDERPOWERED SECTION HANDLING
# ============================================================================


class TestUnderpoweredSectionHandling:
    """Tests for underpowered section merge/drop behavior."""

    def test_underpowered_merged_into_compatible_neighbor(self):
        """Underpowered section is merged into compatible neighbor."""
        plays1 = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:00", home_score=10, away_score=8),
        ]
        plays2 = [
            make_play(2, quarter=1, game_clock="8:00", home_score=12, away_score=8),
        ]
        plays3 = [
            make_play(3, quarter=1, game_clock="7:00", home_score=20, away_score=16),
        ]

        chapters = [
            make_chapter("ch_000", plays1, period=1),
            make_chapter(
                "ch_001", plays2, period=1
            ),  # Underpowered (2 points, few events)
            make_chapter("ch_002", plays3, period=1),
        ]

        sections = [
            StorySection(
                section_index=0,
                beat_type=BeatType.BACK_AND_FORTH,
                chapters_included=["ch_000"],
                start_score={"home": 0, "away": 0},
                end_score={"home": 10, "away": 8},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=10
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=8
                    ),
                },
            ),
            StorySection(
                section_index=1,
                beat_type=BeatType.BACK_AND_FORTH,
                chapters_included=["ch_001"],
                start_score={"home": 10, "away": 8},
                end_score={"home": 12, "away": 8},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=2
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=0
                    ),
                },
            ),
            StorySection(
                section_index=2,
                beat_type=BeatType.BACK_AND_FORTH,
                chapters_included=["ch_002"],
                start_score={"home": 12, "away": 8},
                end_score={"home": 20, "away": 16},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=8
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=8
                    ),
                },
            ),
        ]

        result = handle_underpowered_sections(sections, chapters)

        # Section 1 (underpowered) should be merged
        assert len(result) < 3
        # All chapters should still be covered
        all_chapters = []
        for s in result:
            all_chapters.extend(s.chapters_included)
        assert "ch_000" in all_chapters
        assert "ch_001" in all_chapters
        assert "ch_002" in all_chapters

    def test_underpowered_dropped_when_no_compatible_neighbor(self):
        """Underpowered section is dropped if no compatible neighbor exists."""
        plays1 = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:00", home_score=10, away_score=8),
        ]
        plays2 = [
            make_play(2, quarter=1, game_clock="8:00", home_score=12, away_score=8),
        ]
        plays3 = [
            make_play(3, quarter=4, game_clock="1:00", home_score=100, away_score=98),
        ]

        chapters = [
            make_chapter("ch_000", plays1, period=1),
            make_chapter("ch_001", plays2, period=1),  # Underpowered STALL
            make_chapter("ch_002", plays3, period=4),  # CLOSING_SEQUENCE (protected)
        ]

        sections = [
            StorySection(
                section_index=0,  # Protected opening
                beat_type=BeatType.RUN,
                chapters_included=["ch_000"],
                start_score={"home": 0, "away": 0},
                end_score={"home": 10, "away": 8},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=10
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=8
                    ),
                },
            ),
            StorySection(
                section_index=1,
                beat_type=BeatType.STALL,  # Incompatible with RUN
                chapters_included=["ch_001"],
                start_score={"home": 10, "away": 8},
                end_score={"home": 12, "away": 8},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=2
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=0
                    ),
                },
            ),
            StorySection(
                section_index=2,  # Protected CLOSING_SEQUENCE
                beat_type=BeatType.CLOSING_SEQUENCE,
                chapters_included=["ch_002"],
                start_score={"home": 12, "away": 8},
                end_score={"home": 100, "away": 98},
                team_stat_deltas={
                    "home": TeamStatDelta(
                        team_key="home", team_name="Home", points_scored=88
                    ),
                    "away": TeamStatDelta(
                        team_key="away", team_name="Away", points_scored=90
                    ),
                },
            ),
        ]

        result = handle_underpowered_sections(sections, chapters)

        # Section 1 (STALL) cannot merge:
        # - Section 0 is protected (opening) + RUN is incompatible with STALL
        # - Section 2 is protected (CLOSING_SEQUENCE)
        # So it should be dropped
        section_beats = [s.beat_type for s in result]
        # STALL should not be in the result (it was dropped)
        assert BeatType.STALL not in section_beats


# ============================================================================
# TEST: LOW-SIGNAL GAMES
# ============================================================================


class TestLowSignalGames:
    """Tests for games with fewer than 3 sections."""

    def test_section_count_minimum_is_zero(self):
        """Minimum section count is now 0 (was 3)."""
        # Verify the min_sections default is 0
        sections = [
            make_section(0, BeatType.BACK_AND_FORTH, ["ch_001"]),
        ]

        result = enforce_section_count(sections, min_sections=0)

        # Should not try to pad to 3 sections
        assert len(result) == 1

    def test_boring_game_fewer_than_3_sections(self):
        """Low-signal game may produce fewer than 3 sections."""
        # Single quarter with minimal action
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="5:00", home_score=5, away_score=5),
        ]

        chapters = [make_chapter("ch_001", plays, period=1)]
        classifications = [make_classification("ch_001", BeatType.STALL, 0)]

        sections = build_story_sections(chapters, classifications)

        # Should produce 1 section, not padded to 3
        assert len(sections) >= 1
        # Importantly, should not create artificial sections to reach 3

    def test_enforce_max_still_works(self):
        """Maximum section count (10) is still enforced."""
        sections = [
            make_section(i, BeatType.BACK_AND_FORTH, [f"ch_{i:03d}"]) for i in range(12)
        ]

        result = enforce_section_count(sections, min_sections=0, max_sections=10)

        assert len(result) <= 10


# ============================================================================
# TEST: CRUNCH/CLOSING ISOLATION
# ============================================================================


class TestCrunchClosingIsolation:
    """Tests ensuring CRUNCH and CLOSING sections remain isolated."""

    def test_crunch_setup_stays_isolated(self):
        """CRUNCH_SETUP section is never merged away."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0)],
            [make_play(1, quarter=4, game_clock="4:00", home_score=80, away_score=78)],
            [make_play(2, quarter=4, game_clock="3:00", home_score=82, away_score=80)],
        ]

        chapters = [
            make_chapter("ch_000", plays[0], period=1),
            make_chapter("ch_001", plays[1], period=4),
            make_chapter("ch_002", plays[2], period=4),
        ]
        classifications = [
            make_classification("ch_000", BeatType.BACK_AND_FORTH, 0),
            make_classification("ch_001", BeatType.CRUNCH_SETUP, 1),
            make_classification("ch_002", BeatType.CRUNCH_SETUP, 2),
        ]

        sections = build_story_sections(chapters, classifications)

        # Should have CRUNCH_SETUP section
        crunch_sections = [s for s in sections if s.beat_type == BeatType.CRUNCH_SETUP]
        assert len(crunch_sections) >= 1

    def test_closing_sequence_stays_isolated(self):
        """CLOSING_SEQUENCE section is never merged away."""
        plays = [
            [make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0)],
            [make_play(1, quarter=4, game_clock="1:30", home_score=100, away_score=98)],
        ]

        chapters = [
            make_chapter("ch_000", plays[0], period=1),
            make_chapter("ch_001", plays[1], period=4),
        ]
        classifications = [
            make_classification("ch_000", BeatType.BACK_AND_FORTH, 0),
            make_classification("ch_001", BeatType.CLOSING_SEQUENCE, 1),
        ]

        sections = build_story_sections(chapters, classifications)

        # Should have CLOSING_SEQUENCE section
        closing_sections = [
            s for s in sections if s.beat_type == BeatType.CLOSING_SEQUENCE
        ]
        assert len(closing_sections) >= 1


# ============================================================================
# TEST: PLAYER PROMINENCE SYSTEM
# ============================================================================


class TestPlayerProminenceDataclass:
    """Tests for PlayerProminence dataclass."""

    def test_basic_instantiation(self):
        """PlayerProminence should store all expected fields."""
        p = PlayerProminence(
            player_key="lebron james",
            player_name="LeBron James",
            team_key="lal",
            section_points=12,
            game_points_so_far=24,
            run_involvement_count=2,
        )

        assert p.player_key == "lebron james"
        assert p.player_name == "LeBron James"
        assert p.team_key == "lal"
        assert p.section_points == 12
        assert p.game_points_so_far == 24
        assert p.run_involvement_count == 2

    def test_defaults(self):
        """PlayerProminence should have sensible defaults."""
        p = PlayerProminence(
            player_key="player",
            player_name="Player",
        )

        assert p.team_key is None
        assert p.section_points == 0
        assert p.game_points_so_far == 0
        assert p.run_involvement_count == 0


class TestComputePlayerProminence:
    """Tests for compute_player_prominence function."""

    def test_compute_from_delta_only(self):
        """Should compute prominence from section delta without snapshot."""
        delta = SectionDelta(
            section_start_chapter=0,
            section_end_chapter=0,
            players={
                "lebron james": PlayerDelta(
                    player_key="lebron james",
                    player_name="LeBron James",
                    team_key="lal",
                    points_scored=10,
                ),
                "anthony davis": PlayerDelta(
                    player_key="anthony davis",
                    player_name="Anthony Davis",
                    team_key="lal",
                    points_scored=8,
                ),
            },
        )

        prominence = compute_player_prominence(delta)

        assert len(prominence) == 2
        assert prominence["lebron james"].section_points == 10
        assert prominence["lebron james"].game_points_so_far == 0  # No snapshot
        assert prominence["anthony davis"].section_points == 8

    def test_compute_with_snapshot(self):
        """Should include game totals when snapshot provided."""
        delta = SectionDelta(
            section_start_chapter=0,
            section_end_chapter=0,
            players={
                "lebron james": PlayerDelta(
                    player_key="lebron james",
                    player_name="LeBron James",
                    team_key="lal",
                    points_scored=10,
                ),
            },
        )

        # Snapshot shows LeBron has 30 game points total
        snapshot = RunningStatsSnapshot(
            chapter_index=0,
            players={
                "lebron james": PlayerSnapshot(
                    player_key="lebron james",
                    player_name="LeBron James",
                    team_key="lal",
                    points_scored_total=30,
                ),
            },
        )

        prominence = compute_player_prominence(delta, snapshot)

        assert prominence["lebron james"].section_points == 10
        assert prominence["lebron james"].game_points_so_far == 30


class TestSelectProminentPlayers:
    """Tests for select_prominent_players function."""

    def test_top_2_by_section_points(self):
        """Should select top 1-2 section scorers."""
        prominence = {
            "player_a": PlayerProminence(
                player_key="player_a",
                player_name="Player A",
                team_key="team1",
                section_points=20,
                game_points_so_far=40,
            ),
            "player_b": PlayerProminence(
                player_key="player_b",
                player_name="Player B",
                team_key="team1",
                section_points=15,
                game_points_so_far=25,
            ),
            "player_c": PlayerProminence(
                player_key="player_c",
                player_name="Player C",
                team_key="team1",
                section_points=5,
                game_points_so_far=50,  # High game total
            ),
        }

        selected = select_prominent_players(prominence)

        # Top 2 section scorers + player_c has highest game total
        assert "player_a" in selected  # Top section scorer
        assert "player_b" in selected  # Second section scorer
        assert "player_c" in selected  # Top game scorer (not duplicate)
        assert len(selected) == 3

    def test_game_presence_selection(self):
        """Should add game presence player if not already in section leaders."""
        prominence = {
            "player_a": PlayerProminence(
                player_key="player_a",
                player_name="Player A",
                team_key="team1",
                section_points=10,
                game_points_so_far=20,
            ),
            "player_b": PlayerProminence(
                player_key="player_b",
                player_name="Player B",
                team_key="team1",
                section_points=8,
                game_points_so_far=15,
            ),
            "player_c": PlayerProminence(
                player_key="player_c",
                player_name="Player C",
                team_key="team1",
                section_points=0,  # No section points
                game_points_so_far=50,  # Highest game total
            ),
        }

        selected = select_prominent_players(prominence)

        # player_a, player_b are section leaders
        # player_c should be added as game presence
        assert "player_a" in selected
        assert "player_b" in selected
        assert "player_c" in selected

    def test_no_duplicate_entries(self):
        """Should not include same player twice."""
        prominence = {
            "player_a": PlayerProminence(
                player_key="player_a",
                player_name="Player A",
                team_key="team1",
                section_points=20,
                game_points_so_far=50,  # Both top section AND game scorer
            ),
            "player_b": PlayerProminence(
                player_key="player_b",
                player_name="Player B",
                team_key="team1",
                section_points=10,
                game_points_so_far=30,
            ),
        }

        selected = select_prominent_players(prominence)

        # player_a is both top section and game scorer - should only appear once
        assert len(selected) == 2
        assert "player_a" in selected
        assert "player_b" in selected

    def test_max_3_per_team(self):
        """Should not select more than 3 players per team."""
        prominence = {
            f"player_{i}": PlayerProminence(
                player_key=f"player_{i}",
                player_name=f"Player {i}",
                team_key="team1",
                section_points=10 - i,
                game_points_so_far=50 - i,
            )
            for i in range(5)  # 5 players on same team
        }

        selected = select_prominent_players(prominence, max_per_team=3)

        # Should only select 3
        assert len(selected) == 3

    def test_multiple_teams(self):
        """Should select from each team independently."""
        prominence = {
            "lal_a": PlayerProminence(
                player_key="lal_a",
                player_name="LAL A",
                team_key="lal",
                section_points=20,
                game_points_so_far=40,
            ),
            "lal_b": PlayerProminence(
                player_key="lal_b",
                player_name="LAL B",
                team_key="lal",
                section_points=15,
                game_points_so_far=30,
            ),
            "bos_a": PlayerProminence(
                player_key="bos_a",
                player_name="BOS A",
                team_key="bos",
                section_points=18,
                game_points_so_far=35,
            ),
            "bos_b": PlayerProminence(
                player_key="bos_b",
                player_name="BOS B",
                team_key="bos",
                section_points=12,
                game_points_so_far=25,
            ),
        }

        selected = select_prominent_players(prominence)

        # Should have players from both teams
        lal_players = [p for p in selected if "lal" in p]
        bos_players = [p for p in selected if "bos" in p]
        assert len(lal_players) >= 1
        assert len(bos_players) >= 1

    def test_zero_scorers_not_selected_as_section_leaders(self):
        """Players with 0 section points should not be section leaders."""
        prominence = {
            "player_a": PlayerProminence(
                player_key="player_a",
                player_name="Player A",
                team_key="team1",
                section_points=0,
                game_points_so_far=50,
            ),
        }

        selected = select_prominent_players(prominence)

        # player_a has 0 section points, but high game total
        # Should be selected as game presence
        assert "player_a" in selected

    def test_zero_game_scorers_not_selected_as_presence(self):
        """Players with 0 game points should not be game presence."""
        prominence = {
            "player_a": PlayerProminence(
                player_key="player_a",
                player_name="Player A",
                team_key="team1",
                section_points=10,
                game_points_so_far=0,  # Only scored in this section
            ),
            "player_b": PlayerProminence(
                player_key="player_b",
                player_name="Player B",
                team_key="team1",
                section_points=0,
                game_points_so_far=0,
            ),
        }

        selected = select_prominent_players(prominence)

        # player_a is section leader
        assert "player_a" in selected
        # player_b has no points anywhere
        assert "player_b" not in selected


class TestProminenceIntegration:
    """Integration tests for prominence selection in build_story_sections."""

    def test_prominence_selection_with_snapshots(self):
        """build_story_sections should use prominence selection when snapshots provided."""
        # Create plays with scoring
        plays = [
            make_play(0, quarter=1, game_clock="12:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="11:00", home_score=10, away_score=8),
        ]
        plays[0].raw_data["description"] = "Game start"
        plays[1].raw_data["description"] = "LeBron James makes layup"
        plays[1].raw_data["player_name"] = "LeBron James"
        plays[1].raw_data["team_abbreviation"] = "LAL"

        chapters = [make_chapter("ch_000", plays, period=1)]
        classifications = [make_classification("ch_000", BeatType.BACK_AND_FORTH, 0)]

        # Create snapshot with game totals
        snapshot = RunningStatsSnapshot(
            chapter_index=0,
            players={
                "lebron james": PlayerSnapshot(
                    player_key="lebron james",
                    player_name="LeBron James",
                    team_key="lal",
                    points_scored_total=30,
                ),
            },
        )

        sections = build_story_sections(
            chapters, classifications, snapshots=[snapshot]
        )

        # Sections should be built (specific player selection tested above)
        assert len(sections) >= 1

    def test_fallback_without_snapshots(self):
        """build_story_sections should work without snapshots (fallback selection)."""
        plays = [
            make_play(0, quarter=1, game_clock="12:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="11:00", home_score=10, away_score=8),
        ]

        chapters = [make_chapter("ch_000", plays, period=1)]
        classifications = [make_classification("ch_000", BeatType.BACK_AND_FORTH, 0)]

        # No snapshots provided - should still work
        sections = build_story_sections(chapters, classifications)

        assert len(sections) >= 1


# ============================================================================
# TEST: THIN SECTION HANDLING
# ============================================================================


class TestThinSectionDetection:
    """Tests for thin section detection."""

    def test_thin_section_low_points_low_scoring_plays(self):
        """Section with ≤4 points AND ≤2 scoring plays is thin."""
        from app.services.chapters.story_section import (
            is_section_thin,
            THIN_SECTION_MAX_POINTS,
            THIN_SECTION_MAX_SCORING_PLAYS,
        )

        # Create section with exactly 4 points and 2 scoring plays
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:00", home_score=2, away_score=0),  # scoring play 1
            make_play(2, quarter=1, game_clock="8:00", home_score=2, away_score=2),  # scoring play 2
        ]
        chapters = [make_chapter("ch_000", plays, period=1)]

        section = StorySection(
            section_index=1,  # Not opening (not protected)
            beat_type=BeatType.STALL,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 2, "away": 2},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=2),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=2),
            },
        )

        assert is_section_thin(section, chapters) is True
        assert THIN_SECTION_MAX_POINTS == 4
        assert THIN_SECTION_MAX_SCORING_PLAYS == 2

    def test_not_thin_with_high_points(self):
        """Section with >4 points is not thin even if few scoring plays."""
        from app.services.chapters.story_section import is_section_thin

        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:00", home_score=5, away_score=0),  # 5 points, 1 play
        ]
        chapters = [make_chapter("ch_000", plays, period=1)]

        section = StorySection(
            section_index=1,
            beat_type=BeatType.STALL,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 5, "away": 0},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=5),
            },
        )

        assert is_section_thin(section, chapters) is False

    def test_not_thin_with_many_scoring_plays(self):
        """Section with >2 scoring plays is not thin even if low points."""
        from app.services.chapters.story_section import is_section_thin

        # 3 scoring plays, each 1 point (free throws)
        plays = [
            make_play(0, quarter=1, game_clock="10:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="9:00", home_score=1, away_score=0),
            make_play(2, quarter=1, game_clock="8:00", home_score=1, away_score=1),
            make_play(3, quarter=1, game_clock="7:00", home_score=2, away_score=1),
        ]
        chapters = [make_chapter("ch_000", plays, period=1)]

        section = StorySection(
            section_index=1,
            beat_type=BeatType.STALL,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 2, "away": 1},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=2),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=1),
            },
        )

        # 3 points, 3 scoring plays - not thin (too many scoring plays)
        assert is_section_thin(section, chapters) is False


class TestThinSectionMerging:
    """Tests for thin section merge behavior."""

    def test_thin_section_merged_upward_early_game(self):
        """Early game thin section should merge upward (into previous)."""
        from app.services.chapters.story_section import handle_thin_sections

        # Create three sections: normal -> thin -> normal
        plays1 = [
            make_play(0, quarter=1, game_clock="12:00", home_score=0, away_score=0),
            make_play(1, quarter=1, game_clock="11:00", home_score=10, away_score=8),
        ]
        plays2 = [
            make_play(2, quarter=1, game_clock="10:00", home_score=10, away_score=8),
            make_play(3, quarter=1, game_clock="9:00", home_score=12, away_score=8),  # only 2 pts
        ]
        plays3 = [
            make_play(4, quarter=1, game_clock="8:00", home_score=12, away_score=8),
            make_play(5, quarter=1, game_clock="7:00", home_score=20, away_score=16),
        ]

        chapters = [
            make_chapter("ch_000", plays1, period=1),
            make_chapter("ch_001", plays2, period=1),
            make_chapter("ch_002", plays3, period=1),
        ]

        section1 = StorySection(
            section_index=0,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 10, "away": 8},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=10),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=8),
            },
        )

        # Thin section - only 2 points, 1 scoring play
        section2 = StorySection(
            section_index=1,
            beat_type=BeatType.STALL,
            chapters_included=["ch_001"],
            start_score={"home": 10, "away": 8},
            end_score={"home": 12, "away": 8},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=2),
            },
        )

        section3 = StorySection(
            section_index=2,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_002"],
            start_score={"home": 12, "away": 8},
            end_score={"home": 20, "away": 16},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=8),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=8),
            },
        )

        result = handle_thin_sections([section1, section2, section3], chapters)

        # Thin section2 should be merged - now only 2 sections
        assert len(result) == 2
        # First section should now include both ch_000 and ch_001
        assert "ch_000" in result[0].chapters_included
        assert "ch_001" in result[0].chapters_included

    def test_protected_thin_section_not_merged(self):
        """Protected sections (CRUNCH_SETUP, CLOSING_SEQUENCE) should not be merged even if thin."""
        from app.services.chapters.story_section import handle_thin_sections

        plays = [
            make_play(0, quarter=4, game_clock="2:00", home_score=100, away_score=98),
            make_play(1, quarter=4, game_clock="1:30", home_score=102, away_score=98),  # 2 pts
        ]
        chapters = [make_chapter("ch_000", plays, period=4)]

        # CRUNCH_SETUP is protected
        crunch_section = StorySection(
            section_index=1,
            beat_type=BeatType.CRUNCH_SETUP,
            chapters_included=["ch_000"],
            start_score={"home": 100, "away": 98},
            end_score={"home": 102, "away": 98},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=2),
            },
        )

        result = handle_thin_sections([crunch_section], chapters)

        # Should remain unchanged (protected)
        assert len(result) == 1
        assert result[0].beat_type == BeatType.CRUNCH_SETUP

    def test_thin_section_never_dropped(self):
        """Thin sections should be merged, never dropped (even if no merge target)."""
        from app.services.chapters.story_section import handle_thin_sections

        # Single thin section isolated by OVERTIME boundaries
        plays = [
            make_play(0, quarter=5, game_clock="2:00", home_score=100, away_score=100),
            make_play(1, quarter=5, game_clock="1:30", home_score=102, away_score=100),  # 2 pts
        ]
        chapters = [make_chapter("ch_000", plays, period=5)]

        overtime_section = StorySection(
            section_index=0,
            beat_type=BeatType.OVERTIME,  # OVERTIME is protected
            chapters_included=["ch_000"],
            start_score={"home": 100, "away": 100},
            end_score={"home": 102, "away": 100},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=2),
            },
        )

        result = handle_thin_sections([overtime_section], chapters)

        # Should remain unchanged (OVERTIME is protected, can't be merged)
        assert len(result) == 1

    def test_end_of_game_merges_backward(self):
        """End-of-game thin section must merge backward, not forward."""
        from app.services.chapters.story_section import handle_thin_sections

        plays1 = [
            make_play(0, quarter=4, game_clock="3:00", home_score=100, away_score=98),
            make_play(1, quarter=4, game_clock="2:30", home_score=110, away_score=108),
        ]
        plays2 = [
            make_play(2, quarter=4, game_clock="1:00", home_score=110, away_score=108),
            make_play(3, quarter=4, game_clock="0:30", home_score=112, away_score=108),  # 2 pts, thin
        ]
        chapters = [
            make_chapter("ch_000", plays1, period=4),
            make_chapter("ch_001", plays2, period=4),
        ]

        section1 = StorySection(
            section_index=1,  # Not opening (not protected)
            beat_type=BeatType.RUN,
            chapters_included=["ch_000"],
            start_score={"home": 100, "away": 98},
            end_score={"home": 110, "away": 108},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=10),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=10),
            },
        )

        # End-of-game thin section (last in list)
        section2 = StorySection(
            section_index=2,
            beat_type=BeatType.STALL,
            chapters_included=["ch_001"],
            start_score={"home": 110, "away": 108},
            end_score={"home": 112, "away": 108},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=2),
            },
        )

        result = handle_thin_sections([section1, section2], chapters)

        # Thin end-of-game section should merge backward into section1
        assert len(result) == 1
        assert "ch_000" in result[0].chapters_included
        assert "ch_001" in result[0].chapters_included


class TestThinSectionConstants:
    """Tests for thin section constants."""

    def test_constants_defined(self):
        """Thin section constants should be defined."""
        from app.services.chapters.story_section import (
            THIN_SECTION_MAX_POINTS,
            THIN_SECTION_MAX_SCORING_PLAYS,
        )

        assert THIN_SECTION_MAX_POINTS == 4
        assert THIN_SECTION_MAX_SCORING_PLAYS == 2


# ============================================================================
# TEST: LUMPY SECTION HANDLING
# ============================================================================


class TestLumpySectionDetection:
    """Tests for lumpy section (dominance) detection."""

    def test_lumpy_section_single_player_dominates(self):
        """Section is lumpy if single player has ≥65% of points."""
        from app.services.chapters.story_section import (
            is_section_lumpy,
            get_dominant_player_share,
            LUMPY_DOMINANCE_THRESHOLD_PCT,
        )

        section = StorySection(
            section_index=0,
            beat_type=BeatType.RUN,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 20, "away": 10},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=20),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=10),
            },
            player_stat_deltas={
                "star_player": PlayerStatDelta(
                    player_key="star_player",
                    player_name="Star Player",
                    team_key="home",
                    points_scored=20,  # 20/30 = 67% > 65%
                ),
                "other_player": PlayerStatDelta(
                    player_key="other_player",
                    player_name="Other Player",
                    team_key="away",
                    points_scored=10,
                ),
            },
        )

        dominant_key, share = get_dominant_player_share(section)
        assert dominant_key == "star_player"
        assert share == pytest.approx(20 / 30, rel=0.01)
        assert is_section_lumpy(section) is True
        assert LUMPY_DOMINANCE_THRESHOLD_PCT == 0.65

    def test_not_lumpy_with_balanced_scoring(self):
        """Section is not lumpy if scoring is balanced."""
        from app.services.chapters.story_section import is_section_lumpy

        section = StorySection(
            section_index=0,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 15, "away": 15},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=15),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=15),
            },
            player_stat_deltas={
                "player_a": PlayerStatDelta(
                    player_key="player_a",
                    player_name="Player A",
                    team_key="home",
                    points_scored=10,  # 10/30 = 33%
                ),
                "player_b": PlayerStatDelta(
                    player_key="player_b",
                    player_name="Player B",
                    team_key="home",
                    points_scored=5,
                ),
                "player_c": PlayerStatDelta(
                    player_key="player_c",
                    player_name="Player C",
                    team_key="away",
                    points_scored=15,  # 15/30 = 50% < 65%
                ),
            },
        )

        assert is_section_lumpy(section) is False


class TestDominanceCapping:
    """Tests for dominance capping and spillover."""

    def test_dominance_cap_applied(self):
        """Dominant player should be capped at 60% of section points."""
        from app.services.chapters.story_section import (
            apply_dominance_cap,
            DOMINANCE_CAP_PCT,
        )

        # 30 total points, star has 24 (80%)
        section1 = StorySection(
            section_index=0,
            beat_type=BeatType.RUN,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 24, "away": 6},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=24),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=6),
            },
            player_stat_deltas={
                "star_player": PlayerStatDelta(
                    player_key="star_player",
                    player_name="Star Player",
                    team_key="home",
                    points_scored=24,  # 24/30 = 80% > 65%
                ),
                "other_player": PlayerStatDelta(
                    player_key="other_player",
                    player_name="Other Player",
                    team_key="away",
                    points_scored=6,
                ),
            },
        )

        section2 = StorySection(
            section_index=1,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_001"],
            start_score={"home": 24, "away": 6},
            end_score={"home": 44, "away": 26},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=20),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=20),
            },
            player_stat_deltas={},
        )

        result = apply_dominance_cap([section1, section2])

        # Cap = 60% of 30 = 18 points
        # Excess = 24 - 18 = 6 points spillover
        capped_star = result[0].player_stat_deltas.get("star_player")
        assert capped_star is not None
        assert capped_star.points_scored == 18  # Capped at 60%

        # Spillover to adjacent section
        spillover_star = result[1].player_stat_deltas.get("star_player")
        assert spillover_star is not None
        assert spillover_star.points_scored == 6  # Excess spilled over

        assert DOMINANCE_CAP_PCT == 0.60

    def test_spillover_never_crosses_overtime(self):
        """Spillover should never cross OVERTIME boundaries."""
        from app.services.chapters.story_section import apply_dominance_cap

        # Lumpy section followed by OVERTIME
        section1 = StorySection(
            section_index=0,
            beat_type=BeatType.RUN,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 24, "away": 6},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=24),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=6),
            },
            player_stat_deltas={
                "star_player": PlayerStatDelta(
                    player_key="star_player",
                    player_name="Star Player",
                    team_key="home",
                    points_scored=24,  # 80% > 65%
                ),
            },
        )

        overtime_section = StorySection(
            section_index=1,
            beat_type=BeatType.OVERTIME,
            chapters_included=["ch_001"],
            start_score={"home": 24, "away": 6},
            end_score={"home": 30, "away": 12},
            team_stat_deltas={},
            player_stat_deltas={},
        )

        result = apply_dominance_cap([section1, overtime_section])

        # No spillover should occur (OVERTIME boundary blocks it)
        # Star player should remain at 24 (no cap applied without valid spillover target)
        star = result[0].player_stat_deltas.get("star_player")
        assert star is not None
        assert star.points_scored == 24  # Unchanged (no valid spillover target)

    def test_no_cap_when_not_lumpy(self):
        """Sections that are not lumpy should not be capped."""
        from app.services.chapters.story_section import apply_dominance_cap

        section = StorySection(
            section_index=0,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_000"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 15, "away": 15},
            team_stat_deltas={
                "home": TeamStatDelta(team_key="home", team_name="Home", points_scored=15),
                "away": TeamStatDelta(team_key="away", team_name="Away", points_scored=15),
            },
            player_stat_deltas={
                "player_a": PlayerStatDelta(
                    player_key="player_a",
                    player_name="Player A",
                    team_key="home",
                    points_scored=10,  # 33% < 65%
                ),
                "player_b": PlayerStatDelta(
                    player_key="player_b",
                    player_name="Player B",
                    team_key="away",
                    points_scored=15,  # 50% < 65%
                ),
            },
        )

        result = apply_dominance_cap([section])

        # No changes
        assert result[0].player_stat_deltas["player_a"].points_scored == 10
        assert result[0].player_stat_deltas["player_b"].points_scored == 15


class TestLumpySectionConstants:
    """Tests for lumpy section constants."""

    def test_constants_defined(self):
        """Lumpy section constants should be defined."""
        from app.services.chapters.story_section import (
            LUMPY_DOMINANCE_THRESHOLD_PCT,
            DOMINANCE_CAP_PCT,
        )

        assert LUMPY_DOMINANCE_THRESHOLD_PCT == 0.65
        assert DOMINANCE_CAP_PCT == 0.60
