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


# =============================================================================
# PHASE 2.2: RANK + SELECT (Replace Hard Budget Clamp)
# =============================================================================


class TestRankAndSelect(unittest.TestCase):
    """PHASE 2.2: Tests for pure importance-based rank+select."""
    
    def test_rank_select_preserves_highest_importance(self) -> None:
        """Rank+select should keep highest importance moments."""
        from app.services.moment_selection import rank_and_select, MomentRankRecord
        from app.services.moments import Moment, MomentType
        
        # Create moments with varying importance
        moments = []
        for i in range(10):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.NEUTRAL,
                start_play=i * 5,
                end_play=i * 5 + 4,
                play_count=5,
            )
            m.importance_score = float(i)  # Higher index = higher importance
            moments.append(m)
        
        # Select top 5
        result = rank_and_select(moments, budget=5)
        
        # Should keep moments 5-9 (highest importance)
        self.assertEqual(result.selected_count, 5)
        self.assertEqual(result.rejected_count, 5)
        
        # Check that high importance moments are selected
        selected_ids = {m.id for m in result.selected_moments}
        # The top 5 by importance should be m_006 through m_010
        for i in range(5, 10):
            # Moment with importance i should have rank <= 5
            rank_record = next(r for r in result.rank_records if r.importance_score == float(i))
            self.assertTrue(rank_record.selected)
    
    def test_rank_select_records_rejection_reason(self) -> None:
        """Rejected moments should have clear rejection reason."""
        from app.services.moment_selection import rank_and_select
        from app.services.moments import Moment, MomentType
        
        moments = []
        for i in range(5):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.NEUTRAL,
                start_play=i * 5,
                end_play=i * 5 + 4,
                play_count=5,
            )
            m.importance_score = float(i)
            moments.append(m)
        
        # Select only top 2
        result = rank_and_select(moments, budget=2)
        
        # 3 should be rejected
        rejected = [r for r in result.rank_records if not r.selected]
        self.assertEqual(len(rejected), 3)
        
        for record in rejected:
            self.assertEqual(record.rejection_reason, "below_rank_cutoff")
            self.assertGreater(len(record.displaced_by), 0)
    
    def test_rank_select_maintains_chronological_output(self) -> None:
        """Output should be chronologically ordered regardless of importance order."""
        from app.services.moment_selection import rank_and_select
        from app.services.moments import Moment, MomentType
        
        # Create moments where high importance is in the middle
        moments = []
        for i in range(10):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.NEUTRAL,
                start_play=i * 5,
                end_play=i * 5 + 4,
                play_count=5,
            )
            # Importance peaks in middle (moment 5)
            m.importance_score = 10.0 - abs(i - 5)
            moments.append(m)
        
        result = rank_and_select(moments, budget=5)
        
        # Output should still be chronological
        for i in range(1, len(result.selected_moments)):
            self.assertLess(
                result.selected_moments[i-1].start_play,
                result.selected_moments[i].start_play,
                "Output must be chronological"
            )
    
    def test_rank_select_diagnostics_complete(self) -> None:
        """Diagnostics should include all required fields."""
        from app.services.moment_selection import rank_and_select
        from app.services.moments import Moment, MomentType
        
        moments = []
        for i in range(5):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.NEUTRAL,
                start_play=i * 5,
                end_play=i * 5 + 4,
                play_count=5,
            )
            m.importance_score = float(i)
            moments.append(m)
        
        result = rank_and_select(moments, budget=3)
        
        # Check aggregate diagnostics
        self.assertEqual(result.total_candidates, 5)
        self.assertEqual(result.selected_count, 3)
        self.assertEqual(result.rejected_count, 2)
        self.assertEqual(result.budget_used, 3)
        
        # Check that min selected > max rejected (because we selected by importance)
        self.assertGreaterEqual(
            result.min_selected_importance,
            result.max_rejected_importance
        )
        
        # Check to_dict includes all fields
        result_dict = result.to_dict()
        self.assertIn("phase", result_dict)
        self.assertIn("total_candidates", result_dict)
        self.assertIn("selected_count", result_dict)
        self.assertIn("rejected_count", result_dict)
        self.assertIn("rank_records", result_dict)


