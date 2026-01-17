"""
Tests for Lead Ladder utilities.

These tests verify the pure functions in lead_ladder.py that track
game control based on lead thresholds.
"""

from __future__ import annotations

import unittest

from app.services.compact_mode_thresholds import get_lead_tier, get_tier_label
from app.services.lead_ladder import (
    Leader,
    TierCrossingType,
    compute_lead_state,
    detect_tier_crossing,
    find_all_tier_crossings,
    track_lead_states,
)


# Sample thresholds for different sports
NBA_THRESHOLDS = [3, 6, 10, 16]
NHL_THRESHOLDS = [1, 2, 3]
NFL_THRESHOLDS = [1, 2, 3, 5]


class TestGetLeadTier(unittest.TestCase):
    """Tests for get_lead_tier() pure function."""

    def test_tier_zero_for_small_lead(self) -> None:
        """Margin below first threshold is tier 0."""
        self.assertEqual(get_lead_tier(0, NBA_THRESHOLDS), 0)
        self.assertEqual(get_lead_tier(1, NBA_THRESHOLDS), 0)
        self.assertEqual(get_lead_tier(2, NBA_THRESHOLDS), 0)

    def test_tier_one_at_first_threshold(self) -> None:
        """Margin at first threshold is tier 1."""
        self.assertEqual(get_lead_tier(3, NBA_THRESHOLDS), 1)
        self.assertEqual(get_lead_tier(4, NBA_THRESHOLDS), 1)
        self.assertEqual(get_lead_tier(5, NBA_THRESHOLDS), 1)

    def test_tier_two_at_second_threshold(self) -> None:
        """Margin at second threshold is tier 2."""
        self.assertEqual(get_lead_tier(6, NBA_THRESHOLDS), 2)
        self.assertEqual(get_lead_tier(7, NBA_THRESHOLDS), 2)
        self.assertEqual(get_lead_tier(9, NBA_THRESHOLDS), 2)

    def test_tier_three_at_third_threshold(self) -> None:
        """Margin at third threshold is tier 3."""
        self.assertEqual(get_lead_tier(10, NBA_THRESHOLDS), 3)
        self.assertEqual(get_lead_tier(12, NBA_THRESHOLDS), 3)
        self.assertEqual(get_lead_tier(15, NBA_THRESHOLDS), 3)

    def test_max_tier_at_highest_threshold(self) -> None:
        """Margin at or above highest threshold is max tier."""
        self.assertEqual(get_lead_tier(16, NBA_THRESHOLDS), 4)
        self.assertEqual(get_lead_tier(20, NBA_THRESHOLDS), 4)
        self.assertEqual(get_lead_tier(50, NBA_THRESHOLDS), 4)

    def test_absolute_value_used(self) -> None:
        """Negative margins are treated as absolute values."""
        self.assertEqual(get_lead_tier(-5, NBA_THRESHOLDS), 1)
        self.assertEqual(get_lead_tier(-10, NBA_THRESHOLDS), 3)

    def test_empty_thresholds(self) -> None:
        """Empty threshold list returns tier 0."""
        self.assertEqual(get_lead_tier(10, []), 0)

    def test_nhl_thresholds(self) -> None:
        """NHL thresholds work correctly (fewer tiers)."""
        self.assertEqual(get_lead_tier(0, NHL_THRESHOLDS), 0)
        self.assertEqual(get_lead_tier(1, NHL_THRESHOLDS), 1)
        self.assertEqual(get_lead_tier(2, NHL_THRESHOLDS), 2)
        self.assertEqual(get_lead_tier(3, NHL_THRESHOLDS), 3)
        self.assertEqual(get_lead_tier(5, NHL_THRESHOLDS), 3)  # Max tier


class TestGetTierLabel(unittest.TestCase):
    """Tests for get_tier_label() pure function."""

    def test_tier_zero_is_small(self) -> None:
        self.assertEqual(get_tier_label(0, 4), "small")

    def test_low_tier_is_meaningful(self) -> None:
        self.assertEqual(get_tier_label(1, 4), "meaningful")

    def test_mid_tier_is_comfortable(self) -> None:
        self.assertEqual(get_tier_label(2, 4), "comfortable")

    def test_high_tier_is_large(self) -> None:
        self.assertEqual(get_tier_label(3, 4), "large")

    def test_max_tier_is_decisive(self) -> None:
        self.assertEqual(get_tier_label(4, 4), "decisive")


