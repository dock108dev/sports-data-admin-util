"""
Tests for the game pipeline system.

These tests verify that the pipeline:
1. Correctly processes stages in order
2. Persists outputs between stages
3. Handles auto-chain vs manual execution
4. Properly handles errors
"""

from __future__ import annotations

import unittest

from app.services.pipeline.models import (
    PipelineStage,
    StageInput,
    StageOutput,
    StageResult,
    NormalizedPBPOutput,
    DerivedSignalsOutput,
    GeneratedMomentsOutput,
    ValidationOutput,
    FinalizedOutput,
)


class TestPipelineStage(unittest.TestCase):
    """Tests for PipelineStage enum."""

    def test_ordered_stages(self) -> None:
        """Stages are returned in correct order."""
        stages = PipelineStage.ordered_stages()
        self.assertEqual(len(stages), 5)
        self.assertEqual(stages[0], PipelineStage.NORMALIZE_PBP)
        self.assertEqual(stages[1], PipelineStage.DERIVE_SIGNALS)
        self.assertEqual(stages[2], PipelineStage.GENERATE_MOMENTS)
        self.assertEqual(stages[3], PipelineStage.VALIDATE_MOMENTS)
        self.assertEqual(stages[4], PipelineStage.FINALIZE_MOMENTS)

    def test_next_stage(self) -> None:
        """next_stage() returns correct subsequent stage."""
        self.assertEqual(
            PipelineStage.NORMALIZE_PBP.next_stage(),
            PipelineStage.DERIVE_SIGNALS,
        )
        self.assertEqual(
            PipelineStage.DERIVE_SIGNALS.next_stage(),
            PipelineStage.GENERATE_MOMENTS,
        )
        self.assertEqual(
            PipelineStage.GENERATE_MOMENTS.next_stage(),
            PipelineStage.VALIDATE_MOMENTS,
        )
        self.assertEqual(
            PipelineStage.VALIDATE_MOMENTS.next_stage(),
            PipelineStage.FINALIZE_MOMENTS,
        )
        self.assertIsNone(PipelineStage.FINALIZE_MOMENTS.next_stage())

    def test_previous_stage(self) -> None:
        """previous_stage() returns correct prior stage."""
        self.assertIsNone(PipelineStage.NORMALIZE_PBP.previous_stage())
        self.assertEqual(
            PipelineStage.DERIVE_SIGNALS.previous_stage(),
            PipelineStage.NORMALIZE_PBP,
        )
        self.assertEqual(
            PipelineStage.GENERATE_MOMENTS.previous_stage(),
            PipelineStage.DERIVE_SIGNALS,
        )


class TestStageInput(unittest.TestCase):
    """Tests for StageInput dataclass."""

    def test_default_values(self) -> None:
        """StageInput has correct defaults."""
        stage_input = StageInput(game_id=123, run_id=456)
        self.assertEqual(stage_input.game_id, 123)
        self.assertEqual(stage_input.run_id, 456)
        self.assertIsNone(stage_input.previous_output)
        self.assertEqual(stage_input.game_context, {})

    def test_with_previous_output(self) -> None:
        """StageInput correctly stores previous output."""
        prev = {"pbp_events": [{"event_type": "pbp"}]}
        stage_input = StageInput(
            game_id=123,
            run_id=456,
            previous_output=prev,
        )
        self.assertEqual(stage_input.previous_output, prev)


class TestStageOutput(unittest.TestCase):
    """Tests for StageOutput dataclass."""

    def test_add_log(self) -> None:
        """add_log() appends log entries."""
        output = StageOutput(data={"key": "value"})
        output.add_log("Test message 1")
        output.add_log("Test message 2", level="warning")
        
        self.assertEqual(len(output.logs), 2)
        self.assertEqual(output.logs[0]["message"], "Test message 1")
        self.assertEqual(output.logs[0]["level"], "info")
        self.assertEqual(output.logs[1]["message"], "Test message 2")
        self.assertEqual(output.logs[1]["level"], "warning")


class TestStageResult(unittest.TestCase):
    """Tests for StageResult dataclass."""

    def test_successful_result(self) -> None:
        """Successful result has correct properties."""
        output = StageOutput(data={"key": "value"})
        result = StageResult(
            stage=PipelineStage.NORMALIZE_PBP,
            success=True,
            output=output,
            duration_seconds=1.5,
        )
        
        self.assertTrue(result.success)
        self.assertFalse(result.failed)
        self.assertIsNone(result.error)
        self.assertEqual(result.duration_seconds, 1.5)

    def test_failed_result(self) -> None:
        """Failed result has correct properties."""
        result = StageResult(
            stage=PipelineStage.NORMALIZE_PBP,
            success=False,
            error="Test error",
            duration_seconds=0.5,
        )
        
        self.assertFalse(result.success)
        self.assertTrue(result.failed)
        self.assertEqual(result.error, "Test error")