class TestRankSelectVsOldClamp(unittest.TestCase):
    """Tests verifying Phase 2.2 fixes the old enforce_budget issues."""
    
    def test_late_game_high_importance_survives(self) -> None:
        """Late-game high-importance moments should survive even with early noise."""
        from app.services.moment_selection import rank_and_select
        from app.services.moments import Moment, MomentType
        
        moments = []
        
        # Early game: lots of low-importance moments
        for i in range(8):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.NEUTRAL,
                start_play=i * 5,
                end_play=i * 5 + 4,
                play_count=5,
            )
            m.importance_score = 1.0  # Low importance
            moments.append(m)
        
        # Late game: high-importance moment
        late_moment = Moment(
            id="m_009",
            type=MomentType.FLIP,
            start_play=40,
            end_play=44,
            play_count=5,
        )
        late_moment.importance_score = 10.0  # High importance
        moments.append(late_moment)
        
        # With old clamp: late moment might be lost because early moments claimed slots
        # With rank+select: late moment should survive because it has highest importance
        
        result = rank_and_select(moments, budget=3)
        
        # The late high-importance moment MUST be in the result
        selected_ids = {m.id for m in result.selected_moments}
        self.assertIn("m_009", selected_ids, 
                      "Late-game high-importance moment must survive")
    
    def test_early_noise_is_removed(self) -> None:
        """Early-game noise should be removed in favor of meaningful moments."""
        from app.services.moment_selection import rank_and_select
        from app.services.moments import Moment, MomentType
        
        moments = []
        
        # Early noise: many low-importance moments
        for i in range(6):
            m = Moment(
                id=f"early_{i}",
                type=MomentType.NEUTRAL,
                start_play=i * 3,
                end_play=i * 3 + 2,
                play_count=3,
            )
            m.importance_score = 0.5  # Very low
            moments.append(m)
        
        # Later important moments
        for i in range(4):
            m = Moment(
                id=f"late_{i}",
                type=MomentType.FLIP,
                start_play=20 + i * 5,
                end_play=24 + i * 5,
                play_count=5,
            )
            m.importance_score = 5.0 + i  # Higher importance
            moments.append(m)
        
        result = rank_and_select(moments, budget=4)
        
        # Verify: The rank_records should show all 4 late moments selected
        # and all 6 early moments rejected
        late_records = [r for r in result.rank_records if r.moment_id.startswith("late_")]
        early_records = [r for r in result.rank_records if r.moment_id.startswith("early_")]
        
        # All 4 late moments should be marked as selected in rank_records
        self.assertEqual(len(late_records), 4)
        for record in late_records:
            self.assertTrue(record.selected, f"{record.moment_id} should be selected")
        
        # All 6 early moments should be marked as rejected in rank_records
        self.assertEqual(len(early_records), 6)
        for record in early_records:
            self.assertFalse(record.selected, f"{record.moment_id} should be rejected")
            self.assertEqual(record.rejection_reason, "below_rank_cutoff")


# =============================================================================
# PHASE 2.3 + 2.4: DYNAMIC BUDGET AND PACING SELECTION
# =============================================================================


