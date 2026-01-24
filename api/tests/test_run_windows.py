"""Tests for run window detection logic."""

import pytest

from app.services.chapters.run_windows import (
    detect_run_windows,
    get_qualifying_run_windows,
    RunWindow,
)
from app.services.chapters.beat_types import (
    RUN_WINDOW_THRESHOLD,
    RUN_MARGIN_EXPANSION_THRESHOLD,
)


def _make_play(description: str, home_score: int, away_score: int) -> dict:
    """Helper to create a play dict."""
    return {
        "description": description,
        "home_score": home_score,
        "away_score": away_score,
    }


class TestDetectRunWindows:
    """Tests for detect_run_windows function."""

    def test_empty_plays_returns_empty(self):
        """Empty plays list returns no run windows."""
        assert detect_run_windows([]) == []

    def test_no_scoring_plays_returns_empty(self):
        """Non-scoring plays return no run windows."""
        plays = [
            _make_play("Turnover by Home", 10, 10),
            _make_play("Rebound by Away", 10, 10),
        ]
        assert detect_run_windows(plays) == []

    def test_chapter_starts_mid_game_no_spurious_run(self):
        """Chapter starting mid-game doesn't create spurious run from score delta.

        This tests the fix for initializing prev scores from first observed score
        rather than zero.
        """
        # Chapter starts at 45-42, first scoring play brings it to 47-42
        plays = [
            _make_play("Home makes layup", 47, 42),  # First scoring play
            _make_play("Home makes three", 50, 42),  # +3 more for home
        ]
        windows = detect_run_windows(plays)

        # Should NOT detect a run of 47 or 50 points
        # Should only see the 3-point delta from second play
        for w in windows:
            assert w.points_scored < 10, "Spurious run detected from mid-game start"

    def test_run_via_lead_change_qualifies(self):
        """Run that causes lead change qualifies as a beat."""
        # Away team leads 20-18, home goes on 8-0 run to take 26-20 lead
        plays = [
            _make_play("Away makes free throw", 18, 20),  # Baseline: away leads
            _make_play("Home makes three", 21, 20),  # +3, home takes lead
            _make_play("Home makes layup", 23, 20),  # +2 more
            _make_play("Home makes three", 26, 20),  # +3 more = 8 total
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 1
        run = windows[0]
        assert run.team == "home"
        assert run.points_scored == 8
        assert run.caused_lead_change is True
        assert run.is_qualifying() is True

    def test_run_via_margin_expansion_qualifies(self):
        """Run that expands margin by threshold qualifies even without lead change."""
        # Home already leads 30-25, goes on 10-0 run to lead 40-25
        plays = [
            _make_play("Home makes layup", 30, 25),  # Baseline: home leads by 5
            _make_play("Home makes three", 33, 25),  # +3
            _make_play("Home makes layup", 35, 25),  # +2
            _make_play("Home makes three", 38, 25),  # +3
            _make_play("Home makes layup", 40, 25),  # +2 = 10 total
        ]
        windows = detect_run_windows(plays)

        assert len(windows) == 1
        run = windows[0]
        assert run.team == "home"
        assert run.points_scored == 10
        assert run.margin_expansion == 10  # Margin went from 5 to 15
        assert run.caused_lead_change is False  # Home already led
        assert run.is_qualifying() is True  # Qualifies via margin expansion

    def test_run_terminates_when_opposing_team_scores(self):
        """Run ends correctly when opposing team scores."""
        plays = [
            _make_play("Home makes layup", 20, 18),  # Baseline
            _make_play("Home makes three", 23, 18),  # +3 home
            _make_play("Home makes layup", 25, 18),  # +2 home = 5 total
            _make_play("Away makes three", 25, 21),  # Away scores - ends run
            _make_play("Home makes layup", 27, 21),  # New potential run starts
        ]
        windows = detect_run_windows(plays)

        # First run was only 5 points (below threshold), shouldn't be recorded
        # No qualifying windows since neither run hit threshold
        for w in windows:
            # If any windows exist, they should have correct termination
            assert w.end_play_index < 4 or w.start_play_index >= 4

    def test_run_below_threshold_not_recorded(self):
        """Runs below threshold are not recorded."""
        plays = [
            _make_play("Home makes layup", 20, 18),  # Baseline
            _make_play("Home makes three", 23, 18),  # +3
            _make_play("Away makes layup", 23, 20),  # Away scores after only 3 pts
        ]
        windows = detect_run_windows(plays)
        assert len(windows) == 0

    def test_run_exactly_at_threshold_recorded(self):
        """Run exactly at threshold is recorded."""
        plays = [
            _make_play("Home makes layup", 20, 18),  # Baseline
            _make_play("Home makes three", 23, 18),  # +3
            _make_play("Home makes three", 26, 18),  # +3 = 6 total (at threshold)
        ]
        windows = detect_run_windows(plays)
        assert len(windows) == 1
        assert windows[0].points_scored == RUN_WINDOW_THRESHOLD

    def test_run_at_chapter_end_recorded(self):
        """Run in progress at chapter end is finalized if at threshold."""
        plays = [
            _make_play("Home makes layup", 20, 18),  # Baseline
            _make_play("Away makes three", 20, 21),  # +3 away
            _make_play("Away makes three", 20, 24),  # +3 more = 6 total
            # Chapter ends with away run in progress
        ]
        windows = detect_run_windows(plays)
        assert len(windows) == 1
        assert windows[0].team == "away"
        assert windows[0].points_scored == 6


class TestGetQualifyingRunWindows:
    """Tests for get_qualifying_run_windows function."""

    def test_filters_non_qualifying_runs(self):
        """Only returns runs that qualify via lead change or margin expansion."""
        # Create a run that hits threshold but doesn't qualify
        # (no lead change, margin expansion < 8)
        plays = [
            _make_play("Home makes layup", 50, 30),  # Baseline: home leads by 20
            _make_play("Home makes three", 53, 30),  # +3
            _make_play("Home makes three", 56, 30),  # +3 = 6 total
        ]
        windows = detect_run_windows(plays)
        qualifying = get_qualifying_run_windows(plays)

        # Run detected but margin expansion only 6, no lead change
        assert len(windows) == 1
        assert windows[0].margin_expansion == 6
        assert windows[0].caused_lead_change is False
        assert len(qualifying) == 0  # Doesn't qualify

    def test_returns_qualifying_runs(self):
        """Returns runs that meet qualifying criteria."""
        # Create a run that causes lead change
        plays = [
            _make_play("Away makes layup", 18, 20),  # Baseline: away leads
            _make_play("Home makes three", 21, 20),  # +3, lead change
            _make_play("Home makes three", 24, 20),  # +3 = 6 total
        ]
        qualifying = get_qualifying_run_windows(plays)

        assert len(qualifying) == 1
        assert qualifying[0].caused_lead_change is True
