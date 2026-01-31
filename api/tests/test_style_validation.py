"""Tests for style_validation stage."""


class TestSplitIntoSentences:
    """Tests for split_into_sentences function."""

    def test_empty_input(self):
        """Empty input returns empty list."""
        from app.services.pipeline.stages.style_validation import split_into_sentences

        assert split_into_sentences("") == []
        assert split_into_sentences(None) == []
        assert split_into_sentences("   ") == []

    def test_single_sentence(self):
        """Single sentence is returned."""
        from app.services.pipeline.stages.style_validation import split_into_sentences

        result = split_into_sentences("Smith hit a three.")
        assert result == ["Smith hit a three."]

    def test_multiple_sentences(self):
        """Multiple sentences are split correctly."""
        from app.services.pipeline.stages.style_validation import split_into_sentences

        result = split_into_sentences("Smith hit a three. Jones got the rebound.")
        assert result == ["Smith hit a three.", "Jones got the rebound."]

    def test_exclamation_and_question(self):
        """Handles exclamation and question marks."""
        from app.services.pipeline.stages.style_validation import split_into_sentences

        result = split_into_sentences("What a shot! Did you see that?")
        assert len(result) == 2

    def test_abbreviations_preserved(self):
        """Common abbreviations don't cause splits."""
        from app.services.pipeline.stages.style_validation import split_into_sentences

        result = split_into_sentences("The Lakers vs. the Celtics. Great game.")
        assert len(result) == 2

        result = split_into_sentences("Dr. Smith made a shot. Mr. Jones blocked it.")
        assert len(result) == 2

    def test_whitespace_handling(self):
        """Extra whitespace is handled."""
        from app.services.pipeline.stages.style_validation import split_into_sentences

        result = split_into_sentences("First sentence.   Second sentence.")
        assert len(result) == 2


class TestGetSentenceOpener:
    """Tests for get_sentence_opener function."""

    def test_default_three_words(self):
        """Default extracts 3 words."""
        from app.services.pipeline.stages.style_validation import get_sentence_opener

        result = get_sentence_opener("The Lakers scored on a fast break.")
        assert result == "the lakers scored"

    def test_custom_word_count(self):
        """Custom word count works."""
        from app.services.pipeline.stages.style_validation import get_sentence_opener

        result = get_sentence_opener("The Lakers scored on a fast break.", 2)
        assert result == "the lakers"

    def test_short_sentence(self):
        """Short sentence returns available words."""
        from app.services.pipeline.stages.style_validation import get_sentence_opener

        result = get_sentence_opener("He scored.")
        assert result == "he scored."

    def test_lowercase(self):
        """Returns lowercase."""
        from app.services.pipeline.stages.style_validation import get_sentence_opener

        result = get_sentence_opener("SMITH HIT A THREE.")
        assert result == "smith hit a"


class TestCheckSentenceLengthVariance:
    """Tests for check_sentence_length_variance function."""

    def test_single_sentence(self):
        """Single sentence passes."""
        from app.services.pipeline.stages.style_validation import (
            check_sentence_length_variance,
        )

        has_variance, _ = check_sentence_length_variance(["One sentence here."])
        assert has_variance is True

    def test_varied_lengths(self):
        """Varied lengths pass."""
        from app.services.pipeline.stages.style_validation import (
            check_sentence_length_variance,
        )

        sentences = [
            "Short one.",
            "This is a much longer sentence with more words.",
            "Medium here.",
        ]
        has_variance, _ = check_sentence_length_variance(sentences)
        assert has_variance is True

    def test_uniform_lengths(self):
        """Very uniform lengths fail for 3+ sentences."""
        from app.services.pipeline.stages.style_validation import (
            check_sentence_length_variance,
        )

        sentences = [
            "One two three four.",  # 4 words
            "One two three five.",  # 4 words
            "One two three here.",  # 4 words
        ]
        has_variance, _ = check_sentence_length_variance(sentences)
        assert has_variance is False

    def test_two_sentences_always_pass(self):
        """Two sentences always pass (skip check)."""
        from app.services.pipeline.stages.style_validation import (
            check_sentence_length_variance,
        )

        sentences = [
            "One two three four.",  # 4 words
            "One two three five.",  # 4 words
        ]
        has_variance, _ = check_sentence_length_variance(sentences)
        # Only fails with 3+ sentences of very narrow range
        assert has_variance is True


class TestCheckRepeatedOpeners:
    """Tests for check_repeated_openers function."""

    def test_no_repeats(self):
        """No repeated openers returns empty."""
        from app.services.pipeline.stages.style_validation import check_repeated_openers

        sentences = [
            "Smith scored the basket.",
            "Jones got the rebound.",
            "Brown made the steal.",
        ]
        result = check_repeated_openers(sentences)
        assert result == []

    def test_repeated_openers(self):
        """Repeated openers are detected."""
        from app.services.pipeline.stages.style_validation import check_repeated_openers

        # Same 3-word opener "the lakers scored"
        sentences = [
            "The Lakers scored again.",
            "The Lakers scored another basket.",
            "The Celtics fought back.",
        ]
        result = check_repeated_openers(sentences)
        assert len(result) == 1
        assert "the lakers scored" in result[0]

    def test_single_sentence(self):
        """Single sentence returns empty."""
        from app.services.pipeline.stages.style_validation import check_repeated_openers

        result = check_repeated_openers(["Just one sentence."])
        assert result == []