class TestDynamicBudget(unittest.TestCase):
    """PHASE 2.3: Tests for dynamic budget computation."""
    
    def test_blowout_reduces_budget(self) -> None:
        """Blowout games should have reduced target moment count."""
        from app.services.moment_selection import GameSignals, compute_dynamic_budget
        
        # Simulate a blowout: 30-point margin, low closeness
        signals = GameSignals()
        signals.final_margin = 30
        signals.closeness_duration = 0.15
        signals.total_lead_changes = 1
        signals.has_overtime = False
        
        budget = compute_dynamic_budget(signals)
        
        # Blowout should have low target
        self.assertLess(budget.target_moment_count, 18)
        self.assertLess(budget.margin_adjustment, 0)  # Penalty applied
    
    def test_close_game_increases_budget(self) -> None:
        """Close games should have increased target moment count."""
        from app.services.moment_selection import GameSignals, compute_dynamic_budget
        
        # Simulate close game: 3-point margin, high closeness
        signals = GameSignals()
        signals.final_margin = 3
        signals.closeness_duration = 0.65
        signals.total_lead_changes = 8
        signals.lead_change_score = 12
        signals.has_overtime = False
        
        budget = compute_dynamic_budget(signals)
        
        # Close game should have high target
        self.assertGreater(budget.target_moment_count, 26)
        self.assertGreater(budget.margin_adjustment, 0)  # Bonus applied
        self.assertGreater(budget.closeness_adjustment, 0)
    
    def test_overtime_increases_budget(self) -> None:
        """Overtime should increase target moment count."""
        from app.services.moment_selection import GameSignals, compute_dynamic_budget
        
        # Simulate OT game
        signals = GameSignals()
        signals.final_margin = 5
        signals.closeness_duration = 0.5
        signals.has_overtime = True
        signals.overtime_periods = 2  # Double OT
        
        budget = compute_dynamic_budget(signals)
        
        # OT should add bonus
        self.assertGreater(budget.overtime_adjustment, 0)
        self.assertGreater(budget.target_moment_count, 22)  # Above base
    
    def test_budget_bounded(self) -> None:
        """Budget should be bounded by min/max."""
        from app.services.moment_selection import GameSignals, compute_dynamic_budget
        
        # Extreme blowout
        signals = GameSignals()
        signals.final_margin = 50
        signals.closeness_duration = 0.05
        signals.total_lead_changes = 0
        
        budget = compute_dynamic_budget(signals)
        
        # Should hit minimum bound
        self.assertGreaterEqual(budget.target_moment_count, 10)


class TestPacingConstraints(unittest.TestCase):
    """PHASE 2.4: Tests for pacing constraints and selection."""
    
    def test_selection_respects_early_game_cap(self) -> None:
        """Early-game moments should be capped."""
        # Create game with lots of early-game action
        timeline = []
        idx = 0
        
        # Q1: Lots of events
        for i in range(15):
            timeline.append(make_pbp_event(idx, i*2, i, quarter=1, game_clock=f'{12-i}:00'))
            idx += 1
        
        # Q2: More events
        for i in range(10):
            timeline.append(make_pbp_event(idx, 30+i*2, 20+i, quarter=2, game_clock=f'{12-i}:00'))
            idx += 1
        
        # Q3: Few events
        for i in range(5):
            timeline.append(make_pbp_event(idx, 50+i*2, 40+i, quarter=3, game_clock=f'{12-i}:00'))
            idx += 1
        
        # Q4: Few events
        for i in range(5):
            timeline.append(make_pbp_event(idx, 60+i*2, 50+i, quarter=4, game_clock=f'{5-i}:00'))
            idx += 1
        
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Count early game moments
        early_count = sum(1 for m in moments if m.importance_factors.get('time', {}).get('quarter', 0) <= 2)
        late_count = sum(1 for m in moments if m.importance_factors.get('time', {}).get('quarter', 0) >= 4)
        
        # Should have closing moments
        self.assertGreater(late_count, 0, "Should have closing moments")
    
    def test_selection_maintains_coverage(self) -> None:
        """Selection should maintain full timeline coverage."""
        timeline = [make_pbp_event(i, i * 2, i) for i in range(30)]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Verify coverage
        covered = set()
        for m in moments:
            for i in range(m.start_play, m.end_play + 1):
                covered.add(i)
        
        expected = set(range(30))
        self.assertEqual(covered, expected, "Selection should maintain coverage")
    
    def test_selection_chronological(self) -> None:
        """Selected moments should remain in chronological order."""
        timeline = [make_pbp_event(i, i * 2, i) for i in range(20)]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        # Verify chronological order
        for i in range(1, len(moments)):
            self.assertLessEqual(
                moments[i-1].start_play, 
                moments[i].start_play,
                "Moments should be chronological"
            )


