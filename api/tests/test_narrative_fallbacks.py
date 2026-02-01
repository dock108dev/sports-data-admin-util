"""Tests for deterministic narrative fallbacks.

These tests verify:
1. Valid fallbacks are used for low-signal gameplay
2. Invalid fallbacks are used for pipeline/AI failures
3. Fallback classification is correct based on moment context
4. Fallback narratives are never empty
"""

from app.services.pipeline.stages.fallback_helpers import (
    classify_empty_narrative_fallback,
    get_invalid_fallback_narrative,
    get_valid_fallback_narrative,
    has_valid_play_metadata,
    is_valid_score_context,
)
from app.services.pipeline.stages.narrative_types import (
    FallbackReason,
    FallbackType,
    VALID_FALLBACK_NARRATIVES,
)


class TestFallbackClassification:
    """Tests for fallback type classification logic."""

    def test_valid_fallback_for_low_signal_gameplay(self):
        """VALID fallback when: no explicit plays, valid scores, valid metadata."""
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

        narrative, fallback_type, reason = classify_empty_narrative_fallback(
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

        narrative, fallback_type, reason = classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.EMPTY_NARRATIVE_WITH_EXPLICIT_PLAYS
        assert "[Narrative unavailable" in narrative
        assert "explicit plays" in narrative.lower()

    def test_invalid_fallback_when_score_context_invalid(self):
        """INVALID fallback when: score context is missing or invalid."""
        moment = {
            "play_ids": [1],
            "explicitly_narrated_play_ids": [],
            "score_before": None,  # Invalid!
            "score_after": [10, 12],
            "period": 1,
        }
        moment_plays = [{"play_index": 1, "description": "Foul"}]

        narrative, fallback_type, reason = classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.SCORE_CONTEXT_INVALID
        assert "[Narrative unavailable" in narrative
        assert "score context" in narrative.lower()

    def test_invalid_fallback_when_score_decreases(self):
        """INVALID fallback when: score decreases within moment (non-monotonic)."""
        moment = {
            "play_ids": [1],
            "explicitly_narrated_play_ids": [],
            "score_before": [15, 20],
            "score_after": [10, 20],  # Home score decreased!
            "period": 2,
        }
        moment_plays = [{"play_index": 1, "description": "Timeout"}]

        narrative, fallback_type, reason = classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.SCORE_CONTEXT_INVALID
        assert "[Narrative unavailable" in narrative

    def test_invalid_fallback_when_play_metadata_missing(self):
        """INVALID fallback when: required play fields are missing."""
        moment = {
            "play_ids": [1],
            "explicitly_narrated_play_ids": [],
            "score_before": [10, 12],
            "score_after": [10, 12],
            "period": 1,
        }
        moment_plays = []  # No plays!

        narrative, fallback_type, reason = classify_empty_narrative_fallback(
            moment, moment_plays, moment_index=5
        )

        assert fallback_type == FallbackType.INVALID
        assert reason == FallbackReason.MISSING_PLAY_METADATA
        assert "[Narrative unavailable" in narrative


class TestFallbackNarrativeGeneration:
    """Tests for fallback narrative text generation."""

    def test_valid_fallback_narratives_are_deterministic(self):
        """VALID fallbacks rotate deterministically based on moment index."""
        # Same index should always give same narrative
        assert get_valid_fallback_narrative(0) == get_valid_fallback_narrative(0)
        assert get_valid_fallback_narrative(1) == get_valid_fallback_narrative(1)

        # Different indices should rotate
        assert get_valid_fallback_narrative(0) == VALID_FALLBACK_NARRATIVES[0]
        assert get_valid_fallback_narrative(1) == VALID_FALLBACK_NARRATIVES[1]

        # Should cycle back
        assert get_valid_fallback_narrative(0) == get_valid_fallback_narrative(
            len(VALID_FALLBACK_NARRATIVES)
        )

    def test_invalid_fallback_narratives_include_reason(self):
        """INVALID fallbacks include diagnostic reason in text."""
        for reason in FallbackReason:
            narrative = get_invalid_fallback_narrative(reason)
            assert "[Narrative unavailable" in narrative
            assert "]" in narrative
            # Reason should be in human-readable form
            expected_text = reason.value.replace("_", " ")
            assert expected_text in narrative

    def test_fallback_narratives_are_never_empty(self):
        """All fallback generation functions return non-empty strings."""
        # Test valid fallbacks
        for i in range(10):
            narrative = get_valid_fallback_narrative(i)
            assert narrative
            assert len(narrative.strip()) > 0

        # Test invalid fallbacks
        for reason in FallbackReason:
            narrative = get_invalid_fallback_narrative(reason)
            assert narrative
            assert len(narrative.strip()) > 0


class TestScoreContextValidation:
    """Tests for score context validation helper."""

    def test_valid_score_context(self):
        """Valid score context with proper structure and values."""
        moment = {
            "score_before": [10, 12],
            "score_after": [12, 12],
        }
        assert is_valid_score_context(moment) is True

    def test_missing_score_before(self):
        """Invalid when score_before is missing."""
        moment = {
            "score_before": None,
            "score_after": [10, 12],
        }
        assert is_valid_score_context(moment) is False

    def test_missing_score_after(self):
        """Invalid when score_after is missing."""
        moment = {
            "score_before": [10, 12],
            "score_after": None,
        }
        assert is_valid_score_context(moment) is False

    def test_wrong_score_format(self):
        """Invalid when score format is wrong."""
        # Single value instead of list
        moment = {"score_before": 10, "score_after": [10, 12]}
        assert is_valid_score_context(moment) is False

        # Wrong length
        moment = {"score_before": [10], "score_after": [10, 12]}
        assert is_valid_score_context(moment) is False

    def test_negative_scores(self):
        """Invalid when scores are negative."""
        moment = {
            "score_before": [-1, 10],
            "score_after": [10, 12],
        }
        assert is_valid_score_context(moment) is False

    def test_score_decrease(self):
        """Invalid when score decreases within moment."""
        moment = {
            "score_before": [15, 20],
            "score_after": [10, 20],  # Away score decreased
        }
        assert is_valid_score_context(moment) is False

    def test_wrong_score_after_format(self):
        """Invalid when score_after format is wrong."""
        # Single value instead of list for score_after
        moment = {"score_before": [10, 12], "score_after": 15}
        assert is_valid_score_context(moment) is False

        # Wrong length for score_after
        moment = {"score_before": [10, 12], "score_after": [15]}
        assert is_valid_score_context(moment) is False

    def test_negative_score_after(self):
        """Invalid when score_after values are negative."""
        moment = {
            "score_before": [10, 12],
            "score_after": [-1, 15],  # Negative score_after
        }
        assert is_valid_score_context(moment) is False

        moment = {
            "score_before": [10, 12],
            "score_after": [15, -2],  # Negative score_after (home)
        }
        assert is_valid_score_context(moment) is False

    def test_score_with_non_numeric_values(self):
        """Invalid when scores contain non-numeric values."""
        # Non-numeric in score_before
        moment = {"score_before": ["a", 12], "score_after": [10, 12]}
        assert is_valid_score_context(moment) is False

        # Non-numeric in score_after
        moment = {"score_before": [10, 12], "score_after": [10, "b"]}
        assert is_valid_score_context(moment) is False


class TestPlayMetadataValidation:
    """Tests for play metadata validation helper."""

    def test_valid_play_metadata(self):
        """Valid plays with required fields."""
        plays = [
            {"play_index": 1, "description": "Made shot"},
            {"play_index": 2, "description": "Rebound"},
        ]
        assert has_valid_play_metadata(plays) is True

    def test_empty_plays_list(self):
        """Invalid when plays list is empty."""
        assert has_valid_play_metadata([]) is False

    def test_missing_play_index(self):
        """Invalid when play_index is missing."""
        plays = [{"description": "Made shot"}]  # No play_index
        assert has_valid_play_metadata(plays) is False

    def test_missing_description_key(self):
        """Invalid when description key is missing."""
        plays = [{"play_index": 1}]  # No description key
        assert has_valid_play_metadata(plays) is False

    def test_empty_description_is_valid(self):
        """Empty description is valid (key exists but value is empty)."""
        plays = [{"play_index": 1, "description": ""}]  # Empty but key exists
        assert has_valid_play_metadata(plays) is True