class TestCheckMetricFirstSentences:
    """Tests for check_metric_first_sentences function."""

    def test_no_metrics(self):
        """No metric-first sentences returns empty."""
        from app.services.pipeline.stages.style_validation import (
            check_metric_first_sentences,
        )

        sentences = [
            "Smith drove to the basket.",
            "Jones grabbed the rebound.",
        ]
        result = check_metric_first_sentences(sentences)
        assert result == []

    def test_points_metric_first(self):
        """Detects points metric-first."""
        from app.services.pipeline.stages.style_validation import (
            check_metric_first_sentences,
        )

        sentences = [
            "Smith scored 12 points.",
            "Jones grabbed the rebound.",
        ]
        result = check_metric_first_sentences(sentences)
        assert len(result) >= 1

    def test_shooting_stat_first(self):
        """Detects shooting stats first."""
        from app.services.pipeline.stages.style_validation import (
            check_metric_first_sentences,
        )

        sentences = [
            "Smith shot 4-of-5 from the line.",
            "Jones played well.",
        ]
        result = check_metric_first_sentences(sentences)
        assert len(result) >= 1

    def test_with_metric_prefix(self):
        """Detects 'With X points' construction."""
        from app.services.pipeline.stages.style_validation import (
            check_metric_first_sentences,
        )

        sentences = [
            "With 15 points already, Smith kept scoring.",
            "The game continued.",
        ]
        result = check_metric_first_sentences(sentences)
        assert len(result) >= 1


class TestCheckTemplateRepetition:
    """Tests for check_template_repetition function."""

    def test_no_repetition(self):
        """Varied sentences don't trigger."""
        from app.services.pipeline.stages.style_validation import (
            check_template_repetition,
        )

        sentences = [
            "Smith drove to the basket.",
            "Jones got the rebound.",
            "Brown took the shot.",
        ]
        assert check_template_repetition(sentences) is False

    def test_scored_on_pattern(self):
        """Detects 'X scored on a' repetition."""
        from app.services.pipeline.stages.style_validation import (
            check_template_repetition,
        )

        sentences = [
            "Smith scored on a layup.",
            "Jones scored on a dunk.",
            "Brown scored on a three.",
        ]
        assert check_template_repetition(sentences) is True

    def test_made_a_pattern(self):
        """Detects 'X made a' repetition."""
        from app.services.pipeline.stages.style_validation import (
            check_template_repetition,
        )

        sentences = [
            "Smith made a three.",
            "Jones made a layup.",
            "Brown made a dunk.",
        ]
        assert check_template_repetition(sentences) is True

    def test_two_sentences_no_check(self):
        """Two sentences don't trigger (need 3+)."""
        from app.services.pipeline.stages.style_validation import (
            check_template_repetition,
        )

        sentences = [
            "Smith scored on a layup.",
            "Jones scored on a dunk.",
        ]
        assert check_template_repetition(sentences) is False


class TestValidateNarrativeStyle:
    """Tests for validate_narrative_style function."""

    def test_empty_narrative(self):
        """Empty narrative returns no warnings."""
        from app.services.pipeline.stages.style_validation import (
            validate_narrative_style,
        )

        warnings, details = validate_narrative_style("", 0)
        assert warnings == []
        assert details == []

    def test_short_narrative_skipped(self):
        """Short narratives (<=2 sentences) skip style checks."""
        from app.services.pipeline.stages.style_validation import (
            validate_narrative_style,
        )

        warnings, details = validate_narrative_style("One sentence. Two sentences.", 0)
        assert warnings == []

    def test_good_narrative_passes(self):
        """Good varied narrative has no warnings."""
        from app.services.pipeline.stages.style_validation import (
            validate_narrative_style,
        )

        narrative = (
            "Smith drove to the basket for an easy layup. "
            "Jones grabbed the defensive rebound on the other end. "
            "The possession ended with a turnover."
        )
        warnings, details = validate_narrative_style(narrative, 0)
        assert len(warnings) == 0

    def test_repeated_openers_warning(self):
        """Repeated openers generate warnings."""
        from app.services.pipeline.stages.style_validation import (
            validate_narrative_style,
        )

        # Same 3-word opener "the lakers scored"
        narrative = (
            "The Lakers scored on a layup. "
            "The Lakers scored from downtown. "
            "The Lakers scored on a dunk."
        )
        warnings, details = validate_narrative_style(narrative, 0)
        # Should detect repeated "the lakers scored" opener
        assert any("repeated" in w.lower() or "opener" in w.lower() for w in warnings)
