"""Tests for VALIDATE_BLOCKS stage."""

from __future__ import annotations

import pytest

from app.services.pipeline.stages.validate_blocks import (
    _validate_block_count,
    _validate_role_constraints,
    _validate_word_counts,
    _validate_score_continuity,
    _validate_moment_coverage,
    _validate_key_plays,
    _count_sentences,
)
from app.services.pipeline.stages.block_types import (
    SemanticRole,
    MIN_BLOCKS,
    MAX_BLOCKS,
    MAX_WORDS_PER_BLOCK,
    MAX_TOTAL_WORDS,
)


class TestValidateBlockCount:
    """Tests for block count validation."""

    def test_valid_block_count(self) -> None:
        """Block count in range [4, 7] passes."""
        for count in range(MIN_BLOCKS, MAX_BLOCKS + 1):
            blocks = [{"block_index": i} for i in range(count)]
            errors, warnings = _validate_block_count(blocks)
            assert len(errors) == 0

    def test_too_few_blocks(self) -> None:
        """Fewer than 4 blocks is error."""
        blocks = [{"block_index": i} for i in range(3)]
        errors, warnings = _validate_block_count(blocks)
        assert len(errors) > 0
        assert "few" in errors[0].lower()

    def test_too_many_blocks(self) -> None:
        """More than 7 blocks is error."""
        blocks = [{"block_index": i} for i in range(8)]
        errors, warnings = _validate_block_count(blocks)
        assert len(errors) > 0
        assert "many" in errors[0].lower()


class TestValidateRoleConstraints:
    """Tests for semantic role validation."""

    def test_first_block_must_be_setup(self) -> None:
        """First block must have SETUP role."""
        blocks = [
            {"role": SemanticRole.RESPONSE.value},  # Should be SETUP
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.RESOLUTION.value},
        ]
        errors, warnings = _validate_role_constraints(blocks)
        assert len(errors) > 0
        assert "SETUP" in errors[0]

    def test_last_block_must_be_resolution(self) -> None:
        """Last block must have RESOLUTION role."""
        blocks = [
            {"role": SemanticRole.SETUP.value},
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.RESPONSE.value},  # Should be RESOLUTION
        ]
        errors, warnings = _validate_role_constraints(blocks)
        assert len(errors) > 0
        assert "RESOLUTION" in errors[0]

    def test_role_appears_more_than_twice(self) -> None:
        """Role appearing more than twice is error."""
        blocks = [
            {"role": SemanticRole.SETUP.value},
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.RESPONSE.value},  # Third RESPONSE
            {"role": SemanticRole.RESOLUTION.value},
        ]
        errors, warnings = _validate_role_constraints(blocks)
        assert len(errors) > 0
        assert "RESPONSE" in errors[0]

    def test_valid_role_distribution(self) -> None:
        """Valid role distribution passes."""
        blocks = [
            {"role": SemanticRole.SETUP.value},
            {"role": SemanticRole.MOMENTUM_SHIFT.value},
            {"role": SemanticRole.RESPONSE.value},
            {"role": SemanticRole.DECISION_POINT.value},
            {"role": SemanticRole.RESOLUTION.value},
        ]
        errors, warnings = _validate_role_constraints(blocks)
        assert len(errors) == 0


class TestValidateWordCounts:
    """Tests for word count validation."""

    def test_missing_narrative_is_error(self) -> None:
        """Block without narrative produces error."""
        blocks = [{"block_index": 0, "narrative": ""}]
        errors, warnings = _validate_word_counts(blocks)
        assert len(errors) > 0
        assert "Missing" in errors[0]

    def test_too_short_narrative_is_warning(self) -> None:
        """Narrative shorter than minimum produces warning."""
        blocks = [{"block_index": 0, "narrative": "Short."}]
        errors, warnings = _validate_word_counts(blocks)
        assert len(warnings) > 0
        assert "short" in warnings[0].lower()

    def test_too_long_narrative_is_warning(self) -> None:
        """Narrative longer than maximum produces warning."""
        long_narrative = " ".join(["word"] * (MAX_WORDS_PER_BLOCK + 10))
        blocks = [{"block_index": 0, "narrative": long_narrative}]
        errors, warnings = _validate_word_counts(blocks)
        assert len(warnings) > 0
        assert "long" in warnings[0].lower()

    def test_total_word_count_too_high(self) -> None:
        """Total word count exceeding limit produces warning."""
        # Create blocks with enough words to exceed limit
        words_per_block = MAX_TOTAL_WORDS // 4 + 10  # Will exceed when summed
        blocks = [
            {"block_index": i, "narrative": " ".join(["word"] * words_per_block)}
            for i in range(4)
        ]
        errors, warnings = _validate_word_counts(blocks)
        assert any("total" in w.lower() for w in warnings)

    def test_valid_word_counts(self) -> None:
        """Valid word counts produce no errors."""
        blocks = [
            {"block_index": i, "narrative": " ".join(["word"] * 30)}
            for i in range(5)
        ]  # 5 blocks × 30 words = 150 total
        errors, warnings = _validate_word_counts(blocks)
        assert len(errors) == 0
        # Only warnings, no errors for valid range


