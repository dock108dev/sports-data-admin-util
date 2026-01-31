"""Tests for score continuity enforcement.

These tests verify the score continuity validation rules (Rules 6 and 7)
added to validate_moments.py as part of Phase 0 Task 0.1.
"""



class TestScoreNeverDecreases:
    """Tests for Rule 6: Score Never Decreases."""

    def test_valid_increasing_scores(self):
        """Scores that increase normally should pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        valid_moments = [
            {"play_ids": [1], "score_before": [0, 0], "score_after": [2, 0]},
            {"play_ids": [2], "score_before": [2, 0], "score_after": [2, 3]},
            {"play_ids": [3], "score_before": [2, 3], "score_after": [5, 3]},
        ]
        errors = _validate_score_never_decreases(valid_moments)
        assert len(errors) == 0, f"Expected no errors, got: {[e.to_dict() for e in errors]}"

    def test_score_decrease_between_moments_fails(self):
        """Score decrease between moments should be detected."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        decrease_moments = [
            {"play_ids": [1], "score_before": [0, 0], "score_after": [10, 8]},
            {"play_ids": [2], "score_before": [5, 8], "score_after": [5, 10]},  # away decreased!
        ]
        errors = _validate_score_never_decreases(decrease_moments)
        assert len(errors) > 0, "Expected error for score decrease"
        assert errors[0].code == "SCORE_DECREASE_BEFORE"

    def test_score_decrease_within_moment_fails(self):
        """Score that decreases within a moment should be detected."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_never_decreases,
        )

        decrease_moments = [
            {"play_ids": [1], "score_before": [10, 8], "score_after": [5, 8]},  # home decreased!
        ]
        errors = _validate_score_never_decreases(decrease_moments)
        assert len(errors) > 0, "Expected error for score decrease within moment"
        assert errors[0].code == "SCORE_DECREASE_WITHIN"


class TestScoreContinuity:
    """Tests for Rule 7: Score Continuity (score_before[n] == score_after[n-1])."""

    def test_valid_continuity(self):
        """Adjacent moments with matching scores should pass."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        valid_moments = [
            {"play_ids": [1], "score_before": [0, 0], "score_after": [2, 0]},
            {"play_ids": [2], "score_before": [2, 0], "score_after": [2, 3]},
            {"play_ids": [3], "score_before": [2, 3], "score_after": [5, 3]},
        ]
        errors = _validate_score_continuity(valid_moments)
        assert len(errors) == 0, f"Expected no errors, got: {[e.to_dict() for e in errors]}"

    def test_continuity_break_detected(self):
        """Score continuity break should be detected."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        invalid_moments = [
            {"play_ids": [1], "score_before": [0, 0], "score_after": [2, 0]},
            {"play_ids": [2], "score_before": [0, 0], "score_after": [2, 3]},  # WRONG: should be [2, 0]
        ]
        errors = _validate_score_continuity(invalid_moments)
        assert len(errors) > 0, "Expected error for continuity break"
        assert errors[0].code == "SCORE_CONTINUITY_BREAK"

    def test_score_reset_at_quarter_boundary_detected(self):
        """Score reset at quarter boundary (the main bug) should be detected."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        reset_moments = [
            {"play_ids": [1], "score_before": [0, 0], "score_after": [25, 22]},
            {"play_ids": [2], "score_before": [0, 0], "score_after": [0, 0]},  # Score reset!
        ]
        errors = _validate_score_continuity(reset_moments)
        assert len(errors) > 0, "Expected error for score reset at quarter boundary"
        assert errors[0].code == "SCORE_CONTINUITY_BREAK"
        assert "[25, 22]" in errors[0].message or "25" in errors[0].message

    def test_single_moment_no_continuity_check(self):
        """Single moment should not trigger continuity errors."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        single_moment = [
            {"play_ids": [1], "score_before": [0, 0], "score_after": [2, 0]},
        ]
        errors = _validate_score_continuity(single_moment)
        assert len(errors) == 0, "Single moment should have no continuity errors"

    def test_empty_moments_no_errors(self):
        """Empty moment list should not cause errors."""
        from app.services.pipeline.stages.validate_moments import (
            _validate_score_continuity,
        )

        errors = _validate_score_continuity([])
        assert len(errors) == 0
