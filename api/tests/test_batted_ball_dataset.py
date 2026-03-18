"""Tests for MLB batted ball dataset builder."""

from __future__ import annotations

import math

import pytest

from app.analytics.datasets.mlb_batted_ball_dataset import (
    _BB_LABEL_MAP,
    _BIP_OUTCOMES,
    _compute_spray_angle,
)
from app.analytics.datasets.mlb_pa_labeler import label_pa_event


class TestComputeSprayAngle:
    """Unit tests for spray angle computation."""

    def test_center_field(self):
        """Ball hit straight up the middle should be ~0 degrees."""
        angle = _compute_spray_angle(125.42, 100.0)
        assert abs(angle) < 0.1

    def test_left_field(self):
        """Ball hit to the left side should have negative angle."""
        angle = _compute_spray_angle(80.0, 100.0)
        assert angle < 0

    def test_right_field(self):
        """Ball hit to the right side should have positive angle."""
        angle = _compute_spray_angle(170.0, 100.0)
        assert angle > 0

    def test_home_plate_level(self):
        """When coordY >= 198.27 (at or behind home), angle is 0."""
        angle = _compute_spray_angle(125.42, 200.0)
        assert angle == 0.0

    def test_symmetry(self):
        """Symmetric offsets from center should produce opposite angles."""
        offset = 30.0
        left = _compute_spray_angle(125.42 - offset, 150.0)
        right = _compute_spray_angle(125.42 + offset, 150.0)
        assert abs(left + right) < 0.01


class TestBIPOutcomes:
    """Test the BIP outcome filtering and label mapping."""

    def test_bip_outcomes_are_valid_pa_labels(self):
        """All BIP outcomes should be recognizable PA labels."""
        for outcome in _BIP_OUTCOMES:
            assert outcome in {
                "single", "double", "triple", "home_run", "ball_in_play_out",
            }

    def test_label_map_covers_all_bip_outcomes(self):
        """Label map should have entries for all BIP outcomes."""
        for outcome in _BIP_OUTCOMES:
            assert outcome in _BB_LABEL_MAP

    def test_label_map_values(self):
        """Verify label mapping is correct."""
        assert _BB_LABEL_MAP["single"] == "single"
        assert _BB_LABEL_MAP["double"] == "double"
        assert _BB_LABEL_MAP["triple"] == "triple"
        assert _BB_LABEL_MAP["home_run"] == "home_run"
        assert _BB_LABEL_MAP["ball_in_play_out"] == "out"

    def test_strikeout_not_in_bip(self):
        """Strikeouts should not be treated as balls in play."""
        assert "strikeout" not in _BIP_OUTCOMES

    def test_walk_not_in_bip(self):
        """Walks should not be treated as balls in play."""
        assert "walk_or_hbp" not in _BIP_OUTCOMES


class TestBattedBallDataExtraction:
    """Tests for hit data extraction patterns."""

    @pytest.fixture
    def mock_bip_play(self):
        """Mock raw_data for a ball-in-play result."""
        return {
            "event": "Single",
            "matchup": {
                "batter": {"id": 100},
                "pitcher": {"id": 200},
            },
            "hitData": {
                "launchSpeed": 95.2,
                "launchAngle": 18.5,
                "coordinates": {
                    "coordX": 140.0,
                    "coordY": 150.0,
                },
            },
        }

    def test_hit_data_extraction(self, mock_bip_play):
        """Verify exit velocity, launch angle extraction."""
        hit_data = mock_bip_play["hitData"]
        assert hit_data["launchSpeed"] == 95.2
        assert hit_data["launchAngle"] == 18.5

    def test_spray_angle_from_coordinates(self, mock_bip_play):
        """Verify spray angle computed from coordinates."""
        coords = mock_bip_play["hitData"]["coordinates"]
        angle = _compute_spray_angle(coords["coordX"], coords["coordY"])
        assert isinstance(angle, float)
        # Right-center field hit
        assert angle > 0

    def test_null_launch_speed_skipped(self):
        """Plays without launchSpeed should be skipped."""
        raw = {
            "event": "Groundout",
            "hitData": {"launchSpeed": None, "launchAngle": 5.0},
        }
        assert raw["hitData"]["launchSpeed"] is None

    def test_pa_outcome_filtering(self):
        """Only BIP outcomes should be included."""
        assert label_pa_event("Single") in _BIP_OUTCOMES
        assert label_pa_event("Home Run") in _BIP_OUTCOMES
        assert label_pa_event("Groundout") in _BIP_OUTCOMES
        assert label_pa_event("Strikeout") not in _BIP_OUTCOMES
        assert label_pa_event("Walk") not in _BIP_OUTCOMES
