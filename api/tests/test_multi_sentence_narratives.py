"""Tests for multi-sentence narrative generation (Task 1.2).

These tests verify:
1. Sentence counting logic works correctly
2. Explicit play coverage is validated
3. Hard/soft error separation works properly
4. Forbidden language detection includes new subjective adjectives
5. Prompt generates 2-4 sentence narratives
"""



class TestSentenceCounting:
    """Tests for sentence counting helper."""

    def test_empty_text_returns_zero(self):
        """Empty text should return 0 sentences."""
        from app.services.pipeline.stages.render_narratives import _count_sentences

        assert _count_sentences("") == 0
        assert _count_sentences("   ") == 0
        assert _count_sentences(None) == 0

    def test_single_sentence(self):
        """Single sentence should return 1."""
        from app.services.pipeline.stages.render_narratives import _count_sentences

        assert _count_sentences("Mitchell scored on a layup.") == 1
        assert _count_sentences("The Lakers won the game!") == 1
        assert _count_sentences("Who made that shot?") == 1

    def test_multiple_sentences(self):
        """Multiple sentences should be counted correctly."""
        from app.services.pipeline.stages.render_narratives import _count_sentences

        text = "Mitchell scored on a layup. Brown followed with a three."
        assert _count_sentences(text) == 2

        text = "The Suns opened with back-to-back baskets. The Lakers answered with a three. Mitchell converted in transition."
        assert _count_sentences(text) == 3

    def test_handles_abbreviations(self):
        """Common abbreviations should not be counted as sentence endings."""
        from app.services.pipeline.stages.render_narratives import _count_sentences

        # "vs." should not end a sentence
        text = "Lakers vs. Celtics was a great game. Mitchell led all scorers."
        assert _count_sentences(text) == 2

        # "Q1." should not end a sentence
        text = "In Q1. Mitchell had 10 points."
        assert _count_sentences(text) == 1

    def test_sentence_with_exclamation(self):
        """Exclamation marks should end sentences."""
        from app.services.pipeline.stages.render_narratives import _count_sentences

        text = "What a play! Mitchell dunked it. The crowd reacted."
        assert _count_sentences(text) == 3


