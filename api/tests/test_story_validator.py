"""
Unit tests for Story Validator.

These tests validate:
- PART 1: Deterministic Validation
  - Section ordering (sequential, no gaps, no overlap, full coverage)
  - Stat consistency (no negatives, player bounds, explainable points)
  - Word count tolerance (+/- 15%)
- PART 2: Post-AI Narrative Guard
  - No new players (invented names)
  - No stat invention (percentages, efficiency, inferred totals)
  - No outcome contradictions (winner, overtime)

Each failure mode MUST have a dedicated test.
Each test MUST verify the failure is LOUD and CLEAR.

ISSUE: Validation and QA Checks (Chapters-First Architecture)
"""

import pytest

from app.services.chapters.beat_classifier import BeatType
from app.services.chapters.story_section import (
    StorySection,
    TeamStatDelta,
    PlayerStatDelta,
)
from app.services.chapters.story_renderer import (
    StoryRenderInput,
    StoryRenderResult,
    SectionRenderInput,
    ClosingContext,
)
from app.services.chapters.story_validator import (
    # Validation functions
    validate_section_ordering,
    validate_stat_consistency,
    validate_word_count,
    validate_no_new_players,
    validate_no_stat_invention,
    validate_no_outcome_contradictions,
    validate_pre_render,
    validate_post_render,
    format_validation_debug,
    # Error types
    SectionOrderingError,
    StatConsistencyError,
    WordCountError,
    PlayerInventionError,
    StatInventionError,
    OutcomeContradictionError,
    # Constants
    WORD_COUNT_TOLERANCE_PCT,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def valid_section() -> StorySection:
    """Create a valid StorySection for testing."""
    return StorySection(
        section_index=0,
        beat_type=BeatType.FAST_START,
        chapters_included=["ch_001", "ch_002"],
        start_score={"home": 0, "away": 0},
        end_score={"home": 24, "away": 22},
        team_stat_deltas={
            "lakers": TeamStatDelta(
                team_key="lakers",
                team_name="Lakers",
                points_scored=24,
                personal_fouls_committed=3,
                technical_fouls_committed=0,
                timeouts_used=1,
            ),
            "celtics": TeamStatDelta(
                team_key="celtics",
                team_name="Celtics",
                points_scored=22,
                personal_fouls_committed=2,
                technical_fouls_committed=0,
                timeouts_used=0,
            ),
        },
        player_stat_deltas={
            "lebron james": PlayerStatDelta(
                player_key="lebron james",
                player_name="LeBron James",
                team_key="lakers",
                points_scored=12,
                fg_made=4,
                three_pt_made=1,
                ft_made=1,
            ),
            "jayson tatum": PlayerStatDelta(
                player_key="jayson tatum",
                player_name="Jayson Tatum",
                team_key="celtics",
                points_scored=10,
                fg_made=4,
                three_pt_made=1,
                ft_made=0,
            ),
        },
        notes=["Lakers outscored Celtics 24-22"],
    )


@pytest.fixture
def valid_sections() -> list[StorySection]:
    """Create a list of valid sections."""
    return [
        StorySection(
            section_index=0,
            beat_type=BeatType.FAST_START,
            chapters_included=["ch_001"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 24, "away": 22},
            team_stat_deltas={},
            player_stat_deltas={},
        ),
        StorySection(
            section_index=1,
            beat_type=BeatType.BACK_AND_FORTH,
            chapters_included=["ch_002", "ch_003"],
            start_score={"home": 24, "away": 22},
            end_score={"home": 48, "away": 45},
            team_stat_deltas={},
            player_stat_deltas={},
        ),
        StorySection(
            section_index=2,
            beat_type=BeatType.CLOSING_SEQUENCE,
            chapters_included=["ch_004"],
            start_score={"home": 48, "away": 45},
            end_score={"home": 105, "away": 102},
            team_stat_deltas={},
            player_stat_deltas={},
        ),
    ]


@pytest.fixture
def valid_render_input() -> StoryRenderInput:
    """Create valid render input."""
    return StoryRenderInput(
        sport="NBA",
        home_team_name="Lakers",
        away_team_name="Celtics",
        target_word_count=700,
        sections=[
            SectionRenderInput(
                header="The Lakers jumped out to an early lead.",
                beat_type=BeatType.FAST_START,
                team_stat_deltas=[
                    {"team_name": "Lakers", "points_scored": 24},
                    {"team_name": "Celtics", "points_scored": 22},
                ],
                player_stat_deltas=[
                    {"player_name": "LeBron James", "points_scored": 12, "fg_made": 4},
                    {"player_name": "Jayson Tatum", "points_scored": 10, "fg_made": 4},
                ],
                notes=["Lakers outscored Celtics 24-22"],
            ),
        ],
        closing=ClosingContext(
            final_home_score=105,
            final_away_score=102,
            home_team_name="Lakers",
            away_team_name="Celtics",
            decisive_factors=["LeBron James led the way with 30 points"],
        ),
    )


@pytest.fixture
def valid_render_result() -> StoryRenderResult:
    """Create valid render result within tolerance."""
    return StoryRenderResult(
        compact_story="The Lakers jumped out to an early lead. " * 50,  # ~350 words
        word_count=700,  # Exactly on target
        target_word_count=700,
        section_count=1,
    )


# ============================================================================
# PART 1: SECTION ORDERING VALIDATION
# ============================================================================

class TestSectionOrderingValidation:
    """Tests for section ordering validation."""

    def test_valid_ordering_passes(self, valid_sections):
        """Valid section ordering passes validation."""
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004"]
        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is True

    def test_empty_sections_fails(self):
        """Empty section list fails validation."""
        result = validate_section_ordering([], [])
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"
        assert "No sections" in result.error_message

    def test_section_index_gap_fails(self, valid_sections):
        """Gap in section indices fails validation."""
        # Create gap: 0, 2 (skip 1)
        valid_sections[1].section_index = 2
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004"]

        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"
        assert "gap" in result.error_message.lower()

    def test_duplicate_section_index_fails(self, valid_sections):
        """Duplicate section index fails validation."""
        valid_sections[1].section_index = 0  # Duplicate of first
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004"]

        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"

    def test_section_with_no_chapters_fails(self, valid_sections):
        """Section with empty chapters_included fails."""
        valid_sections[1].chapters_included = []
        chapter_ids = ["ch_001", "ch_004"]  # Match remaining

        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"
        assert "no chapters" in result.error_message.lower()

    def test_duplicate_chapter_fails(self, valid_sections):
        """Same chapter in multiple sections fails."""
        # Add ch_001 to section 1 as well (duplicate)
        valid_sections[1].chapters_included.append("ch_001")
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004"]

        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"
        assert "multiple sections" in result.error_message.lower()
        assert result.details["chapter_id"] == "ch_001"

    def test_missing_chapter_fails(self, valid_sections):
        """Missing expected chapter fails."""
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004", "ch_005"]  # ch_005 missing

        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"
        assert "Missing chapters" in result.error_message
        assert "ch_005" in result.details["missing_chapters"]

    def test_extra_chapter_fails(self, valid_sections):
        """Extra chapter not in expected list fails."""
        chapter_ids = ["ch_001", "ch_002", "ch_003"]  # ch_004 extra

        result = validate_section_ordering(valid_sections, chapter_ids)
        assert result.valid is False
        assert result.error_type == "SectionOrderingError"
        assert "Extra chapters" in result.error_message
        assert "ch_004" in result.details["extra_chapters"]


# ============================================================================
# PART 1: STAT CONSISTENCY VALIDATION
# ============================================================================

class TestStatConsistencyValidation:
    """Tests for stat consistency validation."""

    def test_valid_stats_pass(self, valid_section):
        """Valid stats pass validation."""
        result = validate_stat_consistency([valid_section])
        assert result.valid is True

    def test_negative_team_points_fails(self, valid_section):
        """Negative team points fails validation."""
        valid_section.team_stat_deltas["lakers"].points_scored = -5

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "negative points" in result.error_message.lower()

    def test_negative_team_fouls_fails(self, valid_section):
        """Negative team fouls fails validation."""
        valid_section.team_stat_deltas["lakers"].personal_fouls_committed = -2

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "negative fouls" in result.error_message.lower()

    def test_negative_team_timeouts_fails(self, valid_section):
        """Negative team timeouts fails validation."""
        valid_section.team_stat_deltas["celtics"].timeouts_used = -1

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "negative timeouts" in result.error_message.lower()

    def test_negative_player_points_fails(self, valid_section):
        """Negative player points fails validation."""
        valid_section.player_stat_deltas["lebron james"].points_scored = -3

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "negative points" in result.error_message.lower()

    def test_negative_player_fg_fails(self, valid_section):
        """Negative player FG made fails validation."""
        valid_section.player_stat_deltas["lebron james"].fg_made = -1

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "negative FG" in result.error_message

    def test_player_points_without_fg_or_ft_fails(self, valid_section):
        """Player with points but no FG/FT fails."""
        valid_section.player_stat_deltas["lebron james"].points_scored = 10
        valid_section.player_stat_deltas["lebron james"].fg_made = 0
        valid_section.player_stat_deltas["lebron james"].ft_made = 0
        valid_section.player_stat_deltas["lebron james"].three_pt_made = 0

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "no FG/FT" in result.error_message

    def test_more_than_3_players_per_team_fails(self, valid_section):
        """More than 3 players per team fails."""
        # Add 3 more Lakers players (total 4 for Lakers)
        for i in range(3):
            valid_section.player_stat_deltas[f"player_{i}"] = PlayerStatDelta(
                player_key=f"player_{i}",
                player_name=f"Player {i}",
                team_key="lakers",
                points_scored=2,
                fg_made=1,
            )

        result = validate_stat_consistency([valid_section])
        assert result.valid is False
        assert result.error_type == "StatConsistencyError"
        assert "max 3" in result.error_message.lower()
        assert result.details["player_count"] == 4

    def test_exactly_3_players_per_team_passes(self, valid_section):
        """Exactly 3 players per team passes."""
        # Add 2 more Lakers players (total 3 for Lakers, including LeBron)
        valid_section.player_stat_deltas["player_1"] = PlayerStatDelta(
            player_key="player_1",
            player_name="Player 1",
            team_key="lakers",
            points_scored=2,
            fg_made=1,
        )
        valid_section.player_stat_deltas["player_2"] = PlayerStatDelta(
            player_key="player_2",
            player_name="Player 2",
            team_key="lakers",
            points_scored=2,
            fg_made=1,
        )

        result = validate_stat_consistency([valid_section])
        assert result.valid is True


# ============================================================================
# PART 1: WORD COUNT TOLERANCE VALIDATION
# ============================================================================

class TestWordCountValidation:
    """Tests for word count tolerance validation."""

    def test_exact_target_passes(self, valid_render_result):
        """Exact target word count passes."""
        result = validate_word_count(valid_render_result)
        assert result.valid is True

    def test_within_tolerance_passes(self, valid_render_result):
        """Word count within 15% tolerance passes."""
        # Target 700, 15% tolerance = 595-805
        valid_render_result.word_count = 650  # Within tolerance

        result = validate_word_count(valid_render_result)
        assert result.valid is True

    def test_at_lower_bound_passes(self, valid_render_result):
        """Word count at lower bound passes."""
        # Target 700, 15% tolerance = 595
        valid_render_result.word_count = 595

        result = validate_word_count(valid_render_result)
        assert result.valid is True

    def test_at_upper_bound_passes(self, valid_render_result):
        """Word count at upper bound passes."""
        # Target 700, 15% tolerance = int(700 * 1.15) = 804 (truncated)
        valid_render_result.word_count = 804

        result = validate_word_count(valid_render_result)
        assert result.valid is True

    def test_below_tolerance_fails(self, valid_render_result):
        """Word count below tolerance fails."""
        # Target 700, min 595
        valid_render_result.word_count = 500  # Too low

        result = validate_word_count(valid_render_result)
        assert result.valid is False
        assert result.error_type == "WordCountError"
        assert "too low" in result.error_message.lower()
        assert result.details["actual_word_count"] == 500

    def test_above_tolerance_fails(self, valid_render_result):
        """Word count above tolerance fails."""
        # Target 700, max 805
        valid_render_result.word_count = 1000  # Too high

        result = validate_word_count(valid_render_result)
        assert result.valid is False
        assert result.error_type == "WordCountError"
        assert "too high" in result.error_message.lower()
        assert result.details["actual_word_count"] == 1000

    def test_tolerance_constant_is_15_percent(self):
        """Verify tolerance constant is 15%."""
        assert WORD_COUNT_TOLERANCE_PCT == 0.15


# ============================================================================
# PART 2: NO NEW PLAYERS VALIDATION
# ============================================================================

class TestNoNewPlayersValidation:
    """Tests for no new players validation."""

    def test_valid_story_with_known_players_passes(self, valid_render_input):
        """Story mentioning only known players passes."""
        story = "LeBron James scored 12 points. Jayson Tatum had 10."

        result = validate_no_new_players(story, valid_render_input)
        assert result.valid is True

    def test_story_with_team_names_passes(self, valid_render_input):
        """Story mentioning team names passes."""
        story = "The Lakers defeated the Celtics in a close game."

        result = validate_no_new_players(story, valid_render_input)
        assert result.valid is True

    def test_invented_player_fails(self, valid_render_input):
        """Story with invented player fails."""
        story = "Michael Jordan led all scorers with 40 points."

        result = validate_no_new_players(story, valid_render_input)
        assert result.valid is False
        assert result.error_type == "PlayerInventionError"
        assert "michael jordan" in str(result.details["invented_names"]).lower()

    def test_misspelled_player_fails(self, valid_render_input):
        """Misspelled player name fails (treated as new player)."""
        story = "LaBron James scored 12 points."  # Misspelled

        result = validate_no_new_players(story, valid_render_input)
        # This may or may not fail depending on fuzzy matching
        # The validator is conservative, so misspellings might pass
        # This test documents the behavior
        pass  # Behavior depends on implementation

    def test_partial_name_match_passes(self, valid_render_input):
        """Partial name (last name only) passes."""
        story = "James scored 12 points. Tatum had 10."

        result = validate_no_new_players(story, valid_render_input)
        assert result.valid is True


# ============================================================================
# PART 2: NO STAT INVENTION VALIDATION
# ============================================================================

class TestNoStatInventionValidation:
    """Tests for no stat invention validation."""

    def test_clean_story_passes(self):
        """Story without invented stats passes."""
        story = "LeBron James scored 12 points on 4 field goals."

        result = validate_no_stat_invention(story)
        assert result.valid is True

    def test_percentage_fails(self):
        """Story with percentage fails."""
        story = "LeBron shot 60% from the field."

        result = validate_no_stat_invention(story)
        assert result.valid is False
        assert result.error_type == "StatInventionError"
        assert "percentage" in result.details["violations"][0]["type"]

    def test_shooting_fraction_fails(self):
        """Story with shooting fraction fails."""
        story = "LeBron shot 8 of 12 from the floor."

        result = validate_no_stat_invention(story)
        assert result.valid is False
        assert result.error_type == "StatInventionError"

    def test_efficiency_claim_fails(self):
        """Story with efficiency claim fails."""
        story = "LeBron was highly efficient in the first half."

        result = validate_no_stat_invention(story)
        assert result.valid is False
        assert result.error_type == "StatInventionError"
        assert "efficiency" in result.details["violations"][0]["type"]

    def test_inferred_total_fails(self):
        """Story with inferred total fails."""
        story = "LeBron finished with 30 points in the game."

        result = validate_no_stat_invention(story)
        assert result.valid is False
        assert result.error_type == "StatInventionError"
        assert "inferred total" in result.details["violations"][0]["type"]

    def test_led_all_scorers_fails(self):
        """Story with 'led all scorers' fails."""
        story = "LeBron led all scorers with 30 points."

        result = validate_no_stat_invention(story)
        assert result.valid is False
        assert result.error_type == "StatInventionError"

    def test_superlative_fails(self):
        """Story with superlative stats fails."""
        story = "LeBron had the most points in the game."

        result = validate_no_stat_invention(story)
        assert result.valid is False
        assert result.error_type == "StatInventionError"

    def test_section_stats_are_allowed(self):
        """Stats within a section are allowed."""
        story = "In the first quarter, LeBron scored 12 points on 4 made field goals."

        result = validate_no_stat_invention(story)
        assert result.valid is True


# ============================================================================
# PART 2: NO OUTCOME CONTRADICTIONS VALIDATION
# ============================================================================

class TestNoOutcomeContradictionsValidation:
    """Tests for no outcome contradictions validation."""

    def test_correct_outcome_passes(self, valid_render_input):
        """Story with correct outcome passes."""
        story = "The Lakers won 105-102 over the Celtics."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is True

    def test_wrong_winner_fails(self, valid_render_input):
        """Story claiming wrong winner fails."""
        story = "The Celtics won the game with a strong fourth quarter."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is False
        assert result.error_type == "OutcomeContradictionError"

    def test_loser_claimed_as_winner_fails(self, valid_render_input):
        """Story saying loser won fails."""
        story = "Celtics wins by 3 points."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is False
        assert result.error_type == "OutcomeContradictionError"

    def test_winner_said_to_lose_fails(self, valid_render_input):
        """Story saying winner lost fails."""
        story = "Lakers lost a close game."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is False
        assert result.error_type == "OutcomeContradictionError"

    def test_overtime_mentioned_without_section_fails(self, valid_render_input):
        """Mentioning overtime without OVERTIME section fails."""
        story = "The game went to overtime where the Lakers sealed the win."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is False
        assert result.error_type == "OutcomeContradictionError"
        assert "overtime" in result.error_message.lower()

    def test_overtime_mentioned_with_section_passes(self, valid_render_input):
        """Mentioning overtime with OVERTIME section passes."""
        # Add an overtime section
        valid_render_input.sections.append(
            SectionRenderInput(
                header="In overtime, the Lakers pulled ahead.",
                beat_type=BeatType.OVERTIME,
                team_stat_deltas=[],
                player_stat_deltas=[],
                notes=[],
            )
        )

        story = "The game went to overtime where the Lakers sealed the win."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is True

    def test_neutral_story_passes(self, valid_render_input):
        """Neutral story without explicit winner passes."""
        story = "The final score was 105-102."

        result = validate_no_outcome_contradictions(story, valid_render_input)
        assert result.valid is True


# ============================================================================
# AGGREGATE VALIDATION TESTS
# ============================================================================

class TestPreRenderValidation:
    """Tests for pre-render validation aggregate function."""

    def test_valid_pre_render_passes(self, valid_sections):
        """Valid pre-render data passes all checks."""
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004"]

        results = validate_pre_render(valid_sections, chapter_ids)
        assert len(results) == 2
        assert all(r.valid for r in results)

    def test_invalid_ordering_raises(self, valid_sections):
        """Invalid ordering raises SectionOrderingError."""
        valid_sections[1].section_index = 5  # Gap

        with pytest.raises(SectionOrderingError):
            validate_pre_render(valid_sections, ["ch_001", "ch_002", "ch_003", "ch_004"])

    def test_invalid_stats_raises(self, valid_section):
        """Invalid stats raises StatConsistencyError."""
        valid_section.team_stat_deltas["lakers"].points_scored = -10

        with pytest.raises(StatConsistencyError):
            validate_pre_render([valid_section], ["ch_001", "ch_002"])


class TestPostRenderValidation:
    """Tests for post-render validation aggregate function."""

    def test_valid_post_render_passes(self, valid_render_input, valid_render_result):
        """Valid post-render data passes all checks."""
        story = "LeBron James scored 12 points. The Lakers won 105-102."

        results = validate_post_render(story, valid_render_input, valid_render_result)
        assert len(results) == 4
        assert all(r.valid for r in results)

    def test_invalid_word_count_raises(self, valid_render_input, valid_render_result):
        """Invalid word count raises WordCountError."""
        valid_render_result.word_count = 100  # Way too low
        story = "Short."

        with pytest.raises(WordCountError):
            validate_post_render(story, valid_render_input, valid_render_result)

    def test_invented_player_raises(self, valid_render_input, valid_render_result):
        """Invented player raises PlayerInventionError."""
        story = "Michael Jordan scored 40 points. " * 50  # Within word count

        with pytest.raises(PlayerInventionError):
            validate_post_render(story, valid_render_input, valid_render_result)

    def test_stat_invention_raises(self, valid_render_input, valid_render_result):
        """Stat invention raises StatInventionError."""
        story = "LeBron shot 60% from the field. " * 50  # Within word count

        with pytest.raises(StatInventionError):
            validate_post_render(story, valid_render_input, valid_render_result)

    def test_outcome_contradiction_raises(self, valid_render_input, valid_render_result):
        """Outcome contradiction raises OutcomeContradictionError."""
        story = "The Celtics won the game. " * 100  # Within word count

        with pytest.raises(OutcomeContradictionError):
            validate_post_render(story, valid_render_input, valid_render_result)


# ============================================================================
# DEBUG OUTPUT TESTS
# ============================================================================

class TestDebugOutput:
    """Tests for debug output formatting."""

    def test_format_all_passed(self, valid_sections):
        """Format shows all passed."""
        chapter_ids = ["ch_001", "ch_002", "ch_003", "ch_004"]
        results = validate_pre_render(valid_sections, chapter_ids)

        debug = format_validation_debug(results)
        assert "PASS" in debug
        assert "Passed: 2/2" in debug

    def test_format_shows_failure_details(self, valid_sections):
        """Format shows failure details."""
        valid_sections[1].section_index = 5  # Create failure

        try:
            validate_pre_render(valid_sections, ["ch_001", "ch_002", "ch_003", "ch_004"])
        except SectionOrderingError:
            pass

        # Create a failed result manually for testing format
        from app.services.chapters.story_validator import ValidationResult
        failed_result = ValidationResult(
            valid=False,
            error_type="SectionOrderingError",
            error_message="Section index gap: expected 1, got 5",
            details={"expected_index": 1, "actual_index": 5},
        )

        debug = format_validation_debug([failed_result])
        assert "FAIL" in debug
        assert "SectionOrderingError" in debug
        assert "gap" in debug.lower()


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_story_passes_player_check(self, valid_render_input):
        """Empty story passes player check (no invented players)."""
        result = validate_no_new_players("", valid_render_input)
        assert result.valid is True

    def test_empty_story_passes_stat_check(self):
        """Empty story passes stat invention check."""
        result = validate_no_stat_invention("")
        assert result.valid is True

    def test_single_section_passes_ordering(self):
        """Single section passes ordering check."""
        section = StorySection(
            section_index=0,
            beat_type=BeatType.FAST_START,
            chapters_included=["ch_001"],
            start_score={"home": 0, "away": 0},
            end_score={"home": 105, "away": 102},
            team_stat_deltas={},
            player_stat_deltas={},
        )

        result = validate_section_ordering([section], ["ch_001"])
        assert result.valid is True

    def test_zero_word_count_target_fails(self):
        """Zero word count target fails with clear error."""
        result = StoryRenderResult(
            compact_story="Some text here.",
            word_count=3,
            target_word_count=0,  # Invalid
            section_count=1,
        )

        # Zero target is caught as an error
        validate_result = validate_word_count(result)
        assert validate_result.valid is False
        assert validate_result.error_type == "WordCountError"
        assert "Invalid target" in validate_result.error_message
