"""Tests for RENDER_BLOCKS stage."""

from __future__ import annotations


from app.services.pipeline.stages.render_blocks import (
    _build_block_prompt,
    _validate_block_narrative,
    _generate_fallback_narrative,
    _check_play_coverage,
    _generate_play_injection_sentence,
    _validate_style_constraints,
    _is_garbage_time_block,
    FORBIDDEN_WORDS,
)
from app.services.pipeline.stages.block_types import (
    SemanticRole,
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


class TestPlayCoverage:
    """Tests for Task 1.3: Explicit play coverage invariant."""

    def test_play_referenced_by_player_name(self) -> None:
        """Play is detected when player name appears in narrative."""
        narrative = "LeBron James scored on a drive to the basket."
        pbp_events = [
            {"play_index": 1, "player_name": "LeBron James", "description": "James layup"}
        ]
        missing_ids, _ = _check_play_coverage(narrative, [1], pbp_events)
        assert len(missing_ids) == 0

    def test_missing_play_detected(self) -> None:
        """Missing play is detected when not referenced."""
        narrative = "The home team extended their lead."
        pbp_events = [
            {"play_index": 1, "player_name": "Anthony Davis", "description": "Davis dunk"}
        ]
        missing_ids, missing_events = _check_play_coverage(narrative, [1], pbp_events)
        assert 1 in missing_ids
        assert len(missing_events) == 1

    def test_play_referenced_by_action_keyword(self) -> None:
        """Play is detected via action keywords."""
        narrative = "A three-pointer from the corner extended the lead."
        pbp_events = [
            {"play_index": 1, "player_name": "Curry", "description": "Curry 3-pointer"}
        ]
        missing_ids, _ = _check_play_coverage(narrative, [1], pbp_events)
        assert len(missing_ids) == 0

    def test_empty_narrative_returns_no_missing(self) -> None:
        """Empty narrative returns empty list."""
        missing_ids, _ = _check_play_coverage("", [1], [])
        assert missing_ids == []


class TestPlayInjection:
    """Tests for Task 1.3: Play injection recovery."""

    def test_generates_sentence_with_player_and_description(self) -> None:
        """Generates sentence with player name and action."""
        event = {
            "player_name": "LeBron James",
            "description": "makes driving layup"
        }
        sentence = _generate_play_injection_sentence(event, {})
        assert "LeBron James" in sentence
        assert "makes driving layup" in sentence.lower()

    def test_generates_sentence_with_play_type(self) -> None:
        """Falls back to play type when description missing."""
        event = {
            "player_name": "Curry",
            "play_type": "THREE_POINTER"
        }
        sentence = _generate_play_injection_sentence(event, {})
        assert "Curry" in sentence
        assert "three pointer" in sentence.lower()


class TestStyleConstraints:
    """Tests for Task 1.4: Sentence style constraints."""

    def test_detects_stat_feed_pattern(self) -> None:
        """Detects 'X had Y points' patterns."""
        narrative = "James had 32 points in the game."
        errors, warnings = _validate_style_constraints(narrative, 0)
        assert len(warnings) > 0

    def test_detects_finished_with_pattern(self) -> None:
        """Detects 'finished with X' patterns."""
        narrative = "Davis finished with 28 in the quarter."
        errors, warnings = _validate_style_constraints(narrative, 0)
        assert len(warnings) > 0

    def test_detects_subjective_adjectives(self) -> None:
        """Detects subjective adjectives."""
        narrative = "An incredible performance by the team."
        errors, warnings = _validate_style_constraints(narrative, 0)
        assert len(warnings) > 0

    def test_valid_broadcast_style_passes(self) -> None:
        """Valid broadcast-style narrative passes."""
        narrative = "James drove to the basket and scored. The Lakers extended their lead to ten."
        errors, warnings = _validate_style_constraints(narrative, 0)
        # May have some warnings but should not be stat-feed related
        stat_warnings = [w for w in warnings if "stat" in w.lower() or "pattern" in w.lower()]
        assert len(stat_warnings) == 0

    def test_detects_too_many_numbers(self) -> None:
        """Detects stat-feed style from excessive numbers."""
        narrative = "He scored 10, 15, 8, 12, 7, 9, 11 points across stretches."
        errors, warnings = _validate_style_constraints(narrative, 0)
        assert any("numbers" in w.lower() for w in warnings)


class TestGarbageTimeBlock:
    """Tests for Task 1.5: Garbage time detection."""

    def test_block_in_garbage_time(self) -> None:
        """Block with moments after garbage time start is garbage time."""
        block = {"moment_indices": [10, 11, 12]}
        assert _is_garbage_time_block(block, garbage_time_start_idx=8) is True

    def test_block_before_garbage_time(self) -> None:
        """Block with moments before garbage time start is not garbage time."""
        block = {"moment_indices": [5, 6, 7]}
        assert _is_garbage_time_block(block, garbage_time_start_idx=10) is False

    def test_block_spanning_garbage_time(self) -> None:
        """Block spanning garbage time boundary is not fully garbage time."""
        block = {"moment_indices": [8, 9, 10, 11]}
        assert _is_garbage_time_block(block, garbage_time_start_idx=10) is False

    def test_no_garbage_time(self) -> None:
        """Block is not garbage time when no garbage time index."""
        block = {"moment_indices": [10, 11, 12]}
        assert _is_garbage_time_block(block, garbage_time_start_idx=None) is False


class TestGarbageTimeFallback:
    """Tests for Task 1.5: Garbage time fallback narratives."""

    def test_garbage_time_narrative_is_minimal(self) -> None:
        """Garbage time fallback is shorter and more neutral."""
        block = {
            "role": SemanticRole.RESPONSE.value,
            "score_before": [90, 60],
            "score_after": [100, 68],
        }
        game_context = {"home_team_abbrev": "LAL", "away_team_abbrev": "BOS"}

        # Normal narrative should not contain garbage time language
        normal = _generate_fallback_narrative(block, game_context, is_garbage_time=False)
        assert "wound down" not in normal.lower()
        assert "maintained" not in normal.lower()

        # Garbage time narrative should mention "wound down" or "maintained"
        garbage = _generate_fallback_narrative(block, game_context, is_garbage_time=True)
        assert "wound down" in garbage.lower() or "maintained" in garbage.lower()