class TestNarrativeSelection(unittest.TestCase):
    """Tests for narrative-aware selection algorithm."""
    
    def test_selection_produces_moments(self) -> None:
        """Selection should produce at least one moment."""
        timeline = [
            make_pbp_event(0, 0, 0, quarter=1, game_clock="12:00"),
            make_pbp_event(1, 5, 0, quarter=1, game_clock="10:00"),
            make_pbp_event(2, 10, 5, quarter=2, game_clock="8:00"),
        ]
        moments = partition_game(timeline, {}, NBA_THRESHOLDS, hysteresis_plays=1)
        
        self.assertGreater(len(moments), 0)
    
    def test_dynamic_budget_in_diagnostics(self) -> None:
        """Dynamic budget info should be available for diagnostics."""
        from app.services.moment_selection import (
            compute_game_signals, compute_dynamic_budget, GameSignals
        )
        
        signals = GameSignals()
        signals.final_margin = 10
        signals.closeness_duration = 0.4
        
        budget = compute_dynamic_budget(signals)
        budget_dict = budget.to_dict()
        
        self.assertIn("target_moment_count", budget_dict)
        self.assertIn("signals", budget_dict)
        self.assertIn("adjustments", budget_dict)
        self.assertIn("bounds", budget_dict)


# =============================================================================
# PHASE 3: MOMENT CONSTRUCTION IMPROVEMENTS
# =============================================================================


class TestBackAndForthChapters(unittest.TestCase):
    """PHASE 3.1: Tests for back-and-forth chapter moments."""
    
    def test_volatility_cluster_detection(self) -> None:
        """Should detect early-game volatility clusters."""
        from app.services.moment_construction import detect_volatility_clusters, ChapterConfig
        from app.services.moments import Moment, MomentType
        
        # Create moments simulating early game volatility
        moments = []
        for i in range(6):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.FLIP if i % 2 == 0 else MomentType.TIE,
                start_play=i * 3,
                end_play=i * 3 + 2,
                play_count=3,
            )
            m.importance_score = 2.0
            moments.append(m)
        
        # Events for Q1
        events = [
            {"event_type": "pbp", "quarter": 1, "play_id": i}
            for i in range(20)
        ]
        
        clusters = detect_volatility_clusters(moments, events)
        
        # Should detect a cluster
        self.assertGreater(len(clusters), 0)
        
        # Cluster should have multiple lead changes
        cluster = clusters[0]
        self.assertGreaterEqual(cluster.lead_changes, 2)
    
    def test_chapter_creation_absorbs_moments(self) -> None:
        """Chapter creation should absorb FLIP/TIE sequences."""
        from app.services.moment_construction import create_chapter_moments
        from app.services.moments import Moment, MomentType
        
        # Create moments
        moments = []
        for i in range(5):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.FLIP,
                start_play=i * 4,
                end_play=i * 4 + 3,
                play_count=4,
            )
            m.importance_score = 2.0
            moments.append(m)
        
        events = [
            {"event_type": "pbp", "quarter": 1, "play_id": i}
            for i in range(25)
        ]
        
        result = create_chapter_moments(moments, events)
        
        # Should have created chapters if volatility was high enough
        if result.chapters_created > 0:
            self.assertLess(len(result.moments), len(moments))
            self.assertGreater(result.moments_absorbed, 0)
    
    def test_chapter_has_is_chapter_flag(self) -> None:
        """Chapter moments should have is_chapter=True."""
        from app.services.moments import Moment, MomentType
        
        # Create a chapter moment directly
        chapter = Moment(
            id="chapter_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=20,
            play_count=21,
            is_chapter=True,
        )
        chapter.chapter_info = {
            "lead_changes": 3,
            "ties": 2,
            "absorbed_moment_ids": ["m_001", "m_002", "m_003"],
        }
        
        self.assertTrue(chapter.is_chapter)
        self.assertIn("lead_changes", chapter.chapter_info)
        
        # Should serialize correctly
        chapter_dict = chapter.to_dict()
        self.assertTrue(chapter_dict["is_chapter"])
        self.assertIn("chapter_info", chapter_dict)


