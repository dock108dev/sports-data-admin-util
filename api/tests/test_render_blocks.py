"""Tests for RENDER_BLOCKS stage."""

from __future__ import annotations

import pytest

from app.services.pipeline.stages.render_blocks import (
    _build_block_prompt,
    _validate_block_narrative,
    _generate_fallback_narrative,
    FORBIDDEN_WORDS,
)
from app.services.pipeline.stages.block_types import (
    SemanticRole,
    MIN_WORDS_PER_BLOCK,
    MAX_WORDS_PER_BLOCK,
)


class TestBuildBlockPrompt:
    """Tests for block prompt building."""

    def test_prompt_includes_team_names(self) -> None:
        """Prompt includes home and away team names."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1],
            }
        ]
        game_context = {
            "home_team_name": "Lakers",
            "away_team_name": "Celtics",
        }
        pbp_events: list[dict] = []

        prompt = _build_block_prompt(blocks, game_context, pbp_events)

        assert "Lakers" in prompt
        assert "Celtics" in prompt

    def test_prompt_includes_forbidden_words_list(self) -> None:
        """Prompt includes list of forbidden words."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            }
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}
        pbp_events: list[dict] = []

        prompt = _build_block_prompt(blocks, game_context, pbp_events)

        for word in FORBIDDEN_WORDS:
            assert word in prompt.lower()

    def test_prompt_includes_role_info(self) -> None:
        """Prompt includes semantic role for each block."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [],
            },
            {
                "block_index": 1,
                "role": SemanticRole.RESOLUTION.value,
                "score_before": [10, 8],
                "score_after": [20, 18],
                "key_play_ids": [],
            },
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}
        pbp_events: list[dict] = []

        prompt = _build_block_prompt(blocks, game_context, pbp_events)

        assert "SETUP" in prompt
        assert "RESOLUTION" in prompt

    def test_prompt_includes_key_play_descriptions(self) -> None:
        """Prompt includes descriptions of key plays."""
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "score_before": [0, 0],
                "score_after": [10, 8],
                "key_play_ids": [1, 2],
            }
        ]
        game_context = {"home_team_name": "Home", "away_team_name": "Away"}
        pbp_events = [
            {"play_index": 1, "description": "LeBron James makes 3-pointer"},
            {"play_index": 2, "description": "Anthony Davis dunks"},
        ]

        prompt = _build_block_prompt(blocks, game_context, pbp_events)

        assert "LeBron James makes 3-pointer" in prompt
        assert "Anthony Davis dunks" in prompt


class TestValidateBlockNarrative:
    """Tests for block narrative validation."""

    def test_empty_narrative_is_error(self) -> None:
        """Empty narrative produces error."""
        errors, warnings = _validate_block_narrative("", 0)
        assert len(errors) > 0
        assert "Empty" in errors[0]

    def test_whitespace_only_is_error(self) -> None:
        """Whitespace-only narrative produces error."""
        errors, warnings = _validate_block_narrative("   \n\t  ", 0)
        assert len(errors) > 0

    def test_too_short_is_warning(self) -> None:
        """Narrative shorter than minimum produces warning."""
        short_narrative = "Short text."  # ~2 words
        errors, warnings = _validate_block_narrative(short_narrative, 0)
        assert len(warnings) > 0
        assert "short" in warnings[0].lower()

    def test_too_long_is_warning(self) -> None:
        """Narrative longer than maximum produces warning."""
        long_narrative = " ".join(["word"] * (MAX_WORDS_PER_BLOCK + 10))
        errors, warnings = _validate_block_narrative(long_narrative, 0)
        assert len(warnings) > 0
        assert "long" in warnings[0].lower()

    def test_valid_length_no_warnings(self) -> None:
        """Narrative of valid length produces no word count warnings."""
        valid_narrative = " ".join(["word"] * 30)  # 30 words, within limits
        errors, warnings = _validate_block_narrative(valid_narrative, 0)
        assert len(errors) == 0
        word_count_warnings = [w for w in warnings if "short" in w.lower() or "long" in w.lower()]
        assert len(word_count_warnings) == 0

    def test_forbidden_word_is_warning(self) -> None:
        """Narrative containing forbidden word produces warning."""
        narrative = "The team built momentum and scored 10 points in a row."
        errors, warnings = _validate_block_narrative(narrative, 0)
        assert any("momentum" in w.lower() for w in warnings)

    def test_multiple_forbidden_words(self) -> None:
        """Multiple forbidden words produce multiple warnings."""
        narrative = "This was a huge momentum shift and a turning point in the game."
        errors, warnings = _validate_block_narrative(narrative, 0)
        forbidden_warnings = [w for w in warnings if "forbidden" in w.lower()]
        assert len(forbidden_warnings) >= 2


class TestGenerateFallbackNarrative:
    """Tests for fallback narrative generation."""

    def test_setup_fallback_describes_game_start(self) -> None:
        """SETUP fallback describes how game began."""
        block = {
            "role": SemanticRole.SETUP.value,
            "score_before": [0, 0],
            "score_after": [10, 8],
        }
        game_context = {"home_team_abbrev": "LAL", "away_team_abbrev": "BOS"}

        narrative = _generate_fallback_narrative(block, game_context)

        assert "began" in narrative.lower() or "score" in narrative.lower()

    def test_resolution_fallback_describes_final_score(self) -> None:
        """RESOLUTION fallback includes final score."""
        block = {
            "role": SemanticRole.RESOLUTION.value,
            "score_before": [100, 95],
            "score_after": [110, 105],
        }
        game_context = {"home_team_abbrev": "LAL", "away_team_abbrev": "BOS"}

        narrative = _generate_fallback_narrative(block, game_context)

        assert "concluded" in narrative.lower() or "final" in narrative.lower()
        assert "110" in narrative
        assert "105" in narrative

    def test_middle_block_describes_scoring_stretch(self) -> None:
        """Middle block fallback describes who outscored whom."""
        block = {
            "role": SemanticRole.RESPONSE.value,
            "score_before": [50, 45],
            "score_after": [60, 48],  # Home outscored 10-3
        }
        game_context = {"home_team_abbrev": "LAL", "away_team_abbrev": "BOS"}

        narrative = _generate_fallback_narrative(block, game_context)

        assert "outscored" in narrative.lower()
        assert "LAL" in narrative

    def test_even_scoring_stretch(self) -> None:
        """Even scoring stretch produces valid fallback."""
        block = {
            "role": SemanticRole.RESPONSE.value,
            "score_before": [50, 45],
            "score_after": [55, 50],  # Both scored 5
        }
        game_context = {"home_team_abbrev": "LAL", "away_team_abbrev": "BOS"}

        narrative = _generate_fallback_narrative(block, game_context)

        assert "even" in narrative.lower() or "score" in narrative.lower()

    def test_fallback_includes_team_abbreviations(self) -> None:
        """Fallback narratives include team abbreviations."""
        block = {
            "role": SemanticRole.MOMENTUM_SHIFT.value,
            "score_before": [30, 25],
            "score_after": [32, 35],  # Away takes lead
        }
        game_context = {"home_team_abbrev": "MIA", "away_team_abbrev": "NYK"}

        narrative = _generate_fallback_narrative(block, game_context)

        # Should include at least one team abbreviation
        assert "MIA" in narrative or "NYK" in narrative


class TestForbiddenWords:
    """Tests for forbidden words list."""

    def test_forbidden_words_are_defined(self) -> None:
        """Forbidden words list is not empty."""
        assert len(FORBIDDEN_WORDS) > 0

    def test_expected_forbidden_words(self) -> None:
        """Expected forbidden words are in the list."""
        expected = ["momentum", "turning point", "dominant", "huge", "clutch"]
        for word in expected:
            assert word in FORBIDDEN_WORDS, f"Expected '{word}' to be forbidden"

    def test_validation_catches_all_forbidden_words(self) -> None:
        """Validation catches each forbidden word."""
        for word in FORBIDDEN_WORDS:
            narrative = f"The team showed {word} in this stretch."
            errors, warnings = _validate_block_narrative(narrative, 0)
            assert any(word.lower() in w.lower() for w in warnings), f"'{word}' not caught"
