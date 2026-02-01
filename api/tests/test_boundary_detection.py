"""Tests for boundary_detection stage."""


def make_event(
    play_index: int,
    home_score: int = 0,
    away_score: int = 0,
    quarter: int = 1,
    play_type: str = "other",
    description: str = "",
) -> dict:
    """Helper to create a PBP event."""
    return {
        "play_index": play_index,
        "home_score": home_score,
        "away_score": away_score,
        "quarter": quarter,
        "play_type": play_type,
        "description": description,
    }


class TestShouldForceCloseMoment:
    """Tests for should_force_close_moment (HARD boundaries)."""

    def test_absolute_max_plays_forces_close(self):
        """Reaching ABSOLUTE_MAX_PLAYS forces closure."""
        from app.services.pipeline.stages.boundary_detection import (
            should_force_close_moment,
        )
        from app.services.pipeline.stages.moment_types import BoundaryReason

        # ABSOLUTE_MAX_PLAYS is 50
        plays = [make_event(i) for i in range(50)]
        current = plays[-1]
        prev = plays[-2]
        all_events = plays

        should_close, reason = should_force_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is True
        assert reason == BoundaryReason.ABSOLUTE_MAX_PLAYS

    def test_lead_change_forces_close(self):
        """Lead change forces closure."""
        from app.services.pipeline.stages.boundary_detection import (
            should_force_close_moment,
        )
        from app.services.pipeline.stages.moment_types import BoundaryReason

        prev = make_event(1, home_score=10, away_score=5)
        current = make_event(2, home_score=10, away_score=15)
        plays = [prev, current]
        all_events = plays

        should_close, reason = should_force_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is True
        assert reason == BoundaryReason.LEAD_CHANGE

    def test_normal_play_no_force_close(self):
        """Normal play doesn't force closure."""
        from app.services.pipeline.stages.boundary_detection import (
            should_force_close_moment,
        )

        prev = make_event(1, home_score=10, away_score=5)
        current = make_event(2, home_score=12, away_score=5)
        plays = [prev, current]
        all_events = plays

        should_close, reason = should_force_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is False
        assert reason is None

    def test_first_play_no_lead_change(self):
        """First play (no previous) cannot be a lead change."""
        from app.services.pipeline.stages.boundary_detection import (
            should_force_close_moment,
        )

        current = make_event(1, home_score=10, away_score=5)
        plays = [current]
        all_events = plays

        should_close, reason = should_force_close_moment(
            plays, current, None, all_events, 0
        )
        assert should_close is False


class TestShouldPreferCloseMoment:
    """Tests for should_prefer_close_moment (SOFT boundaries)."""

    def test_soft_cap_prefers_close(self):
        """Reaching SOFT_CAP_PLAYS prefers closure."""
        from app.services.pipeline.stages.boundary_detection import (
            should_prefer_close_moment,
        )
        from app.services.pipeline.stages.moment_types import BoundaryReason

        # SOFT_CAP_PLAYS is 30
        plays = [make_event(i) for i in range(30)]
        current = plays[-1]
        prev = plays[-2]
        all_events = plays

        should_close, reason = should_prefer_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is True
        assert reason == BoundaryReason.SOFT_CAP_REACHED

    def test_scoring_play_prefers_close(self):
        """Scoring play prefers closure after 2/3 of soft cap (~20 plays)."""
        from app.services.pipeline.stages.boundary_detection import (
            should_prefer_close_moment,
        )
        from app.services.pipeline.stages.moment_types import BoundaryReason

        # Need 20+ plays (2/3 of SOFT_CAP=30) for scoring play to trigger close
        plays = [make_event(i, home_score=10, away_score=5) for i in range(20)]
        current = make_event(20, home_score=12, away_score=5)  # Scoring play
        plays.append(current)
        prev = plays[-2]
        all_events = plays

        should_close, reason = should_prefer_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is True
        assert reason == BoundaryReason.SCORING_PLAY

    def test_stoppage_prefers_close(self):
        """Stoppage play prefers closure after MIN_PLAYS_BEFORE_SOFT_CLOSE (15 plays)."""
        from app.services.pipeline.stages.boundary_detection import (
            should_prefer_close_moment,
        )
        from app.services.pipeline.stages.moment_types import BoundaryReason

        # Need 15+ plays (MIN_PLAYS_BEFORE_SOFT_CLOSE) for stoppage to trigger close
        plays = [make_event(i) for i in range(15)]
        current = make_event(15, play_type="timeout")
        plays.append(current)
        prev = plays[-2]
        all_events = plays

        should_close, reason = should_prefer_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is True
        assert reason == BoundaryReason.STOPPAGE

    def test_turnover_prefers_close(self):
        """Turnover play prefers closure after half of soft cap (15 plays)."""
        from app.services.pipeline.stages.boundary_detection import (
            should_prefer_close_moment,
        )
        from app.services.pipeline.stages.moment_types import BoundaryReason

        # Need 15+ plays (half of SOFT_CAP=30) for turnover to trigger close
        plays = [make_event(i) for i in range(15)]
        current = make_event(15, play_type="turnover")
        plays.append(current)
        prev = plays[-2]
        all_events = plays

        should_close, reason = should_prefer_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is True
        assert reason == BoundaryReason.POSSESSION_CHANGE

    def test_normal_play_no_prefer_close(self):
        """Normal play doesn't prefer closure."""
        from app.services.pipeline.stages.boundary_detection import (
            should_prefer_close_moment,
        )

        prev = make_event(1, home_score=10, away_score=5)
        current = make_event(2, home_score=10, away_score=5)
        plays = [prev, current]
        all_events = plays

        should_close, reason = should_prefer_close_moment(
            plays, current, prev, all_events, 0
        )
        assert should_close is False
        assert reason is None