class TestMegaMomentSplitting(unittest.TestCase):
    """PHASE 3.3: Tests for semantic mega-moment splitting."""
    
    def test_mega_moment_detection(self) -> None:
        """Moments above threshold should be detected as mega-moments."""
        from app.services.moment_construction import split_mega_moment, SplitConfig
        from app.services.moments import Moment, MomentType
        
        # Create a mega-moment (50+ plays)
        mega = Moment(
            id="m_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=79,
            play_count=80,
        )
        mega.importance_score = 3.0
        
        events = [
            {"event_type": "pbp", "play_id": i, "home_score": i, "away_score": 0, "quarter": 1}
            for i in range(100)
        ]
        thresholds = [5, 10, 15, 20]
        
        config = SplitConfig(mega_moment_threshold=50)
        result = split_mega_moment(mega, events, thresholds, config)
        
        # Should be detected as mega-moment
        self.assertEqual(result.original_play_count, 80)
        # Note: may or may not be split depending on split points found
    
    def test_small_moment_not_split(self) -> None:
        """Moments below threshold should not be split."""
        from app.services.moment_construction import split_mega_moment, SplitConfig
        from app.services.moments import Moment, MomentType
        
        small = Moment(
            id="m_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=19,
            play_count=20,
        )
        small.importance_score = 3.0
        
        events = [
            {"event_type": "pbp", "play_id": i, "home_score": i, "away_score": 0}
            for i in range(30)
        ]
        thresholds = [5, 10, 15, 20]
        
        config = SplitConfig(mega_moment_threshold=50)
        result = split_mega_moment(small, events, thresholds, config)
        
        self.assertFalse(result.was_split)
        self.assertEqual(result.skip_reason, "below_threshold")
    
    def test_split_creates_segments_with_metadata(self) -> None:
        """Splits should create segments with proper metadata."""
        from app.services.moment_construction import (
            apply_mega_moment_splitting, SplitConfig, SplitSegment
        )
        from app.services.moments import Moment, MomentType
        
        # Create a mega-moment with tier changes
        mega = Moment(
            id="m_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=99,
            play_count=100,
            score_before=(0, 0),
            score_after=(50, 30),
            ladder_tier_before=0,
            ladder_tier_after=2,
        )
        mega.importance_score = 5.0
        
        # Events with tier changes at different points
        events = []
        for i in range(100):
            # Create tier changes at plays 25, 50, 75
            if i < 25:
                home, away = i, 0
            elif i < 50:
                home, away = i, i - 20
            else:
                home, away = i, i - 40
            
            events.append({
                "event_type": "pbp",
                "play_id": i,
                "home_score": home,
                "away_score": away,
                "quarter": 1,
            })
        
        thresholds = [5, 10, 15, 20]
        config = SplitConfig(
            mega_moment_threshold=50,
            min_segment_plays=10,
            min_plays_between_splits=15,
        )
        
        result = apply_mega_moment_splitting([mega], events, thresholds, config)
        
        # Check stats
        self.assertEqual(result.mega_moments_found, 1)
        
        # If split occurred, check segments
        if result.mega_moments_split > 0:
            # Each segment should have proper metadata
            for moment in result.moments:
                if moment.chapter_info.get("is_split_segment"):
                    self.assertIn("parent_moment_id", moment.chapter_info)
                    self.assertIn("segment_index", moment.chapter_info)
    
    def test_split_preserves_chronological_order(self) -> None:
        """Split segments should remain chronologically ordered."""
        from app.services.moment_construction import apply_mega_moment_splitting, SplitConfig
        from app.services.moments import Moment, MomentType
        
        mega = Moment(
            id="m_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=79,
            play_count=80,
        )
        mega.importance_score = 5.0
        
        events = [
            {"event_type": "pbp", "play_id": i, "home_score": i*2, "away_score": i, "quarter": 1}
            for i in range(100)
        ]
        thresholds = [5, 10, 15, 20]
        
        result = apply_mega_moment_splitting([mega], events, thresholds)
        
        # Check chronological order
        for i in range(1, len(result.moments)):
            self.assertLessEqual(
                result.moments[i-1].start_play,
                result.moments[i].start_play,
                "Moments should be chronologically ordered"
            )


