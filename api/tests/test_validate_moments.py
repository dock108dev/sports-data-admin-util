"""Tests for validate_moments stage."""

import pytest


class TestValidationError:
    """Tests for ValidationError class."""

    def test_to_dict_basic(self):
        """Basic error converts to dict."""
        from app.services.pipeline.stages.validate_moments import ValidationError

        err = ValidationError(code="TEST", message="Test message")
        result = err.to_dict()
        assert result["code"] == "TEST"
        assert result["message"] == "Test message"
        assert "moment_indices" not in result
        assert "play_ids" not in result

    def test_to_dict_with_moment_indices(self):
        """Error with moment indices includes them."""
        from app.services.pipeline.stages.validate_moments import ValidationError

        err = ValidationError(
            code="TEST", message="Test", moment_indices=[0, 1]
        )
        result = err.to_dict()
        assert result["moment_indices"] == [0, 1]

    def test_to_dict_with_play_ids(self):
        """Error with play_ids includes them."""
        from app.services.pipeline.stages.validate_moments import ValidationError

        err = ValidationError(code="TEST", message="Test", play_ids=[100, 200])
        result = err.to_dict()
        assert result["play_ids"] == [100, 200]

    def test_to_dict_full(self):
        """Full error with all fields."""
        from app.services.pipeline.stages.validate_moments import ValidationError

        err = ValidationError(
            code="FULL",
            message="Full message",
            moment_indices=[0],
            play_ids=[1, 2],
        )
        result = err.to_dict()
        assert result["code"] == "FULL"
        assert result["message"] == "Full message"
        assert result["moment_indices"] == [0]
        assert result["play_ids"] == [1, 2]


class TestValidateNonEmptyPlayIds:
    """Tests for Rule 1: Non-empty play_ids."""

    def test_valid_moments_pass(self):
        """Moments with play_ids pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_non_empty_play_ids,
        )

        moments = [
            {"play_ids": [1, 2]},
            {"play_ids": [3]},
        ]
        errors = _validate_non_empty_play_ids(moments)
        assert len(errors) == 0

    def test_empty_play_ids_fails(self):
        """Empty play_ids list fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_non_empty_play_ids,
        )

        moments = [
            {"play_ids": [1]},
            {"play_ids": []},
        ]
        errors = _validate_non_empty_play_ids(moments)
        assert len(errors) == 1
        assert errors[0].code == "EMPTY_PLAY_IDS"
        assert errors[0].moment_indices == [1]

    def test_missing_play_ids_key_fails(self):
        """Missing play_ids key fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_non_empty_play_ids,
        )

        moments = [{"other_field": "value"}]
        errors = _validate_non_empty_play_ids(moments)
        assert len(errors) == 1
        assert errors[0].code == "EMPTY_PLAY_IDS"

    def test_multiple_failures(self):
        """Multiple empty moments all reported."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_non_empty_play_ids,
        )

        moments = [
            {"play_ids": []},
            {"play_ids": [1]},
            {"play_ids": []},
        ]
        errors = _validate_non_empty_play_ids(moments)
        assert len(errors) == 2
        assert errors[0].moment_indices == [0]
        assert errors[1].moment_indices == [2]

    def test_empty_moments_list(self):
        """Empty moments list passes."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_non_empty_play_ids,
        )

        errors = _validate_non_empty_play_ids([])
        assert len(errors) == 0


class TestValidateExplicitNarration:
    """Tests for Rule 2: Explicit narration guarantee."""

    def test_valid_narration_passes(self):
        """Valid narration subset passes."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_explicit_narration,
        )

        moments = [
            {
                "play_ids": [1, 2, 3],
                "explicitly_narrated_play_ids": [2],
            }
        ]
        errors = _validate_explicit_narration(moments)
        assert len(errors) == 0

    def test_empty_narration_fails(self):
        """Empty narration list fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_explicit_narration,
        )

        moments = [
            {
                "play_ids": [1, 2],
                "explicitly_narrated_play_ids": [],
            }
        ]
        errors = _validate_explicit_narration(moments)
        assert len(errors) == 1
        assert errors[0].code == "EMPTY_NARRATION"

    def test_missing_narration_key_fails(self):
        """Missing explicitly_narrated_play_ids fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_explicit_narration,
        )

        moments = [{"play_ids": [1, 2]}]
        errors = _validate_explicit_narration(moments)
        assert len(errors) == 1
        assert errors[0].code == "EMPTY_NARRATION"

    def test_narration_not_subset_fails(self):
        """Narrated IDs not in play_ids fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_explicit_narration,
        )

        moments = [
            {
                "play_ids": [1, 2],
                "explicitly_narrated_play_ids": [3],  # 3 not in play_ids
            }
        ]
        errors = _validate_explicit_narration(moments)
        assert len(errors) == 1
        assert errors[0].code == "NARRATION_NOT_SUBSET"
        assert errors[0].play_ids == [3]

    def test_partial_subset_fails(self):
        """Partially invalid narration fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_explicit_narration,
        )

        moments = [
            {
                "play_ids": [1, 2],
                "explicitly_narrated_play_ids": [1, 5],  # 5 not in play_ids
            }
        ]
        errors = _validate_explicit_narration(moments)
        assert len(errors) == 1
        assert errors[0].code == "NARRATION_NOT_SUBSET"
        assert 5 in errors[0].play_ids

    def test_all_play_ids_narrated_valid(self):
        """All play_ids being narrated is valid."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_explicit_narration,
        )

        moments = [
            {
                "play_ids": [1, 2],
                "explicitly_narrated_play_ids": [1, 2],
            }
        ]
        errors = _validate_explicit_narration(moments)
        assert len(errors) == 0


class TestValidateNoOverlappingPlays:
    """Tests for Rule 3: No overlapping plays."""

    def test_no_overlap_passes(self):
        """Non-overlapping play_ids pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_no_overlapping_plays,
        )

        moments = [
            {"play_ids": [1, 2]},
            {"play_ids": [3, 4]},
        ]
        errors = _validate_no_overlapping_plays(moments)
        assert len(errors) == 0

    def test_overlap_fails(self):
        """Overlapping play_id fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_no_overlapping_plays,
        )

        moments = [
            {"play_ids": [1, 2]},
            {"play_ids": [2, 3]},  # 2 is duplicated
        ]
        errors = _validate_no_overlapping_plays(moments)
        assert len(errors) == 1
        assert errors[0].code == "OVERLAPPING_PLAY_IDS"
        assert errors[0].play_ids == [2]
        assert errors[0].moment_indices == [0, 1]

    def test_multiple_overlaps(self):
        """Multiple overlapping plays all reported."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_no_overlapping_plays,
        )

        moments = [
            {"play_ids": [1, 2]},
            {"play_ids": [2, 3]},
            {"play_ids": [3, 4]},
        ]
        errors = _validate_no_overlapping_plays(moments)
        # 2 appears in moments 0,1 and 3 appears in moments 1,2
        assert len(errors) == 2

    def test_empty_play_ids_ok(self):
        """Empty play_ids don't cause overlap errors."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_no_overlapping_plays,
        )

        moments = [
            {"play_ids": []},
            {"play_ids": [1]},
        ]
        errors = _validate_no_overlapping_plays(moments)
        assert len(errors) == 0

    def test_single_moment_no_overlap(self):
        """Single moment cannot overlap."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_no_overlapping_plays,
        )

        moments = [{"play_ids": [1, 2, 3]}]
        errors = _validate_no_overlapping_plays(moments)
        assert len(errors) == 0


