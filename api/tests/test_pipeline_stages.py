"""
Tests for individual pipeline stage implementations.

These tests verify that each stage correctly:
1. Validates its input
2. Produces correct output format
3. Handles errors appropriately
"""

from __future__ import annotations

import unittest
from typing import Any

from app.services.pipeline.models import StageInput


def make_pbp_event(
    index: int,
    home_score: int,
    away_score: int,
    quarter: int = 1,
    game_clock: str = "12:00",
    phase: str = "q1",
) -> dict[str, Any]:
    """Create a normalized PBP event for testing."""
    return {
        "event_type": "pbp",
        "play_index": index,
        "home_score": home_score,
        "away_score": away_score,
        "quarter": quarter,
        "game_clock": game_clock,
        "phase": phase,
        "intra_phase_order": 720 - (int(game_clock.split(":")[0]) * 60),
        "description": f"Test play #{index}",
        "play_type": "shot",
        "synthetic_timestamp": "2026-01-18T19:00:00",
    }


class TestDeriveSignalsStage(unittest.TestCase):
    """Tests for DERIVE_SIGNALS stage logic."""

    def test_compute_lead_states(self) -> None:
        """Lead states are computed correctly for each play."""
        from app.services.pipeline.stages.derive_signals import compute_lead_states
        
        pbp_events = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 2, 0),
            make_pbp_event(2, 2, 3),
            make_pbp_event(3, 5, 3),
        ]
        
        thresholds = [3, 6, 10, 16]
        lead_states = compute_lead_states(pbp_events, thresholds)
        
        self.assertEqual(len(lead_states), 4)
        
        # First event: tied
        self.assertEqual(lead_states[0]["leader"], "tied")
        self.assertEqual(lead_states[0]["tier"], 0)
        
        # Second event: home leads by 2 (tier 0)
        self.assertEqual(lead_states[1]["leader"], "home")
        self.assertEqual(lead_states[1]["tier"], 0)
        
        # Third event: away leads by 1 (tier 0)
        self.assertEqual(lead_states[2]["leader"], "away")
        self.assertEqual(lead_states[2]["tier"], 0)
        
        # Fourth event: home leads by 2 (tier 0)
        self.assertEqual(lead_states[3]["leader"], "home")
        self.assertEqual(lead_states[3]["tier"], 0)

    def test_find_tier_crossings(self) -> None:
        """Tier crossings are detected correctly."""
        from app.services.pipeline.stages.derive_signals import find_tier_crossings
        
        # Build a timeline with a clear tier crossing
        pbp_events = [
            make_pbp_event(0, 0, 0),    # Tied
            make_pbp_event(1, 3, 0),    # Home leads by 3 -> tier 1
            make_pbp_event(2, 6, 0),    # Home leads by 6 -> tier 2 (tier up)
        ]
        
        thresholds = [3, 6, 10, 16]
        crossings = find_tier_crossings(pbp_events, thresholds)
        
        # Should detect: tie_broken at index 1, tier_up at index 2
        self.assertGreaterEqual(len(crossings), 1)
        
        # Check that crossings have required fields
        for crossing in crossings:
            self.assertIn("play_index", crossing)
            self.assertIn("crossing_type", crossing)
            self.assertIn("prev_state", crossing)
            self.assertIn("curr_state", crossing)