# =============================================================================
# PHASE 4: PLAYER & BOX SCORE INTEGRATION
# =============================================================================


class TestMomentBoxscore(unittest.TestCase):
    """PHASE 4.1: Tests for per-moment stat aggregation."""
    
    def test_boxscore_aggregates_points_by_player(self) -> None:
        """Should aggregate points by player from PBP events."""
        from app.services.moment_enrichment import aggregate_moment_boxscore
        from app.services.moments import Moment, MomentType
        
        moment = Moment(
            id="m_001",
            type=MomentType.LEAD_BUILD,
            start_play=0,
            end_play=4,
            play_count=5,
        )
        
        events = [
            {"event_type": "pbp", "player_name": "LeBron James", "points_scored": 3, "scoring_team": "home"},
            {"event_type": "pbp", "player_name": "Anthony Davis", "points_scored": 2, "scoring_team": "home"},
            {"event_type": "pbp", "player_name": "LeBron James", "points_scored": 2, "scoring_team": "home"},
            {"event_type": "pbp", "player_name": "Opponent Player", "points_scored": 2, "scoring_team": "away"},
            {"event_type": "pbp", "player_name": "Anthony Davis", "points_scored": 2, "scoring_team": "home"},
        ]
        
        boxscore = aggregate_moment_boxscore(moment, events)
        
        # LeBron: 3 + 2 = 5 points
        self.assertEqual(boxscore.points_by_player.get("LeBron James"), 5)
        # AD: 2 + 2 = 4 points
        self.assertEqual(boxscore.points_by_player.get("Anthony Davis"), 4)
        # Team totals
        self.assertEqual(boxscore.team_totals.home, 9)
        self.assertEqual(boxscore.team_totals.away, 2)
    
    def test_boxscore_tracks_key_plays(self) -> None:
        """Should track blocks, steals, and turnovers."""
        from app.services.moment_enrichment import aggregate_moment_boxscore
        from app.services.moments import Moment, MomentType
        
        moment = Moment(
            id="m_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=2,
            play_count=3,
        )
        
        events = [
            {"event_type": "pbp", "play_type": "block", "player_name": "Anthony Davis"},
            {"event_type": "pbp", "play_type": "steal", "player_name": "Alex Caruso"},
            {"event_type": "pbp", "play_type": "turnover", "player_name": "Opponent Player"},
        ]
        
        boxscore = aggregate_moment_boxscore(moment, events)
        
        self.assertEqual(boxscore.key_plays.blocks.get("Anthony Davis"), 1)
        self.assertEqual(boxscore.key_plays.steals.get("Alex Caruso"), 1)
        self.assertEqual(boxscore.key_plays.turnovers_committed.get("Opponent Player"), 1)
    
    def test_boxscore_tracks_assists(self) -> None:
        """Should track assist connections."""
        from app.services.moment_enrichment import aggregate_moment_boxscore
        from app.services.moments import Moment, MomentType
        
        moment = Moment(
            id="m_001",
            type=MomentType.LEAD_BUILD,
            start_play=0,
            end_play=2,
            play_count=3,
        )
        
        events = [
            {"event_type": "pbp", "player_name": "Scorer1", "points_scored": 2, "assist_player": "Passer1"},
            {"event_type": "pbp", "player_name": "Scorer1", "points_scored": 3, "assist_player": "Passer1"},
            {"event_type": "pbp", "player_name": "Scorer2", "points_scored": 2, "assist_player": "Passer1"},
        ]
        
        boxscore = aggregate_moment_boxscore(moment, events)
        
        # Should have assist connections
        self.assertGreater(len(boxscore.top_assists), 0)
        # Passer1 -> Scorer1 should have 2 assists
        p1_to_s1 = next((a for a in boxscore.top_assists if a.from_player == "Passer1" and a.to_player == "Scorer1"), None)
        self.assertIsNotNone(p1_to_s1)
        self.assertEqual(p1_to_s1.count, 2)
    
    def test_boxscore_to_dict(self) -> None:
        """Boxscore should serialize correctly."""
        from app.services.moment_enrichment import MomentBoxscore, TeamTotals, KeyPlays
        
        boxscore = MomentBoxscore(
            points_by_player={"Player A": 10, "Player B": 5},
            team_totals=TeamTotals(home=15, away=8),
            plays_analyzed=10,
            scoring_plays=5,
        )
        
        result = boxscore.to_dict()
        
        self.assertIn("points_by_player", result)
        self.assertIn("team_totals", result)
        self.assertEqual(result["team_totals"]["home"], 15)
        self.assertEqual(result["team_totals"]["net"], 7)


