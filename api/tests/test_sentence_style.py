"""Tests for sentence style constraints (Task 2.2).

These tests verify:
1. Sentence length variance detection
2. Repeated opener detection
3. Metric-first sentence detection
4. Template repetition detection
5. Style validation integration
"""

import pytest


class TestSentenceSplitting:
    """Tests for sentence splitting helper."""

    def test_split_simple_sentences(self):
        """Split simple sentences correctly."""
        from app.services.pipeline.stages.render_narratives import _split_into_sentences

        text = "Mitchell scored. Brown answered with a three."
        sentences = _split_into_sentences(text)

        assert len(sentences) == 2
        assert "Mitchell scored" in sentences[0]
        assert "Brown answered" in sentences[1]

    def test_split_handles_abbreviations(self):
        """Abbreviations should not cause splits."""
        from app.services.pipeline.stages.render_narratives import _split_into_sentences

        text = "Lakers vs. Celtics was great. The game ended in overtime."
        sentences = _split_into_sentences(text)

        assert len(sentences) == 2

    def test_split_handles_empty_text(self):
        """Empty text returns empty list."""
        from app.services.pipeline.stages.render_narratives import _split_into_sentences

        assert _split_into_sentences("") == []
        assert _split_into_sentences("   ") == []
        assert _split_into_sentences(None) == []

    def test_split_handles_exclamation_marks(self):
        """Exclamation marks end sentences."""
        from app.services.pipeline.stages.render_narratives import _split_into_sentences

        text = "What a shot! Mitchell delivered. The crowd reacted."
        sentences = _split_into_sentences(text)

        assert len(sentences) == 3


class TestSentenceLengthVariance:
    """Tests for sentence length variance detection."""

    def test_variance_with_diverse_lengths(self):
        """Diverse sentence lengths should pass."""
        from app.services.pipeline.stages.render_narratives import (
            _check_sentence_length_variance,
        )

        sentences = [
            "Mitchell scored",  # 2 words
            "The Lakers answered with a three-pointer from the corner",  # 9 words
            "Brown hit a jumper",  # 4 words
        ]

        has_variance, score = _check_sentence_length_variance(sentences)
        assert has_variance is True

    def test_no_variance_with_uniform_lengths(self):
        """Uniform sentence lengths should fail."""
        from app.services.pipeline.stages.render_narratives import (
            _check_sentence_length_variance,
        )

        sentences = [
            "Mitchell scored on layup",  # 4 words
            "Brown answered with three",  # 4 words
            "James blocked the shot",  # 4 words
        ]

        has_variance, score = _check_sentence_length_variance(sentences)
        # All 4 words - very uniform
        assert has_variance is False

    def test_variance_single_sentence(self):
        """Single sentence always passes."""
        from app.services.pipeline.stages.render_narratives import (
            _check_sentence_length_variance,
        )

        sentences = ["Just one sentence here"]
        has_variance, score = _check_sentence_length_variance(sentences)
        assert has_variance is True


class TestRepeatedOpeners:
    """Tests for repeated sentence opener detection."""

    def test_detect_repeated_openers(self):
        """Same opener repeated should be detected."""
        from app.services.pipeline.stages.render_narratives import (
            _check_repeated_openers,
        )

        sentences = [
            "The Lakers scored on a fast break",
            "The Lakers answered with a three",
            "The Lakers extended the lead",
        ]

        repeated = _check_repeated_openers(sentences)
        assert len(repeated) > 0
        assert "the lakers" in repeated

    def test_no_repeated_openers(self):
        """Different openers should pass."""
        from app.services.pipeline.stages.render_narratives import (
            _check_repeated_openers,
        )

        sentences = [
            "Mitchell scored on a layup",
            "The Lakers responded with a dunk",
            "After a timeout, Brown hit a three",
        ]

        repeated = _check_repeated_openers(sentences)
        assert len(repeated) == 0

    def test_repeated_openers_single_sentence(self):
        """Single sentence has no repeated openers."""
        from app.services.pipeline.stages.render_narratives import (
            _check_repeated_openers,
        )

        sentences = ["Just one sentence"]
        repeated = _check_repeated_openers(sentences)
        assert len(repeated) == 0


