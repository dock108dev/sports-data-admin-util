"""Tests for soft-capped moment compression (Task 1.1).

These tests verify:
1. Hard boundary conditions always force closure
2. Soft boundary conditions prefer but don't force closure
3. Merge eligibility can override soft conditions
4. Distribution metrics are tracked correctly
5. Max 2 explicitly narrated plays per moment
"""

import pytest


class TestLeadChangeDetection:
    """Tests for lead change detection."""

    def test_lead_change_home_to_away(self):
        """Lead change when home lead becomes away lead."""
        from app.services.pipeline.stages.generate_moments import _is_lead_change

        # Home leading 50-45, then Away leading 50-52
        assert _is_lead_change(50, 45, 50, 52) is True

    def test_lead_change_away_to_home(self):
        """Lead change when away lead becomes home lead."""
        from app.services.pipeline.stages.generate_moments import _is_lead_change

        # Away leading 45-50, then Home leading 52-50
        assert _is_lead_change(45, 50, 52, 50) is True

    def test_no_lead_change_tie_to_lead(self):
        """Going from tied to a lead is NOT a lead change."""
        from app.services.pipeline.stages.generate_moments import _is_lead_change

        # Tied 50-50, then Home leads 52-50
        assert _is_lead_change(50, 50, 52, 50) is False

    def test_no_lead_change_lead_to_tie(self):
        """Going from a lead to tied is NOT a lead change."""
        from app.services.pipeline.stages.generate_moments import _is_lead_change

        # Home leading 52-50, then Tied 52-52
        assert _is_lead_change(52, 50, 52, 52) is False

    def test_no_lead_change_same_leader(self):
        """No change when same team continues leading."""
        from app.services.pipeline.stages.generate_moments import _is_lead_change

        # Home leading 50-45, still leading 52-45
        assert _is_lead_change(50, 45, 52, 45) is False


class TestHardBoundaryConditions:
    """Tests for hard (non-negotiable) boundary conditions."""

    def test_absolute_max_plays_forces_closure(self):
        """ABSOLUTE_MAX_PLAYS reached must force closure."""
        from app.services.pipeline.stages.generate_moments import (
            _should_force_close_moment,
            ABSOLUTE_MAX_PLAYS,
            BoundaryReason,
        )

        # Create moment with ABSOLUTE_MAX_PLAYS plays
        plays = [{"play_index": i, "home_score": 0, "away_score": 0} for i in range(ABSOLUTE_MAX_PLAYS)]
        current_event = plays[-1]
        previous_event = plays[-2] if len(plays) > 1 else None

        should_close, reason = _should_force_close_moment(
            plays, current_event, previous_event, plays, 0
        )

        assert should_close is True
        assert reason == BoundaryReason.ABSOLUTE_MAX_PLAYS

    def test_lead_change_forces_closure(self):
        """Lead change must force closure."""
        from app.services.pipeline.stages.generate_moments import (
            _should_force_close_moment,
            BoundaryReason,
        )

        # Home was leading 50-45, now Away leads 50-52
        plays = [
            {"play_index": 1, "home_score": 50, "away_score": 45},
            {"play_index": 2, "home_score": 50, "away_score": 52},
        ]
        current_event = plays[1]
        previous_event = plays[0]

        should_close, reason = _should_force_close_moment(
            plays, current_event, previous_event, plays, 0
        )

        assert should_close is True
        assert reason == BoundaryReason.LEAD_CHANGE