class TestValidateScoreContinuity:
    """Tests for score continuity validation."""

    def test_continuous_scores_pass(self) -> None:
        """Continuous scores across blocks pass."""
        blocks = [
            {"score_before": [0, 0], "score_after": [10, 8]},
            {"score_before": [10, 8], "score_after": [20, 18]},
            {"score_before": [20, 18], "score_after": [30, 28]},
        ]
        errors, warnings = _validate_score_continuity(blocks)
        assert len(errors) == 0

    def test_discontinuous_scores_is_error(self) -> None:
        """Score discontinuity produces error."""
        blocks = [
            {"score_before": [0, 0], "score_after": [10, 8]},
            {"score_before": [15, 10], "score_after": [25, 20]},  # Gap!
        ]
        errors, warnings = _validate_score_continuity(blocks)
        assert len(errors) > 0
        assert "discontinuity" in errors[0].lower()

    def test_single_block_no_check(self) -> None:
        """Single block has no continuity check."""
        blocks = [{"score_before": [0, 0], "score_after": [100, 95]}]
        errors, warnings = _validate_score_continuity(blocks)
        assert len(errors) == 0


class TestValidateMomentCoverage:
    """Tests for moment coverage validation."""

    def test_all_moments_covered(self) -> None:
        """All moments covered by blocks passes."""
        blocks = [
            {"moment_indices": [0, 1]},
            {"moment_indices": [2, 3]},
            {"moment_indices": [4]},
        ]
        errors, warnings = _validate_moment_coverage(blocks, total_moments=5)
        assert len(errors) == 0

    def test_moment_in_multiple_blocks(self) -> None:
        """Moment in multiple blocks produces error."""
        blocks = [
            {"moment_indices": [0, 1, 2]},
            {"moment_indices": [2, 3, 4]},  # Moment 2 duplicated
        ]
        errors, warnings = _validate_moment_coverage(blocks, total_moments=5)
        assert len(errors) > 0
        assert "multiple" in errors[0].lower()

    def test_missing_moments(self) -> None:
        """Moments not covered by any block produces error."""
        blocks = [
            {"moment_indices": [0, 1]},
            {"moment_indices": [3, 4]},  # Missing moment 2
        ]
        errors, warnings = _validate_moment_coverage(blocks, total_moments=5)
        assert len(errors) > 0
        assert "not covered" in errors[0].lower()

    def test_extra_moment_indices(self) -> None:
        """Reference to non-existent moment produces warning."""
        blocks = [
            {"moment_indices": [0, 1, 2]},
            {"moment_indices": [3, 4, 10]},  # Moment 10 doesn't exist
        ]
        errors, warnings = _validate_moment_coverage(blocks, total_moments=5)
        assert len(warnings) > 0
        assert "non-existent" in warnings[0].lower()


class TestValidateKeyPlays:
    """Tests for key play validation."""

    def test_valid_key_plays(self) -> None:
        """Valid key plays pass."""
        blocks = [
            {
                "block_index": 0,
                "play_ids": [1, 2, 3, 4, 5],
                "key_play_ids": [2, 4],
            }
        ]
        errors, warnings = _validate_key_plays(blocks)
        assert len(errors) == 0

    def test_no_key_plays_is_warning(self) -> None:
        """Block without key plays produces warning."""
        blocks = [
            {
                "block_index": 0,
                "play_ids": [1, 2, 3],
                "key_play_ids": [],
            }
        ]
        errors, warnings = _validate_key_plays(blocks)
        assert len(warnings) > 0
        assert "No key plays" in warnings[0]

    def test_too_many_key_plays_is_warning(self) -> None:
        """More than 3 key plays produces warning."""
        blocks = [
            {
                "block_index": 0,
                "play_ids": [1, 2, 3, 4, 5],
                "key_play_ids": [1, 2, 3, 4],  # 4 is too many
            }
        ]
        errors, warnings = _validate_key_plays(blocks)
        assert len(warnings) > 0
        assert "Too many" in warnings[0]

    def test_key_play_not_in_block(self) -> None:
        """Key play not in block's play_ids produces error."""
        blocks = [
            {
                "block_index": 0,
                "play_ids": [1, 2, 3],
                "key_play_ids": [5],  # Not in play_ids
            }
        ]
        errors, warnings = _validate_key_plays(blocks)
        assert len(errors) > 0
        assert "not in block's play_ids" in errors[0]