class TestExplicitPlayCoverage:
    """Tests for explicit play coverage validation."""

    def test_no_explicit_plays_returns_empty(self):
        """Moments with no explicit plays should return empty list."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [{"play_index": 1, "description": "Shot"}]
        narrative = "Some narrative."

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == []

    def test_explicit_play_covered_by_player_name(self):
        """Explicit plays covered by player name should not be missing."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        moment = {"explicitly_narrated_play_ids": [1]}
        moment_plays = [
            {"play_index": 1, "player_name": "Donovan Mitchell", "description": "Made layup"}
        ]
        narrative = "Mitchell scored on a layup."

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == []

    def test_explicit_play_covered_by_full_name(self):
        """Explicit plays covered by full player name should not be missing."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        moment = {"explicitly_narrated_play_ids": [1]}
        moment_plays = [
            {"play_index": 1, "player_name": "Donovan Mitchell", "description": "Made three"}
        ]
        narrative = "Donovan Mitchell hit a three-pointer."

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == []

    def test_explicit_play_missing_from_narrative(self):
        """Explicit plays not mentioned should be returned as missing."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        moment = {"explicitly_narrated_play_ids": [1]}
        moment_plays = [
            {"play_index": 1, "player_name": "Donovan Mitchell", "description": "Made layup"}
        ]
        narrative = "The Lakers scored on a fast break."

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == [1]

    def test_multiple_explicit_plays_partial_coverage(self):
        """When some explicit plays are missing, only those should be returned."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        moment = {"explicitly_narrated_play_ids": [1, 2]}
        moment_plays = [
            {"play_index": 1, "player_name": "Donovan Mitchell", "description": "Made layup"},
            {"play_index": 2, "player_name": "Jaylen Brown", "description": "Made three"},
        ]
        narrative = "Mitchell scored on a layup."  # Missing Brown

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == [2]

    def test_coverage_by_team_abbreviation(self):
        """Explicit plays can be covered by team abbreviation."""
        from app.services.pipeline.stages.render_narratives import (
            _check_explicit_play_coverage,
        )

        moment = {"explicitly_narrated_play_ids": [1]}
        moment_plays = [
            {"play_index": 1, "team_abbreviation": "LAL", "description": "Team timeout"}
        ]
        narrative = "LAL called timeout."

        missing = _check_explicit_play_coverage(narrative, moment, moment_plays)
        assert missing == []


class TestNarrativeValidation:
    """Tests for narrative validation with hard/soft error separation."""

    def test_empty_narrative_is_hard_error(self):
        """Empty narrative should be a hard error."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [{"play_index": 1, "description": "Shot"}]

        # Task 2.2: Now returns 3 values (hard_errors, soft_errors, style_details)
        hard_errors, soft_errors, _ = _validate_narrative("", moment, moment_plays, 0)

        assert len(hard_errors) > 0
        assert "empty" in hard_errors[0].lower()

    def test_missing_explicit_play_is_hard_error(self):
        """Missing explicit play reference should be a hard error."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        moment = {"explicitly_narrated_play_ids": [1]}
        moment_plays = [
            {"play_index": 1, "player_name": "Mitchell", "description": "Made layup"}
        ]
        narrative = "The Lakers played well this quarter."

        hard_errors, soft_errors, _ = _validate_narrative(narrative, moment, moment_plays, 0)

        assert len(hard_errors) > 0
        assert "explicit" in hard_errors[0].lower() or "missing" in hard_errors[0].lower()

    def test_forbidden_phrase_is_soft_error(self):
        """Forbidden phrases should be soft errors (can retry)."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [{"play_index": 1, "description": "Shot"}]
        narrative = "This was a crucial turning point in the game."

        hard_errors, soft_errors, _ = _validate_narrative(narrative, moment, moment_plays, 0)

        assert len(hard_errors) == 0
        assert len(soft_errors) > 0
        assert any("crucial" in e.lower() or "turning point" in e.lower() for e in soft_errors)

    def test_single_sentence_for_multiple_plays_is_soft_error(self):
        """Single sentence when multiple plays exist should be soft error."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        moment = {"explicitly_narrated_play_ids": []}
        moment_plays = [
            {"play_index": 1, "description": "Shot"},
            {"play_index": 2, "description": "Rebound"},
            {"play_index": 3, "description": "Layup"},
        ]
        narrative = "Mitchell scored on a layup."  # Only 1 sentence for 3 plays

        hard_errors, soft_errors, _ = _validate_narrative(
            narrative, moment, moment_plays, 0, strict_sentence_check=True
        )

        assert len(hard_errors) == 0
        assert len(soft_errors) > 0
        assert any("sentence" in e.lower() for e in soft_errors)

    def test_valid_multi_sentence_narrative_passes(self):
        """Valid multi-sentence narrative should have no errors."""
        from app.services.pipeline.stages.render_narratives import _validate_narrative

        moment = {"explicitly_narrated_play_ids": [1]}
        moment_plays = [
            {"play_index": 1, "player_name": "Donovan Mitchell", "description": "Made layup"},
            {"play_index": 2, "description": "Rebound"},
        ]
        narrative = (
            "Mitchell drove to the basket and finished with a layup. "
            "The Lakers grabbed the rebound on the next possession."
        )

        hard_errors, soft_errors, _ = _validate_narrative(
            narrative, moment, moment_plays, 0, check_style=False  # Disable style check
        )

        assert len(hard_errors) == 0
        assert len(soft_errors) == 0


class TestForbiddenSubjectiveAdjectives:
    """Tests for new forbidden subjective adjectives (Task 1.2)."""

    def test_dominant_is_forbidden(self):
        """'Dominant' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Mitchell had a dominant performance."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_electric_is_forbidden(self):
        """'Electric' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "The Suns went on an electric run."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_huge_is_forbidden(self):
        """'Huge' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "That was a huge shot by Mitchell."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_massive_is_forbidden(self):
        """'Massive' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "A massive dunk from Brown."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_took_over_is_forbidden(self):
        """'Took over' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Mitchell took over the game."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_crowd_erupted_is_forbidden(self):
        """'Crowd erupted' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "The crowd erupted after the dunk."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_clutch_is_forbidden(self):
        """'Clutch' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "What a clutch shot!"
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_wanted_to_is_forbidden(self):
        """'Wanted to' (speculation) should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Mitchell wanted to prove a point."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)


class TestForbiddenIntentLanguage:
    """Tests for forbidden intent/psychology speculation."""

    def test_tried_to_is_forbidden(self):
        """'Tried to' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Brown tried to block the shot."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_needed_to_is_forbidden(self):
        """'Needed to' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "The Lakers needed to make a stop."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_felt_is_forbidden(self):
        """'Felt' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Mitchell felt confident after the three."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)

    def test_frustrated_is_forbidden(self):
        """'Frustrated' should be forbidden."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Brown looked frustrated after the foul."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert any(m for m in matches if m)


class TestAllowedFactualLanguage:
    """Tests that factual basketball language is allowed."""

    def test_scoring_run_is_allowed(self):
        """'Scoring run' is factual and should be allowed."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "The Lakers went on a 10-2 scoring run."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert not any(m for m in matches if m)

    def test_unanswered_points_is_allowed(self):
        """'Unanswered points' is factual and should be allowed."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "The Suns scored 8 unanswered points."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert not any(m for m in matches if m)

    def test_answered_with_is_allowed(self):
        """'Answered with' is factual and should be allowed."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "The Lakers answered with a three-pointer."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert not any(m for m in matches if m)

    def test_concrete_actions_allowed(self):
        """Concrete basketball actions should be allowed."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Mitchell drove baseline and finished with a layup, giving the Celtics a 45-42 lead."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert not any(m for m in matches if m)

    def test_extended_lead_is_allowed(self):
        """'Extended the lead' is factual and should be allowed."""
        from app.services.pipeline.stages.render_narratives import FORBIDDEN_PATTERNS

        text = "Mitchell's three extended the lead to ten points."
        matches = [p.search(text) for p in FORBIDDEN_PATTERNS]
        assert not any(m for m in matches if m)


class TestPromptGeneration:
    """Tests for multi-sentence prompt generation."""

    def test_batch_prompt_requests_multi_sentence(self):
        """Batch prompt should request 2-4 sentences."""
        from app.services.pipeline.stages.render_narratives import _build_batch_prompt

        moment = {
            "period": 1,
            "start_clock": "10:30",
            "score_before": [10, 12],
            "score_after": [12, 14],
            "explicitly_narrated_play_ids": [1],
        }
        moment_plays = [
            {"play_index": 1, "description": "Mitchell made layup"},
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        prompt = _build_batch_prompt([(0, moment, moment_plays)], game_context)

        assert "2-4 sentence" in prompt.lower()

    def test_batch_prompt_includes_forbidden_examples(self):
        """Batch prompt should include examples of forbidden language."""
        from app.services.pipeline.stages.render_narratives import _build_batch_prompt

        moment = {
            "period": 1,
            "start_clock": "10:30",
            "score_before": [10, 12],
            "score_after": [12, 14],
            "explicitly_narrated_play_ids": [1],
        }
        moment_plays = [
            {"play_index": 1, "description": "Mitchell made layup"},
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        prompt = _build_batch_prompt([(0, moment, moment_plays)], game_context)

        assert "dominant" in prompt.lower()
        assert "electric" in prompt.lower()
        assert "took over" in prompt.lower()

    def test_retry_prompt_includes_warning(self):
        """Retry prompt should include explicit warning."""
        from app.services.pipeline.stages.render_narratives import _build_batch_prompt

        moment = {
            "period": 1,
            "start_clock": "10:30",
            "score_before": [10, 12],
            "score_after": [12, 14],
            "explicitly_narrated_play_ids": [1],
        }
        moment_plays = [
            {"play_index": 1, "description": "Mitchell made layup"},
        ]
        game_context = {"home_team_name": "Lakers", "away_team_name": "Suns"}

        prompt = _build_batch_prompt([(0, moment, moment_plays)], game_context, is_retry=True)

        assert "previous response failed" in prompt.lower()
        assert "2-4 sentences" in prompt.lower()


class TestFallbackReasons:
    """Tests for new Task 1.2 fallback reasons."""

    def test_insufficient_sentences_reason_exists(self):
        """FallbackReason should include INSUFFICIENT_SENTENCES."""
        from app.services.pipeline.stages.render_narratives import FallbackReason

        assert hasattr(FallbackReason, "INSUFFICIENT_SENTENCES")
        assert FallbackReason.INSUFFICIENT_SENTENCES.value == "insufficient_sentences"

    def test_forbidden_language_reason_exists(self):
        """FallbackReason should include FORBIDDEN_LANGUAGE_DETECTED."""
        from app.services.pipeline.stages.render_narratives import FallbackReason

        assert hasattr(FallbackReason, "FORBIDDEN_LANGUAGE_DETECTED")
        assert FallbackReason.FORBIDDEN_LANGUAGE_DETECTED.value == "forbidden_language_detected"

    def test_missing_explicit_play_reason_exists(self):
        """FallbackReason should include MISSING_EXPLICIT_PLAY_REFERENCE."""
        from app.services.pipeline.stages.render_narratives import FallbackReason

        assert hasattr(FallbackReason, "MISSING_EXPLICIT_PLAY_REFERENCE")
        assert FallbackReason.MISSING_EXPLICIT_PLAY_REFERENCE.value == "missing_explicit_play_reference"
