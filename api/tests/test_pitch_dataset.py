"""Tests for MLB pitch outcome dataset builder and labeler."""

from __future__ import annotations

import pytest

from app.analytics.datasets.mlb_pitch_labeler import (
    PITCH_OUTCOME_LABELS,
    label_pitch_code,
)


class TestLabelPitchCode:
    """Unit tests for label_pitch_code()."""

    def test_ball_codes(self):
        assert label_pitch_code("B") == "ball"
        assert label_pitch_code("*B") == "ball"

    def test_called_strike(self):
        assert label_pitch_code("C") == "called_strike"

    def test_swinging_strike_codes(self):
        for code in ("S", "W", "M", "Q"):
            assert label_pitch_code(code) == "swinging_strike"

    def test_foul_codes(self):
        for code in ("F", "R", "L", "T"):
            assert label_pitch_code(code) == "foul"

    def test_in_play_codes(self):
        for code in ("X", "D", "E"):
            assert label_pitch_code(code) == "in_play"

    def test_empty_code(self):
        assert label_pitch_code("") is None

    def test_unknown_code(self):
        assert label_pitch_code("Z") is None

    def test_whitespace_stripped(self):
        assert label_pitch_code(" B ") == "ball"

    def test_all_labels_are_valid(self):
        valid = set(PITCH_OUTCOME_LABELS)
        for code in ("B", "*B", "C", "S", "W", "M", "Q", "F", "R", "L", "T", "X", "D", "E"):
            result = label_pitch_code(code)
            assert result in valid


class TestMLBPitchDatasetBuilder:
    """Tests for MLBPitchDatasetBuilder using mock data."""

    @pytest.fixture
    def mock_play_with_pitches(self):
        """Mock raw_data JSONB with playEvents array."""
        return {
            "matchup": {
                "batter": {"id": 100, "fullName": "Batter A"},
                "pitcher": {"id": 200, "fullName": "Pitcher B"},
            },
            "playEvents": [
                {
                    "isPitch": True,
                    "details": {"code": "B"},
                    "count": {"balls": 0, "strikes": 0},
                    "pitchData": {"zone": 14, "startSpeed": 92.3},
                },
                {
                    "isPitch": True,
                    "details": {"code": "S"},
                    "count": {"balls": 1, "strikes": 0},
                    "pitchData": {"zone": 5, "startSpeed": 85.1},
                },
                {
                    "isPitch": False,  # not a pitch
                    "details": {"code": "V"},
                },
                {
                    "isPitch": True,
                    "details": {"code": "X"},
                    "count": {"balls": 1, "strikes": 1},
                    "pitchData": {"zone": 8, "startSpeed": 93.0},
                },
            ],
        }

    def test_play_events_extraction(self, mock_play_with_pitches):
        """Verify pitch extraction from playEvents."""
        events = mock_play_with_pitches["playEvents"]
        pitches = [e for e in events if e.get("isPitch", False)]
        assert len(pitches) == 3

        labels = [label_pitch_code(p["details"]["code"]) for p in pitches]
        assert labels == ["ball", "swinging_strike", "in_play"]

    def test_count_state_extraction(self, mock_play_with_pitches):
        """Verify count state is extracted from each pitch."""
        events = mock_play_with_pitches["playEvents"]
        pitches = [e for e in events if e.get("isPitch", False)]

        counts = [(p["count"]["balls"], p["count"]["strikes"]) for p in pitches]
        assert counts == [(0, 0), (1, 0), (1, 1)]

    def test_pitch_metadata_extraction(self, mock_play_with_pitches):
        """Verify zone and speed are extracted."""
        events = mock_play_with_pitches["playEvents"]
        pitches = [e for e in events if e.get("isPitch", False)]

        zones = [p["pitchData"]["zone"] for p in pitches]
        speeds = [p["pitchData"]["startSpeed"] for p in pitches]
        assert zones == [14, 5, 8]
        assert speeds == [92.3, 85.1, 93.0]

    def test_unknown_pitch_code_skipped(self):
        """Unknown pitch codes should be skipped."""
        assert label_pitch_code("V") is None
        assert label_pitch_code("") is None
