"""Tests for ANALYZE_DRAMA stage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.pipeline.models import StageInput
from app.services.pipeline.stages.analyze_drama import (
    DEFAULT_QUARTER_WEIGHTS,
    _build_drama_prompt,
    _extract_quarter_summary,
    _parse_ai_response,
    execute_analyze_drama,
)


class TestExtractQuarterSummary:
    """Tests for _extract_quarter_summary function."""

    def test_four_quarter_game_with_lead_changes(self) -> None:
        """Four quarter game groups moments correctly with lead changes."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 8]},
            {"period": 1, "score_before": [10, 8], "score_after": [15, 20]},  # Lead change
            {"period": 2, "score_before": [15, 20], "score_after": [25, 28]},
            {"period": 2, "score_before": [25, 28], "score_after": [35, 30]},  # Lead change
            {"period": 3, "score_before": [35, 30], "score_after": [50, 45]},
            {"period": 4, "score_before": [50, 45], "score_after": [60, 55]},
        ]

        summary = _extract_quarter_summary(moments)

        assert "Q1" in summary
        assert "Q2" in summary
        assert "Q3" in summary
        assert "Q4" in summary
        assert summary["Q1"]["moment_count"] == 2
        assert summary["Q2"]["moment_count"] == 2
        assert summary["Q3"]["moment_count"] == 1
        assert summary["Q4"]["moment_count"] == 1
        # Lead change in Q1: went from home leading to away leading
        assert summary["Q1"]["lead_changes"] == 1

    def test_overtime_game_creates_ot_keys(self) -> None:
        """Overtime periods create OT1, OT2, etc. keys."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [25, 25]},
            {"period": 2, "score_before": [25, 25], "score_after": [50, 50]},
            {"period": 3, "score_before": [50, 50], "score_after": [75, 75]},
            {"period": 4, "score_before": [75, 75], "score_after": [100, 100]},
            {"period": 5, "score_before": [100, 100], "score_after": [105, 102]},  # OT1
            {"period": 6, "score_before": [105, 102], "score_after": [110, 110]},  # OT2
        ]

        summary = _extract_quarter_summary(moments)

        assert "OT1" in summary
        assert "OT2" in summary
        assert summary["OT1"]["moment_count"] == 1
        assert summary["OT2"]["moment_count"] == 1

    def test_no_lead_changes(self) -> None:
        """Game with one team always leading has no lead changes."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 5]},
            {"period": 1, "score_before": [10, 5], "score_after": [20, 10]},
            {"period": 2, "score_before": [20, 10], "score_after": [30, 15]},
        ]

        summary = _extract_quarter_summary(moments)

        assert summary["Q1"]["lead_changes"] == 0
        assert summary["Q2"]["lead_changes"] == 0

    def test_empty_moments_returns_empty(self) -> None:
        """Empty moments list returns empty summary."""
        summary = _extract_quarter_summary([])
        assert summary == {}

    def test_point_swing_calculated(self) -> None:
        """Point swing is calculated as change in margin."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [20, 10]},  # Margin: +10
            {"period": 1, "score_before": [20, 10], "score_after": [25, 30]},  # Margin: -5
        ]

        summary = _extract_quarter_summary(moments)

        # Margin went from +10 to -5, swing = |(-5) - 0| = 5
        # Actually: start margin = 0-0=0, end margin = 25-30=-5, swing = |-5-0| = 5
        assert summary["Q1"]["point_swing"] == 5

    def test_peak_margin_tracked_within_quarter(self) -> None:
        """Peak margin tracks the largest margin within a quarter, even if it erodes."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [22, 0]},   # Home leads by 22
            {"period": 1, "score_before": [22, 0], "score_after": [25, 18]},  # Lead shrinks to 7
        ]

        summary = _extract_quarter_summary(moments)

        assert summary["Q1"]["peak_margin"] == 22
        assert summary["Q1"]["peak_leader"] == 1  # Home led at peak

    def test_peak_margin_away_team(self) -> None:
        """Peak margin correctly identifies away team as leader."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [5, 20]},   # Away leads by 15
            {"period": 1, "score_before": [5, 20], "score_after": [15, 22]},  # Away still leads but margin shrinks
        ]

        summary = _extract_quarter_summary(moments)

        assert summary["Q1"]["peak_margin"] == 15
        assert summary["Q1"]["peak_leader"] == -1  # Away led at peak

    def test_peak_margin_zero_in_tied_game(self) -> None:
        """Peak margin is 0 when game stays tied."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 10]},
        ]

        summary = _extract_quarter_summary(moments)

        assert summary["Q1"]["peak_margin"] == 0

    def test_score_start_and_end_tracked(self) -> None:
        """Score start and end tracked correctly for each quarter."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [5, 3]},
            {"period": 1, "score_before": [5, 3], "score_after": [12, 10]},
            {"period": 2, "score_before": [12, 10], "score_after": [25, 22]},
        ]

        summary = _extract_quarter_summary(moments)

        assert summary["Q1"]["score_start"] == [0, 0]
        assert summary["Q1"]["score_end"] == [12, 10]
        assert summary["Q2"]["score_start"] == [12, 10]
        assert summary["Q2"]["score_end"] == [25, 22]


class TestBuildDramaPrompt:
    """Tests for _build_drama_prompt function."""

    def test_home_team_wins(self) -> None:
        """Prompt correctly identifies home team as winner."""
        quarter_summary = {
            "Q1": {"score_start": [0, 0], "score_end": [25, 20], "moment_count": 5, "lead_changes": 1, "point_swing": 5},
            "Q4": {"score_start": [75, 70], "score_end": [100, 95], "moment_count": 5, "lead_changes": 0, "point_swing": 0},
        }
        game_context = {"home_team": "Lakers", "away_team": "Celtics", "sport": "basketball"}
        final_score = [100, 95]

        prompt = _build_drama_prompt(quarter_summary, game_context, final_score)

        assert "Lakers" in prompt
        assert "Celtics" in prompt
        assert "Lakers wins by 5" in prompt
        assert "100-95" in prompt

    def test_away_team_wins(self) -> None:
        """Prompt correctly identifies away team as winner."""
        quarter_summary = {
            "Q4": {"score_start": [75, 80], "score_end": [90, 100], "moment_count": 5, "lead_changes": 0, "point_swing": 0},
        }
        game_context = {"home_team": "Lakers", "away_team": "Celtics", "sport": "basketball"}
        final_score = [90, 100]

        prompt = _build_drama_prompt(quarter_summary, game_context, final_score)

        assert "Celtics wins by 10" in prompt

    def test_overtime_quarters_sorted(self) -> None:
        """Quarter lines are sorted correctly including overtime."""
        quarter_summary = {
            "Q4": {"score_start": [75, 75], "score_end": [100, 100], "moment_count": 5, "lead_changes": 2, "point_swing": 0},
            "Q1": {"score_start": [0, 0], "score_end": [25, 25], "moment_count": 5, "lead_changes": 1, "point_swing": 0},
            "OT1": {"score_start": [100, 100], "score_end": [105, 103], "moment_count": 3, "lead_changes": 1, "point_swing": 2},
        }
        game_context = {"home_team": "Lakers", "away_team": "Celtics", "sport": "basketball"}
        final_score = [105, 103]

        prompt = _build_drama_prompt(quarter_summary, game_context, final_score)

        # Lines should be sorted: OT1, Q1, Q4 (alphabetically)
        q1_pos = prompt.find("Q1:")
        q4_pos = prompt.find("Q4:")
        ot1_pos = prompt.find("OT1:")

        # OT1 comes before Q1 alphabetically
        assert ot1_pos < q1_pos < q4_pos

    def test_default_sport(self) -> None:
        """Default sport is basketball when not specified."""
        quarter_summary = {"Q1": {"score_start": [0, 0], "score_end": [10, 8], "moment_count": 1, "lead_changes": 0, "point_swing": 2}}
        game_context = {"home_team": "Lakers", "away_team": "Celtics"}  # No sport
        final_score = [100, 90]

        prompt = _build_drama_prompt(quarter_summary, game_context, final_score)

        assert "basketball" in prompt


class TestParseAiResponse:
    """Tests for _parse_ai_response function."""

    def test_plain_json(self) -> None:
        """Parse plain JSON response."""
        response = '{"quarter_weights": {"Q1": 1.0, "Q4": 2.0}, "peak_quarter": "Q4"}'

        result = _parse_ai_response(response)

        assert result["quarter_weights"]["Q1"] == 1.0
        assert result["quarter_weights"]["Q4"] == 2.0
        assert result["peak_quarter"] == "Q4"

    def test_json_with_markdown_wrapper(self) -> None:
        """Parse JSON wrapped in markdown code blocks."""
        response = '''```json
{"quarter_weights": {"Q1": 0.8, "Q4": 2.5}, "peak_quarter": "Q4"}
```'''

        result = _parse_ai_response(response)

        assert result["quarter_weights"]["Q1"] == 0.8
        assert result["quarter_weights"]["Q4"] == 2.5

    def test_json_with_generic_code_block(self) -> None:
        """Parse JSON wrapped in generic code blocks (no json specifier)."""
        response = '''```
{"quarter_weights": {"Q1": 1.2}, "peak_quarter": "Q1"}
```'''

        result = _parse_ai_response(response)

        assert result["quarter_weights"]["Q1"] == 1.2

    def test_invalid_json_raises(self) -> None:
        """Invalid JSON raises exception."""
        response = "This is not valid JSON"

        with pytest.raises(json.JSONDecodeError):
            _parse_ai_response(response)

    def test_whitespace_stripped(self) -> None:
        """Whitespace is stripped from response."""
        response = '  \n  {"quarter_weights": {"Q1": 1.0}}  \n  '

        result = _parse_ai_response(response)

        assert result["quarter_weights"]["Q1"] == 1.0


class TestExecuteAnalyzeDrama:
    """Tests for execute_analyze_drama async function."""

    @pytest.mark.asyncio
    async def test_missing_previous_output_raises(self) -> None:
        """Missing previous output raises ValueError."""
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output=None,
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with pytest.raises(ValueError, match="requires VALIDATE_MOMENTS output"):
            await execute_analyze_drama(stage_input)

    @pytest.mark.asyncio
    async def test_validation_failed_raises(self) -> None:
        """Previous output with validated=False raises ValueError."""
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"validated": False, "moments": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with pytest.raises(ValueError, match="requires validated moments"):
            await execute_analyze_drama(stage_input)

    @pytest.mark.asyncio
    async def test_empty_moments_returns_defaults(self) -> None:
        """Empty moments list returns default weights."""
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"validated": True, "moments": [], "pbp_events": [], "errors": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        result = await execute_analyze_drama(stage_input)

        assert result.data["drama_analyzed"] is False
        assert result.data["quarter_weights"] == DEFAULT_QUARTER_WEIGHTS

    @pytest.mark.asyncio
    async def test_openai_unavailable_uses_defaults(self) -> None:
        """When OpenAI is unavailable, uses default weights."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 8]},
            {"period": 4, "score_before": [90, 85], "score_after": [100, 95]},
        ]
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"validated": True, "moments": moments, "pbp_events": [], "errors": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with patch("app.services.pipeline.stages.analyze_drama.get_openai_client", return_value=None):
            result = await execute_analyze_drama(stage_input)

        assert result.data["quarter_weights"]["Q4"] == 1.5  # Default Q4 weight

    @pytest.mark.asyncio
    async def test_weights_clamped_to_range(self) -> None:
        """Quarter weights are clamped to [0.5, 2.5] range."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 8]},
            {"period": 2, "score_before": [10, 8], "score_after": [30, 25]},
        ]
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"validated": True, "moments": moments, "pbp_events": [], "errors": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        # Mock OpenAI to return out-of-range weights
        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "quarter_weights": {"Q1": 0.1, "Q2": 5.0},  # Out of range
            "peak_quarter": "Q2",
            "story_type": "blowout",
            "headline": "Test"
        })

        with patch("app.services.pipeline.stages.analyze_drama.get_openai_client", return_value=mock_client):
            result = await execute_analyze_drama(stage_input)

        # Weights should be clamped
        assert result.data["quarter_weights"]["Q1"] == 0.5  # Clamped from 0.1
        assert result.data["quarter_weights"]["Q2"] == 2.5  # Clamped from 5.0

    @pytest.mark.asyncio
    async def test_missing_quarters_get_default_weight(self) -> None:
        """Quarters in game but not in AI response get default weight 1.0."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 8]},
            {"period": 2, "score_before": [10, 8], "score_after": [30, 25]},
            {"period": 3, "score_before": [30, 25], "score_after": [50, 45]},
        ]
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"validated": True, "moments": moments, "pbp_events": [], "errors": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        # Mock OpenAI to return only Q1 weight
        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "quarter_weights": {"Q1": 1.0},  # Missing Q2, Q3
            "peak_quarter": "Q1",
            "story_type": "test",
            "headline": "Test"
        })

        with patch("app.services.pipeline.stages.analyze_drama.get_openai_client", return_value=mock_client):
            result = await execute_analyze_drama(stage_input)

        # Missing quarters should get 1.0
        assert result.data["quarter_weights"]["Q2"] == 1.0
        assert result.data["quarter_weights"]["Q3"] == 1.0

    @pytest.mark.asyncio
    async def test_passthrough_data_preserved(self) -> None:
        """Data from previous stage is passed through."""
        moments = [{"period": 1, "score_before": [0, 0], "score_after": [10, 8]}]
        pbp_events = [{"play_index": 1, "description": "Test play"}]
        errors = ["Some error from previous stage"]

        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={
                "validated": True,
                "moments": moments,
                "pbp_events": pbp_events,
                "errors": errors,
            },
            game_context={"home_team": "Lakers", "away_team": "Celtics"},
        )

        with patch("app.services.pipeline.stages.analyze_drama.get_openai_client", return_value=None):
            result = await execute_analyze_drama(stage_input)

        assert result.data["moments"] == moments
        assert result.data["pbp_events"] == pbp_events
        assert result.data["errors"] == errors
        assert result.data["validated"] is True

    @pytest.mark.asyncio
    async def test_successful_openai_call(self) -> None:
        """Successful OpenAI call returns parsed drama analysis."""
        moments = [
            {"period": 1, "score_before": [0, 0], "score_after": [10, 8]},
            {"period": 4, "score_before": [90, 85], "score_after": [100, 95]},
        ]
        stage_input = StageInput(
            game_id=1,
            run_id=1,
            previous_output={"validated": True, "moments": moments, "pbp_events": [], "errors": []},
            game_context={"home_team": "Lakers", "away_team": "Celtics", "sport": "basketball"},
        )

        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps({
            "quarter_weights": {"Q1": 0.8, "Q4": 2.2},
            "peak_quarter": "Q4",
            "story_type": "close_finish",
            "headline": "Lakers hold on for close win"
        })

        with patch("app.services.pipeline.stages.analyze_drama.get_openai_client", return_value=mock_client):
            result = await execute_analyze_drama(stage_input)

        assert result.data["drama_analyzed"] is True
        assert result.data["quarter_weights"]["Q1"] == 0.8
        assert result.data["quarter_weights"]["Q4"] == 2.2
        assert result.data["peak_quarter"] == "Q4"
        assert result.data["story_type"] == "close_finish"
        assert result.data["headline"] == "Lakers hold on for close win"