class TestValidateCanonicalOrdering:
    """Tests for Rule 4: Canonical ordering."""

    def test_correct_ordering_passes(self):
        """Correctly ordered moments pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_canonical_ordering,
        )

        moments = [
            {"play_ids": [1, 2]},
            {"play_ids": [3, 4]},
            {"play_ids": [5]},
        ]
        errors = _validate_canonical_ordering(moments)
        assert len(errors) == 0

    def test_out_of_order_fails(self):
        """Out of order moments fail."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_canonical_ordering,
        )

        moments = [
            {"play_ids": [3, 4]},
            {"play_ids": [1, 2]},  # 1 < 3
        ]
        errors = _validate_canonical_ordering(moments)
        assert len(errors) == 1
        assert errors[0].code == "ORDERING_VIOLATION"

    def test_equal_ordering_fails(self):
        """Equal first play_ids fail."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_canonical_ordering,
        )

        moments = [
            {"play_ids": [5]},
            {"play_ids": [5]},  # Same as previous
        ]
        errors = _validate_canonical_ordering(moments)
        assert len(errors) == 1
        assert errors[0].code == "ORDERING_VIOLATION"

    def test_empty_play_ids_skipped(self):
        """Empty play_ids are skipped."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_canonical_ordering,
        )

        moments = [
            {"play_ids": [1]},
            {"play_ids": []},  # Skipped
            {"play_ids": [5]},
        ]
        errors = _validate_canonical_ordering(moments)
        assert len(errors) == 0

    def test_single_moment_ok(self):
        """Single moment always passes."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_canonical_ordering,
        )

        moments = [{"play_ids": [10]}]
        errors = _validate_canonical_ordering(moments)
        assert len(errors) == 0


class TestValidatePlayReferences:
    """Tests for Rule 5: Valid play references."""

    def test_valid_references_pass(self):
        """Valid play references pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_play_references,
        )

        moments = [
            {"play_ids": [1, 2]},
            {"play_ids": [3]},
        ]
        valid_ids = {1, 2, 3, 4, 5}
        errors = _validate_play_references(moments, valid_ids)
        assert len(errors) == 0

    def test_invalid_reference_fails(self):
        """Invalid play reference fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_play_references,
        )

        moments = [{"play_ids": [1, 99]}]  # 99 doesn't exist
        valid_ids = {1, 2, 3}
        errors = _validate_play_references(moments, valid_ids)
        assert len(errors) == 1
        assert errors[0].code == "INVALID_PLAY_REFERENCE"
        assert errors[0].play_ids == [99]

    def test_multiple_invalid_references(self):
        """Multiple invalid references in one moment."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_play_references,
        )

        moments = [{"play_ids": [1, 99, 100]}]
        valid_ids = {1, 2}
        errors = _validate_play_references(moments, valid_ids)
        assert len(errors) == 1
        assert set(errors[0].play_ids) == {99, 100}

    def test_empty_valid_ids(self):
        """All references invalid if valid_ids empty."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_play_references,
        )

        moments = [{"play_ids": [1]}]
        valid_ids: set[int] = set()
        errors = _validate_play_references(moments, valid_ids)
        assert len(errors) == 1

    def test_empty_play_ids_ok(self):
        """Empty play_ids don't cause reference errors."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_play_references,
        )

        moments = [{"play_ids": []}]
        valid_ids = {1, 2}
        errors = _validate_play_references(moments, valid_ids)
        assert len(errors) == 0


