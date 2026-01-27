"""
Story Contract Compliance Test Suite.

These tests verify that the validation layer correctly enforces
ALL requirements from docs/story_contract.md.

Tests are organized by contract section:
- Section 3: Required Fields
- Section 4: Narrative Rules
- Section 6: Explicit Non-Goals
- Section 7: Success Criteria

Each test explicitly references the contract clause it enforces.
"""

import pytest

from app.services.story.schema import (
    CondensedMoment,
    ScoreTuple,
    StoryOutput,
    SchemaValidationError,
)
from app.services.story.moment_builder import PlayData
from app.services.story.validators import (
    ContractViolation,
    ValidationResult,
    validate_story_structure,
    validate_plays_exist,
    validate_forbidden_language,
    validate_narrative_traceability,
    validate_no_future_references,
    validate_story_contract,
    validate_moment_contract,
    trace_sentence_to_plays,
    trace_narrative_to_plays,
    explain_moment_backing,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


def make_play(
    play_index: int,
    description: str,
    period: int = 1,
    game_clock: str = "10:00",
    home_score: int = 0,
    away_score: int = 0,
) -> PlayData:
    """Create a PlayData for testing."""
    return PlayData(
        play_index=play_index,
        period=period,
        game_clock=game_clock,
        description=description,
        play_type=None,
        team_id=None,
        home_score=home_score,
        away_score=away_score,
    )


def make_moment(
    play_ids: tuple[int, ...],
    explicit_ids: tuple[int, ...],
    narrative: str,
    period: int = 1,
    start_clock: str = "10:00",
    end_clock: str = "9:45",
    score_before: tuple[int, int] = (0, 0),
    score_after: tuple[int, int] = (0, 0),
) -> CondensedMoment:
    """Create a CondensedMoment for testing."""
    return CondensedMoment(
        play_ids=play_ids,
        explicitly_narrated_play_ids=explicit_ids,
        start_clock=start_clock,
        end_clock=end_clock,
        period=period,
        score_before=ScoreTuple(home=score_before[0], away=score_before[1]),
        score_after=ScoreTuple(home=score_after[0], away=score_after[1]),
        narrative=narrative,
    )


def make_valid_moment() -> tuple[CondensedMoment, list[PlayData]]:
    """Create a valid moment with matching plays for testing."""
    plays = [
        make_play(1, "Smith misses jumper", home_score=10, away_score=12),
        make_play(2, "Jones rebound", home_score=10, away_score=12),
        make_play(3, "Jones drives for layup", home_score=12, away_score=12),
    ]

    moment = make_moment(
        play_ids=(1, 2, 3),
        explicit_ids=(3,),
        narrative="Jones grabs the rebound and drives for the layup to tie the game.",
        score_before=(10, 12),
        score_after=(12, 12),
    )

    return moment, plays


def make_valid_story() -> tuple[StoryOutput, list[PlayData]]:
    """Create a valid story with matching plays for testing."""
    plays = [
        make_play(1, "Smith three-pointer", period=1, game_clock="11:30", home_score=3, away_score=0),
        make_play(2, "Jones rebound", period=1, game_clock="11:00", home_score=3, away_score=0),
        make_play(3, "Jones layup", period=1, game_clock="10:45", home_score=3, away_score=2),
        make_play(4, "Williams steal", period=1, game_clock="10:30", home_score=3, away_score=2),
        make_play(5, "Williams dunk", period=1, game_clock="10:15", home_score=3, away_score=4),
    ]

    moments = (
        make_moment(
            play_ids=(1,),
            explicit_ids=(1,),
            narrative="Smith drills the three-pointer to open the scoring.",
            period=1,
            start_clock="11:30",
            end_clock="11:30",
            score_before=(0, 0),
            score_after=(3, 0),
        ),
        make_moment(
            play_ids=(2, 3),
            explicit_ids=(3,),
            narrative="Jones pulls down the rebound and finishes with a layup.",
            period=1,
            start_clock="11:00",
            end_clock="10:45",
            score_before=(3, 0),
            score_after=(3, 2),
        ),
        make_moment(
            play_ids=(4, 5),
            explicit_ids=(4, 5),
            narrative="Williams comes up with the steal and throws down a thunderous dunk.",
            period=1,
            start_clock="10:30",
            end_clock="10:15",
            score_before=(3, 2),
            score_after=(3, 4),
        ),
    )

    story = StoryOutput(moments=moments)
    return story, plays


# =============================================================================
# CONTRACT SECTION 3: REQUIRED FIELDS
# =============================================================================


class TestRequiredFields:
    """Tests for Contract Section 3: Required Fields of a Condensed Moment."""

    def test_valid_moment_passes(self):
        """A moment with all required fields passes validation."""
        moment, plays = make_valid_moment()
        result = validate_moment_contract(moment, plays)
        assert result.valid, f"Valid moment failed: {result.violations}"

    def test_empty_play_ids_fails(self):
        """Contract: play_ids must be non-empty."""
        with pytest.raises(SchemaValidationError, match="play_ids must be non-empty"):
            make_moment(
                play_ids=(),
                explicit_ids=(1,),
                narrative="Test narrative.",
            )

    def test_empty_explicitly_narrated_play_ids_fails(self):
        """Contract: explicitly_narrated_play_ids must be non-empty."""
        with pytest.raises(
            SchemaValidationError,
            match="explicitly_narrated_play_ids must be non-empty"
        ):
            make_moment(
                play_ids=(1, 2),
                explicit_ids=(),
                narrative="Test narrative.",
            )

    def test_explicit_ids_not_subset_of_play_ids_fails(self):
        """Contract: explicitly_narrated_play_ids must be strict subset of play_ids."""
        with pytest.raises(
            SchemaValidationError,
            match="explicitly_narrated_play_ids must be subset"
        ):
            make_moment(
                play_ids=(1, 2),
                explicit_ids=(3,),  # 3 not in play_ids
                narrative="Test narrative.",
            )

    def test_empty_narrative_fails(self):
        """Contract: narrative must be non-empty."""
        with pytest.raises(SchemaValidationError, match="narrative must be non-empty"):
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="",
            )

    def test_whitespace_only_narrative_fails(self):
        """Contract: narrative must be non-empty (whitespace doesn't count)."""
        with pytest.raises(SchemaValidationError, match="narrative must be non-empty"):
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="   \n\t  ",
            )

    def test_empty_start_clock_fails(self):
        """Contract: start_clock must be valid clock."""
        with pytest.raises(SchemaValidationError, match="start_clock must be non-empty"):
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="Test narrative.",
                start_clock="",
            )

    def test_empty_end_clock_fails(self):
        """Contract: end_clock must be valid clock."""
        with pytest.raises(SchemaValidationError, match="end_clock must be non-empty"):
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="Test narrative.",
                end_clock="",
            )

    def test_invalid_period_fails(self):
        """Contract: period must be valid period number (>= 1)."""
        with pytest.raises(SchemaValidationError, match="period must be >= 1"):
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="Test narrative.",
                period=0,
            )

    def test_negative_score_fails(self):
        """Contract: scores must be non-negative."""
        with pytest.raises(
            SchemaValidationError,
            match="score.home must be non-negative"
        ):
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="Test narrative.",
                score_before=(-1, 0),
            )