class TestComputeLeadState(unittest.TestCase):
    """Tests for compute_lead_state() pure function."""

    def test_tied_game(self) -> None:
        """Tied scores produce TIED leader."""
        state = compute_lead_state(50, 50, NBA_THRESHOLDS)
        self.assertEqual(state.leader, Leader.TIED)
        self.assertEqual(state.margin, 0)
        self.assertEqual(state.tier, 0)
        self.assertTrue(state.is_tied)

    def test_home_leading(self) -> None:
        """Home team ahead produces HOME leader."""
        state = compute_lead_state(55, 50, NBA_THRESHOLDS)
        self.assertEqual(state.leader, Leader.HOME)
        self.assertEqual(state.margin, 5)
        self.assertTrue(state.home_leading)
        self.assertFalse(state.away_leading)

    def test_away_leading(self) -> None:
        """Away team ahead produces AWAY leader."""
        state = compute_lead_state(45, 52, NBA_THRESHOLDS)
        self.assertEqual(state.leader, Leader.AWAY)
        self.assertEqual(state.margin, 7)
        self.assertTrue(state.away_leading)
        self.assertFalse(state.home_leading)

    def test_tier_computed_correctly(self) -> None:
        """Tier is computed from margin and thresholds."""
        # Small lead (tier 0)
        state = compute_lead_state(52, 50, NBA_THRESHOLDS)
        self.assertEqual(state.tier, 0)
        self.assertEqual(state.tier_label, "small")

        # Meaningful lead (tier 1)
        state = compute_lead_state(55, 50, NBA_THRESHOLDS)
        self.assertEqual(state.tier, 1)
        self.assertEqual(state.tier_label, "meaningful")

        # Comfortable lead (tier 2)
        state = compute_lead_state(58, 50, NBA_THRESHOLDS)
        self.assertEqual(state.tier, 2)
        self.assertEqual(state.tier_label, "comfortable")

        # Decisive lead (tier 4)
        state = compute_lead_state(70, 50, NBA_THRESHOLDS)
        self.assertEqual(state.tier, 4)
        self.assertEqual(state.tier_label, "decisive")

    def test_tied_has_tier_label_tied(self) -> None:
        """Tied games have tier_label 'tied'."""
        state = compute_lead_state(50, 50, NBA_THRESHOLDS)
        self.assertEqual(state.tier_label, "tied")


class TestDetectTierCrossing(unittest.TestCase):
    """Tests for detect_tier_crossing() pure function."""

    def test_no_crossing_same_tier(self) -> None:
        """No crossing when tier stays the same."""
        prev = compute_lead_state(52, 50, NBA_THRESHOLDS)  # tier 0
        curr = compute_lead_state(54, 52, NBA_THRESHOLDS)  # still tier 0
        crossing = detect_tier_crossing(prev, curr)
        self.assertIsNone(crossing)

    def test_tier_up_crossing(self) -> None:
        """Tier up crossing when lead increases to new tier."""
        prev = compute_lead_state(52, 50, NBA_THRESHOLDS)  # tier 0, margin 2
        curr = compute_lead_state(55, 50, NBA_THRESHOLDS)  # tier 1, margin 5
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIER_UP)
        self.assertEqual(crossing.tier_delta, 1)
        self.assertTrue(crossing.is_significant)

    def test_tier_down_crossing(self) -> None:
        """Tier down crossing when opponent cuts lead."""
        prev = compute_lead_state(58, 50, NBA_THRESHOLDS)  # tier 2, margin 8
        curr = compute_lead_state(58, 55, NBA_THRESHOLDS)  # tier 1, margin 3
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIER_DOWN)
        self.assertEqual(crossing.tier_delta, -1)
        self.assertTrue(crossing.is_significant)

    def test_flip_crossing(self) -> None:
        """Flip crossing when leader changes."""
        prev = compute_lead_state(55, 50, NBA_THRESHOLDS)  # home leading
        curr = compute_lead_state(55, 58, NBA_THRESHOLDS)  # away leading
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        self.assertEqual(crossing.crossing_type, TierCrossingType.FLIP)
        self.assertTrue(crossing.is_significant)

    def test_tie_reached_crossing(self) -> None:
        """Tie reached crossing when game becomes tied."""
        prev = compute_lead_state(55, 50, NBA_THRESHOLDS)  # home leading
        curr = compute_lead_state(55, 55, NBA_THRESHOLDS)  # tied
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_REACHED)
        self.assertTrue(crossing.is_significant)

    def test_tie_broken_crossing(self) -> None:
        """Tie broken crossing when someone takes lead from tie."""
        prev = compute_lead_state(50, 50, NBA_THRESHOLDS)  # tied
        curr = compute_lead_state(53, 50, NBA_THRESHOLDS)  # home takes lead
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_BROKEN)
        self.assertTrue(crossing.is_significant)

    def test_multi_tier_jump(self) -> None:
        """Multi-tier crossing detected correctly."""
        prev = compute_lead_state(50, 50, NBA_THRESHOLDS)  # tier 0 (tied)
        curr = compute_lead_state(60, 50, NBA_THRESHOLDS)  # tier 3, margin 10
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        # This is a tie_broken, not tier_up (leader changed)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_BROKEN)