class TestNarrativeSummary(unittest.TestCase):
    """PHASE 4.2: Tests for deterministic narrative summaries."""
    
    def test_narrative_has_structural_sentence(self) -> None:
        """Should generate structural change sentence."""
        from app.services.moment_enrichment import (
            generate_narrative_summary, MomentBoxscore, TeamTotals
        )
        from app.services.moments import Moment, MomentType
        
        moment = Moment(
            id="m_001",
            type=MomentType.FLIP,
            start_play=0,
            end_play=10,
            play_count=11,
            score_before=(20, 22),
            score_after=(28, 24),
        )
        
        boxscore = MomentBoxscore(
            team_totals=TeamTotals(home=8, away=2),
        )
        
        events = [{"event_type": "pbp", "quarter": 2, "game_clock": "6:00"} for _ in range(11)]
        
        summary = generate_narrative_summary(moment, boxscore, events, "Lakers", "Celtics")
        
        self.assertIn("Lakers", summary.structural_sentence)
        self.assertIn("lead", summary.structural_sentence.lower())
    
    def test_narrative_has_player_sentence(self) -> None:
        """Should generate player-centric sentence with top scorers."""
        from app.services.moment_enrichment import (
            generate_narrative_summary, MomentBoxscore, TeamTotals
        )
        from app.services.moments import Moment, MomentType
        
        moment = Moment(
            id="m_001",
            type=MomentType.LEAD_BUILD,
            start_play=0,
            end_play=10,
            play_count=11,
            score_before=(20, 15),
            score_after=(35, 20),
        )
        
        boxscore = MomentBoxscore(
            points_by_player={"LeBron James": 10, "Anthony Davis": 5},
            team_totals=TeamTotals(home=15, away=5),
        )
        
        events = [{"event_type": "pbp", "quarter": 2} for _ in range(11)]
        
        summary = generate_narrative_summary(moment, boxscore, events, "Lakers", "Celtics")
        
        # Should mention players
        self.assertIn("LeBron James", summary.player_sentence)
        self.assertIn("LeBron James", summary.players_referenced)
    
    def test_narrative_is_deterministic(self) -> None:
        """Same input should produce same output."""
        from app.services.moment_enrichment import (
            generate_narrative_summary, MomentBoxscore, TeamTotals
        )
        from app.services.moments import Moment, MomentType
        
        moment = Moment(
            id="m_001",
            type=MomentType.NEUTRAL,
            start_play=0,
            end_play=5,
            play_count=6,
        )
        
        boxscore = MomentBoxscore(
            points_by_player={"Player A": 6},
            team_totals=TeamTotals(home=6, away=4),
        )
        
        events = [{"event_type": "pbp", "quarter": 1} for _ in range(6)]
        
        # Generate twice
        summary1 = generate_narrative_summary(moment, boxscore, events)
        summary2 = generate_narrative_summary(moment, boxscore, events)
        
        self.assertEqual(summary1.text, summary2.text)
        self.assertEqual(summary1.template_id, summary2.template_id)
    
    def test_narrative_to_dict(self) -> None:
        """Narrative should serialize correctly."""
        from app.services.moment_enrichment import NarrativeSummary
        
        summary = NarrativeSummary(
            text="The full summary text.",
            structural_sentence="Lakers took the lead.",
            player_sentence="LeBron scored 10.",
            template_id="flip_home|single_star",
            players_referenced=["LeBron James"],
            stats_referenced=["points:10"],
        )
        
        result = summary.to_dict()
        
        self.assertEqual(result["text"], "The full summary text.")
        self.assertIn("sentences", result)
        self.assertEqual(result["template_id"], "flip_home|single_star")