# =============================================================================
# CONTRACT SECTION 4: NARRATIVE RULES
# =============================================================================


class TestNarrativeRules:
    """Tests for Contract Section 4: Narrative Rules."""

    def test_narrative_references_explicit_play(self):
        """Contract: Narrative must reference at least one explicitly narrated play."""
        moment, plays = make_valid_moment()
        result = validate_narrative_traceability(moment, plays)
        assert not result, f"Valid narrative failed: {result}"

    def test_narrative_without_explicit_play_reference_fails(self):
        """Contract: Narrative must reference explicit plays."""
        plays = [
            make_play(1, "Smith makes three-pointer"),
        ]
        moment = make_moment(
            play_ids=(1,),
            explicit_ids=(1,),
            # Narrative doesn't mention Smith or three-pointer
            narrative="The team scores to take the lead.",
        )

        result = validate_narrative_traceability(moment, plays)
        assert any("does not reference" in v for v in result), \
            f"Should fail for missing explicit play reference: {result}"

    def test_traceability_identifies_backing_plays(self):
        """Contract: 'Which plays back this sentence?' returns specific play_ids."""
        moment, plays = make_valid_moment()

        result = trace_sentence_to_plays(
            "Jones drives for the layup",
            moment,
            plays,
        )

        assert result.traceable
        assert 3 in result.matched_play_ids  # Jones drives for layup is play 3


