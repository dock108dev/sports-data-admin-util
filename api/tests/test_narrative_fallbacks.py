"""Tests for deterministic narrative fallbacks (Task 0.2).

These tests verify:
1. Valid fallbacks are used for low-signal gameplay
2. Invalid fallbacks are used for pipeline/AI failures
3. Fallback classification is correct based on moment context
4. Fallback narratives are never empty
"""



class TestFallbackClassification:
    """Tests for fallback type classification logic."""

    def test_valid_fallback_for_low_signal_gameplay(self):
        """VALID fallback when: no explicit plays, valid scores, valid metadata."""
        from app.services.pipeline.stages.render_narratives import (
            _classify_empty_narrative_fallback,
            FallbackType,
        )

        moment = {
            "play_ids": [1, 2],
            "explicitly_narrated_play_ids": [],  # No explicit plays
            "score_before": [10, 12],
            "score_after": [10, 12],  # No score change
            "period": 1,
            "start_clock": "10:30",
        }
        moment_plays = [
            {"play_index": 1, "description": "Defensive rebound"},
            {"play_index": 2, "description": "Ball advanced"},
        ]

        narrative, fallback_type, reason = _classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.VALID
        assert reason is None
        assert narrative in [
            "No scoring on this sequence.",
            "Possession traded without a basket.",
        ]
        assert "[Narrative unavailable" not in narrative

    def test_invalid_fallback_when_explicit_plays_exist(self):
        """INVALID fallback when: explicit plays exist but narrative is empty."""
        from app.services.pipeline.stages.render_narratives import (
            _classify_empty_narrative_fallback,
            FallbackType,
            FallbackReason,
        )

        moment = {
            "play_ids": [1, 2, 3],
            "explicitly_narrated_play_ids": [2],  # Has explicit play!
            "score_before": [10, 12],
            "score_after": [12, 12],
            "period": 1,
            "start_clock": "10:30",
        }
        moment_plays = [
            {"play_index": 1, "description": "Shot attempt"},
            {"play_index": 2, "description": "Made layup"},
            {"play_index": 3, "description": "Inbound"},
        ]

        narrative, fallback_type, reason = _classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.EMPTY_NARRATIVE_WITH_EXPLICIT_PLAYS
        assert "[Narrative unavailable" in narrative
        assert "explicit plays" in narrative.lower()

    def test_invalid_fallback_when_score_context_invalid(self):
        """INVALID fallback when: score context is missing or invalid."""
        from app.services.pipeline.stages.render_narratives import (
            _classify_empty_narrative_fallback,
            FallbackType,
            FallbackReason,
        )

        moment = {
            "play_ids": [1],
            "explicitly_narrated_play_ids": [],
            "score_before": None,  # Invalid!
            "score_after": [10, 12],
            "period": 1,
        }
        moment_plays = [{"play_index": 1, "description": "Foul"}]

        narrative, fallback_type, reason = _classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.SCORE_CONTEXT_INVALID
        assert "[Narrative unavailable" in narrative
        assert "score context" in narrative.lower()

    def test_invalid_fallback_when_score_decreases(self):
        """INVALID fallback when: score decreases within moment (non-monotonic)."""
        from app.services.pipeline.stages.render_narratives import (
            _classify_empty_narrative_fallback,
            FallbackType,
            FallbackReason,
        )

        moment = {
            "play_ids": [1],
            "explicitly_narrated_play_ids": [],
            "score_before": [15, 20],
            "score_after": [10, 20],  # Home score decreased!
            "period": 2,
        }
        moment_plays = [{"play_index": 1, "description": "Timeout"}]

        narrative, fallback_type, reason = _classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.SCORE_CONTEXT_INVALID
        assert "[Narrative unavailable" in narrative

    def test_invalid_fallback_when_play_metadata_missing(self):
        """INVALID fallback when: required play fields are missing."""
        from app.services.pipeline.stages.render_narratives import (
            _classify_empty_narrative_fallback,
            FallbackType,
            FallbackReason,
        )

        moment = {
            "play_ids": [1],
            "explicitly_narrated_play_ids": [],
            "score_before": [10, 12],
            "score_after": [10, 12],
            "period": 1,
        }
        moment_plays = []  # No plays!

        narrative, fallback_type, reason = _classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.MISSING_PLAY_METADATA
        assert "[Narrative unavailable" in narrative


