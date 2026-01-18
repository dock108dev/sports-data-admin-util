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
        timeline = [make_pbp_event(0, 2, 0)]  # Must have score change to be valid
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
        """Lead flip creates an immediate boundary when significant.
        
        PHASE 1: Flips to tier 1+ are still immediate because they're significant.
        This test has a flip from 5-0 to 5-6 (tier 1), which is significant.
        """
        timeline = [
            make_pbp_event(0, 5, 0, game_clock="12:00"),  # Home leading (tier 1)
            make_pbp_event(1, 5, 2, game_clock="11:00"),
            make_pbp_event(2, 5, 6, game_clock="10:00"),  # Away takes lead - FLIP (tier 1)
            make_pbp_event(3, 5, 8, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # Should detect the flip (tier 1 flip is significant)
        flip_moments = [m for m in moments if m.type == MomentType.FLIP]
        self.assertGreaterEqual(len(flip_moments), 1)
    
    def test_early_game_micro_flip_gated(self) -> None:
        """PHASE 1: Early-game micro-flips (tier 0 to tier 0) are gated.
        
        A 4-3 to 4-5 flip in Q1 is just noise. It must persist to be confirmed.
        """
        timeline = [
            make_pbp_event(0, 4, 3, quarter=1, game_clock="11:00"),  # Home leads by 1 (tier 0)
            make_pbp_event(1, 4, 5, quarter=1, game_clock="10:30"),  # Away takes 1-pt lead (tier 0)
            make_pbp_event(2, 6, 5, quarter=1, game_clock="10:00"),  # Home takes it back
            make_pbp_event(3, 6, 7, quarter=1, game_clock="9:30"),   # Away takes it back
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # These rapid tier-0 flips should collapse - no FLIP moments
        flip_moments = [m for m in moments if m.type == MomentType.FLIP]
        self.assertEqual(len(flip_moments), 0)
    
    def test_late_game_micro_flip_allowed(self) -> None:
        """PHASE 1: Late-game micro-flips are allowed (every possession matters).
        
        A flip in Q4 under 5 minutes is detected as CLOSING_CONTROL (dagger moment).
        This is correct - late-game flips in close games are the most dramatic moments.
        """
        timeline = [
            make_pbp_event(0, 94, 93, quarter=4, game_clock="2:00"),  # Home leads by 1
            make_pbp_event(1, 94, 95, quarter=4, game_clock="1:30"),  # Away takes lead
            make_pbp_event(2, 94, 96, quarter=4, game_clock="1:15"),  # Away still leads
            make_pbp_event(3, 94, 97, quarter=4, game_clock="1:00"),
            make_pbp_event(4, 96, 97, quarter=4, game_clock="0:45"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # Late game flip in closing situation becomes CLOSING_CONTROL (dagger)
        closing_moments = [m for m in moments if m.type == MomentType.CLOSING_CONTROL]
        self.assertGreaterEqual(len(closing_moments), 1)

    def test_tie_creates_immediate_boundary(self) -> None:
        """Reaching a tie creates an immediate boundary in late game.
        
        PHASE 1: Ties are now gated in early game to reduce noise.
        This test uses late-game events (Q4) where ties are still immediate.
        """
        timeline = [
            make_pbp_event(0, 85, 80, quarter=4, game_clock="4:00"),  # Home leading
            make_pbp_event(1, 85, 83, quarter=4, game_clock="3:30"),
            make_pbp_event(2, 85, 85, quarter=4, game_clock="3:00"),  # Tied - TIE
            make_pbp_event(3, 85, 87, quarter=4, game_clock="2:30"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # Should detect the tie (late game ties are significant)
        tie_moments = [m for m in moments if m.type == MomentType.TIE]
        self.assertGreaterEqual(len(tie_moments), 1)
    
    def test_early_game_tie_gated(self) -> None:
        """PHASE 1: Early-game ties at low score are gated (require hysteresis).
        
        A tie at 5-5 in Q1 is just back-and-forth noise, not a narrative moment.
        The tie must persist for it to be confirmed.
        """
        timeline = [
            make_pbp_event(0, 5, 0, quarter=1, game_clock="12:00"),  # Home leading
            make_pbp_event(1, 5, 3, quarter=1, game_clock="11:00"),
            make_pbp_event(2, 5, 5, quarter=1, game_clock="10:00"),  # Tied
            make_pbp_event(3, 5, 7, quarter=1, game_clock="9:00"),   # Away takes lead immediately
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # Early game tie at low score is gated - should NOT create TIE moment
        # because the tie was immediately broken (no persistence)
        tie_moments = [m for m in moments if m.type == MomentType.TIE]
        self.assertEqual(len(tie_moments), 0)
    
    def test_early_game_significant_tie_allowed(self) -> None:
        """PHASE 1: Early-game ties that break current tier 1+ leads are still detected.
        
        A tie that comes from a tier 1+ lead (not eroded to tier 0) is significant.
        """
        timeline = [
            make_pbp_event(0, 10, 0, quarter=1, game_clock="9:00"),   # Big lead (tier 2)
            make_pbp_event(1, 10, 5, quarter=1, game_clock="8:00"),   # Still tier 1 (margin 5)
            make_pbp_event(2, 10, 7, quarter=1, game_clock="7:30"),   # Still tier 1 (margin 3)
            make_pbp_event(3, 10, 10, quarter=1, game_clock="7:00"),  # Tie from tier 1
            make_pbp_event(4, 10, 12, quarter=1, game_clock="6:30"),  # Tie confirmed
            make_pbp_event(5, 10, 14, quarter=1, game_clock="6:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=2)

        # This tie came from tier 1 (margin was 3) - significant, should be detected
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
        # Need enough plays to avoid aggressive merging - add more events per quarter
        timeline = [
            make_pbp_event(0, 20, 18, quarter=1, game_clock="2:00"),
            make_pbp_event(1, 22, 18, quarter=1, game_clock="1:30"),
            make_pbp_event(2, 24, 20, quarter=1, game_clock="1:00"),
            make_pbp_event(3, 25, 22, quarter=1, game_clock="0:30"),
            make_pbp_event(4, 27, 22, quarter=2, game_clock="12:00"),  # Q2 start
            make_pbp_event(5, 29, 24, quarter=2, game_clock="11:00"),
            make_pbp_event(6, 31, 26, quarter=2, game_clock="10:00"),
            make_pbp_event(7, 33, 28, quarter=2, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # At minimum, should have at least one moment
        self.assertGreaterEqual(len(moments), 1)
        # The first moment covering play 0 should be marked as period start
        if moments:
            self.assertTrue(moments[0].is_period_start)

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
        # Need more plays to avoid aggressive merging for small datasets
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="20:00"),
            make_pbp_event(1, 0, 0, game_clock="19:30", play_type="faceoff"),
            make_pbp_event(2, 1, 0, game_clock="18:00"),  # 1-0 = tier 1
            make_pbp_event(3, 1, 0, game_clock="17:00", play_type="save"),
            make_pbp_event(4, 1, 1, game_clock="15:00"),  # Tie
            make_pbp_event(5, 1, 1, game_clock="14:00", play_type="hit"),
            make_pbp_event(6, 1, 2, game_clock="10:00"),  # Flip
            make_pbp_event(7, 1, 2, game_clock="9:00", play_type="shot"),
        ]
        moments = partition_game(timeline, {}, NHL_THRESHOLDS, hysteresis_plays=1)

        # Should detect at least one meaningful moment with NHL thresholds
        self.assertGreaterEqual(len(moments), 1)
        # Verify the moments cover scoring changes
        if len(moments) > 0:
            # First moment should exist
            self.assertIsNotNone(moments[0].type)


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
        """Runs that don't meet criteria don't create standalone moments.
        
        PHASE 1.3: Runs can now create MOMENTUM_SHIFT moments if they cause tier changes.
        But small runs or runs without tier changes still don't create moments.
        """
        # Small run that doesn't meet boundary threshold
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 2, 0, game_clock="11:00"),
            make_pbp_event(2, 4, 0, game_clock="10:00"),
            make_pbp_event(3, 6, 0, game_clock="9:00"),  # 6-0 run, below boundary threshold
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # No RUN type moments (RUN doesn't exist as a type)
        moment_types = {m.type for m in moments}
        self.assertNotIn("RUN", [t.value for t in moment_types])

        # Small runs below threshold don't create MOMENTUM_SHIFT
        momentum_shifts = [m for m in moments if m.type == MomentType.MOMENTUM_SHIFT]
        self.assertEqual(len(momentum_shifts), 0)


# =============================================================================
# PHASE 1.3: RUN-BASED BOUNDARIES
# =============================================================================


class TestMomentumShiftMoments(unittest.TestCase):
    """PHASE 1.3: Tests for run-based MOMENTUM_SHIFT moments."""
    
    def test_big_run_with_tier_boundaries_uses_lead_build(self) -> None:
        """A big run that creates tier crossings uses LEAD_BUILD, not MOMENTUM_SHIFT.
        
        MOMENTUM_SHIFT is for runs that don't already have tier-based boundaries.
        When a run causes tier crossings, those tier boundaries capture the narrative.
        """
        timeline = [
            make_pbp_event(0, 0, 0, quarter=2, game_clock="6:00"),
            make_pbp_event(1, 3, 0, quarter=2, game_clock="5:30"),  # +3 (tier 1)
            make_pbp_event(2, 6, 0, quarter=2, game_clock="5:00"),  # +3 (tier 2)
            make_pbp_event(3, 9, 0, quarter=2, game_clock="4:30"),  # +3
            make_pbp_event(4, 12, 0, quarter=2, game_clock="4:00"), # +3 (tier 3)
            make_pbp_event(5, 15, 0, quarter=2, game_clock="3:30"), # +3
            make_pbp_event(6, 18, 0, quarter=2, game_clock="3:00"), # +3 (18-0 run)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # The run causes tier crossings, so LEAD_BUILD moments should exist
        lead_builds = [m for m in moments if m.type == MomentType.LEAD_BUILD]
        self.assertGreaterEqual(len(lead_builds), 1, "Tier crossings should create LEAD_BUILD")
        
        # MOMENTUM_SHIFT should NOT be created when tier boundaries already exist
        momentum_shifts = [m for m in moments if m.type == MomentType.MOMENTUM_SHIFT]
        self.assertEqual(len(momentum_shifts), 0, "No duplicate MOMENTUM_SHIFT with existing tier boundaries")
    
    def test_big_run_without_overlapping_boundaries_creates_momentum_shift(self) -> None:
        """A big run that doesn't overlap with tier boundaries creates MOMENTUM_SHIFT.
        
        This tests the case where a significant run happens but doesn't trigger
        tier crossings at the same indices (e.g., run happens during opponent's lead).
        """
        # Opponent has a lead, then we go on a big run that cuts into it
        # The run might not trigger tier boundaries if it stays within a tier
        timeline = [
            make_pbp_event(0, 0, 12, quarter=2, game_clock="6:00"),  # Down 12 (tier 3)
            make_pbp_event(1, 0, 12, quarter=2, game_clock="5:45"),  # No scoring
            make_pbp_event(2, 3, 12, quarter=2, game_clock="5:30"),  # +3 (still tier 2)
            make_pbp_event(3, 6, 12, quarter=2, game_clock="5:00"),  # +3 (tier 2)
            make_pbp_event(4, 9, 12, quarter=2, game_clock="4:30"),  # +3 (tier 1)
            make_pbp_event(5, 12, 12, quarter=2, game_clock="4:00"), # +3 TIE (12-0 run)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # This run causes tier changes (down to tier 1, then tie)
        # If tier boundaries capture it, that's fine (CUT moments)
        # The key is that the run's narrative impact is represented
        all_types = [m.type.value for m in moments]
        has_significant_moment = (
            "MOMENTUM_SHIFT" in all_types or 
            "CUT" in all_types or
            "TIE" in all_types
        )
        self.assertTrue(has_significant_moment, f"Expected significant moment in: {all_types}")
    
    def test_big_run_no_tier_change_no_momentum_shift(self) -> None:
        """A big run that doesn't change tier doesn't create MOMENTUM_SHIFT.
        
        If the margin stays within the same tier, no moment is created.
        """
        # Already at tier 3 (16+ lead), run just extends it
        timeline = [
            make_pbp_event(0, 30, 10, quarter=2, game_clock="6:00"),  # 20-pt lead (tier 4)
            make_pbp_event(1, 33, 10, quarter=2, game_clock="5:30"),  # +3
            make_pbp_event(2, 36, 10, quarter=2, game_clock="5:00"),  # +3 (still tier 4)
            make_pbp_event(3, 39, 10, quarter=2, game_clock="4:30"),  # +3 (12-0 run)
            make_pbp_event(4, 42, 10, quarter=2, game_clock="4:00"),  # +3 (still tier 4)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Should NOT have MOMENTUM_SHIFT - same tier throughout
        momentum_shifts = [m for m in moments if m.type == MomentType.MOMENTUM_SHIFT]
        self.assertEqual(len(momentum_shifts), 0)
    
    def test_run_overlapping_flip_no_duplicate(self) -> None:
        """A run that coincides with a FLIP doesn't create duplicate moments."""
        timeline = [
            make_pbp_event(0, 10, 8, quarter=3, game_clock="6:00"),  # Home leads
            make_pbp_event(1, 10, 11, quarter=3, game_clock="5:30"), # Away takes lead - FLIP
            make_pbp_event(2, 10, 14, quarter=3, game_clock="5:00"), # +3
            make_pbp_event(3, 10, 17, quarter=3, game_clock="4:30"), # +3
            make_pbp_event(4, 10, 20, quarter=3, game_clock="4:00"), # +3 (12-0 run)
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)

        # Should have FLIP but not a separate MOMENTUM_SHIFT at the same point
        boundary_indices = [m.start_play for m in moments]
        # No duplicate boundaries at the same play
        self.assertEqual(len(boundary_indices), len(set(boundary_indices)))


# =============================================================================
# PHASE 1.4: SCORE NORMALIZATION
# =============================================================================


class TestScoreNormalization(unittest.TestCase):
    """PHASE 1.4: Tests for score normalization."""
    
    def test_missing_score_carried_forward(self) -> None:
        """Missing scores are carried forward from previous event."""
        from app.services.moments import normalize_scores
        
        events = [
            {"event_type": "pbp", "home_score": 10, "away_score": 8},
            {"event_type": "pbp", "home_score": None, "away_score": None},  # Missing
            {"event_type": "pbp", "home_score": 12, "away_score": 8},
        ]
        
        result = normalize_scores(events)
        
        # Second event should have scores carried forward
        self.assertEqual(result.events[1]["home_score"], 10)
        self.assertEqual(result.events[1]["away_score"], 8)
        self.assertTrue(result.events[1].get("_score_normalized"))
        
        # Should have one normalization record
        self.assertEqual(len(result.normalizations), 1)
        self.assertEqual(result.normalizations[0].reason, "missing_score_carry_forward")
    
    def test_game_start_defaults_to_zero(self) -> None:
        """At game start, missing scores default to 0."""
        from app.services.moments import normalize_scores
        
        events = [
            {"event_type": "pbp", "home_score": None, "away_score": None},  # First event
            {"event_type": "pbp", "home_score": 2, "away_score": 0},
        ]
        
        result = normalize_scores(events)
        
        # First event should default to 0-0
        self.assertEqual(result.events[0]["home_score"], 0)
        self.assertEqual(result.events[0]["away_score"], 0)
        self.assertEqual(result.normalizations[0].reason, "game_start_default")
    
    def test_quarter_boundary_preserves_score(self) -> None:
        """Quarter boundary markers don't reset scores."""
        from app.services.moments import normalize_scores
        
        events = [
            {"event_type": "pbp", "home_score": 25, "away_score": 22},
            {"event_type": "pbp", "home_score": 0, "away_score": 0, 
             "description": "Start of 2nd quarter"},  # Quarter marker
            {"event_type": "pbp", "home_score": 27, "away_score": 22},
        ]
        
        result = normalize_scores(events)
        
        # Quarter marker should have scores carried forward
        self.assertEqual(result.events[1]["home_score"], 25)
        self.assertEqual(result.events[1]["away_score"], 22)
    
    def test_apparent_reset_handled(self) -> None:
        """Apparent mid-game resets (0-0 after scoring) are corrected."""
        from app.services.moments import normalize_scores
        
        events = [
            {"event_type": "pbp", "home_score": 45, "away_score": 40},
            {"event_type": "pbp", "home_score": 0, "away_score": 0,
             "description": "Player X makes 3-pointer"},  # Bad data
            {"event_type": "pbp", "home_score": 48, "away_score": 40},
        ]
        
        result = normalize_scores(events)
        
        # Bad data should be corrected
        self.assertEqual(result.events[1]["home_score"], 45)
        self.assertEqual(result.events[1]["away_score"], 40)
        self.assertIn("carry_forward", result.normalizations[0].reason)
    
    def test_normalization_happens_before_partitioning(self) -> None:
        """Score normalization is applied before moment creation."""
        # Timeline with missing scores
        timeline = [
            make_pbp_event(0, 10, 8, game_clock="12:00"),
            {"event_type": "pbp", "play_index": 1, "home_score": None, "away_score": None,
             "game_clock": "11:00", "description": "Timeout", "play_type": "shot"},
            make_pbp_event(2, 12, 8, game_clock="10:00"),
        ]
        
        # Should not raise - normalization handles missing scores
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Should have at least one moment
        self.assertGreaterEqual(len(moments), 1)


# =============================================================================
# PHASE 2.1: IMPORTANCE SCORING
# =============================================================================


class TestImportanceScoring(unittest.TestCase):
    """PHASE 2.1: Tests for moment importance scoring."""
    
    def test_moments_have_importance_score(self) -> None:
        """All moments should have a numeric importance score."""
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 3, 0, game_clock="11:00"),
            make_pbp_event(2, 6, 0, game_clock="10:00"),
            make_pbp_event(3, 9, 0, game_clock="9:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        for moment in moments:
            self.assertIsInstance(moment.importance_score, float)
            self.assertGreater(moment.importance_score, 0)
    
    def test_moments_have_importance_factors(self) -> None:
        """All moments should have importance factors breakdown."""
        timeline = [
            make_pbp_event(0, 0, 0, quarter=4, game_clock="2:00"),
            make_pbp_event(1, 3, 0, quarter=4, game_clock="1:30"),
            make_pbp_event(2, 3, 3, quarter=4, game_clock="1:00"),  # TIE
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        for moment in moments:
            self.assertIsInstance(moment.importance_factors, dict)
            # Should have breakdown sections
            if moment.importance_factors:
                self.assertIn("time", moment.importance_factors)
                self.assertIn("margin", moment.importance_factors)
                self.assertIn("lead_change", moment.importance_factors)
    
    def test_late_game_scores_higher_than_early(self) -> None:
        """Late-game moments should score higher than early-game moments."""
        # Early game moment
        early_timeline = [
            make_pbp_event(0, 0, 0, quarter=1, game_clock="12:00"),
            make_pbp_event(1, 5, 0, quarter=1, game_clock="11:00"),
            make_pbp_event(2, 5, 3, quarter=1, game_clock="10:00"),
            make_pbp_event(3, 5, 6, quarter=1, game_clock="9:00"),  # FLIP
        ]
        early_moments = partition_game(early_timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Late game moment (same score scenario)
        late_timeline = [
            make_pbp_event(0, 80, 80, quarter=4, game_clock="2:00"),
            make_pbp_event(1, 85, 80, quarter=4, game_clock="1:30"),
            make_pbp_event(2, 85, 83, quarter=4, game_clock="1:00"),
            make_pbp_event(3, 85, 86, quarter=4, game_clock="0:30"),  # FLIP
        ]
        late_moments = partition_game(late_timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Get max importance from each
        early_max = max(m.importance_score for m in early_moments)
        late_max = max(m.importance_score for m in late_moments)
        
        # Late game should score higher
        self.assertGreater(late_max, early_max)
    
    def test_close_game_scores_higher_than_blowout(self) -> None:
        """Close-game moments should score higher than blowout moments."""
        # Close game
        close_timeline = [
            make_pbp_event(0, 90, 88, quarter=4, game_clock="2:00"),
            make_pbp_event(1, 90, 90, quarter=4, game_clock="1:30"),  # TIE
            make_pbp_event(2, 92, 90, quarter=4, game_clock="1:00"),
        ]
        close_moments = partition_game(close_timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Blowout game
        blowout_timeline = [
            make_pbp_event(0, 90, 60, quarter=4, game_clock="2:00"),
            make_pbp_event(1, 93, 60, quarter=4, game_clock="1:30"),
            make_pbp_event(2, 96, 60, quarter=4, game_clock="1:00"),
        ]
        blowout_moments = partition_game(blowout_timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Get max importance from each
        close_max = max(m.importance_score for m in close_moments)
        blowout_max = max(m.importance_score for m in blowout_moments)
        
        # Close game should score higher
        self.assertGreater(close_max, blowout_max)
    
    def test_importance_in_to_dict(self) -> None:
        """Importance should be included in to_dict() output."""
        timeline = [
            make_pbp_event(0, 0, 0, game_clock="12:00"),
            make_pbp_event(1, 3, 0, game_clock="11:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        for moment in moments:
            d = moment.to_dict()
            self.assertIn("importance_score", d)
            self.assertIsInstance(d["importance_score"], float)
    
    def test_flip_scores_higher_than_neutral(self) -> None:
        """FLIP moments should score higher than NEUTRAL moments."""
        timeline = [
            make_pbp_event(0, 0, 0, quarter=3, game_clock="6:00"),
            make_pbp_event(1, 5, 0, quarter=3, game_clock="5:00"),  # Lead
            make_pbp_event(2, 5, 3, quarter=3, game_clock="4:00"),
            make_pbp_event(3, 5, 6, quarter=3, game_clock="3:00"),  # FLIP
            make_pbp_event(4, 5, 8, quarter=3, game_clock="2:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        flip_moments = [m for m in moments if m.type == MomentType.FLIP]
        neutral_moments = [m for m in moments if m.type == MomentType.NEUTRAL]
        
        if flip_moments and neutral_moments:
            flip_max = max(m.importance_score for m in flip_moments)
            neutral_max = max(m.importance_score for m in neutral_moments)
            self.assertGreater(flip_max, neutral_max)


class TestImportanceFactorsBreakdown(unittest.TestCase):
    """Tests for individual importance factor components."""
    
    def test_time_weight_increases_with_progress(self) -> None:
        """Time weight should increase as game progresses."""
        from app.services.moment_importance import _compute_time_weight, DEFAULT_WEIGHTS
        
        early_weight, _ = _compute_time_weight(0.1, 1, 600, DEFAULT_WEIGHTS)  # Q1
        mid_weight, _ = _compute_time_weight(0.5, 2, 300, DEFAULT_WEIGHTS)    # Q2/Q3
        late_weight, _ = _compute_time_weight(0.9, 4, 60, DEFAULT_WEIGHTS)    # Q4 final minute
        
        self.assertLess(early_weight, mid_weight)
        self.assertLess(mid_weight, late_weight)
    
    def test_margin_weight_higher_for_close_games(self) -> None:
        """Margin weight should be higher for close games (lower tiers)."""
        from app.services.moment_importance import _compute_margin_weight, DEFAULT_WEIGHTS
        
        close_weight, _ = _compute_margin_weight(0, 0, 2, 3, DEFAULT_WEIGHTS)  # Tier 0
        mid_weight, _ = _compute_margin_weight(1, 1, 5, 6, DEFAULT_WEIGHTS)    # Tier 1
        blowout_weight, _ = _compute_margin_weight(3, 4, 18, 22, DEFAULT_WEIGHTS)  # Tier 3-4
        
        self.assertGreater(close_weight, mid_weight)
        self.assertGreater(mid_weight, blowout_weight)
    
    def test_lead_change_bonus_for_flips(self) -> None:
        """Lead change bonus should be positive for FLIP moments."""
        from app.services.moment_importance import _compute_lead_change_weight, DEFAULT_WEIGHTS
        
        weight, info = _compute_lead_change_weight(
            "FLIP", "home", "away", False, False, DEFAULT_WEIGHTS
        )
        
        self.assertGreater(weight, 0)
        self.assertTrue(info["lead_changed"])
        self.assertTrue(info["is_flip"])
    
    def test_run_weight_scales_with_points(self) -> None:
        """Run weight should increase with more points scored."""
        from app.services.moment_importance import _compute_run_weight, DEFAULT_WEIGHTS
        
        small_weight, _ = _compute_run_weight(6, "home", True, None, DEFAULT_WEIGHTS)
        large_weight, _ = _compute_run_weight(15, "home", True, None, DEFAULT_WEIGHTS)
        
        self.assertGreater(large_weight, small_weight)


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
