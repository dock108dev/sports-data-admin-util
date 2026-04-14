"""Tests for three-layer prompt architecture in render_prompts.py."""

from app.services.pipeline.stages.render_prompts import (
    GUARDRAIL_POSTSCRIPT,
    SYSTEM_PROMPT,
    build_block_prompt,
    build_game_flow_pass_prompt,
)
from app.services.pipeline.stages.render_validation import FORBIDDEN_WORDS
from app.services.pipeline.stages.tone_detection import ToneCategory


def _make_blocks(count: int = 3) -> list[dict]:
    """Build minimal block dicts for prompt testing."""
    roles = ["SETUP", "MOMENTUM_SHIFT", "RESOLUTION"]
    blocks = []
    for i in range(count):
        blocks.append({
            "block_index": i,
            "role": roles[i % len(roles)],
            "score_before": [i * 20, i * 18],
            "score_after": [(i + 1) * 20, (i + 1) * 18],
            "key_play_ids": [],
            "period_start": i + 1,
            "period_end": i + 1,
        })
    return blocks


class TestThreeLayerArchitecture:
    """Verify the prompt contains all three layers."""

    def test_system_prompt_present(self):
        blocks = _make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        assert "OUTPUT CONTRACT" in prompt
        assert "HARD RULES" in prompt
        assert "ROLE-SPECIFIC GUIDANCE" in prompt

    def test_game_specific_layer_present(self):
        blocks = _make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        assert "Hawks" in prompt
        assert "Celtics" in prompt
        assert "TONE:" in prompt
        assert "TEAM ATTRIBUTION:" in prompt

    def test_guardrail_postscript_present(self):
        blocks = _make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        assert "FINAL CHECKLIST" in prompt
        assert "FORBIDDEN WORDS" in prompt

    def test_forbidden_words_in_guardrail(self):
        blocks = _make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        for word in FORBIDDEN_WORDS[:3]:
            assert word in prompt

    def test_tone_detected_and_injected(self):
        """Standard tone is injected for a normal game."""
        blocks = _make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        assert "TONE: STANDARD" in prompt

    def test_blowout_tone_for_large_margin(self):
        blocks = [
            {"block_index": 0, "role": "SETUP", "score_before": [0, 0], "score_after": [30, 5],
             "key_play_ids": [], "period_start": 1, "period_end": 1},
            {"block_index": 1, "role": "MOMENTUM_SHIFT", "score_before": [30, 5], "score_after": [60, 15],
             "key_play_ids": [], "period_start": 2, "period_end": 2},
            {"block_index": 2, "role": "RESOLUTION", "score_before": [60, 15], "score_after": [100, 70],
             "key_play_ids": [], "period_start": 4, "period_end": 4},
        ]
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        assert "TONE: BLOWOUT" in prompt

    def test_mlb_specific_rules(self):
        blocks = _make_blocks()
        context = {"home_team_name": "Braves", "away_team_name": "Mets", "sport": "MLB"}
        prompt = build_block_prompt(blocks, context, [])
        assert "BASEBALL-SPECIFIC" in prompt
        assert "INNING STRUCTURE" in prompt

    def test_block_data_included(self):
        blocks = _make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_block_prompt(blocks, context, [])
        assert "Block 0" in prompt
        assert "Block 1" in prompt
        assert "Block 2" in prompt
        assert "SETUP" in prompt
        assert "RESOLUTION" in prompt


class TestFlowPassPrompt:
    def test_flow_pass_has_system_prompt(self):
        blocks = [
            {"block_index": 0, "role": "SETUP", "score_before": [0, 0],
             "score_after": [20, 18], "narrative": "Opening action.",
             "period_start": 1, "period_end": 1},
            {"block_index": 1, "role": "RESOLUTION", "score_before": [20, 18],
             "score_after": [100, 95], "narrative": "Final moments.",
             "period_start": 4, "period_end": 4},
        ]
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_game_flow_pass_prompt(blocks, context)
        assert "narrative coherence" in prompt
        assert "Preserve block order" in prompt

    def test_flow_pass_includes_narratives(self):
        blocks = [
            {"block_index": 0, "role": "SETUP", "score_before": [0, 0],
             "score_after": [20, 18], "narrative": "The game opened with energy.",
             "period_start": 1, "period_end": 1},
        ]
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        prompt = build_game_flow_pass_prompt(blocks, context)
        assert "The game opened with energy." in prompt