class TestValidationIntegration:
    """Integration tests for block validation."""

    def test_valid_blocks_pass_all_checks(self) -> None:
        """Fully valid blocks pass all validation checks."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "moment_indices": [0, 1],
                "score_before": [0, 0],
                "score_after": [10, 8],
                "play_ids": [1, 2, 3],
                "key_play_ids": [2],
                "narrative": "The Lakers started strong with a quick 10-8 lead.",
            },
            {
                "block_index": 1,
                "role": SemanticRole.MOMENTUM_SHIFT.value,
                "moment_indices": [2, 3],
                "score_before": [10, 8],
                "score_after": [15, 20],
                "play_ids": [4, 5, 6],
                "key_play_ids": [5],
                "narrative": "The Celtics responded with a scoring run to take the lead.",
            },
            {
                "block_index": 2,
                "role": SemanticRole.RESPONSE.value,
                "moment_indices": [4, 5],
                "score_before": [15, 20],
                "score_after": [25, 22],
                "play_ids": [7, 8, 9],
                "key_play_ids": [8],
                "narrative": "The Lakers came back with a strong third quarter performance.",
            },
            {
                "block_index": 3,
                "role": SemanticRole.RESOLUTION.value,
                "moment_indices": [6, 7],
                "score_before": [25, 22],
                "score_after": [30, 28],
                "play_ids": [10, 11, 12],
                "key_play_ids": [11],
                "narrative": "The game concluded with the Lakers holding on for a 30-28 win.",
            },
        ]

        # Run all validations
        errors: list[str] = []
        warnings: list[str] = []

        e, w = _validate_block_count(blocks)
        errors.extend(e)
        warnings.extend(w)

        e, w = _validate_role_constraints(blocks)
        errors.extend(e)
        warnings.extend(w)

        e, w = _validate_word_counts(blocks)
        errors.extend(e)
        warnings.extend(w)

        e, w = _validate_score_continuity(blocks)
        errors.extend(e)
        warnings.extend(w)

        e, w = _validate_moment_coverage(blocks, total_moments=8)
        errors.extend(e)
        warnings.extend(w)

        e, w = _validate_key_plays(blocks)
        errors.extend(e)
        warnings.extend(w)

        assert len(errors) == 0, f"Errors: {errors}"


class TestExecuteValidateBlocks:
    """Tests for execute_validate_blocks async function."""

    @pytest.mark.asyncio
    async def test_missing_previous_output_raises(self) -> None:
        """Missing previous output raises ValueError."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput
        import pytest

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output=None,
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with pytest.raises(ValueError, match="requires previous stage output"):
            await execute_validate_blocks(stage_input)

    @pytest.mark.asyncio
    async def test_not_rendered_raises(self) -> None:
        """Previous output without blocks_rendered=True raises ValueError."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput
        import pytest

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"blocks_rendered": False, "blocks": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with pytest.raises(ValueError, match="RENDER_BLOCKS to complete"):
            await execute_validate_blocks(stage_input)

    @pytest.mark.asyncio
    async def test_no_blocks_raises(self) -> None:
        """Empty blocks list raises ValueError."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput
        import pytest

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"blocks_rendered": True, "blocks": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with pytest.raises(ValueError, match="No blocks"):
            await execute_validate_blocks(stage_input)

    @pytest.mark.asyncio
    async def test_all_validations_passing(self) -> None:
        """All validations pass with valid blocks."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput

        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "moment_indices": [0, 1],
                "score_before": [0, 0],
                "score_after": [10, 8],
                "play_ids": [1, 2, 3],
                "key_play_ids": [2],
                "narrative": "The Lakers started strong with a quick 10-8 lead in the opening minutes.",
            },
            {
                "block_index": 1,
                "role": SemanticRole.MOMENTUM_SHIFT.value,
                "moment_indices": [2, 3],
                "score_before": [10, 8],
                "score_after": [15, 20],
                "play_ids": [4, 5, 6],
                "key_play_ids": [5],
                "narrative": "The Celtics responded with a scoring run to take the lead midway through.",
            },
            {
                "block_index": 2,
                "role": SemanticRole.RESPONSE.value,
                "moment_indices": [4, 5],
                "score_before": [15, 20],
                "score_after": [25, 22],
                "play_ids": [7, 8, 9],
                "key_play_ids": [8],
                "narrative": "The Lakers came back with a strong third quarter performance and retook control.",
            },
            {
                "block_index": 3,
                "role": SemanticRole.RESOLUTION.value,
                "moment_indices": [6, 7],
                "score_before": [25, 22],
                "score_after": [30, 28],
                "play_ids": [10, 11, 12],
                "key_play_ids": [11],
                "narrative": "The game concluded with the Lakers holding on for a close 30-28 victory.",
            },
        ]

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={
                "blocks_rendered": True,
                "blocks": blocks,
                "moments": [{} for _ in range(8)],
                "pbp_events": [],
                "validated": True,
            },
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        result = await execute_validate_blocks(stage_input)

        assert result.data["blocks_validated"] is True
        assert len(result.data["errors"]) == 0

    @pytest.mark.asyncio
    async def test_with_validation_errors(self) -> None:
        """Validation fails with invalid blocks."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput

        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.RESPONSE.value,  # Should be SETUP
                "moment_indices": [0],
                "score_before": [0, 0],
                "score_after": [10, 8],
                "play_ids": [1],
                "key_play_ids": [1],
                "narrative": "Short narrative here for block zero that tests the word count.",
            },
            {
                "block_index": 1,
                "role": SemanticRole.RESPONSE.value,  # Should be RESOLUTION
                "moment_indices": [1],
                "score_before": [10, 8],
                "score_after": [20, 15],
                "play_ids": [2],
                "key_play_ids": [2],
                "narrative": "Another short narrative for block one that tests word count.",
            },
        ]

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={
                "blocks_rendered": True,
                "blocks": blocks,
                "moments": [{} for _ in range(2)],
            },
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        result = await execute_validate_blocks(stage_input)

        # Should fail due to role constraints
        assert result.data["blocks_validated"] is False
        assert len(result.data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_with_warnings_only(self) -> None:
        """Validation passes with warnings but no errors."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput

        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "moment_indices": [0],
                "score_before": [0, 0],
                "score_after": [10, 8],
                "play_ids": [1],
                "key_play_ids": [],  # Missing key plays - warning
                "narrative": "Short.",  # Too short - warning
            },
            {
                "block_index": 1,
                "role": SemanticRole.MOMENTUM_SHIFT.value,
                "moment_indices": [1],
                "score_before": [10, 8],
                "score_after": [15, 18],
                "play_ids": [2],
                "key_play_ids": [2],
                "narrative": "The Celtics made a strong comeback push to take the lead.",
            },
            {
                "block_index": 2,
                "role": SemanticRole.RESPONSE.value,
                "moment_indices": [2],
                "score_before": [15, 18],
                "score_after": [22, 20],
                "play_ids": [3],
                "key_play_ids": [3],
                "narrative": "Lakers fought back with determination and skill throughout.",
            },
            {
                "block_index": 3,
                "role": SemanticRole.RESOLUTION.value,
                "moment_indices": [3],
                "score_before": [22, 20],
                "score_after": [30, 28],
                "play_ids": [4],
                "key_play_ids": [4],
                "narrative": "The final quarter saw Lakers close out the game successfully.",
            },
        ]

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={
                "blocks_rendered": True,
                "blocks": blocks,
                "moments": [{} for _ in range(4)],
            },
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        result = await execute_validate_blocks(stage_input)

        # Should pass despite warnings
        assert result.data["blocks_validated"] is True
        assert len(result.data["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_output_structure(self) -> None:
        """Output contains all expected fields."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput

        blocks = [
            {
                "block_index": i,
                "role": [SemanticRole.SETUP.value, SemanticRole.RESPONSE.value,
                         SemanticRole.RESPONSE.value, SemanticRole.RESOLUTION.value][i],
                "moment_indices": [i],
                "score_before": [i * 10, i * 8],
                "score_after": [(i + 1) * 10, (i + 1) * 8],
                "play_ids": [i + 1],
                "key_play_ids": [i + 1],
                "narrative": f"Block {i} narrative with enough words to pass minimum.",
            }
            for i in range(4)
        ]

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={
                "blocks_rendered": True,
                "blocks": blocks,
                "moments": [{} for _ in range(4)],
                "pbp_events": [{"test": "event"}],
                "validated": True,
            },
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        result = await execute_validate_blocks(stage_input)

        # Check output structure
        assert "blocks_validated" in result.data
        assert "blocks" in result.data
        assert "block_count" in result.data
        assert "total_words" in result.data
        assert "errors" in result.data
        assert "warnings" in result.data
        assert "moments" in result.data
        assert "pbp_events" in result.data

    @pytest.mark.asyncio
    async def test_score_discontinuity_detected(self) -> None:
        """Score discontinuity is detected as error."""
        from app.services.pipeline.stages.validate_blocks import execute_validate_blocks
        from app.services.pipeline.models import StageInput

        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "moment_indices": [0],
                "score_before": [0, 0],
                "score_after": [10, 8],
                "play_ids": [1],
                "key_play_ids": [1],
                "narrative": "Opening narrative block with enough words for validation.",
            },
            {
                "block_index": 1,
                "role": SemanticRole.MOMENTUM_SHIFT.value,
                "moment_indices": [1],
                "score_before": [15, 12],  # Discontinuity! Should be [10, 8]
                "score_after": [25, 22],
                "play_ids": [2],
                "key_play_ids": [2],
                "narrative": "Second narrative block with enough words for validation.",
            },
            {
                "block_index": 2,
                "role": SemanticRole.RESPONSE.value,
                "moment_indices": [2],
                "score_before": [25, 22],
                "score_after": [35, 30],
                "play_ids": [3],
                "key_play_ids": [3],
                "narrative": "Third narrative block with enough words for validation test.",
            },
            {
                "block_index": 3,
                "role": SemanticRole.RESOLUTION.value,
                "moment_indices": [3],
                "score_before": [35, 30],
                "score_after": [45, 38],
                "play_ids": [4],
                "key_play_ids": [4],
                "narrative": "Final narrative block with enough words for validation test.",
            },
        ]

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={
                "blocks_rendered": True,
                "blocks": blocks,
                "moments": [{} for _ in range(4)],
            },
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        result = await execute_validate_blocks(stage_input)

        assert result.data["blocks_validated"] is False
        assert any("discontinuity" in e.lower() for e in result.data["errors"])