class TestTrackLeadStates(unittest.TestCase):
    """Tests for track_lead_states() utility function."""

    def test_tracks_sequence(self) -> None:
        """Tracks lead states through score sequence."""
        scores = [(0, 0), (3, 0), (3, 3), (6, 3)]
        states = track_lead_states(scores, NBA_THRESHOLDS)

        self.assertEqual(len(states), 4)
        self.assertEqual(states[0].leader, Leader.TIED)
        self.assertEqual(states[1].leader, Leader.HOME)
        self.assertEqual(states[2].leader, Leader.TIED)
        self.assertEqual(states[3].leader, Leader.HOME)

    def test_empty_sequence(self) -> None:
        """Empty sequence returns empty list."""
        states = track_lead_states([], NBA_THRESHOLDS)
        self.assertEqual(states, [])


class TestFindAllTierCrossings(unittest.TestCase):
    """Tests for find_all_tier_crossings() utility function."""

    def test_finds_all_crossings(self) -> None:
        """Finds all tier crossings in sequence."""
        # Score sequence with multiple crossings
        scores = [
            (0, 0),    # Start tied
            (3, 0),    # Tie broken (home takes lead, tier 1)
            (3, 3),    # Tie reached
            (6, 3),    # Tie broken (tier 1)
            (10, 3),   # Tier up to tier 2
        ]
        crossings = find_all_tier_crossings(scores, NBA_THRESHOLDS)

        self.assertEqual(len(crossings), 4)

        # First crossing: tie broken at index 1
        idx, crossing = crossings[0]
        self.assertEqual(idx, 1)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_BROKEN)

        # Second crossing: tie reached at index 2
        idx, crossing = crossings[1]
        self.assertEqual(idx, 2)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_REACHED)

        # Third crossing: tie broken at index 3
        idx, crossing = crossings[2]
        self.assertEqual(idx, 3)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_BROKEN)

        # Fourth crossing: tier up at index 4
        idx, crossing = crossings[3]
        self.assertEqual(idx, 4)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIER_UP)

    def test_no_crossings_in_stable_game(self) -> None:
        """No crossings when lead is stable."""
        scores = [
            (10, 8),   # Tier 0 home leading
            (12, 10),  # Tier 0 home leading
            (14, 12),  # Tier 0 home leading
        ]
        crossings = find_all_tier_crossings(scores, NBA_THRESHOLDS)
        self.assertEqual(len(crossings), 0)

    def test_short_sequence(self) -> None:
        """Single score returns no crossings."""
        crossings = find_all_tier_crossings([(50, 50)], NBA_THRESHOLDS)
        self.assertEqual(crossings, [])