class TestIsMergeEligible:
    """Tests for is_merge_eligible function."""

    def test_merge_eligible_same_period_no_scoring(self):
        """Merge eligible when same period and no scoring."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        plays = [
            make_event(1, home_score=0, away_score=0, quarter=1),
            make_event(2, home_score=0, away_score=0, quarter=1),
        ]
        current = plays[-1]
        prev = plays[-2]
        next_event = make_event(3, quarter=1)

        assert is_merge_eligible(plays, current, prev, next_event) is True

    def test_small_moment_merge_eligible_despite_scoring(self):
        """Small moments (< MIN_PLAYS_BEFORE_SOFT_CLOSE) merge even with scoring."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        # Only 2 plays - small moment should still be eligible to merge
        plays = [
            make_event(1, home_score=0, away_score=0, quarter=1),
            make_event(2, home_score=2, away_score=0, quarter=1),  # Scoring
        ]
        current = plays[-1]
        prev = plays[-2]
        next_event = make_event(3, quarter=1)

        # Small moments merge regardless of scoring to avoid tiny 1-2 play moments
        assert is_merge_eligible(plays, current, prev, next_event) is True

    def test_not_merge_eligible_scoring_in_large_moment(self):
        """Not merge eligible when significant scoring in larger moment (20+ plays, 4+ scores, 10+ pts)."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        # 20+ plays with 4+ scoring plays and 10+ points - should NOT be eligible
        plays = [
            make_event(1, home_score=0, away_score=0, quarter=1),
            make_event(2, home_score=0, away_score=0, quarter=1),
            make_event(3, home_score=3, away_score=0, quarter=1),  # Scoring +3
            make_event(4, home_score=3, away_score=0, quarter=1),
            make_event(5, home_score=5, away_score=0, quarter=1),  # Scoring +2
            make_event(6, home_score=5, away_score=0, quarter=1),
            make_event(7, home_score=5, away_score=0, quarter=1),
            make_event(8, home_score=8, away_score=0, quarter=1),  # Scoring +3
            make_event(9, home_score=8, away_score=0, quarter=1),
            make_event(10, home_score=8, away_score=0, quarter=1),
            make_event(11, home_score=8, away_score=0, quarter=1),
            make_event(12, home_score=8, away_score=0, quarter=1),
            make_event(13, home_score=8, away_score=0, quarter=1),
            make_event(14, home_score=8, away_score=0, quarter=1),
            make_event(15, home_score=8, away_score=0, quarter=1),
            make_event(16, home_score=8, away_score=0, quarter=1),
            make_event(17, home_score=8, away_score=0, quarter=1),
            make_event(18, home_score=8, away_score=0, quarter=1),
            make_event(19, home_score=8, away_score=0, quarter=1),
            make_event(20, home_score=11, away_score=0, quarter=1),  # Scoring +3, total 11pts
        ]
        current = plays[-1]
        prev = plays[-2]
        next_event = make_event(21, quarter=1)

        assert is_merge_eligible(plays, current, prev, next_event) is False

    def test_not_merge_eligible_period_change(self):
        """Not merge eligible when next event is different period."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        plays = [
            make_event(1, home_score=0, away_score=0, quarter=1),
            make_event(2, home_score=0, away_score=0, quarter=1),
        ]
        current = plays[-1]
        prev = plays[-2]
        next_event = make_event(3, quarter=2)  # Different period

        assert is_merge_eligible(plays, current, prev, next_event) is False

    def test_not_merge_eligible_no_next_event(self):
        """Not merge eligible when no next event."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        plays = [
            make_event(1, home_score=0, away_score=0, quarter=1),
            make_event(2, home_score=0, away_score=0, quarter=1),
        ]
        current = plays[-1]
        prev = plays[-2]

        assert is_merge_eligible(plays, current, prev, None) is False

    def test_single_play_merge_eligible(self):
        """Single play moment can be merge eligible."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        plays = [make_event(1, home_score=0, away_score=0, quarter=1)]
        current = plays[0]
        next_event = make_event(2, quarter=1)

        assert is_merge_eligible(plays, current, None, next_event) is True

    def test_large_moment_no_next_event(self):
        """Large moment without next event is not merge eligible."""
        from app.services.pipeline.stages.boundary_detection import is_merge_eligible

        # 5+ plays, no scoring, but no next event
        plays = [make_event(i, quarter=1) for i in range(6)]
        current = plays[-1]
        prev = plays[-2]

        assert is_merge_eligible(plays, current, prev, None) is False