class TestMetricFirstSentences:
    """Tests for metric-first sentence detection."""

    def test_detect_points_scored(self):
        """Points scored patterns should be detected."""
        from app.services.pipeline.stages.render_narratives import (
            _check_metric_first_sentences,
        )

        sentences = [
            "Mitchell scored 12 points in the quarter",
            "The team shot 4-of-5 from three",
        ]

        metric_first = _check_metric_first_sentences(sentences)
        assert len(metric_first) == 2

    def test_detect_shooting_stats(self):
        """Shooting stat patterns should be detected."""
        from app.services.pipeline.stages.render_narratives import (
            _check_metric_first_sentences,
        )

        sentences = [
            "Curry went 3-for-4 from three",
            "With 15 points, James led the team",
        ]

        metric_first = _check_metric_first_sentences(sentences)
        assert len(metric_first) == 2

    def test_action_first_allowed(self):
        """Action-first sentences should not be detected."""
        from app.services.pipeline.stages.render_narratives import (
            _check_metric_first_sentences,
        )

        sentences = [
            "Mitchell drove to the basket for a layup",
            "The Lakers extended their lead with a three",
            "Brown grabbed the rebound and pushed the ball",
        ]

        metric_first = _check_metric_first_sentences(sentences)
        assert len(metric_first) == 0


class TestTemplateRepetition:
    """Tests for template repetition detection."""

    def test_detect_same_template(self):
        """Same sentence template repeated should be detected."""
        from app.services.pipeline.stages.render_narratives import (
            _check_template_repetition,
        )

        # Same "scored on a" pattern repeated 3 times
        sentences = [
            "Mitchell scored on a layup",
            "Brown scored on a jumper",
            "James scored on a dunk",
            "Curry scored on a three",
        ]

        has_repetition = _check_template_repetition(sentences)
        assert has_repetition is True

    def test_varied_templates(self):
        """Different templates should pass."""
        from app.services.pipeline.stages.render_narratives import (
            _check_template_repetition,
        )

        sentences = [
            "Mitchell drove baseline for the layup",
            "The Lakers answered when Brown hit a three",
            "After the timeout, James grabbed the rebound",
        ]

        has_repetition = _check_template_repetition(sentences)
        assert has_repetition is False

    def test_template_single_sentence(self):
        """Single sentence has no repetition."""
        from app.services.pipeline.stages.render_narratives import (
            _check_template_repetition,
        )

        sentences = ["Just one sentence here"]
        has_repetition = _check_template_repetition(sentences)
        assert has_repetition is False