class TestForbiddenLanguage:
    """Tests for Contract Section 6: Explicit Non-Goals."""

    def test_abstract_momentum_term_fails(self):
        """Contract: No 'momentum' (abstract narrative theme)."""
        result = validate_forbidden_language(
            "The momentum shifted in favor of the home team."
        )
        assert any("momentum" in v.lower() for v in result)

    def test_abstract_turning_point_term_fails(self):
        """Contract: No 'turning point' (abstract narrative theme)."""
        result = validate_forbidden_language(
            "This was the turning point of the game."
        )
        assert any("turning point" in v.lower() for v in result)

    def test_abstract_flow_term_fails(self):
        """Contract: No 'flow' (abstract narrative theme)."""
        result = validate_forbidden_language(
            "The game flow changed dramatically."
        )
        assert any("flow" in v.lower() for v in result)

    def test_temporal_foreshadowing_term_fails(self):
        """Contract: No retrospective narration ('little did they know')."""
        result = validate_forbidden_language(
            "Little did they know this would be their last lead."
        )
        assert any("little did they know" in v.lower() for v in result)

    def test_summary_throughout_game_term_fails(self):
        """Contract: No game-level summaries ('throughout the game')."""
        result = validate_forbidden_language(
            "Throughout the game, the defense struggled."
        )
        assert any("throughout the game" in v.lower() for v in result)

    def test_meta_in_this_moment_term_fails(self):
        """Contract: No meta-language ('in this moment')."""
        result = validate_forbidden_language(
            "In this moment, the team showed resilience."
        )
        assert any("in this moment" in v.lower() for v in result)

    def test_markdown_header_fails(self):
        """Contract: Stories have no named divisions (no headers)."""
        result = validate_forbidden_language(
            "## First Quarter\n\nThe game begins."
        )
        assert any("header" in v.lower() for v in result)

    def test_quarter_header_fails(self):
        """Contract: Stories have no named divisions."""
        result = validate_forbidden_language(
            "Quarter 1\n\nThe opening tip."
        )
        assert any("header" in v.lower() or "quarter" in v.lower() for v in result)

    def test_valid_narrative_passes(self):
        """Valid narrative without forbidden language passes."""
        result = validate_forbidden_language(
            "Smith drains the three-pointer. Jones answers with a layup."
        )
        assert not result, f"Valid narrative should pass: {result}"


# =============================================================================
# CONTRACT SECTION 7: STRUCTURAL TESTS
# =============================================================================