class TestNHLThresholds(unittest.TestCase):
    """Tests verifying NHL thresholds work correctly."""

    def test_nhl_tier_progression(self) -> None:
        """NHL thresholds have fewer tiers."""
        # NHL: [1, 2, 3] - 3 tiers max
        self.assertEqual(get_lead_tier(0, NHL_THRESHOLDS), 0)
        self.assertEqual(get_lead_tier(1, NHL_THRESHOLDS), 1)
        self.assertEqual(get_lead_tier(2, NHL_THRESHOLDS), 2)
        self.assertEqual(get_lead_tier(3, NHL_THRESHOLDS), 3)
        self.assertEqual(get_lead_tier(5, NHL_THRESHOLDS), 3)  # Max

    def test_nhl_single_goal_is_significant(self) -> None:
        """Single goal in NHL creates tier crossing."""
        prev = compute_lead_state(0, 0, NHL_THRESHOLDS)
        curr = compute_lead_state(1, 0, NHL_THRESHOLDS)
        crossing = detect_tier_crossing(prev, curr)

        self.assertIsNotNone(crossing)
        self.assertEqual(crossing.crossing_type, TierCrossingType.TIE_BROKEN)


class TestNoHardcodedDefaults(unittest.TestCase):
    """Tests verifying no hardcoded sport-specific defaults."""

    def test_thresholds_must_be_provided(self) -> None:
        """Functions require thresholds to be passed explicitly."""
        # This test documents that there are no hidden defaults
        # All functions require thresholds as an argument
        with self.assertRaises(TypeError):
            compute_lead_state(50, 45)  # Missing thresholds

    def test_different_sports_different_behavior(self) -> None:
        """Same margin produces different tiers with different thresholds."""
        # 5-point margin
        nba_state = compute_lead_state(55, 50, NBA_THRESHOLDS)
        nhl_state = compute_lead_state(55, 50, NHL_THRESHOLDS)

        # NBA: 5 is tier 1 (3 <= 5 < 6)
        self.assertEqual(nba_state.tier, 1)

        # NHL: 5 is tier 3 (max tier, 5 >= 3)
        self.assertEqual(nhl_state.tier, 3)


# =============================================================================
# INVARIANT GUARDRAILS - These tests MUST pass to prevent regressions
# =============================================================================


class TestLeadLadderInvariants(unittest.TestCase):
    """
    GUARDRAIL: Lead Ladder invariants that must never be violated.
    """

    def test_tier_never_negative(self) -> None:
        """Tier is never negative."""
        for margin in range(-50, 51):
            tier = get_lead_tier(margin, NBA_THRESHOLDS)
            self.assertGreaterEqual(tier, 0, f"Negative tier for margin {margin}")

    def test_tier_never_exceeds_threshold_count(self) -> None:
        """Tier never exceeds len(thresholds)."""
        max_tier = len(NBA_THRESHOLDS)
        for margin in range(0, 100):
            tier = get_lead_tier(margin, NBA_THRESHOLDS)
            self.assertLessEqual(tier, max_tier, f"Tier {tier} > max {max_tier}")

    def test_compute_lead_state_is_pure(self) -> None:
        """compute_lead_state is a pure function (same input → same output)."""
        state1 = compute_lead_state(55, 50, NBA_THRESHOLDS)
        state2 = compute_lead_state(55, 50, NBA_THRESHOLDS)
        
        self.assertEqual(state1.home_score, state2.home_score)
        self.assertEqual(state1.away_score, state2.away_score)
        self.assertEqual(state1.margin, state2.margin)
        self.assertEqual(state1.leader, state2.leader)
        self.assertEqual(state1.tier, state2.tier)

    def test_leader_enum_complete(self) -> None:
        """Leader enum has all required values."""
        self.assertTrue(hasattr(Leader, "HOME"))
        self.assertTrue(hasattr(Leader, "AWAY"))
        self.assertTrue(hasattr(Leader, "TIED"))

    def test_crossing_type_enum_complete(self) -> None:
        """TierCrossingType enum has all required values."""
        required = ["TIER_UP", "TIER_DOWN", "FLIP", "TIE_REACHED", "TIE_BROKEN"]
        for name in required:
            self.assertTrue(hasattr(TierCrossingType, name))