class TestSoftBoundaryConditions:
    """Tests for soft (prefer closing) boundary conditions."""

    def test_soft_cap_prefers_closure(self):
        """SOFT_CAP_PLAYS reached should prefer closure."""
        from app.services.pipeline.stages.generate_moments import (
            _should_prefer_close_moment,
            SOFT_CAP_PLAYS,
            BoundaryReason,
        )

        # Create moment with SOFT_CAP_PLAYS plays
        plays = [{"play_index": i, "home_score": 0, "away_score": 0, "description": ""} for i in range(SOFT_CAP_PLAYS)]
        current_event = plays[-1]
        previous_event = plays[-2] if len(plays) > 1 else None

        should_close, reason = _should_prefer_close_moment(
            plays, current_event, previous_event, plays, 0
        )

        assert should_close is True
        assert reason == BoundaryReason.SOFT_CAP_REACHED

    def test_scoring_play_prefers_closure(self):
        """Scoring play should prefer closure."""
        from app.services.pipeline.stages.generate_moments import (
            _should_prefer_close_moment,
            BoundaryReason,
        )

        plays = [
            {"play_index": 1, "home_score": 50, "away_score": 45, "description": ""},
            {"play_index": 2, "home_score": 52, "away_score": 45, "description": ""},  # Scoring!
        ]
        current_event = plays[1]
        previous_event = plays[0]

        should_close, reason = _should_prefer_close_moment(
            plays, current_event, previous_event, plays, 0
        )

        assert should_close is True
        assert reason == BoundaryReason.SCORING_PLAY

    def test_stoppage_prefers_closure(self):
        """Stoppage (timeout) should prefer closure."""
        from app.services.pipeline.stages.generate_moments import (
            _should_prefer_close_moment,
            BoundaryReason,
        )

        plays = [
            {"play_index": 1, "home_score": 50, "away_score": 45, "play_type": "timeout", "description": ""},
        ]
        current_event = plays[0]

        should_close, reason = _should_prefer_close_moment(
            plays, current_event, None, plays, 0
        )

        assert should_close is True
        assert reason == BoundaryReason.STOPPAGE


class TestMergeEligibility:
    """Tests for merge eligibility logic."""

    def test_merge_eligible_when_no_scoring(self):
        """Merge should be eligible when no scoring in moment."""
        from app.services.pipeline.stages.generate_moments import _is_merge_eligible

        plays = [
            {"play_index": 1, "home_score": 50, "away_score": 45, "quarter": 1},
            {"play_index": 2, "home_score": 50, "away_score": 45, "quarter": 1},  # No score change
        ]
        current = plays[1]
        previous = plays[0]
        next_event = {"play_index": 3, "quarter": 1}

        is_eligible = _is_merge_eligible(plays, current, previous, next_event)
        assert is_eligible is True

    def test_not_merge_eligible_after_scoring(self):
        """Merge should not be eligible after scoring occurred."""
        from app.services.pipeline.stages.generate_moments import _is_merge_eligible

        plays = [
            {"play_index": 1, "home_score": 50, "away_score": 45, "quarter": 1},
            {"play_index": 2, "home_score": 52, "away_score": 45, "quarter": 1},  # Scoring!
        ]
        current = plays[1]
        previous = plays[0]
        next_event = {"play_index": 3, "quarter": 1}

        is_eligible = _is_merge_eligible(plays, current, previous, next_event)
        assert is_eligible is False


class TestExplicitPlayConstraints:
    """Tests for explicitly narrated play constraints."""

    def test_max_two_explicit_plays(self):
        """Select at most MAX_EXPLICIT_PLAYS_PER_MOMENT explicitly narrated plays."""
        from app.services.pipeline.stages.generate_moments import (
            _select_explicitly_narrated_plays,
            MAX_EXPLICIT_PLAYS_PER_MOMENT,
        )

        # Create moment with multiple scoring plays
        plays = [
            {"play_index": 1, "home_score": 2, "away_score": 0},
            {"play_index": 2, "home_score": 4, "away_score": 0},
            {"play_index": 3, "home_score": 6, "away_score": 0},
            {"play_index": 4, "home_score": 8, "away_score": 0},
        ]
        all_events = plays

        narrated = _select_explicitly_narrated_plays(plays, all_events, 0)

        assert len(narrated) <= MAX_EXPLICIT_PLAYS_PER_MOMENT
        assert len(narrated) == 2  # Should be exactly 2 since we have many scoring plays

    def test_at_least_one_explicit_play(self):
        """Every moment must have at least one explicitly narrated play."""
        from app.services.pipeline.stages.generate_moments import (
            _select_explicitly_narrated_plays,
        )

        # Create moment with no scoring or notable plays
        plays = [
            {"play_index": 1, "home_score": 50, "away_score": 45, "play_type": ""},
            {"play_index": 2, "home_score": 50, "away_score": 45, "play_type": ""},
        ]
        all_events = plays

        narrated = _select_explicitly_narrated_plays(plays, all_events, 0)

        assert len(narrated) >= 1