class TestStructuralValidation:
    """Tests for Contract Section 7: Structural Tests."""

    def test_valid_story_passes_structural_validation(self):
        """A valid story passes all structural tests."""
        story, plays = make_valid_story()
        violations = validate_story_structure(story)
        assert not violations, f"Valid story failed: {violations}"

    def test_empty_story_fails(self):
        """Contract: Story must be non-empty ordered list."""
        with pytest.raises(SchemaValidationError, match="moments must be non-empty"):
            StoryOutput(moments=())

    def test_overlapping_play_ids_fails(self):
        """Contract: No play_id appears in multiple moments."""
        moments = (
            make_moment(
                play_ids=(1, 2),
                explicit_ids=(1,),
                narrative="First moment with plays one and two.",
                start_clock="11:00",
            ),
            make_moment(
                play_ids=(2, 3),  # play_id 2 overlaps!
                explicit_ids=(3,),
                narrative="Second moment with plays two and three.",
                start_clock="10:00",
            ),
        )

        with pytest.raises(SchemaValidationError, match="play_id 2 appears"):
            StoryOutput(moments=moments)

    def test_moments_not_ordered_by_period_fails(self):
        """Contract: Moments must be ordered by game time (period)."""
        moments = (
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="Second period moment.",
                period=2,
                start_clock="10:00",
            ),
            make_moment(
                play_ids=(2,),
                explicit_ids=(2,),
                narrative="First period moment.",
                period=1,  # Should be >= 2
                start_clock="10:00",
            ),
        )

        with pytest.raises(SchemaValidationError, match="not ordered by period"):
            StoryOutput(moments=moments)

    def test_moments_not_ordered_by_clock_fails(self):
        """Contract: Moments must be ordered by clock (descending within period)."""
        moments = (
            make_moment(
                play_ids=(1,),
                explicit_ids=(1,),
                narrative="Early in period.",
                period=1,
                start_clock="5:00",  # Later in period
            ),
            make_moment(
                play_ids=(2,),
                explicit_ids=(2,),
                narrative="Start of period.",
                period=1,
                start_clock="10:00",  # Should be <= 5:00 (earlier clock)
            ),
        )

        with pytest.raises(SchemaValidationError, match="not ordered by clock"):
            StoryOutput(moments=moments)

    def test_play_ids_exist_in_source(self):
        """Contract: All play_ids must exist in source PBP."""
        story, plays = make_valid_story()
        available_ids = {p.play_index for p in plays}

        violations = validate_plays_exist(story, available_ids)
        assert not violations, f"Valid story failed existence check: {violations}"

    def test_missing_play_ids_fails(self):
        """Contract: play_ids must exist in source PBP."""
        moment = make_moment(
            play_ids=(1, 2, 99),  # 99 doesn't exist
            explicit_ids=(1,),
            narrative="Test narrative.",
        )
        story = StoryOutput(moments=(moment,))

        available_ids = {1, 2, 3}
        violations = validate_plays_exist(story, available_ids)
        assert any("99" in v and "does not exist" in v for v in violations)


# =============================================================================
# CONTRACT SECTION 7: NARRATIVE TESTS
# =============================================================================


class TestNarrativeValidation:
    """Tests for Contract Section 7: Narrative Tests."""

    def test_valid_story_passes_full_validation(self):
        """A valid story passes complete contract validation."""
        story, plays = make_valid_story()
        result = validate_story_contract(story, plays)
        assert result.valid, f"Valid story failed: {result.violations}"

    def test_no_future_references(self):
        """Contract: No narrative references future events."""
        story, plays = make_valid_story()
        violations = validate_no_future_references(story, plays)
        assert not violations, f"Valid story has future refs: {violations}"


# =============================================================================
# TRACEABILITY DEBUG HOOKS (Contract Verification Questions)
# =============================================================================


class TestTraceabilityHooks:
    """Tests for Contract Section 7: Verification Questions."""

    def test_which_plays_back_this_sentence(self):
        """Contract: 'Which plays back this sentence?' returns specific play_ids."""
        moment, plays = make_valid_moment()

        # Test tracing a specific sentence
        result = trace_sentence_to_plays(
            "Jones grabs the rebound",
            moment,
            plays,
        )

        assert result.traceable
        assert 2 in result.matched_play_ids  # "Jones rebound" is play 2

    def test_untraceable_sentence_identified(self):
        """Untraceable sentences are correctly identified."""
        moment, plays = make_valid_moment()

        result = trace_sentence_to_plays(
            "The crowd goes wild",  # Not in any play description
            moment,
            plays,
        )

        assert not result.traceable

    def test_explain_moment_backing(self):
        """Contract: All verification questions can be answered."""
        moment, plays = make_valid_moment()
        explanation = explain_moment_backing(moment, plays)

        # Q1: Which plays back this moment?
        assert "moment_play_ids" in explanation
        assert explanation["moment_play_ids"] == [1, 2, 3]

        # Q2: What was the score?
        assert "score_before" in explanation
        assert "score_after" in explanation
        assert explanation["score_before"]["home"] == 10
        assert explanation["score_after"]["home"] == 12

        # Q3: What plays are not explicitly narrated?
        assert "implicitly_covered_play_ids" in explanation
        assert 1 in explanation["implicitly_covered_play_ids"]
        assert 2 in explanation["implicitly_covered_play_ids"]
        assert 3 not in explanation["implicitly_covered_play_ids"]

        # Q4: Is this moment grounded?
        assert "is_grounded" in explanation

    def test_trace_full_narrative(self):
        """Can trace all sentences in a narrative."""
        moment, plays = make_valid_moment()
        results = trace_narrative_to_plays(moment, plays)

        assert len(results) > 0
        # At least one sentence should trace
        assert any(r.traceable for r in results)


