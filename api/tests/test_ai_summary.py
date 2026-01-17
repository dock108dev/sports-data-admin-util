"""
Tests for AI summary generation.

These tests verify that:
1. AI only writes copy (headline, subhead)
2. AI cannot affect structure (attention_points, flow, etc.)
3. Fallbacks work when AI is disabled
4. Structured inputs are correctly formatted
"""

from __future__ import annotations

import unittest

# Note: AIHeadlineOutput, generate_fallback_headline, generate_fallback_moment_label
# were removed during the 2026-01 refactoring. AI enrichment is now required.
# These tests are disabled until we add tests for the new enrichment system.

# from app.services.ai_client import (
#     AIHeadlineOutput,
#     GameSummaryInput,
#     generate_fallback_headline,
#     generate_fallback_moment_label,
# )
from app.services.summary_builder import (
    build_summary_from_timeline,
    classify_game_flow,
    generate_attention_points,
)
from app.services.moments import MomentType


class TestFlowClassification(unittest.TestCase):
    """Tests for deterministic flow classification."""

    def test_close_game(self) -> None:
        """Score diff <= 5 is close."""
        self.assertEqual(classify_game_flow(3), "close")
        self.assertEqual(classify_game_flow(5), "close")

    def test_competitive_game(self) -> None:
        """Score diff 6-12 is competitive."""
        self.assertEqual(classify_game_flow(6), "competitive")
        self.assertEqual(classify_game_flow(12), "competitive")

    def test_comfortable_game(self) -> None:
        """Score diff 13-20 is comfortable."""
        self.assertEqual(classify_game_flow(15), "comfortable")
        self.assertEqual(classify_game_flow(20), "comfortable")

    def test_blowout_game(self) -> None:
        """Score diff > 20 is blowout."""
        self.assertEqual(classify_game_flow(21), "blowout")
        self.assertEqual(classify_game_flow(35), "blowout")


@unittest.skip("Fallback functions removed - AI enrichment now required")
class TestFallbackHeadline(unittest.TestCase):
    """Tests for deterministic fallback headline generation.
    
    DISABLED: These tests are for fallback functions that were removed in 2026-01 refactoring.
    """

    def test_fallback_headline_blowout(self) -> None:
        """Blowout generates appropriate headline."""
        input_data = GameSummaryInput(
            home_team="Lakers",
            away_team="Celtics",
            final_score_home=120,
            final_score_away=85,
            flow="blowout",
            has_overtime=False,
            moment_types=["OPENER", "LEAD_BUILD", "NEUTRAL"],
            notable_count=2,
        )
        result = generate_fallback_headline(input_data)

        self.assertIsInstance(result, AIHeadlineOutput)
        self.assertIn("Lakers", result.headline)
        self.assertIn("rolls", result.headline.lower())
        self.assertIn("120", result.subhead)

    def test_fallback_headline_close_ot(self) -> None:
        """Close OT game generates appropriate headline."""
        input_data = GameSummaryInput(
            home_team="Heat",
            away_team="Bulls",
            final_score_home=108,
            final_score_away=105,
            flow="close",
            has_overtime=True,
            moment_types=["OPENER", "FLIP", "TIE", "CLOSING_CONTROL"],
            notable_count=4,
        )
        result = generate_fallback_headline(input_data)

        self.assertIn("Heat", result.headline)
        self.assertIn("OT", result.headline)
        self.assertIn("108", result.subhead)

    def test_fallback_headline_with_flip(self) -> None:
        """Game with FLIP gets mentioned in subhead."""
        input_data = GameSummaryInput(
            home_team="Warriors",
            away_team="Nuggets",
            final_score_home=115,
            final_score_away=110,
            flow="competitive",
            has_overtime=False,
            moment_types=["OPENER", "FLIP", "LEAD_BUILD"],
            notable_count=2,
        )
        result = generate_fallback_headline(input_data)

        self.assertIn("Lead changed", result.subhead)

    def test_fallback_headline_max_length(self) -> None:
        """Headlines respect max length."""
        input_data = GameSummaryInput(
            home_team="Los Angeles Lakers",
            away_team="Boston Celtics",
            final_score_home=100,
            final_score_away=98,
            flow="close",
            has_overtime=False,
            moment_types=[],
            notable_count=0,
        )
        result = generate_fallback_headline(input_data)

        self.assertLessEqual(len(result.headline), 80)
        self.assertLessEqual(len(result.subhead), 120)


