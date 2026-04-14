"""Tests for sentence budget validation."""

from app.services.pipeline.stages.render_validation import (
    SENTENCE_BUDGETS,
    _count_sentences,
    validate_all_blocks,
    validate_sentence_budget,
)


class TestCountSentences:
    def test_single_sentence(self):
        assert _count_sentences("The Hawks won the game.") == 1

    def test_multiple_sentences(self):
        assert _count_sentences("First sentence. Second sentence. Third sentence.") == 3

    def test_exclamation_and_question(self):
        assert _count_sentences("What a play! Did you see that? Incredible.") == 3

    def test_empty_string(self):
        assert _count_sentences("") == 0

    def test_whitespace_only(self):
        assert _count_sentences("   ") == 0

    def test_sentence_with_abbreviation_like_text(self):
        text = "The Hawks scored 25 pts. in the first quarter. They led by 10."
        assert _count_sentences(text) == 3

    def test_single_sentence_no_trailing_space(self):
        assert _count_sentences("The game ended at the buzzer.") == 1


class TestValidateSentenceBudget:
    def test_setup_within_budget(self):
        text = "The game opened with both teams trading baskets. Neither team could pull ahead."
        warnings = validate_sentence_budget(text, 0, "SETUP")
        assert len(warnings) == 0

    def test_setup_too_many_sentences(self):
        text = (
            "First sentence. Second sentence. Third sentence. "
            "Fourth sentence. Fifth sentence."
        )
        warnings = validate_sentence_budget(text, 0, "SETUP")
        assert any("Too many sentences" in w for w in warnings)

    def test_decision_point_within_budget(self):
        text = (
            "Mitchell drove to the basket for the go-ahead score. "
            "The defense collapsed, leaving the corner open. "
            "Williams hit the three to seal it."
        )
        warnings = validate_sentence_budget(text, 3, "DECISION_POINT")
        assert len(warnings) == 0

    def test_decision_point_too_few(self):
        text = "One short sentence."
        warnings = validate_sentence_budget(text, 3, "DECISION_POINT")
        assert any("Too few sentences" in w for w in warnings)

    def test_momentum_shift_at_max(self):
        text = (
            "First. Second. Third. Fourth. Fifth."
        )
        warnings = validate_sentence_budget(text, 1, "MOMENTUM_SHIFT")
        assert len(warnings) == 0

    def test_resolution_single_sentence_ok(self):
        text = "The Hawks held on for the 110-105 victory."
        warnings = validate_sentence_budget(text, 5, "RESOLUTION")
        assert len(warnings) == 0

    def test_unknown_role_uses_default(self):
        text = "Single sentence."
        warnings = validate_sentence_budget(text, 0, "UNKNOWN_ROLE")
        assert len(warnings) == 0

    def test_empty_narrative(self):
        warnings = validate_sentence_budget("", 0, "SETUP")
        assert len(warnings) == 0


class TestValidateAllBlocks:
    def test_all_blocks_valid(self):
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "narrative": "The game started with energy from both sides. Neither team could establish an early lead in the opening minutes.",
            },
            {
                "block_index": 1,
                "role": "RESOLUTION",
                "narrative": "The Hawks pulled away in the final minutes to secure a comfortable victory over the visiting Celtics.",
            },
        ]
        errors, warnings = validate_all_blocks(blocks)
        assert len(errors) == 0

    def test_empty_narrative_is_error(self):
        blocks = [
            {"block_index": 0, "role": "SETUP", "narrative": ""},
        ]
        errors, warnings = validate_all_blocks(blocks)
        assert any("Empty narrative" in e for e in errors)

    def test_budget_violation_is_warning(self):
        blocks = [
            {
                "block_index": 0,
                "role": "DECISION_POINT",
                "narrative": "One short sentence.",
            },
        ]
        errors, warnings = validate_all_blocks(blocks)
        assert any("Too few sentences" in w for w in warnings)


class TestSentenceBudgetConstants:
    def test_all_roles_have_budgets(self):
        expected_roles = {"SETUP", "MOMENTUM_SHIFT", "RESPONSE", "DECISION_POINT", "RESOLUTION"}
        assert set(SENTENCE_BUDGETS.keys()) == expected_roles

    def test_budgets_are_reasonable(self):
        for role, (min_s, max_s) in SENTENCE_BUDGETS.items():
            assert min_s >= 1, f"{role} min_sentences must be >= 1"
            assert max_s <= 5, f"{role} max_sentences must be <= 5"
            assert min_s <= max_s, f"{role} min must be <= max"