# =============================================================================
# INTEGRATION: COMPLETE CONTRACT VALIDATION
# =============================================================================


class TestCompleteContractValidation:
    """Integration tests for complete contract validation."""

    def test_valid_story_passes_all_checks(self):
        """A properly constructed story passes all validation."""
        story, plays = make_valid_story()
        result = validate_story_contract(story, plays, strict=True)

        assert result.valid, f"Violations: {result.violations}"

    def test_raise_if_invalid(self):
        """ValidationResult.raise_if_invalid raises ContractViolation."""
        result = ValidationResult(valid=False, violations=["Test violation"])

        with pytest.raises(ContractViolation) as exc_info:
            result.raise_if_invalid()

        assert "Test violation" in exc_info.value.violations

    def test_invalid_story_fails_with_details(self):
        """Invalid stories fail with detailed violation messages."""
        plays = [make_play(1, "Smith scores")]
        moment = make_moment(
            play_ids=(1,),
            explicit_ids=(1,),
            # Uses forbidden language
            narrative="This was the turning point. The momentum shifted dramatically.",
        )
        story = StoryOutput(moments=(moment,))

        result = validate_story_contract(story, plays, strict=True)

        assert not result.valid
        assert any("turning point" in v.lower() for v in result.violations)
        assert any("momentum" in v.lower() for v in result.violations)

    def test_multiple_violations_all_reported(self):
        """Multiple violations are all reported, not just first."""
        plays = [make_play(1, "Smith scores")]
        moment = make_moment(
            play_ids=(1,),
            explicit_ids=(1,),
            # Multiple forbidden terms
            narrative="The momentum shifted. Throughout the game, the flow changed. Little did they know.",
        )
        story = StoryOutput(moments=(moment,))

        result = validate_story_contract(story, plays, strict=True)

        assert not result.valid
        # Should report all three violations
        assert len([v for v in result.violations if "Forbidden term" in v]) >= 3


# =============================================================================
# REGRESSION PREVENTION TESTS
# =============================================================================


class TestRegressionPrevention:
    """Tests to prevent reintroduction of forbidden patterns."""

    def test_story_with_headers_fails(self):
        """Headers and sections are forbidden."""
        result = validate_forbidden_language(
            "## Opening Quarter\n\nThe game begins with intensity."
        )
        assert result, "Headers should be forbidden"

    def test_story_with_summary_fails(self):
        """Game-level summaries are forbidden."""
        result = validate_forbidden_language(
            "Overall, this was a defensive battle throughout the game."
        )
        assert result, "Summary language should be forbidden"

    def test_story_with_abstract_themes_fails(self):
        """Abstract narrative themes are forbidden."""
        result = validate_forbidden_language(
            "This was clearly the key moment and turning point of the game."
        )
        assert result, "Abstract themes should be forbidden"

    def test_retrospective_narration_fails(self):
        """Retrospective commentary is forbidden."""
        result = validate_forbidden_language(
            "As we'll see later, this play would prove crucial."
        )
        assert result, "Retrospective narration should be forbidden"