class TestSentenceCounting:
    """Tests for sentence counting with abbreviation handling."""

    def test_basic_sentence_counting(self) -> None:
        """Counts simple sentences correctly."""
        assert _count_sentences("One sentence. Two sentences.") == 2
        assert _count_sentences("Just one sentence.") == 1
        assert _count_sentences("First! Second? Third.") == 3

    def test_empty_text_returns_zero(self) -> None:
        """Empty or whitespace text returns zero."""
        assert _count_sentences("") == 0
        assert _count_sentences("   ") == 0

    def test_abbreviation_dr(self) -> None:
        """Dr. abbreviation does not break sentence counting."""
        text = "Dr. James made a shot. Then he scored again."
        assert _count_sentences(text) == 2

    def test_abbreviation_mr_mrs(self) -> None:
        """Mr. and Mrs. abbreviations don't break counting."""
        text = "Mr. Smith scored. Mrs. Jones assisted."
        assert _count_sentences(text) == 2

    def test_abbreviation_vs(self) -> None:
        """vs. abbreviation doesn't break counting."""
        text = "Lakers vs. Celtics was exciting. Great game."
        assert _count_sentences(text) == 2

    def test_abbreviation_st_ave(self) -> None:
        """Address abbreviations don't break counting."""
        text = "Game at St. Louis Arena. The fans were loud."
        assert _count_sentences(text) == 2

    def test_multiple_abbreviations(self) -> None:
        """Multiple abbreviations in one sentence work correctly."""
        text = "Dr. Smith and Mr. Jones watched. They enjoyed it."
        assert _count_sentences(text) == 2

    def test_ellipsis_not_sentence_break(self) -> None:
        """Ellipsis (...) is not treated as sentence break."""
        text = "The play was... interesting. Next play was better."
        assert _count_sentences(text) == 2

    def test_exclamation_and_question(self) -> None:
        """Exclamation and question marks count as sentence ends."""
        text = "What a play! Did you see that? Amazing."
        assert _count_sentences(text) == 3

    def test_consecutive_punctuation(self) -> None:
        """Consecutive punctuation counts as single sentence end."""
        text = "Really?! Yes. Wow..."
        # "Really?!" = 1, "Yes." = 1, "Wow..." (ellipsis) = 1
        # But ellipsis should be protected, so just "Wow" after
        assert _count_sentences(text) == 3

    def test_case_insensitive_abbreviations(self) -> None:
        """Abbreviations work case-insensitively."""
        text = "DR. JAMES scored. mr. smith assisted."
        assert _count_sentences(text) == 2

    def test_month_abbreviations(self) -> None:
        """Month abbreviations don't break counting."""
        text = "Game on Jan. 15. Next game Feb. 20."
        assert _count_sentences(text) == 2