class TestNoLeagueSpecificHardcoding(unittest.TestCase):
    """
    GUARDRAIL: No league-specific values hardcoded in lead_ladder.py.
    
    This test scans the source code to ensure no NBA/NHL/etc constants
    are embedded in the module.
    """

    def test_no_nba_constants_in_lead_ladder(self) -> None:
        """lead_ladder.py has no hardcoded NBA constants in function defaults."""
        import inspect
        import re
        from app.services import lead_ladder
        
        source = inspect.getsource(lead_ladder)
        
        # Should NOT have "NBA" as a string constant (outside docstrings)
        # We check for assignments like NBA = "..." or = "NBA"
        nba_assignment = re.search(r'\b(?:NBA|nba)\s*=\s*["\']', source)
        self.assertIsNone(nba_assignment, "NBA string constant found")
        
        # Should NOT have hardcoded threshold arrays as DEFAULT PARAMETERS
        # Pattern: "thresholds = [3, 6, 10, 16]" in function signatures
        # Note: Examples in docstrings are fine
        default_pattern = r"def.*thresholds\s*=\s*\[\d"
        defaults = re.findall(default_pattern, source)
        self.assertEqual(len(defaults), 0, f"Default thresholds in function: {defaults}")

    def test_no_sport_defaults_in_lead_ladder(self) -> None:
        """lead_ladder.py has no default thresholds."""
        import inspect
        from app.services import lead_ladder
        
        source = inspect.getsource(lead_ladder)
        
        # Should NOT have default thresholds
        self.assertNotIn("DEFAULT_THRESHOLDS", source)
        self.assertNotIn("default_thresholds", source)


class TestMultiSportLeadLadder(unittest.TestCase):
    """
    REGRESSION TESTS: Lead Ladder works for all sports.
    """

    def test_tier_progression_nba(self) -> None:
        """NBA tier progression is correct."""
        thresholds = [3, 6, 10, 16]
        
        # Verify tier boundaries
        self.assertEqual(get_lead_tier(2, thresholds), 0)
        self.assertEqual(get_lead_tier(3, thresholds), 1)
        self.assertEqual(get_lead_tier(5, thresholds), 1)
        self.assertEqual(get_lead_tier(6, thresholds), 2)
        self.assertEqual(get_lead_tier(9, thresholds), 2)
        self.assertEqual(get_lead_tier(10, thresholds), 3)
        self.assertEqual(get_lead_tier(15, thresholds), 3)
        self.assertEqual(get_lead_tier(16, thresholds), 4)

    def test_tier_progression_nhl(self) -> None:
        """NHL tier progression is correct (fewer tiers)."""
        thresholds = [1, 2, 3]
        
        self.assertEqual(get_lead_tier(0, thresholds), 0)
        self.assertEqual(get_lead_tier(1, thresholds), 1)
        self.assertEqual(get_lead_tier(2, thresholds), 2)
        self.assertEqual(get_lead_tier(3, thresholds), 3)
        self.assertEqual(get_lead_tier(10, thresholds), 3)  # Max

    def test_tier_progression_nfl(self) -> None:
        """NFL tier progression is correct (TD-based)."""
        # NFL: 1 TD = 7, 2 FG = 6, close games matter
        thresholds = [3, 7, 14, 21]
        
        self.assertEqual(get_lead_tier(0, thresholds), 0)   # Tied
        self.assertEqual(get_lead_tier(3, thresholds), 1)   # FG lead
        self.assertEqual(get_lead_tier(6, thresholds), 1)   # 2 FG
        self.assertEqual(get_lead_tier(7, thresholds), 2)   # TD lead
        self.assertEqual(get_lead_tier(14, thresholds), 3)  # 2 TD
        self.assertEqual(get_lead_tier(21, thresholds), 4)  # 3 TD

    def test_tier_progression_soccer(self) -> None:
        """Soccer tier progression is correct (low scores)."""
        thresholds = [1, 2, 3]
        
        self.assertEqual(get_lead_tier(0, thresholds), 0)
        self.assertEqual(get_lead_tier(1, thresholds), 1)
        self.assertEqual(get_lead_tier(2, thresholds), 2)
        self.assertEqual(get_lead_tier(3, thresholds), 3)


if __name__ == "__main__":
    unittest.main()