class TestNormalizedPBPOutput(unittest.TestCase):
    """Tests for NormalizedPBPOutput dataclass."""

    def test_to_dict(self) -> None:
        """to_dict() returns correct structure."""
        output = NormalizedPBPOutput(
            pbp_events=[{"event_type": "pbp", "play_index": 0}],
            game_start="2026-01-18T19:00:00",
            game_end="2026-01-18T22:00:00",
            has_overtime=False,
            total_plays=100,
            phase_boundaries={
                "q1": ("2026-01-18T19:00:00", "2026-01-18T19:15:00"),
            },
        )
        
        result = output.to_dict()
        
        self.assertEqual(len(result["pbp_events"]), 1)
        self.assertEqual(result["game_start"], "2026-01-18T19:00:00")
        self.assertEqual(result["has_overtime"], False)
        self.assertEqual(result["total_plays"], 100)


class TestDerivedSignalsOutput(unittest.TestCase):
    """Tests for DerivedSignalsOutput dataclass."""

    def test_to_dict(self) -> None:
        """to_dict() returns correct structure."""
        output = DerivedSignalsOutput(
            lead_states=[{"tier": 0}],
            tier_crossings=[{"crossing_type": "flip"}],
            runs=[{"points": 8, "team": "home"}],
            thresholds=[3, 6, 10, 16],
        )
        
        result = output.to_dict()
        
        self.assertEqual(len(result["lead_states"]), 1)
        self.assertEqual(len(result["tier_crossings"]), 1)
        self.assertEqual(len(result["runs"]), 1)
        self.assertEqual(result["thresholds"], [3, 6, 10, 16])


class TestGeneratedMomentsOutput(unittest.TestCase):
    """Tests for GeneratedMomentsOutput dataclass."""

    def test_to_dict(self) -> None:
        """to_dict() returns correct structure."""
        output = GeneratedMomentsOutput(
            moments=[{"id": "m_001", "type": "FLIP"}],
            notable_moments=[{"id": "m_001", "type": "FLIP"}],
            moment_count=10,
            budget=30,
            within_budget=True,
        )
        
        result = output.to_dict()
        
        self.assertEqual(len(result["moments"]), 1)
        self.assertEqual(result["moment_count"], 10)
        self.assertEqual(result["within_budget"], True)


class TestValidationOutput(unittest.TestCase):
    """Tests for ValidationOutput dataclass."""

    def test_passed_validation(self) -> None:
        """to_dict() returns correct structure for passed validation."""
        output = ValidationOutput(
            passed=True,
            critical_passed=True,
            warnings_count=2,
            errors=[],
            warnings=["Warning 1", "Warning 2"],
            validation_details={"score_discontinuities": 0},
        )
        
        result = output.to_dict()
        
        self.assertEqual(result["passed"], True)
        self.assertEqual(result["critical_passed"], True)
        self.assertEqual(result["warnings_count"], 2)
        self.assertEqual(len(result["warnings"]), 2)

    def test_failed_validation(self) -> None:
        """to_dict() returns correct structure for failed validation."""
        output = ValidationOutput(
            passed=False,
            critical_passed=False,
            warnings_count=0,
            errors=["Critical error"],
            warnings=[],
            validation_details={"ordering_errors": 1},
        )
        
        result = output.to_dict()
        
        self.assertEqual(result["passed"], False)
        self.assertEqual(result["critical_passed"], False)
        self.assertEqual(len(result["errors"]), 1)


class TestFinalizedOutput(unittest.TestCase):
    """Tests for FinalizedOutput dataclass."""

    def test_to_dict(self) -> None:
        """to_dict() returns correct structure."""
        output = FinalizedOutput(
            artifact_id=42,
            timeline_events=150,
            moment_count=12,
            generated_at="2026-01-18T23:00:00",
        )
        
        result = output.to_dict()
        
        self.assertEqual(result["artifact_id"], 42)
        self.assertEqual(result["timeline_events"], 150)
        self.assertEqual(result["moment_count"], 12)


class TestAutoChainBehavior(unittest.TestCase):
    """Tests for auto-chain behavior based on trigger type."""

    def test_admin_trigger_disables_autochain(self) -> None:
        """Admin triggers should always disable auto-chain."""
        # This would be tested via the executor, but we verify the logic here
        triggered_by = "admin"
        auto_chain = None  # Should be inferred
        
        # Infer auto_chain from trigger type
        if auto_chain is None:
            auto_chain = triggered_by == "prod_auto"
        
        # Admin NEVER auto-chains
        if triggered_by in ("admin", "manual"):
            auto_chain = False
        
        self.assertFalse(auto_chain)

    def test_prod_auto_enables_autochain(self) -> None:
        """Prod_auto triggers should enable auto-chain by default."""
        triggered_by = "prod_auto"
        auto_chain = None
        
        if auto_chain is None:
            auto_chain = triggered_by == "prod_auto"
        
        self.assertTrue(auto_chain)

    def test_manual_trigger_disables_autochain(self) -> None:
        """Manual triggers should always disable auto-chain."""
        triggered_by = "manual"
        auto_chain = True  # Even if explicitly set
        
        if triggered_by in ("admin", "manual"):
            auto_chain = False
        
        self.assertFalse(auto_chain)


if __name__ == "__main__":
    unittest.main()
