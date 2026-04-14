"""Tests for Stage 4: Decision engine and template fallback."""

from __future__ import annotations

from app.services.pipeline.stages.content_decision import (
    MAX_RETRIES,
    ContentDecision,
    DecisionResult,
    generate_template_fallback,
    make_decision,
    run_decision_engine,
)


class TestMakeDecision:
    """Tests for the decision function."""

    def test_high_score_publishes(self) -> None:
        assert make_decision(85, True, True) == ContentDecision.PUBLISH

    def test_threshold_score_publishes(self) -> None:
        assert make_decision(70, True, True) == ContentDecision.PUBLISH

    def test_medium_score_regenerates(self) -> None:
        assert make_decision(55, True, True) == ContentDecision.REGENERATE

    def test_medium_score_falls_back_after_max_retries(self) -> None:
        assert make_decision(55, True, True, retry_count=MAX_RETRIES) == ContentDecision.FALLBACK

    def test_low_score_falls_back(self) -> None:
        assert make_decision(30, True, True) == ContentDecision.FALLBACK

    def test_zero_score_falls_back(self) -> None:
        assert make_decision(0, True, True) == ContentDecision.FALLBACK

    def test_factual_failure_regenerates(self) -> None:
        assert make_decision(90, False, True) == ContentDecision.REGENERATE

    def test_factual_failure_falls_back_after_retries(self) -> None:
        assert make_decision(90, False, True, retry_count=MAX_RETRIES) == ContentDecision.FALLBACK

    def test_structural_failure_regenerates(self) -> None:
        assert make_decision(90, True, False) == ContentDecision.REGENERATE

    def test_structural_failure_falls_back_after_retries(self) -> None:
        assert make_decision(90, True, False, retry_count=MAX_RETRIES) == ContentDecision.FALLBACK

    def test_both_failures_regenerate(self) -> None:
        assert make_decision(90, False, False) == ContentDecision.REGENERATE

    def test_boundary_40_regenerates(self) -> None:
        assert make_decision(40, True, True) == ContentDecision.REGENERATE

    def test_boundary_39_falls_back(self) -> None:
        assert make_decision(39, True, True) == ContentDecision.FALLBACK


class TestRunDecisionEngine:
    """Tests for the full decision engine result."""

    def test_returns_decision_result(self) -> None:
        result = run_decision_engine(85, True, True)
        assert isinstance(result, DecisionResult)
        assert result.decision == ContentDecision.PUBLISH
        assert result.quality_score == 85

    def test_includes_errors_and_warnings(self) -> None:
        result = run_decision_engine(
            50, True, True,
            all_errors=["error1"],
            all_warnings=["warn1"],
        )
        assert result.errors == ["error1"]
        assert result.warnings == ["warn1"]

    def test_to_dict_format(self) -> None:
        result = run_decision_engine(75, True, True)
        d = result.to_dict()
        assert d["decision"] == "PUBLISH"
        assert d["quality_score"] == 75
        assert d["factual_passed"] is True
        assert d["structural_passed"] is True