class TestValidateScoreNeverDecreases:
    """Tests for Rule 6: Score never decreases."""

    def test_increasing_scores_pass(self):
        """Increasing scores pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [2, 0]},
            {"score_before": [2, 0], "score_after": [2, 3]},
            {"score_before": [2, 3], "score_after": [5, 3]},
        ]
        errors = _validate_score_never_decreases(moments)
        assert len(errors) == 0

    def test_static_scores_pass(self):
        """Static scores (no change) pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [0, 0]},
            {"score_before": [0, 0], "score_after": [2, 0]},
        ]
        errors = _validate_score_never_decreases(moments)
        assert len(errors) == 0

    def test_score_decrease_within_moment_fails(self):
        """Score decrease within moment fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        moments = [
            {"score_before": [5, 3], "score_after": [3, 3]},  # Home decreased
        ]
        errors = _validate_score_never_decreases(moments)
        assert len(errors) == 1
        assert errors[0].code == "SCORE_DECREASE_WITHIN"

    def test_score_decrease_between_moments_fails(self):
        """Score decrease between moments fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [5, 3]},
            {"score_before": [2, 0], "score_after": [7, 3]},  # Before < previous after
        ]
        errors = _validate_score_never_decreases(moments)
        assert len(errors) == 1
        assert errors[0].code == "SCORE_DECREASE_BEFORE"

    def test_missing_scores_default_to_zero(self):
        """Missing scores default to zero."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [2, 0]},
            {},  # Missing scores, defaults to [0,0] which is < previous
        ]
        errors = _validate_score_never_decreases(moments)
        # Second moment's score_before [0,0] < first moment's score_after [2,0]
        assert len(errors) >= 1

    def test_empty_moments_pass(self):
        """Empty moments list passes."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        errors = _validate_score_never_decreases([])
        assert len(errors) == 0


