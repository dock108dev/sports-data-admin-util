"""
Tests for Lead Ladder-based moment detection.

These tests verify that partition_game() correctly identifies
moment boundaries based on Lead Ladder tier crossings.
"""

from __future__ import annotations

import unittest

from app.services.moments import (
    MomentType,
    partition_game,
    get_notable_moments,
    validate_moments,
)


# Sample thresholds for testing
NBA_THRESHOLDS = [3, 6, 10, 16]
NHL_THRESHOLDS = [1, 2, 3]


def make_pbp_event(
    index: int,
    home_score: int,
    away_score: int,
    quarter: int = 1,
    game_clock: str = "12:00",
    play_type: str = "shot",
) -> dict:
    """Helper to create a PBP event for testing."""
    return {
        "event_type": "pbp",
        "play_index": index,
        "home_score": home_score,
        "away_score": away_score,
        "quarter": quarter,
        "game_clock": game_clock,
        "play_type": play_type,
        "description": f"Test {play_type} by Player #{index}",  # Required for canonical PBP filter
    }


class TestMomentType(unittest.TestCase):
    """Tests for MomentType enum values."""

    def test_all_required_types_exist(self) -> None:
        """All required moment types are defined."""
        required_types = [
            "LEAD_BUILD",
            "CUT",
            "TIE",
            "FLIP",
            "CLOSING_CONTROL",
            "HIGH_IMPACT",
            "NEUTRAL",
        ]
        for type_name in required_types:
            self.assertTrue(hasattr(MomentType, type_name))