class TestFallbackNarrativeGeneration:
    """Tests for fallback narrative text generation."""

    def test_valid_fallback_narratives_are_deterministic(self):
        """VALID fallbacks rotate deterministically based on moment index."""
        from app.services.pipeline.stages.render_narratives import (
            _get_valid_fallback_narrative,
            VALID_FALLBACK_NARRATIVES,
        )

        # Same index should always give same narrative
        assert _get_valid_fallback_narrative(0) == _get_valid_fallback_narrative(0)
        assert _get_valid_fallback_narrative(1) == _get_valid_fallback_narrative(1)

        # Different indices should rotate
        assert _get_valid_fallback_narrative(0) == VALID_FALLBACK_NARRATIVES[0]
        assert _get_valid_fallback_narrative(1) == VALID_FALLBACK_NARRATIVES[1]

        # Should cycle back
        assert _get_valid_fallback_narrative(0) == _get_valid_fallback_narrative(
            len(VALID_FALLBACK_NARRATIVES)
        )

    def test_invalid_fallback_narratives_include_reason(self):
        """INVALID fallbacks include diagnostic reason in text."""
        from app.services.pipeline.stages.render_narratives import (
            _get_invalid_fallback_narrative,
            FallbackReason,
        )

        for reason in FallbackReason:
            narrative = _get_invalid_fallback_narrative(reason)
            assert "[Narrative unavailable" in narrative
            assert "]" in narrative
            # Reason should be in human-readable form
            expected_text = reason.value.replace("_", " ")
            assert expected_text in narrative

    def test_fallback_narratives_are_never_empty(self):
        """All fallback generation functions return non-empty strings."""
        from app.services.pipeline.stages.render_narratives import (
            _get_valid_fallback_narrative,
            _get_invalid_fallback_narrative,
            FallbackReason,
        )

        # Test valid fallbacks
        for i in range(10):
            narrative = _get_valid_fallback_narrative(i)
            assert narrative
            assert len(narrative.strip()) > 0

        # Test invalid fallbacks
        for reason in FallbackReason:
            narrative = _get_invalid_fallback_narrative(reason)
            assert narrative
            assert len(narrative.strip()) > 0


class TestScoreContextValidation:
    """Tests for score context validation helper."""

    def test_valid_score_context(self):
        """Valid score context with proper structure and values."""
        from app.services.pipeline.stages.render_narratives import (
            _is_valid_score_context,
        )

        # Valid case
        moment = {
            "score_before": [10, 12],
            "score_after": [12, 12],
        }
        assert _is_valid_score_context(moment) is True

    def test_missing_score_before(self):
        """Invalid when score_before is missing."""
        from app.services.pipeline.stages.render_narratives import (
            _is_valid_score_context,
        )

        moment = {
            "score_before": None,
            "score_after": [10, 12],
        }
        assert _is_valid_score_context(moment) is False

    def test_missing_score_after(self):
        """Invalid when score_after is missing."""
        from app.services.pipeline.stages.render_narratives import (
            _is_valid_score_context,
        )

        moment = {
            "score_before": [10, 12],
            "score_after": None,
        }
        assert _is_valid_score_context(moment) is False

    def test_wrong_score_format(self):
        """Invalid when score format is wrong."""
        from app.services.pipeline.stages.render_narratives import (
            _is_valid_score_context,
        )

        # Single value instead of list
        moment = {"score_before": 10, "score_after": [10, 12]}
        assert _is_valid_score_context(moment) is False

        # Wrong length
        moment = {"score_before": [10], "score_after": [10, 12]}
        assert _is_valid_score_context(moment) is False

    def test_negative_scores(self):
        """Invalid when scores are negative."""
        from app.services.pipeline.stages.render_narratives import (
            _is_valid_score_context,
        )

        moment = {
            "score_before": [-1, 10],
            "score_after": [10, 12],
        }
        assert _is_valid_score_context(moment) is False

    def test_score_decrease(self):
        """Invalid when score decreases within moment."""
        from app.services.pipeline.stages.render_narratives import (
            _is_valid_score_context,
        )

        moment = {
            "score_before": [15, 20],
            "score_after": [10, 20],  # Away score decreased
        }
        assert _is_valid_score_context(moment) is False


class TestPlayMetadataValidation:
    """Tests for play metadata validation helper."""

    def test_valid_play_metadata(self):
        """Valid plays with required fields."""
        from app.services.pipeline.stages.render_narratives import (
            _has_valid_play_metadata,
        )

        plays = [
            {"play_index": 1, "description": "Made shot"},
            {"play_index": 2, "description": "Rebound"},
        ]
        assert _has_valid_play_metadata(plays) is True

    def test_empty_plays_list(self):
        """Invalid when plays list is empty."""
        from app.services.pipeline.stages.render_narratives import (
            _has_valid_play_metadata,
        )

        assert _has_valid_play_metadata([]) is False

    def test_missing_play_index(self):
        """Invalid when play_index is missing."""
        from app.services.pipeline.stages.render_narratives import (
            _has_valid_play_metadata,
        )

        plays = [{"description": "Made shot"}]  # No play_index
        assert _has_valid_play_metadata(plays) is False

    def test_missing_description_key(self):
        """Invalid when description key is missing."""
        from app.services.pipeline.stages.render_narratives import (
            _has_valid_play_metadata,
        )

        plays = [{"play_index": 1}]  # No description key
        assert _has_valid_play_metadata(plays) is False

    def test_empty_description_is_valid(self):
        """Empty description is valid (key exists but value is empty)."""
        from app.services.pipeline.stages.render_narratives import (
            _has_valid_play_metadata,
        )

        plays = [{"play_index": 1, "description": ""}]  # Empty but key exists
        assert _has_valid_play_metadata(plays) is True
