"""Tests for stat_normalization.normalize_stats."""

from __future__ import annotations

from app.services.stat_normalization import normalize_stats


class TestNormalizeStats:
    def test_empty_stats(self) -> None:
        assert normalize_stats({}, "NBA") == []

    def test_basic_flat_stats(self) -> None:
        raw = {"points": 25, "rebounds": 10, "assists": 7}
        result = normalize_stats(raw, "NBA")
        keys = [s["key"] for s in result]
        assert "points" in keys
        assert "rebounds" in keys
        assert "assists" in keys

    def test_alias_resolution(self) -> None:
        # Basketball Reference uses "trb" for total rebounds
        raw = {"trb": 12, "ast": 5, "pts": 20}
        result = normalize_stats(raw, "NBA")
        keys = {s["key"]: s["value"] for s in result}
        assert keys["rebounds"] == 12
        assert keys["assists"] == 5
        assert keys["points"] == 20

    def test_nested_cbb_format(self) -> None:
        # CBB API nests rebounds like {"total": 8, "offensive": 3}
        raw = {
            "rebounds": {"total": 8, "offensive": 3, "defensive": 5},
            "points": 15,
        }
        result = normalize_stats(raw, "NCAAB")
        keys = {s["key"]: s["value"] for s in result}
        assert keys["rebounds"] == 8

    def test_dot_notation_alias(self) -> None:
        raw = {
            "free_throws": {"made": 5, "attempted": 7},
            "points": 20,
        }
        result = normalize_stats(raw, "NBA")
        keys = {s["key"]: s["value"] for s in result}
        assert keys.get("free_throws_made") == 5

    def test_dedup(self) -> None:
        # If both canonical and alias present, only one should appear
        raw = {"rebounds": 10, "trb": 12}
        result = normalize_stats(raw, "NBA")
        reb_entries = [s for s in result if s["key"] == "rebounds"]
        assert len(reb_entries) == 1

    def test_display_label(self) -> None:
        raw = {"points": 25}
        result = normalize_stats(raw, "NBA")
        assert result[0]["displayLabel"] == "PTS"

    def test_group(self) -> None:
        raw = {"points": 25}
        result = normalize_stats(raw, "NBA")
        assert result[0]["group"] == "scoring"

    def test_format_type(self) -> None:
        raw = {"fg_pct": 0.485}
        result = normalize_stats(raw, "NBA")
        pct_stats = [s for s in result if s["formatType"] == "pct"]
        assert len(pct_stats) >= 1

    def test_invalid_value_skipped(self) -> None:
        raw = {"points": "not_a_number"}
        result = normalize_stats(raw, "NBA")
        pts = [s for s in result if s["key"] == "points"]
        assert len(pts) == 0
