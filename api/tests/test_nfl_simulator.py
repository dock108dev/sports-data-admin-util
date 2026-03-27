"""Tests for the NFL drive-based game simulator."""

from __future__ import annotations

import random

import pytest

from app.analytics.sports.nfl.game_simulator import (
    NFLGameSimulator,
    _build_weights,
    _resolve_drive,
    _new_event_counts,
)


class TestBuildWeights:
    """Verify drive outcome weight construction."""

    def test_default_weights_sum_to_one(self):
        w = _build_weights({})
        assert abs(sum(w) - 1.0) < 0.01

    def test_custom_weights_sum_to_one(self):
        probs = {
            "touchdown_probability": 0.30,
            "field_goal_probability": 0.15,
            "turnover_probability": 0.10,
            "turnover_on_downs_probability": 0.05,
        }
        w = _build_weights(probs)
        assert abs(sum(w) - 1.0) < 0.01
        # Punt absorbs remainder
        assert w[2] == pytest.approx(0.40, abs=0.01)

    def test_order_matches_sample_outcomes(self):
        probs = {
            "touchdown_probability": 0.25,
            "field_goal_probability": 0.12,
            "turnover_probability": 0.11,
            "turnover_on_downs_probability": 0.04,
        }
        w = _build_weights(probs)
        # Order: td, fg, punt, turnover, turnover_on_downs
        assert w[0] == 0.25  # td
        assert w[1] == 0.12  # fg
        assert w[3] == 0.11  # turnover
        assert w[4] == 0.04  # downs


class TestResolveDrive:
    """Verify individual drive scoring."""

    def test_touchdown_scores_six_or_seven(self):
        rng = random.Random(42)
        events = _new_event_counts()
        # All weight on touchdown
        weights = [1.0, 0.0, 0.0, 0.0, 0.0]
        points = _resolve_drive(weights, rng, events, 0.94, 0.85)
        assert points in (6, 7, 8)
        assert events["touchdown"] == 1

    def test_field_goal_scores_zero_or_three(self):
        rng = random.Random(42)
        events = _new_event_counts()
        weights = [0.0, 1.0, 0.0, 0.0, 0.0]
        points = _resolve_drive(weights, rng, events, 0.94, 1.0)
        assert points == 3
        assert events["field_goal"] == 1

    def test_punt_scores_zero(self):
        rng = random.Random(42)
        events = _new_event_counts()
        weights = [0.0, 0.0, 1.0, 0.0, 0.0]
        points = _resolve_drive(weights, rng, events, 0.94, 0.85)
        assert points == 0
        assert events["punt"] == 1

    def test_turnover_scores_zero(self):
        rng = random.Random(42)
        events = _new_event_counts()
        weights = [0.0, 0.0, 0.0, 1.0, 0.0]
        points = _resolve_drive(weights, rng, events, 0.94, 0.85)
        assert points == 0
        assert events["turnover"] == 1


class TestNFLGameSimulator:
    """Verify full game simulation."""

    def test_deterministic_with_seed(self):
        sim = NFLGameSimulator()
        ctx = {"home_probabilities": {}, "away_probabilities": {}}
        r1 = sim.simulate_game(ctx, random.Random(99))
        r2 = sim.simulate_game(ctx, random.Random(99))
        assert r1["home_score"] == r2["home_score"]
        assert r1["away_score"] == r2["away_score"]

    def test_realistic_score_range(self):
        sim = NFLGameSimulator()
        ctx = {"home_probabilities": {}, "away_probabilities": {}}
        scores = []
        for i in range(50):
            r = sim.simulate_game(ctx, random.Random(i))
            scores.append(r["home_score"] + r["away_score"])
        avg = sum(scores) / len(scores)
        # Real NFL avg total is ~44-48
        assert 35 < avg < 55

    def test_winner_always_set(self):
        sim = NFLGameSimulator()
        ctx = {"home_probabilities": {}, "away_probabilities": {}}
        for i in range(20):
            r = sim.simulate_game(ctx, random.Random(i))
            assert r["winner"] in ("home", "away")

    def test_events_tracked(self):
        sim = NFLGameSimulator()
        ctx = {"home_probabilities": {}, "away_probabilities": {}}
        r = sim.simulate_game(ctx, random.Random(42))
        assert r["home_events"]["drives_total"] > 0
        assert r["away_events"]["drives_total"] > 0

    def test_overtime_possible(self):
        sim = NFLGameSimulator()
        ctx = {"home_probabilities": {}, "away_probabilities": {}}
        ot_found = False
        for i in range(200):
            r = sim.simulate_game(ctx, random.Random(i))
            if r["went_to_overtime"]:
                ot_found = True
                assert r["periods_played"] == 5
                break
        # OT should happen at least once in 200 sims
        assert ot_found

    def test_lineup_mode_with_drive_weights(self):
        sim = NFLGameSimulator()
        ctx = {
            "home_drive_weights": [0.28, 0.14, 0.38, 0.10, 0.03],
            "away_drive_weights": [0.18, 0.10, 0.50, 0.15, 0.05],
            "home_xp_pct": 0.95,
            "away_xp_pct": 0.93,
            "home_fg_pct": 0.88,
            "away_fg_pct": 0.82,
        }
        r = sim.simulate_game_with_lineups(ctx, random.Random(42))
        assert r["home_score"] > 0 or r["away_score"] > 0
        # Strong offense should outscore weak offense on average
        scores = {"home": 0, "away": 0}
        for i in range(100):
            r = sim.simulate_game_with_lineups(ctx, random.Random(i))
            scores["home"] += r["home_score"]
            scores["away"] += r["away_score"]
        assert scores["home"] > scores["away"]

    def test_lineup_mode_fallback_without_weights(self):
        sim = NFLGameSimulator()
        ctx = {"home_probabilities": {}, "away_probabilities": {}}
        r = sim.simulate_game_with_lineups(ctx, random.Random(42))
        assert "home_score" in r
        assert "away_score" in r