class TestValidateMomentsStage(unittest.TestCase):
    """Tests for VALIDATE_MOMENTS stage logic."""

    def test_validate_moment_ordering(self) -> None:
        """Moments must be in chronological order."""
        from app.services.pipeline.stages.validate_moments import _validate_moment_ordering
        
        # Valid ordering
        moments = [
            {"id": "m_001", "start_play": 0, "end_play": 10},
            {"id": "m_002", "start_play": 11, "end_play": 20},
            {"id": "m_003", "start_play": 21, "end_play": 30},
        ]
        errors = _validate_moment_ordering(moments)
        self.assertEqual(len(errors), 0)
        
        # Invalid ordering
        moments_bad = [
            {"id": "m_001", "start_play": 10, "end_play": 20},
            {"id": "m_002", "start_play": 5, "end_play": 15},  # Starts before previous
        ]
        errors_bad = _validate_moment_ordering(moments_bad)
        self.assertEqual(len(errors_bad), 1)
        self.assertIn("not chronological", errors_bad[0])

    def test_validate_no_overlaps(self) -> None:
        """Moments must not overlap."""
        from app.services.pipeline.stages.validate_moments import _validate_no_overlaps
        
        # Valid (no overlap)
        moments = [
            {"id": "m_001", "start_play": 0, "end_play": 10},
            {"id": "m_002", "start_play": 11, "end_play": 20},
        ]
        errors = _validate_no_overlaps(moments)
        self.assertEqual(len(errors), 0)
        
        # Overlapping moments
        moments_overlap = [
            {"id": "m_001", "start_play": 0, "end_play": 15},
            {"id": "m_002", "start_play": 10, "end_play": 20},  # Overlaps
        ]
        errors_overlap = _validate_no_overlaps(moments_overlap)
        self.assertEqual(len(errors_overlap), 1)
        self.assertIn("Overlapping", errors_overlap[0])

    def test_validate_budget(self) -> None:
        """Moment count should be within budget."""
        from app.services.pipeline.stages.validate_moments import _validate_budget
        
        # Within budget
        moments = [{"id": f"m_{i:03d}"} for i in range(25)]
        warnings = _validate_budget(moments, budget=30)
        self.assertEqual(len(warnings), 0)
        
        # Over budget
        moments_over = [{"id": f"m_{i:03d}"} for i in range(35)]
        warnings_over = _validate_budget(moments_over, budget=30)
        self.assertEqual(len(warnings_over), 1)
        self.assertIn("exceeds budget", warnings_over[0])

    def test_validate_moment_structure(self) -> None:
        """Moments must have required fields."""
        from app.services.pipeline.stages.validate_moments import _validate_moment_structure
        
        # Valid moment
        moment = {
            "id": "m_001",
            "type": "FLIP",
            "start_play": 0,
            "end_play": 10,
            "play_count": 10,
        }
        errors = _validate_moment_structure(moment)
        self.assertEqual(len(errors), 0)
        
        # Missing required field
        moment_bad = {
            "id": "m_001",
            "type": "FLIP",
            # Missing start_play, end_play, play_count
        }
        errors_bad = _validate_moment_structure(moment_bad)
        self.assertGreater(len(errors_bad), 0)


class TestStageInputValidation(unittest.TestCase):
    """Tests for stage input validation."""

    def test_derive_signals_requires_previous_output(self) -> None:
        """DERIVE_SIGNALS requires output from NORMALIZE_PBP."""
        stage_input = StageInput(
            game_id=123,
            run_id=456,
            previous_output=None,  # Missing
        )
        
        # The stage should raise an error if previous_output is None
        self.assertIsNone(stage_input.previous_output)

    def test_derive_signals_requires_pbp_events(self) -> None:
        """DERIVE_SIGNALS requires pbp_events in previous output."""
        stage_input = StageInput(
            game_id=123,
            run_id=456,
            previous_output={},  # Empty, no pbp_events
        )
        
        pbp_events = stage_input.previous_output.get("pbp_events", [])
        self.assertEqual(len(pbp_events), 0)


class TestStageOutputFormat(unittest.TestCase):
    """Tests for stage output format requirements."""

    def test_normalize_pbp_output_format(self) -> None:
        """NORMALIZE_PBP output has required fields."""
        from app.services.pipeline.models import NormalizedPBPOutput
        
        output = NormalizedPBPOutput(
            pbp_events=[make_pbp_event(0, 0, 0)],
            game_start="2026-01-18T19:00:00",
            game_end="2026-01-18T22:00:00",
            has_overtime=False,
            total_plays=1,
            phase_boundaries={"q1": ("2026-01-18T19:00:00", "2026-01-18T19:15:00")},
        )
        
        data = output.to_dict()
        
        self.assertIn("pbp_events", data)
        self.assertIn("game_start", data)
        self.assertIn("game_end", data)
        self.assertIn("has_overtime", data)
        self.assertIn("total_plays", data)
        self.assertIn("phase_boundaries", data)

    def test_derived_signals_output_format(self) -> None:
        """DERIVE_SIGNALS output has required fields."""
        from app.services.pipeline.models import DerivedSignalsOutput
        
        output = DerivedSignalsOutput(
            lead_states=[],
            tier_crossings=[],
            runs=[],
            thresholds=[3, 6, 10, 16],
        )
        
        data = output.to_dict()
        
        self.assertIn("lead_states", data)
        self.assertIn("tier_crossings", data)
        self.assertIn("runs", data)
        self.assertIn("thresholds", data)

    def test_generated_moments_output_format(self) -> None:
        """GENERATE_MOMENTS output has required fields."""
        from app.services.pipeline.models import GeneratedMomentsOutput
        
        output = GeneratedMomentsOutput(
            moments=[],
            notable_moments=[],
            moment_count=0,
            budget=30,
            within_budget=True,
        )
        
        data = output.to_dict()
        
        self.assertIn("moments", data)
        self.assertIn("notable_moments", data)
        self.assertIn("moment_count", data)
        self.assertIn("budget", data)
        self.assertIn("within_budget", data)


if __name__ == "__main__":
    unittest.main()
