"""Integration tests for the 4-stage content validation pipeline."""

from __future__ import annotations

from app.services.pipeline.stages.block_types import SemanticRole
from app.services.pipeline.stages.content_decision import ContentDecision
from app.services.pipeline.stages.content_pipeline import (
    ContentPipelineResult,
    PipelineMetrics,
    run_content_pipeline,
)


def _make_valid_blocks() -> list[dict]:
    """Create blocks that pass all 4 stages."""
    return [
        {
            "block_index": 0,
            "role": SemanticRole.SETUP.value,
            "narrative": (
                "The Hawks opened with sharp ball movement, finding Young on consecutive "
                "possessions near the arc. Atlanta built an early cushion as the Celtics "
                "struggled to contain dribble penetration."
            ),
            "score_before": [0, 0],
            "score_after": [28, 20],
            "period_start": 1,
            "period_end": 1,
            "mini_box": {
                "home": {"team": "Hawks", "players": [{"name": "Trae Young", "pts": 12, "ast": 4}]},
                "away": {"team": "Celtics", "players": [{"name": "Jayson Tatum", "pts": 8}]},
            },
        },
        {
            "block_index": 1,
            "role": SemanticRole.MOMENTUM_SHIFT.value,
            "narrative": (
                "Boston stormed back behind Tatum's pull-up baseline jumpers, trimming "
                "the deficit to three before the intermission. The defensive intensity "
                "shifted noticeably during the second frame."
            ),
            "score_before": [28, 20],
            "score_after": [52, 49],
            "period_start": 2,
            "period_end": 2,
            "mini_box": {
                "home": {"team": "Hawks", "players": [{"name": "Trae Young", "pts": 20, "ast": 7}]},
                "away": {"team": "Celtics", "players": [{"name": "Jayson Tatum", "pts": 22}]},
            },
        },
        {
            "block_index": 2,
            "role": SemanticRole.RESPONSE.value,
            "narrative": (
                "Atlanta answered in the third with a decisive stretch of transition "
                "baskets and forced turnovers. Young orchestrated the offense with "
                "precision, extending the margin back to double figures."
            ),
            "score_before": [52, 49],
            "score_after": [82, 70],
            "period_start": 3,
            "period_end": 3,
            "mini_box": {
                "home": {"team": "Hawks", "players": [{"name": "Trae Young", "pts": 28, "ast": 9}]},
                "away": {"team": "Celtics", "players": [{"name": "Jayson Tatum", "pts": 26}]},
            },
        },
        {
            "block_index": 3,
            "role": SemanticRole.RESOLUTION.value,
            "narrative": (
                "The fourth quarter was procedural, with Atlanta managing the clock "
                "and free throw line to seal a comfortable victory. The final minutes "
                "saw reserves close out the contest."
            ),
            "score_before": [82, 70],
            "score_after": [110, 95],
            "period_start": 4,
            "period_end": 4,
            "mini_box": {
                "home": {"team": "Hawks", "players": [{"name": "Trae Young", "pts": 32, "ast": 11}]},
                "away": {"team": "Celtics", "players": [{"name": "Jayson Tatum", "pts": 30}]},
            },
        },
    ]


GAME_CONTEXT = {
    "sport": "NBA",
    "home_team_name": "Hawks",
    "away_team_name": "Celtics",
    "home_team_abbrev": "ATL",
    "away_team_abbrev": "BOS",
    "player_names": {
        "T. Young": "Trae Young",
        "J. Tatum": "Jayson Tatum",
    },
}


class TestContentPipelineIntegration:
    """Full pipeline integration tests."""

    def test_valid_content_publishes(self) -> None:
        blocks = _make_valid_blocks()
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA")
        assert isinstance(result, ContentPipelineResult)
        assert result.structural_passed is True
        assert result.factual_result.passed is True
        assert result.quality_result.composite_score > 0
        assert result.is_fallback is False

    def test_pipeline_returns_all_stages(self) -> None:
        blocks = _make_valid_blocks()
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA")
        d = result.to_dict()
        assert "structural_passed" in d
        assert "factual" in d
        assert "quality" in d
        assert "decision_engine" in d

    def test_training_bleed_triggers_regenerate_or_fallback(self) -> None:
        blocks = _make_valid_blocks()
        blocks[0]["narrative"] = (
            "Young, averaging 28.5 points this season, opened with a flurry. "
            "His career-high streak continued as the Hawks built an early lead."
        )
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA")
        assert result.factual_result.passed is False
        assert result.decision in (ContentDecision.REGENERATE, ContentDecision.FALLBACK)

    def test_fallback_after_max_retries(self) -> None:
        blocks = _make_valid_blocks()
        blocks[0]["narrative"] = "He is averaging 25 points on the season. His injury concerns linger."
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA", retry_count=2)
        assert result.decision == ContentDecision.FALLBACK
        assert result.is_fallback is True
        # Fallback blocks should have template content
        assert result.blocks[0]["narrative"] != blocks[0]["narrative"]

    def test_factual_error_detected(self) -> None:
        blocks = _make_valid_blocks()
        # Claim Young scored 50, but mini_box says 12
        blocks[0]["narrative"] = (
            "Young scored 50 in a blistering opening quarter, setting "
            "the tone for the Hawks from the outset."
        )
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA")
        assert result.factual_result.claims_failed > 0
        assert result.factual_result.passed is False

    def test_quality_score_computed(self) -> None:
        blocks = _make_valid_blocks()
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA")
        assert result.quality_result.composite_score >= 0
        assert result.quality_result.composite_score <= 100
        assert result.quality_result.cliche_count >= 0

    def test_empty_blocks_handled(self) -> None:
        result = run_content_pipeline([], GAME_CONTEXT, "NBA")
        assert result.structural_passed is True
        assert result.quality_result.composite_score == 100.0

    def test_different_sports(self) -> None:
        blocks = _make_valid_blocks()
        for sport in ("NBA", "NHL", "MLB", "NCAAB"):
            result = run_content_pipeline(blocks, GAME_CONTEXT, sport)
            assert isinstance(result, ContentPipelineResult)