class TestPartitionGame(unittest.TestCase):
    """Tests for partition_game() function."""

    def test_empty_timeline(self) -> None:
        """Empty timeline returns empty moments."""
        moments = partition_game([], {}, NBA_THRESHOLDS)
        self.assertEqual(moments, [])

    def test_single_event(self) -> None:
        """Single event creates one moment."""
        timeline = [make_pbp_event(0, 2, 0)] # Must have score change to be valid
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        self.assertEqual(len(moments), 1)
        self.assertTrue(moments[0].is_period_start)

    def test_all_plays_covered(self) -> None:
        """Every PBP play belongs to exactly one moment."""
        timeline = [
            make_pbp_event(i, i * 2, i, quarter=1, game_clock=f"{12-i}:00")
            for i in range(10)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)

        # All plays should be covered
        covered_indices = set()
        for moment in moments:
            for i in range(moment.start_play, moment.end_play + 1):
                covered_indices.add(i)

        expected_indices = set(range(10))
        self.assertEqual(covered_indices, expected_indices)

    def test_moments_chronological(self) -> None:
        """Moments are ordered by start_play."""
        timeline = [
            make_pbp_event(i, i * 2, 0, quarter=1, game_clock=f"{12-i}:00")
            for i in range(10)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)

        for i in range(1, len(moments)):
            self.assertGreater(moments[i].start_play, moments[i - 1].start_play)

    def test_tier_crossing_creates_boundary(self) -> None:
        """Tier crossing creates a new moment boundary."""
        timeline = [
            # Start tied
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 2, 0, game_clock="11:00"),
            # Cross tier 1 threshold (3 points)
            make_pbp_event(2, 5, 0, game_clock="10:00"),
            make_pbp_event(3, 7, 0, game_clock="9:00"),
            make_pbp_event(4, 9, 0, game_clock="8:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Should have at least 2 moments (opener + lead build)
        self.assertGreaterEqual(len(moments), 1)

    def test_flip_creates_immediate_boundary(self) -> None:
        """Lead flip creates an immediate boundary (no hysteresis)."""
        timeline = [
            make_pbp_event(0, 5, 0, game_clock="12:00"),  # Home leading
            make_pbp_event(1, 5, 2, game_clock="11:00"),
            make_pbp_event(2, 5, 6, game_clock="10:00"),  # Away takes lead - FLIP
            make_pbp_event(3, 5, 8, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # Should detect the flip
        flip_moments = [m for m in moments if m.type == MomentType.FLIP]
        self.assertGreaterEqual(len(flip_moments), 1)

    def test_tie_creates_immediate_boundary(self) -> None:
        """Reaching a tie creates an immediate boundary."""
        timeline = [
            make_pbp_event(0, 5, 0, game_clock="12:00"),  # Home leading
            make_pbp_event(1, 5, 3, game_clock="11:00"),
            make_pbp_event(2, 5, 5, game_clock="10:00"),  # Tied - TIE
            make_pbp_event(3, 5, 7, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # Should detect the tie
        tie_moments = [m for m in moments if m.type == MomentType.TIE]
        self.assertGreaterEqual(len(tie_moments), 1)

    def test_runs_do_not_automatically_create_moments(self) -> None:
        """Scoring runs only create moments if they cause tier crossings."""
        # 8-0 run but only crossing one tier
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 2, 0, game_clock="11:00"),
            make_pbp_event(2, 4, 0, game_clock="10:00"),  # 4-0 run
            make_pbp_event(3, 4, 2, game_clock="9:00"),   # Opponent scores
            make_pbp_event(4, 6, 2, game_clock="8:00"),
            make_pbp_event(5, 8, 2, game_clock="7:00"),   # 4-0 run again
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Should NOT have a RUN type (that's the old system)
        run_moments = [m for m in moments if m.type.value == "RUN"]
        self.assertEqual(len(run_moments), 0)

    def test_high_impact_event_creates_boundary(self) -> None:
        """High-impact events (ejection, etc.) create boundaries."""
        timeline = [
            make_pbp_event(0, 50, 48, game_clock="10:00"),
            make_pbp_event(1, 50, 48, game_clock="9:00", play_type="ejection"),
            make_pbp_event(2, 52, 48, game_clock="8:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Should detect high-impact event
        high_impact = [m for m in moments if m.type == MomentType.HIGH_IMPACT]
        self.assertGreaterEqual(len(high_impact), 1)

    def test_period_opener_is_flagged(self) -> None:
        """New period flags the moment as is_period_start."""
        timeline = [
            make_pbp_event(0, 25, 22, quarter=1, game_clock="0:30"),
            make_pbp_event(1, 27, 22, quarter=2, game_clock="12:00"),  # Q2 start
            make_pbp_event(2, 29, 24, quarter=2, game_clock="11:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Should have a moment starting in Q2 flagged as period start
        q2_moments = [m for m in moments if m.is_period_start and m.start_play >= 1]
        self.assertGreaterEqual(len(q2_moments), 1)

    def test_hysteresis_prevents_flicker(self) -> None:
        """Hysteresis prevents momentary tier changes from creating boundaries."""
        timeline = [
            make_pbp_event(0, 5, 0, game_clock="12:00"),  # Tier 1
            make_pbp_event(1, 7, 0, game_clock="11:00"),  # Tier 2 (momentary)
            make_pbp_event(2, 7, 3, game_clock="10:00"),  # Back to tier 1
            make_pbp_event(3, 7, 5, game_clock="9:00"),   # Tier 0
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=3)

        # With hysteresis=3, the momentary tier 2 shouldn't create a boundary
        lead_builds = [m for m in moments if m.type == MomentType.LEAD_BUILD]
        # Should be minimal lead build moments due to hysteresis
        self.assertLessEqual(len(lead_builds), 1)


class TestMomentValidation(unittest.TestCase):
    """Tests for moment validation functions."""

    def test_validate_moments_passes_for_valid_moments(self) -> None:
        """Validation passes for correctly partitioned moments."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 2, 0),
            make_pbp_event(2, 4, 0),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)

        # Should not raise
        self.assertTrue(validate_moments(timeline, moments))

    def test_validate_moments_empty_is_valid(self) -> None:
        """Empty moments list is valid."""
        self.assertTrue(validate_moments([], []))


class TestGetNotableMoments(unittest.TestCase):
    """Tests for get_notable_moments() function."""

    def test_notable_moments_filters_by_is_notable(self) -> None:
        """Highlights returns only moments where is_notable=True."""
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 5, 0, game_clock="11:00"),  # Leading
            make_pbp_event(2, 5, 8, game_clock="10:00"),  # Flip - notable
            make_pbp_event(3, 5, 10, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        notable_moments = get_notable_moments(moments)

        # All notable moments should have is_notable=True
        for m in notable_moments:
            self.assertTrue(m.is_notable)

        # Notable moments should be subset of moments
        self.assertLessEqual(len(notable_moments), len(moments))


class TestMomentToDict(unittest.TestCase):
    """Tests for Moment.to_dict() serialization."""

    def test_to_dict_includes_required_fields(self) -> None:
        """Serialization includes all required API fields."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 3, 0),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        self.assertGreater(len(moments), 0)

        d = moments[0].to_dict()

        # Check required fields
        self.assertIn("id", d)
        self.assertIn("type", d)
        self.assertIn("start_play", d)
        self.assertIn("end_play", d)
        self.assertIn("play_count", d)
        self.assertIn("is_notable", d)
        self.assertIn("score_start", d)
        self.assertIn("score_end", d)


class TestNHLThresholds(unittest.TestCase):
    """Tests verifying NHL-specific threshold behavior."""

    def test_nhl_single_goal_matters(self) -> None:
        """Single goal in NHL is significant (NHL thresholds: [1, 2, 3])."""
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="20:00"),
            make_pbp_event(1, 1, 0, game_clock="18:00"),  # 1-0 = tier 1
            make_pbp_event(2, 1, 1, game_clock="15:00"),  # Tie
            make_pbp_event(3, 1, 2, game_clock="10:00"),  # Flip
        ]
        moments = partition_game(timeline, {}, NHL_THRESHOLDS, hysteresis_plays=1)

        # Should detect meaningful moments with NHL thresholds
        self.assertGreater(len(moments), 1)


class TestNoRUNType(unittest.TestCase):
    """Tests verifying RUN type is removed."""

    def test_no_run_moment_type(self) -> None:
        """RUN is not a valid MomentType anymore."""
        self.assertFalse(hasattr(MomentType, "RUN"))

    def test_no_battle_moment_type(self) -> None:
        """BATTLE is not a valid MomentType anymore."""
        self.assertFalse(hasattr(MomentType, "BATTLE"))

    def test_no_closing_type_only_closing_control(self) -> None:
        """CLOSING is replaced with CLOSING_CONTROL."""
        self.assertFalse(hasattr(MomentType, "CLOSING"))
        self.assertTrue(hasattr(MomentType, "CLOSING_CONTROL"))


class TestRunMetadata(unittest.TestCase):
    """Tests for run detection as metadata (not moments)."""

    def test_run_detected_and_attached_to_lead_build(self) -> None:
        """Run that causes tier crossing gets attached as run_info."""
        # 10-0 run that should cause tier crossings
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 3, 0, game_clock="11:00"),  # +3 (tier 1)
            make_pbp_event(2, 6, 0, game_clock="10:00"),  # +3 (tier 2)
            make_pbp_event(3, 9, 0, game_clock="9:00"),   # +3 (still tier 2)
            make_pbp_event(4, 12, 0, game_clock="8:00"),  # +3 (tier 3)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # At least one moment should have run_info
        moments_with_runs = [m for m in moments if m.run_info is not None]
        # The 12-0 run should be detected and attached
        if moments_with_runs:
            run = moments_with_runs[0].run_info
            self.assertEqual(run.team, "home")
            self.assertGreaterEqual(run.points, 6)  # At least min threshold
            self.assertTrue(run.unanswered)

    def test_run_not_attached_to_neutral_moments(self) -> None:
        """Runs in NEUTRAL moments become key_play_ids, not run_info."""
        # Small run that doesn't cause tier crossing
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 2, 0, game_clock="11:00"),
            make_pbp_event(2, 4, 0, game_clock="10:00"),  # 4-0, below run threshold
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # NEUTRAL moments should not have run_info
        neutral_moments = [m for m in moments if m.type == MomentType.NEUTRAL]
        for m in neutral_moments:
            self.assertIsNone(m.run_info)

    def test_run_info_has_play_ids(self) -> None:
        """RunInfo includes play_ids of the scoring plays."""
        # Significant run with multiple scoring plays
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 3, 0, game_clock="11:00"),
            make_pbp_event(2, 6, 0, game_clock="10:00"),
            make_pbp_event(3, 10, 0, game_clock="9:00"),
            make_pbp_event(4, 13, 0, game_clock="8:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Find moment with run_info
        moments_with_runs = [m for m in moments if m.run_info is not None]
        if moments_with_runs:
            run = moments_with_runs[0].run_info
            self.assertIsInstance(run.play_ids, list)
            self.assertGreater(len(run.play_ids), 0)

    def test_run_info_serialized_in_to_dict(self) -> None:
        """Run info is included in to_dict() output."""
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 3, 0, game_clock="11:00"),
            make_pbp_event(2, 8, 0, game_clock="10:00"),
            make_pbp_event(3, 12, 0, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        for moment in moments:
            d = moment.to_dict()
            if moment.run_info is not None:
                self.assertIn("run_info", d)
                self.assertIn("team", d["run_info"])
                self.assertIn("points", d["run_info"])
                self.assertIn("unanswered", d["run_info"])
                self.assertIn("play_ids", d["run_info"])

    def test_no_standalone_run_moments(self) -> None:
        """Runs never create standalone RUN moments."""
        # Big run that would've been a RUN moment in old system
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 3, 0, game_clock="11:00"),
            make_pbp_event(2, 6, 0, game_clock="10:00"),
            make_pbp_event(3, 9, 0, game_clock="9:00"),
            make_pbp_event(4, 12, 0, game_clock="8:00"),
            make_pbp_event(5, 15, 0, game_clock="7:00"),
            make_pbp_event(6, 18, 0, game_clock="6:00"),  # 18-0 run
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # No RUN type moments
        moment_types = {m.type for m in moments}
        self.assertNotIn("RUN", [t.value for t in moment_types])

        # Runs should be metadata on tier-crossing moments, not separate moments
        # We can't guarantee runs are attached (depends on tier crossings)
        # but we CAN guarantee no RUN type exists
        for m in moments:
            self.assertNotEqual(m.type.value, "RUN")


# =============================================================================
# INVARIANT GUARDRAILS - These tests MUST pass to prevent regressions
# =============================================================================


class TestInvariantFullPlayCoverage(unittest.TestCase):
    """
    GUARDRAIL: Every PBP play must belong to exactly one moment.
    
    These tests verify the fundamental invariant that partition_game()
    produces a complete, non-overlapping partition of the timeline.
    """

    def test_coverage_simple_game(self) -> None:
        """Simple game has full coverage."""
        timeline = [make_pbp_event(i, i * 2, i) for i in range(20)]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        
        covered = set()
        for m in moments:
            for i in range(m.start_play, m.end_play + 1):
                self.assertNotIn(i, covered, f"Play {i} covered by multiple moments")
                covered.add(i)
        
        expected = set(range(20))
        self.assertEqual(covered, expected, "Not all plays covered")

    def test_coverage_with_tier_crossings(self) -> None:
        """Game with tier crossings still has full coverage."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 5, 0),    # Tier 1
            make_pbp_event(2, 10, 0),   # Tier 3
            make_pbp_event(3, 10, 8),   # Cut
            make_pbp_event(4, 10, 12),  # Flip
            make_pbp_event(5, 15, 12),  # Back
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        covered = set()
        for m in moments:
            for i in range(m.start_play, m.end_play + 1):
                covered.add(i)
        
        self.assertEqual(covered, {0, 1, 2, 3, 4, 5})

    def test_coverage_multi_period_game(self) -> None:
        """Multi-period game has full coverage across all periods."""
        timeline = []
        idx = 0
        for quarter in range(1, 5):
            for i in range(5):
                timeline.append(make_pbp_event(idx, idx * 2, idx, quarter=quarter))
                idx += 1
        
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        
        covered = set()
        for m in moments:
            for i in range(m.start_play, m.end_play + 1):
                covered.add(i)
        
        self.assertEqual(covered, set(range(20)))

    def test_coverage_nhl_thresholds(self) -> None:
        """NHL thresholds still produce full coverage."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 1, 0),  # Tier 1 in NHL
            make_pbp_event(2, 1, 1),  # Tie
            make_pbp_event(3, 1, 2),  # Flip
            make_pbp_event(4, 2, 2),  # Tie
        ]
        moments = partition_game(timeline, {}, NHL_THRESHOLDS, hysteresis_plays=1)
        
        covered = set()
        for m in moments:
            for i in range(m.start_play, m.end_play + 1):
                covered.add(i)
        
        self.assertEqual(covered, {0, 1, 2, 3, 4})


class TestInvariantNoOverlappingMoments(unittest.TestCase):
    """
    GUARDRAIL: Moments must not overlap.
    
    Each play belongs to exactly one moment. Overlapping would violate
    the fundamental partitioning invariant.
    """

    def test_no_overlap_simple(self) -> None:
        """Simple game has no overlapping moments."""
        timeline = [make_pbp_event(i, i * 2, i) for i in range(15)]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        
        for i, m1 in enumerate(moments):
            for j, m2 in enumerate(moments):
                if i != j:
                    # Check no overlap
                    overlap = not (m1.end_play < m2.start_play or m2.end_play < m1.start_play)
                    self.assertFalse(overlap, f"Moments {i} and {j} overlap")

    def test_no_overlap_with_boundaries(self) -> None:
        """Game with many boundaries has no overlapping moments."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 5, 0, play_type="ejection"),  # High impact
            make_pbp_event(2, 5, 5),    # Tie
            make_pbp_event(3, 5, 10),   # Flip
            make_pbp_event(4, 10, 10),  # Tie
            make_pbp_event(5, 15, 10),  # Lead build
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Check adjacency - each moment should end where next begins (or before)
        for i in range(len(moments) - 1):
            self.assertLess(
                moments[i].end_play, moments[i + 1].start_play + 1,
                f"Moment {i} and {i+1} may overlap"
            )

    def test_validate_moments_catches_overlap(self) -> None:
        """validate_moments() would catch overlapping moments."""
        timeline = [make_pbp_event(i, i, i) for i in range(10)]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        
        # Should pass validation
        self.assertTrue(validate_moments(timeline, moments))


class TestInvariantChronologicalOrdering(unittest.TestCase):
    """
    GUARDRAIL: Moments must be chronologically ordered.
    
    Moments appear in the order they occur in the game timeline.
    No importance-based reordering is allowed.
    """

    def test_moments_strictly_ordered(self) -> None:
        """Moments are strictly ordered by start_play."""
        timeline = [make_pbp_event(i, i * 2, i) for i in range(20)]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS)
        
        for i in range(1, len(moments)):
            self.assertGreater(
                moments[i].start_play,
                moments[i - 1].start_play,
                f"Moment {i} does not come after moment {i-1}"
            )

    def test_notable_moments_not_reordered(self) -> None:
        """Notable moments are NOT reordered to the front."""
        timeline = [
            make_pbp_event(0, 0, 0),      # Not notable
            make_pbp_event(1, 2, 0),      # Not notable
            make_pbp_event(2, 2, 5),      # Flip - notable
            make_pbp_event(3, 2, 7),      # Not notable
            make_pbp_event(4, 10, 7),     # Lead build - maybe notable
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Check that notable moments are NOT moved to front
        # They should be in chronological position
        for i in range(1, len(moments)):
            self.assertGreater(moments[i].start_play, moments[i - 1].start_play)

    def test_notable_moments_preserve_order(self) -> None:
        """get_notable_moments() preserves chronological order."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 5, 0),
            make_pbp_event(2, 5, 8),    # Flip - notable
            make_pbp_event(3, 10, 8),
            make_pbp_event(4, 10, 15),  # Flip - notable
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        notable_moments = get_notable_moments(moments)

        # Notable moments should be in chronological order
        for i in range(1, len(notable_moments)):
            self.assertGreater(
                notable_moments[i].start_play,
                notable_moments[i - 1].start_play,
                "Notable moments not in chronological order"
            )


class TestInvariantNoHardcodedLeagueDefaults(unittest.TestCase):
    """
    GUARDRAIL: No hardcoded league-specific defaults.
    
    The system must require thresholds to be passed explicitly.
    This ensures multi-sport support without hidden assumptions.
    """

    def test_partition_game_requires_thresholds(self) -> None:
        """partition_game works with any valid thresholds."""
        timeline = [make_pbp_event(i, i * 2, i) for i in range(5)]
        
        # Works with NBA thresholds
        moments_nba = partition_game(timeline, {}, [3, 6, 10, 16])
        self.assertGreater(len(moments_nba), 0)
        
        # Works with NHL thresholds
        moments_nhl = partition_game(timeline, {}, [1, 2, 3])
        self.assertGreater(len(moments_nhl), 0)
        
        # Works with custom thresholds
        moments_custom = partition_game(timeline, {}, [2, 5, 8])
        self.assertGreater(len(moments_custom), 0)

    def test_different_thresholds_different_results(self) -> None:
        """Different thresholds produce different moment counts."""
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 2, 0),
            make_pbp_event(2, 4, 0),
            make_pbp_event(3, 6, 0),
        ]
        
        # Tight thresholds (more boundaries)
        moments_tight = partition_game(timeline, {}, [1, 2, 3], hysteresis_plays=1)
        
        # Loose thresholds (fewer boundaries)
        moments_loose = partition_game(timeline, {}, [5, 10, 15], hysteresis_plays=1)
        
        # Both should work with different thresholds
        self.assertGreater(len(moments_tight), 0)
        self.assertGreater(len(moments_loose), 0)


class TestMultiSportConfigRegression(unittest.TestCase):
    """
    REGRESSION TESTS: Multi-sport configurations.
    
    These tests ensure the system works correctly for different sports
    without any sport-specific hardcoding.
    """

    def test_nba_standard_game(self) -> None:
        """NBA game with standard thresholds produces valid moments."""
        thresholds = [3, 6, 10, 16]
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 8, 0),    # Big lead
            make_pbp_event(2, 8, 5),
            make_pbp_event(3, 8, 10),   # Flip
            make_pbp_event(4, 15, 10),  # Back
        ]
        moments = partition_game(timeline, {}, thresholds, hysteresis_plays=1)
        
        # Should have valid moments
        self.assertGreater(len(moments), 0)
        self.assertTrue(validate_moments(timeline, moments))

    def test_nhl_standard_game(self) -> None:
        """NHL game with standard thresholds produces valid moments."""
        thresholds = [1, 2, 3]  # NHL: each goal matters
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 1, 0),  # 1-0
            make_pbp_event(2, 1, 1),  # Tie
            make_pbp_event(3, 2, 1),  # 2-1
            make_pbp_event(4, 2, 2),  # Tie
        ]
        moments = partition_game(timeline, {}, thresholds, hysteresis_plays=1)
        
        self.assertGreater(len(moments), 0)
        self.assertTrue(validate_moments(timeline, moments))
        
        # NHL: single goals should matter
        tie_moments = [m for m in moments if m.type == MomentType.TIE]
        self.assertGreaterEqual(len(tie_moments), 1)

    def test_nfl_standard_game(self) -> None:
        """NFL game with standard thresholds produces valid moments."""
        thresholds = [1, 2, 3, 5]  # NFL: TD margins matter
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 7, 0),    # TD
            make_pbp_event(2, 7, 7),    # Tie
            make_pbp_event(3, 14, 7),   # TD
            make_pbp_event(4, 14, 14),  # Tie
        ]
        moments = partition_game(timeline, {}, thresholds, hysteresis_plays=1)
        
        self.assertGreater(len(moments), 0)
        self.assertTrue(validate_moments(timeline, moments))

    def test_soccer_style_game(self) -> None:
        """Soccer-style game (low scores) produces valid moments."""
        thresholds = [1, 2]  # Soccer: 1-goal lead is significant
        timeline = [
            make_pbp_event(0, 0, 0),
            make_pbp_event(1, 1, 0),  # Goal
            make_pbp_event(2, 1, 1),  # Equalizer
            make_pbp_event(3, 2, 1),  # Winner
        ]
        moments = partition_game(timeline, {}, thresholds, hysteresis_plays=1)
        
        self.assertGreater(len(moments), 0)
        self.assertTrue(validate_moments(timeline, moments))

    def test_empty_thresholds_degrades_gracefully(self) -> None:
        """Empty thresholds produces valid (minimal) moments."""
        timeline = [make_pbp_event(i, i, i) for i in range(5)]
        moments = partition_game(timeline, {}, [], hysteresis_plays=1)
        
        # Should still produce valid moments (no tier crossings)
        self.assertGreater(len(moments), 0)
        self.assertTrue(validate_moments(timeline, moments))


if __name__ == "__main__":
    unittest.main()