class TestCompressionMetrics:
    """Tests for compression metrics tracking."""

    def test_metrics_initialization(self):
        """CompressionMetrics should initialize with correct defaults."""
        from app.services.pipeline.stages.generate_moments import CompressionMetrics

        metrics = CompressionMetrics()

        assert metrics.total_moments == 0
        assert metrics.total_plays == 0
        assert metrics.plays_per_moment == []
        assert metrics.explicit_plays_per_moment == []

    def test_metrics_percentages(self):
        """Metrics should calculate percentages correctly."""
        from app.services.pipeline.stages.generate_moments import (
            CompressionMetrics,
            SOFT_CAP_PLAYS,
        )

        metrics = CompressionMetrics()
        # 8 moments with varying play counts
        metrics.plays_per_moment = [3, 5, 7, 8, 9, 10, 4, 6]  # 6 under soft cap
        metrics.explicit_plays_per_moment = [1, 1, 1, 2, 1, 1, 1, 1]  # 7 with ≤1

        # 6/8 = 75% under soft cap (assuming SOFT_CAP=8)
        assert 70 <= metrics.pct_moments_under_soft_cap <= 80  # Allow for SOFT_CAP variations

        # 7/8 = 87.5% with single explicit
        assert metrics.pct_moments_single_explicit == 87.5

    def test_metrics_median(self):
        """Median should be calculated correctly."""
        from app.services.pipeline.stages.generate_moments import CompressionMetrics

        metrics = CompressionMetrics()
        metrics.plays_per_moment = [1, 2, 3, 4, 5, 6, 7, 8, 9]  # Odd count

        assert metrics.median_plays_per_moment == 5.0

        metrics.plays_per_moment = [1, 2, 3, 4, 5, 6, 7, 8]  # Even count
        assert metrics.median_plays_per_moment == 4.5


class TestSegmentationIntegration:
    """Integration tests for the full segmentation process."""

    def test_no_cross_period_moments(self):
        """Moments should never span across periods."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        # Create events spanning two periods
        events = [
            {"play_index": 1, "quarter": 1, "home_score": 10, "away_score": 8, "description": "", "play_type": ""},
            {"play_index": 2, "quarter": 1, "home_score": 10, "away_score": 8, "description": "", "play_type": ""},
            {"play_index": 3, "quarter": 2, "home_score": 10, "away_score": 8, "description": "", "play_type": ""},  # New period!
            {"play_index": 4, "quarter": 2, "home_score": 12, "away_score": 8, "description": "", "play_type": ""},
        ]

        moments, metrics = _segment_plays_into_moments(events)

        # Check no moment contains plays from different periods
        for moment in moments:
            play_ids = moment["play_ids"]
            periods = set()
            for pid in play_ids:
                for e in events:
                    if e["play_index"] == pid:
                        periods.add(e["quarter"])
            assert len(periods) == 1, f"Moment spans multiple periods: {periods}"

    def test_full_play_coverage(self):
        """All plays must be covered exactly once."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "home_score": i * 2, "away_score": i, "description": "", "play_type": ""}
            for i in range(1, 21)
        ]

        moments, metrics = _segment_plays_into_moments(events)

        # Collect all play_ids from moments
        moment_play_ids = set()
        for moment in moments:
            for pid in moment["play_ids"]:
                assert pid not in moment_play_ids, f"Play {pid} appears multiple times"
                moment_play_ids.add(pid)

        # Check coverage
        expected_ids = {e["play_index"] for e in events}
        assert moment_play_ids == expected_ids

    def test_moments_ordered_correctly(self):
        """Moments should be ordered by first play index."""
        from app.services.pipeline.stages.generate_moments import (
            _segment_plays_into_moments,
        )

        events = [
            {"play_index": i, "quarter": 1, "home_score": i * 2, "away_score": i, "description": "", "play_type": ""}
            for i in range(1, 21)
        ]

        moments, metrics = _segment_plays_into_moments(events)

        prev_first_play = -1
        for moment in moments:
            first_play = moment["play_ids"][0]
            assert first_play > prev_first_play
            prev_first_play = first_play