class TestPipelineMetrics:
    """Tests for monitoring metrics."""

    def test_metrics_to_dict(self) -> None:
        m = PipelineMetrics(
            sport="NBA",
            factual_error_rate=0.05,
            regenerate_count=1,
            is_fallback=False,
            quality_score=78.5,
            claims_checked=10,
            claims_failed=1,
        )
        d = m.to_dict()
        assert d["sport"] == "NBA"
        assert d["factual_error_rate"] == 0.05
        assert d["regenerate_count"] == 1
        assert d["quality_score"] == 78.5

    def test_zero_claims_no_division_error(self) -> None:
        blocks = [
            {
                "block_index": 0,
                "role": SemanticRole.SETUP.value,
                "narrative": "The teams exchanged baskets in a tight opening frame.",
                "mini_box": {"home": {"team": "Hawks", "players": []}, "away": {"team": "Celtics", "players": []}},
            }
        ]
        result = run_content_pipeline(blocks, GAME_CONTEXT, "NBA")
        assert result.factual_result.claims_checked == 0


class TestPipelineWithFallback:
    """Tests ensuring fallback produces valid content for all sports."""

    def _make_minimal_blocks(self, sport: str) -> list[dict]:
        return [
            {
                "block_index": 0,
                "role": "SETUP",
                "score_before": [0, 0],
                "score_after": [3, 1],
                "period_start": 1,
                "period_end": 1,
                "narrative": "He is averaging 25 points this season.",
                "mini_box": {
                    "home": {"team": "Team A", "players": [{"name": "Star Player", "pts": 10, "goals": 1, "rbi": 2}]},
                    "away": {"team": "Team B", "players": []},
                },
            },
            {
                "block_index": 1,
                "role": "RESOLUTION",
                "score_before": [3, 1],
                "score_after": [5, 2],
                "period_start": 2,
                "period_end": 4,
                "narrative": "His injury concerns remain.",
                "mini_box": {
                    "home": {"team": "Team A", "players": [{"name": "Star Player", "pts": 20, "goals": 2, "rbi": 3}]},
                    "away": {"team": "Team B", "players": []},
                },
            },
        ]

    def test_nba_fallback(self) -> None:
        blocks = self._make_minimal_blocks("NBA")
        context = {"home_team_name": "Team A", "away_team_name": "Team B", "sport": "NBA"}
        result = run_content_pipeline(blocks, context, "NBA", retry_count=2)
        assert result.is_fallback is True
        for b in result.blocks:
            assert b["narrative"]
            assert len(b["narrative"]) > 0

    def test_nhl_fallback(self) -> None:
        blocks = self._make_minimal_blocks("NHL")
        context = {"home_team_name": "Team A", "away_team_name": "Team B", "sport": "NHL"}
        result = run_content_pipeline(blocks, context, "NHL", retry_count=2)
        assert result.is_fallback is True
        assert all(b["narrative"] for b in result.blocks)

    def test_mlb_fallback(self) -> None:
        blocks = self._make_minimal_blocks("MLB")
        context = {"home_team_name": "Team A", "away_team_name": "Team B", "sport": "MLB"}
        result = run_content_pipeline(blocks, context, "MLB", retry_count=2)
        assert result.is_fallback is True
        assert all(b["narrative"] for b in result.blocks)

    def test_ncaab_fallback(self) -> None:
        blocks = self._make_minimal_blocks("NCAAB")
        context = {"home_team_name": "Team A", "away_team_name": "Team B", "sport": "NCAAB"}
        result = run_content_pipeline(blocks, context, "NCAAB", retry_count=2)
        assert result.is_fallback is True
        assert all(b["narrative"] for b in result.blocks)