class TestStyleValidation:
    """Tests for integrated style validation."""

    def test_good_style_passes(self):
        """Well-written narrative should have no warnings."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        narrative = (
            "The Suns opened with back-to-back baskets before the Lakers answered with a three. "
            "Mitchell converted in transition. "
            "The lead grew to five as the quarter wound down."
        )

        warnings, details = _validate_narrative_style(narrative, 0)
        # May have minor warnings, but should be limited
        assert len(warnings) <= 1

    def test_bad_style_has_warnings(self):
        """Poorly styled narrative should have warnings."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        # All sentences start the same way
        narrative = (
            "The Lakers scored. The Lakers answered. The Lakers extended."
        )

        warnings, details = _validate_narrative_style(narrative, 0)
        assert len(warnings) > 0

    def test_metric_first_detected(self):
        """Metric-first narrative should be flagged."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        narrative = (
            "Mitchell scored 12 points in the quarter. "
            "The team shot 4-of-5 during the stretch. "
            "Curry went 3-for-4 from three."
        )

        warnings, details = _validate_narrative_style(narrative, 0)
        assert len(warnings) > 0
        assert any("metric" in w.lower() for w in warnings)


class TestStyleViolationType:
    """Tests for StyleViolationType enum."""

    def test_violation_types_exist(self):
        """All expected violation types should exist."""
        from app.services.pipeline.stages.render_narratives import StyleViolationType

        assert StyleViolationType.REPEATED_OPENER.value == "repeated_opener"
        assert StyleViolationType.UNIFORM_LENGTH.value == "uniform_length"
        assert StyleViolationType.METRIC_FIRST.value == "metric_first"
        assert StyleViolationType.TEMPLATE_REPETITION.value == "template_repetition"


class TestValidateNarrativeWithStyle:
    """Tests for _validate_narrative with style checking."""

    def test_validate_returns_style_details(self):
        """_validate_narrative should return style details."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        narrative = (
            "The Lakers scored. The Lakers answered. The Lakers extended."
        )
        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [{"play_index": 1}, {"play_index": 2}]

        hard_errors, soft_errors, style_details = _validate_narrative(
            narrative, moment, moment_plays, 0, check_style=True
        )

        # Should have style warnings in soft_errors
        # style_details should have structured info
        assert isinstance(style_details, list)

    def test_validate_without_style_check(self):
        """Style check can be disabled."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        narrative = (
            "The Lakers scored. The Lakers answered. The Lakers extended."
        )
        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [{"play_index": 1}, {"play_index": 2}]

        hard_errors, soft_errors, style_details = _validate_narrative(
            narrative, moment, moment_plays, 0, check_style=False
        )

        # No style details when disabled
        assert style_details == []


class TestPromptStyleGuidance:
    """Tests for style guidance in prompts."""

    def test_prompt_includes_variance_guidance(self):
        """Prompt should include sentence variance guidance."""
        from app.services.pipeline.stages.render_narratives import _build_batch_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [2, 0],
            "explicitly_narrated_play_ids": [1],
        }
        moment_plays = [{"play_index": 1, "description": "Made shot"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        prompt = _build_batch_prompt([(0, moment, moment_plays)], game_context)

        assert "vary sentence length" in prompt.lower()
        assert "vary sentence opener" in prompt.lower()

    def test_prompt_includes_action_first_guidance(self):
        """Prompt should include action-first guidance."""
        from app.services.pipeline.stages.render_narratives import _build_batch_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [2, 0],
            "explicitly_narrated_play_ids": [1],
        }
        moment_plays = [{"play_index": 1, "description": "Made shot"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        prompt = _build_batch_prompt([(0, moment, moment_plays)], game_context)

        assert "lead with actions" in prompt.lower() or "action" in prompt.lower()

    def test_retry_prompt_has_style_emphasis(self):
        """Retry prompt should emphasize style requirements."""
        from app.services.pipeline.stages.render_narratives import _build_batch_prompt

        moment = {
            "period": 1,
            "start_clock": "10:00",
            "score_before": [0, 0],
            "score_after": [2, 0],
            "explicitly_narrated_play_ids": [1],
        }
        moment_plays = [{"play_index": 1, "description": "Made shot"}]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        prompt = _build_batch_prompt([(0, moment, moment_plays)], game_context, is_retry=True)

        assert "style" in prompt.lower()


class TestNaturalReadability:
    """Tests verifying natural readability when spoken aloud."""

    def test_broadcast_style_example(self):
        """Good broadcast-style narrative should pass validation."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        # This is the kind of narrative we want - 3 sentences with varied structure
        narrative = (
            "The Suns opened with back-to-back baskets before the Lakers answered with a three. "
            "Mitchell converted in transition. "
            "The lead extended to five as the quarter wound down."
        )

        warnings, details = _validate_narrative_style(narrative, 0)
        # Should have minimal or no warnings
        assert len(warnings) <= 1  # Allow 1 minor warning

    def test_stat_sheet_style_fails(self):
        """Stat-sheet style narrative should have warnings."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        # This reads like a stat sheet, not a broadcast
        narrative = (
            "Mitchell scored 8 points. The team shot 4-of-5. Curry went 2-for-3 from three."
        )

        warnings, details = _validate_narrative_style(narrative, 0)
        # Should have warnings about metric-first and similar structure
        assert len(warnings) > 0


class TestEdgeCases:
    """Tests for edge cases in style validation."""

    def test_empty_narrative(self):
        """Empty narrative should not crash."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        warnings, details = _validate_narrative_style("", 0)
        assert warnings == []
        assert details == []

    def test_single_sentence_narrative(self):
        """Single sentence should not have style issues."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        warnings, details = _validate_narrative_style("Mitchell scored on a layup.", 0)
        assert warnings == []

    def test_two_sentence_narrative(self):
        """Two sentences with different structure should pass (lenient for short narratives)."""
        from app.services.pipeline.stages.render_narratives import (
            _validate_narrative_style,
        )

        narrative = "Mitchell drove to the basket. The Lakers extended their lead."
        warnings, details = _validate_narrative_style(narrative, 0)
        # Two sentences get lenient treatment - should pass
        # (Style checks are mainly for 3+ sentence narratives)
        assert len(warnings) == 0