class TestGenerateTemplateFallback:
    """Tests for template-based fallback generation."""

    def _make_blocks(self, home_final: int = 110, away_final: int = 98) -> list[dict]:
        return [
            {
                "block_index": 0,
                "role": "SETUP",
                "score_before": [0, 0],
                "score_after": [28, 25],
                "period_start": 1,
                "period_end": 1,
                "narrative": "Original narrative block 0.",
                "mini_box": {
                    "home": {
                        "team": "Hawks",
                        "players": [{"name": "Trae Young", "pts": 12}],
                    },
                    "away": {
                        "team": "Celtics",
                        "players": [{"name": "Jayson Tatum", "pts": 10}],
                    },
                },
            },
            {
                "block_index": 1,
                "role": "MOMENTUM_SHIFT",
                "score_before": [28, 25],
                "score_after": [55, 52],
                "period_start": 2,
                "period_end": 2,
                "narrative": "Original narrative block 1.",
                "mini_box": {
                    "home": {
                        "team": "Hawks",
                        "players": [{"name": "Trae Young", "pts": 22}],
                    },
                    "away": {
                        "team": "Celtics",
                        "players": [{"name": "Jayson Tatum", "pts": 20}],
                    },
                },
            },
            {
                "block_index": 2,
                "role": "RESOLUTION",
                "score_before": [55, 52],
                "score_after": [home_final, away_final],
                "period_start": 3,
                "period_end": 4,
                "narrative": "Original narrative block 2.",
                "mini_box": {
                    "home": {
                        "team": "Hawks",
                        "players": [{"name": "Trae Young", "pts": 32}],
                    },
                    "away": {
                        "team": "Celtics",
                        "players": [{"name": "Jayson Tatum", "pts": 28}],
                    },
                },
            },
        ]

    def test_fallback_produces_valid_blocks(self) -> None:
        blocks = self._make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = generate_template_fallback(blocks, context, "NBA")
        assert len(result) == 3
        for block in result:
            assert block["narrative"]
            assert len(block["narrative"]) > 0

    def test_fallback_contains_correct_score(self) -> None:
        blocks = self._make_blocks(110, 98)
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = generate_template_fallback(blocks, context, "NBA")
        all_text = " ".join(b["narrative"] for b in result)
        assert "110" in all_text
        assert "98" in all_text

    def test_fallback_identifies_winner(self) -> None:
        blocks = self._make_blocks(110, 98)
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = generate_template_fallback(blocks, context, "NBA")
        first_block = result[0]["narrative"]
        assert "Hawks" in first_block

    def test_fallback_away_team_wins(self) -> None:
        blocks = self._make_blocks(90, 105)
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = generate_template_fallback(blocks, context, "NBA")
        first_block = result[0]["narrative"]
        assert "Celtics" in first_block

    def test_fallback_nhl(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "score_before": [0, 0],
                "score_after": [3, 1],
                "period_start": 1,
                "period_end": 3,
                "narrative": "Original.",
                "mini_box": {
                    "home": {"team": "Bruins", "players": [{"name": "Pastrnak", "goals": 2}]},
                    "away": {"team": "Rangers", "players": []},
                },
            }
        ]
        context = {"home_team_name": "Bruins", "away_team_name": "Rangers"}
        result = generate_template_fallback(blocks, context, "NHL")
        assert "Bruins" in result[0]["narrative"]
        assert "skated past" in result[0]["narrative"]

    def test_fallback_mlb(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "role": "SETUP",
                "score_before": [0, 0],
                "score_after": [5, 3],
                "period_start": 1,
                "period_end": 9,
                "narrative": "Original.",
                "mini_box": {
                    "home": {"team": "Yankees", "players": [{"name": "Judge", "rbi": 3}]},
                    "away": {"team": "Red Sox", "players": []},
                },
            }
        ]
        context = {"home_team_name": "Yankees", "away_team_name": "Red Sox"}
        result = generate_template_fallback(blocks, context, "MLB")
        assert "Yankees" in result[0]["narrative"]
        assert "beat" in result[0]["narrative"]

    def test_fallback_empty_blocks(self) -> None:
        result = generate_template_fallback([], {}, "NBA")
        assert result == []

    def test_fallback_includes_top_performer(self) -> None:
        blocks = self._make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = generate_template_fallback(blocks, context, "NBA")
        all_text = " ".join(b["narrative"] for b in result)
        assert "Trae Young" in all_text

    def test_fallback_preserves_block_structure(self) -> None:
        blocks = self._make_blocks()
        context = {"home_team_name": "Hawks", "away_team_name": "Celtics"}
        result = generate_template_fallback(blocks, context, "NBA")
        for orig, fb in zip(blocks, result):
            assert fb["block_index"] == orig["block_index"]
            assert fb["role"] == orig["role"]
            assert fb["score_before"] == orig["score_before"]
            assert fb["score_after"] == orig["score_after"]