class TestValidateScoreContinuity:
    """Tests for Rule 7: Score continuity."""

    def test_continuous_scores_pass(self):
        """Continuous scores pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [2, 0]},
            {"score_before": [2, 0], "score_after": [2, 3]},
            {"score_before": [2, 3], "score_after": [5, 3]},
        ]
        errors = _validate_score_continuity(moments)
        assert len(errors) == 0

    def test_continuity_break_fails(self):
        """Score continuity break fails."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [2, 0]},
            {"score_before": [3, 0], "score_after": [5, 0]},  # 3 != 2
        ]
        errors = _validate_score_continuity(moments)
        assert len(errors) == 1
        assert errors[0].code == "SCORE_CONTINUITY_BREAK"
        assert errors[0].moment_indices == [0, 1]

    def test_single_moment_passes(self):
        """Single moment passes (no continuity to check)."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        moments = [{"score_before": [0, 0], "score_after": [10, 5]}]
        errors = _validate_score_continuity(moments)
        assert len(errors) == 0

    def test_empty_moments_passes(self):
        """Empty moments passes."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        errors = _validate_score_continuity([])
        assert len(errors) == 0

    def test_multiple_breaks_all_reported(self):
        """Multiple continuity breaks all reported."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        moments = [
            {"score_before": [0, 0], "score_after": [2, 0]},
            {"score_before": [5, 0], "score_after": [7, 0]},  # Break
            {"score_before": [10, 0], "score_after": [12, 0]},  # Break
        ]
        errors = _validate_score_continuity(moments)
        assert len(errors) == 2


class TestExecuteValidateMoments:
    """Tests for execute_validate_moments function."""

    def _make_valid_moment(self, play_ids, score_before, score_after):
        """Create a valid moment with all required fields."""
        return {
            "play_ids": play_ids,
            "explicitly_narrated_play_ids": [play_ids[0]] if play_ids else [],
            "score_before": score_before,
            "score_after": score_after,
            "period": 1,
            "start_clock": "12:00",
            "end_clock": "11:30",
        }

    @pytest.mark.asyncio
    async def test_requires_previous_output(self):
        """Raises if no previous output."""
        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output=None,
        )

        with pytest.raises(ValueError, match="requires previous stage output"):
            await execute_validate_moments(stage_input)

    @pytest.mark.asyncio
    async def test_requires_moments(self):
        """Raises if no moments in previous output."""
        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"pbp_events": [{"play_index": 1}]},
        )

        with pytest.raises(ValueError, match="No moments"):
            await execute_validate_moments(stage_input)

    @pytest.mark.asyncio
    async def test_requires_pbp_events(self):
        """Raises if no pbp_events in previous output."""
        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": []},
        )

        with pytest.raises(ValueError, match="No pbp_events"):
            await execute_validate_moments(stage_input)

    @pytest.mark.asyncio
    async def test_valid_moments_pass(self):
        """Valid moments pass all validation rules."""
        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        moments = [
            self._make_valid_moment([1, 2], [0, 0], [2, 0]),
            self._make_valid_moment([3, 4], [2, 0], [4, 0]),
            self._make_valid_moment([5], [4, 0], [6, 0]),
        ]
        pbp_events = [{"play_index": i} for i in range(1, 6)]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": moments, "pbp_events": pbp_events},
        )

        result = await execute_validate_moments(stage_input)

        assert result.data["validated"] is True
        assert result.data["errors"] == []

    @pytest.mark.asyncio
    async def test_empty_moments_passes(self):
        """Empty moments list passes validation."""
        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": [], "pbp_events": [{"play_index": 1}]},
        )

        result = await execute_validate_moments(stage_input)

        assert result.data["validated"] is True

    @pytest.mark.asyncio
    async def test_validation_failure_raises(self):
        """Validation failures raise ValueError with JSON details."""
        import json

        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        # Invalid moment: empty play_ids
        moments = [{"play_ids": [], "explicitly_narrated_play_ids": []}]
        pbp_events = [{"play_index": 1}]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": moments, "pbp_events": pbp_events},
        )

        with pytest.raises(ValueError) as exc_info:
            await execute_validate_moments(stage_input)

        # Parse the JSON error message
        error_data = json.loads(str(exc_info.value))
        assert error_data["validated"] is False
        assert len(error_data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_overlapping_plays_fails(self):
        """Overlapping plays fail validation."""
        import json

        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        moments = [
            self._make_valid_moment([1, 2], [0, 0], [2, 0]),
            self._make_valid_moment([2, 3], [2, 0], [4, 0]),  # 2 overlaps
        ]
        pbp_events = [{"play_index": i} for i in range(1, 4)]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": moments, "pbp_events": pbp_events},
        )

        with pytest.raises(ValueError) as exc_info:
            await execute_validate_moments(stage_input)

        error_data = json.loads(str(exc_info.value))
        assert error_data["validated"] is False
        assert any(e["code"] == "OVERLAPPING_PLAY_IDS" for e in error_data["errors"])

    @pytest.mark.asyncio
    async def test_invalid_play_reference_fails(self):
        """Invalid play reference fails validation."""
        import json

        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        moments = [
            self._make_valid_moment([1, 99], [0, 0], [2, 0]),  # 99 doesn't exist
        ]
        pbp_events = [{"play_index": 1}]  # Only play 1 exists

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": moments, "pbp_events": pbp_events},
        )

        with pytest.raises(ValueError) as exc_info:
            await execute_validate_moments(stage_input)

        error_data = json.loads(str(exc_info.value))
        assert any(e["code"] == "INVALID_PLAY_REFERENCE" for e in error_data["errors"])

    @pytest.mark.asyncio
    async def test_logs_added(self):
        """Execution adds log entries."""
        from app.services.pipeline.models import StageInput
        from app.services.pipeline.stages.validate_moments import (
            execute_validate_moments,
        )

        moments = [self._make_valid_moment([1], [0, 0], [2, 0])]
        pbp_events = [{"play_index": 1}]

        stage_input = StageInput(
            game_id=123,
            run_id=1,
            previous_output={"moments": moments, "pbp_events": pbp_events},
        )

        result = await execute_validate_moments(stage_input)

        assert len(result.logs) > 0
        log_messages = [log["message"] for log in result.logs]
        assert any("Starting VALIDATE_MOMENTS" in msg for msg in log_messages)
        assert any("Rule 1 PASSED" in msg for msg in log_messages)
