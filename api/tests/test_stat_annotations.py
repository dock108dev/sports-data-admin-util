"""Tests for stat_annotations.compute_team_annotations."""

from __future__ import annotations

import pytest

from app.services.stat_annotations import compute_team_annotations


class TestComputeTeamAnnotations:
    def test_no_annotations_when_close(self) -> None:
        home = {"offensive_rebounds": 5, "turnovers": 10}
        away = {"offensive_rebounds": 4, "turnovers": 10}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        assert result == []

    def test_oreb_annotation(self) -> None:
        home = {"offensive_rebounds": 12}
        away = {"offensive_rebounds": 5}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        oreb = [a for a in result if a["key"] == "offensive_rebounds"]
        assert len(oreb) == 1
        assert "BOS" in oreb[0]["text"]
        assert "+7 OREB" in oreb[0]["text"]

    def test_away_team_advantage(self) -> None:
        home = {"steals": 2}
        away = {"steals": 8}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        stl = [a for a in result if a["key"] == "steals"]
        assert len(stl) == 1
        assert "NYK" in stl[0]["text"]

    def test_turnovers_threshold(self) -> None:
        home = {"turnovers": 15}
        away = {"turnovers": 12}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        to = [a for a in result if a["key"] == "turnovers"]
        assert len(to) == 1
        assert "3 more turnovers" in to[0]["text"]

    def test_three_pointers_annotation(self) -> None:
        home = {"three_pointers_made": 14}
        away = {"three_pointers_made": 8}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        threes = [a for a in result if a["key"] == "three_pointers_made"]
        assert len(threes) == 1
        assert "6 more threes" in threes[0]["text"]

    def test_alias_resolution(self) -> None:
        home = {"orb": 10}
        away = {"orb": 3}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        oreb = [a for a in result if a["key"] == "offensive_rebounds"]
        assert len(oreb) == 1

    def test_nested_dict_stats(self) -> None:
        home = {"offensive_rebounds": {"total": 12}}
        away = {"offensive_rebounds": {"total": 5}}
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        oreb = [a for a in result if a["key"] == "offensive_rebounds"]
        assert len(oreb) == 1

    def test_multiple_annotations(self) -> None:
        home = {
            "offensive_rebounds": 12,
            "assists": 30,
            "steals": 10,
        }
        away = {
            "offensive_rebounds": 5,
            "assists": 22,
            "steals": 4,
        }
        result = compute_team_annotations(home, away, "BOS", "NYK", "NBA")
        assert len(result) >= 2