@unittest.skip("Fallback functions removed - AI enrichment now required")
class TestFallbackMomentLabel(unittest.TestCase):
    """Tests for deterministic moment label generation.
    
    DISABLED: These tests are for fallback functions that were removed in 2026-01 refactoring.
    """

    def test_flip_label(self) -> None:
        """FLIP generates lead change label."""
        label = generate_fallback_moment_label("FLIP", None)
        self.assertIn("Lead changes", label)

    def test_lead_build_with_note(self) -> None:
        """LEAD_BUILD with note includes note."""
        label = generate_fallback_moment_label("LEAD_BUILD", "12-0 run")
        self.assertIn("Lead extended", label)
        self.assertIn("12-0 run", label)

    def test_neutral_label(self) -> None:
        """NEUTRAL generates back and forth label."""
        label = generate_fallback_moment_label("NEUTRAL", None)
        self.assertIn("Back and forth", label)


class TestAttentionPoints(unittest.TestCase):
    """Tests for attention point generation from Moments."""

    def test_attention_points_with_flip(self) -> None:
        """FLIP moment creates lead change attention point."""
        # Create simple moment objects
        class SimpleMoment:
            def __init__(self, t: MomentType) -> None:
                self.type = t

        moments = [
            SimpleMoment(MomentType.NEUTRAL),  # OPENER was removed in 2026-01 refactor
            SimpleMoment(MomentType.LEAD_BUILD),
            SimpleMoment(MomentType.FLIP),
            SimpleMoment(MomentType.NEUTRAL),
        ]

        points = generate_attention_points(
            moments,
            social_by_phase={"q4": 2, "postgame": 5},
            flow="competitive",
            has_overtime=False,
        )

        # Should mention lead change
        self.assertTrue(any("lead" in p.lower() for p in points))

    def test_attention_points_close_game(self) -> None:
        """Close game gets final minutes attention point."""
        class SimpleMoment:
            def __init__(self, t: MomentType) -> None:
                self.type = t

        moments = [SimpleMoment(MomentType.NEUTRAL), SimpleMoment(MomentType.NEUTRAL)]

        points = generate_attention_points(
            moments,
            social_by_phase={},
            flow="close",
            has_overtime=False,
        )

        # Should mention final minutes
        self.assertTrue(any("final" in p.lower() for p in points))

    def test_attention_points_overtime(self) -> None:
        """Overtime game mentions OT."""
        class SimpleMoment:
            def __init__(self, t: MomentType) -> None:
                self.type = t

        moments = [SimpleMoment(MomentType.NEUTRAL)]

        points = generate_attention_points(
            moments,
            social_by_phase={},
            flow="close",
            has_overtime=True,
        )

        # Should mention overtime
        self.assertTrue(any("overtime" in p.lower() for p in points))


class TestBuildSummaryFromTimeline(unittest.TestCase):
    """Tests for full summary building."""

    def test_summary_is_deterministic(self) -> None:
        """Same input produces same output."""
        timeline = [
            {"event_type": "pbp", "home_score": 50, "away_score": 48, "phase": "q2"},
            {"event_type": "pbp", "home_score": 100, "away_score": 95, "phase": "q4"},
        ]
        game_analysis = {
            "summary": {
                "teams": {
                    "home": {"id": 1, "name": "Lakers"},
                    "away": {"id": 2, "name": "Celtics"},
                },
            },
            "moments": [
                {"type": "OPENER", "is_notable": False},
                {"type": "FLIP", "is_notable": True},
            ],
        }

        result1 = build_summary_from_timeline(timeline, game_analysis)
        result2 = build_summary_from_timeline(timeline, game_analysis)

        # Should be identical
        self.assertEqual(result1["headline"], result2["headline"])
        self.assertEqual(result1["attention_points"], result2["attention_points"])
        self.assertEqual(result1["flow"], result2["flow"])

    def test_summary_includes_required_fields(self) -> None:
        """Summary includes all required fields."""
        timeline = [
            {"event_type": "pbp", "home_score": 100, "away_score": 98, "phase": "q4"},
        ]
        game_analysis = {
            "summary": {
                "teams": {
                    "home": {"id": 1, "name": "Team A"},
                    "away": {"id": 2, "name": "Team B"},
                },
            },
            "moments": [],
        }

        result = build_summary_from_timeline(timeline, game_analysis)

        # Check required fields
        self.assertIn("teams", result)
        self.assertIn("final_score", result)
        self.assertIn("flow", result)
        self.assertIn("headline", result)
        self.assertIn("subhead", result)
        self.assertIn("attention_points", result)
        # Note: ai_generated field was removed in 2026-01 refactor
        # AI enrichment is now always required

    def test_summary_no_ai_influence_on_structure(self) -> None:
        """AI cannot affect structural fields."""
        timeline = [
            {"event_type": "pbp", "home_score": 100, "away_score": 75, "phase": "q4"},
        ]
        game_analysis = {
            "summary": {
                "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
            },
            "moments": [{"type": "LEAD_BUILD", "is_notable": True}],
        }

        result = build_summary_from_timeline(timeline, game_analysis)

        # Flow is deterministic from score diff
        self.assertEqual(result["flow"], "blowout")

        # Attention points are deterministic from moments
        self.assertIsInstance(result["attention_points"], list)


if __name__ == "__main__":
    unittest.main()