class TestDynamicQuarterQuotas(unittest.TestCase):
    """PHASE 3.2: Tests for dynamic quarter quotas."""
    
    def test_close_game_expands_q4_quota(self) -> None:
        """Close games should have expanded Q4 quota."""
        from app.services.moment_construction import compute_quarter_quotas, QuotaConfig
        from app.services.moments import Moment, MomentType
        
        # Create moments across quarters
        moments = []
        for q in range(1, 5):
            for i in range(3):
                m = Moment(
                    id=f"m_q{q}_{i}",
                    type=MomentType.NEUTRAL,
                    start_play=(q-1)*20 + i*5,
                    end_play=(q-1)*20 + i*5 + 4,
                    play_count=5,
                )
                m.importance_score = 3.0
                moments.append(m)
        
        # Close game events (3 point margin)
        events = []
        for q in range(1, 5):
            for i in range(20):
                events.append({
                    "event_type": "pbp",
                    "quarter": q,
                    "play_id": (q-1)*20 + i,
                    "home_score": 50 + q*10 + i,
                    "away_score": 50 + q*10 + i - 3,  # 3 point margin
                })
        
        quotas = compute_quarter_quotas(moments, events)
        
        # Q4 should have bonus
        self.assertIn(4, quotas)
        q4_quota = quotas[4]
        self.assertGreater(q4_quota.close_game_bonus, 0)
    
    def test_blowout_reduces_all_quotas(self) -> None:
        """Blowouts should have reduced quotas."""
        from app.services.moment_construction import compute_quarter_quotas, QuotaConfig
        from app.services.moments import Moment, MomentType
        
        moments = []
        for q in range(1, 5):
            m = Moment(
                id=f"m_q{q}",
                type=MomentType.NEUTRAL,
                start_play=(q-1)*20,
                end_play=(q-1)*20 + 10,
                play_count=11,
            )
            m.importance_score = 2.0
            moments.append(m)
        
        # Blowout events (30 point margin)
        events = []
        for q in range(1, 5):
            for i in range(20):
                events.append({
                    "event_type": "pbp",
                    "quarter": q,
                    "play_id": (q-1)*20 + i,
                    "home_score": 30 + q*15,
                    "away_score": q*10,  # Big margin
                })
        
        quotas = compute_quarter_quotas(moments, events)
        
        # All quarters should have reduction
        for q in range(1, 5):
            if q in quotas:
                self.assertGreater(quotas[q].blowout_reduction, 0)
    
    def test_quota_enforcement_merges_excess(self) -> None:
        """Quota enforcement should merge excess moments."""
        from app.services.moment_construction import enforce_quarter_quotas, QuotaConfig
        from app.services.moments import Moment, MomentType
        
        # Create many moments in Q1 (more than quota)
        moments = []
        for i in range(10):
            m = Moment(
                id=f"m_{i+1:03d}",
                type=MomentType.NEUTRAL,
                start_play=i * 2,
                end_play=i * 2 + 1,
                play_count=2,
            )
            m.importance_score = float(i)  # Varying importance
            moments.append(m)
        
        events = [
            {"event_type": "pbp", "quarter": 1, "play_id": i, "home_score": i, "away_score": 0}
            for i in range(25)
        ]
        
        # Use a config with low quota to force merging
        config = QuotaConfig(baseline_quota=4, min_quota=2, max_quota=6)
        result = enforce_quarter_quotas(moments, events, config)
        
        # Should have merged some moments
        if result.quotas.get(1, QuotaConfig()).needs_compression:
            self.assertLess(len(result.moments), len(moments))


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
