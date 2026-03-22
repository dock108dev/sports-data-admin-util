"""Tests for live/nhl_advanced.py and services/nhl_advanced_stats_ingestion.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from sports_scraper.live.nhl_advanced import (
    NHLAdvancedStatsFetcher,
    _classify_danger,
    _safe_float,
    _safe_int,
)
from sports_scraper.services.nhl_advanced_stats_ingestion import (
    ingest_advanced_stats_for_game,
)

# ---------------------------------------------------------------------------
# Sample shot data used across tests
# Uses arenaAdjustedShotDistance (the actual CSV field name)
# ---------------------------------------------------------------------------

SAMPLE_SHOTS = [
    {
        "game_id": "2025020001",
        "team": "BOS",
        "isHomeTeam": "1",
        "event": "GOAL",
        "xGoal": "0.12",
        "arenaAdjustedShotDistance": "15",
        "shooterPlayerId": "8001",
        "goalieIdForShot": "9001",
    },
    {
        "game_id": "2025020001",
        "team": "NYR",
        "isHomeTeam": "0",
        "event": "SHOT",
        "xGoal": "0.05",
        "arenaAdjustedShotDistance": "40",
        "shooterPlayerId": "8002",
        "goalieIdForShot": "9002",
    },
    {
        "game_id": "2025020001",
        "team": "BOS",
        "isHomeTeam": "1",
        "event": "MISS",
        "xGoal": "0.03",
        "arenaAdjustedShotDistance": "50",
        "shooterPlayerId": "8001",
        "goalieIdForShot": "9001",
    },
]


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_valid_float_string(self):
        assert _safe_float("3.14") == 3.14

    def test_valid_int_string(self):
        assert _safe_float("42") == 42.0

    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_empty_string_returns_default(self):
        assert _safe_float("") == 0.0

    def test_invalid_string_returns_default(self):
        assert _safe_float("abc") == 0.0

    def test_custom_default(self):
        assert _safe_float(None, default=-1.0) == -1.0


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


class TestSafeInt:
    def test_valid_int_string(self):
        assert _safe_int("42") == 42

    def test_none_returns_default(self):
        assert _safe_int(None) == 0

    def test_empty_string_returns_default(self):
        assert _safe_int("") == 0

    def test_float_string(self):
        # Should handle float string by converting to float first, then int
        assert _safe_int("3.7") == 3

    def test_invalid_string_returns_default(self):
        assert _safe_int("abc") == 0


# ---------------------------------------------------------------------------
# _classify_danger
# _classify_danger takes a float (distance in feet), not a string
# ---------------------------------------------------------------------------


class TestClassifyDanger:
    def test_high_danger_close_range(self):
        """Shots within 20 feet should be high danger."""
        result = _classify_danger(10.0)
        assert result == "high"

    def test_medium_danger_mid_range(self):
        """Shots between 20-40 feet should be medium danger."""
        result = _classify_danger(30.0)
        assert result == "medium"

    def test_low_danger_far_range(self):
        """Shots beyond 40 feet should be low danger."""
        result = _classify_danger(55.0)
        assert result == "low"

    def test_boundary_at_20(self):
        """20 feet is exactly high danger threshold."""
        result = _classify_danger(20.0)
        assert result == "high"

    def test_zero_distance(self):
        """Zero distance is high danger."""
        result = _classify_danger(0.0)
        assert result == "high"


# ---------------------------------------------------------------------------
# NHLAdvancedStatsFetcher.aggregate_team_stats
# Returns {"home": TeamAdvancedAggregates, "away": TeamAdvancedAggregates}
# ---------------------------------------------------------------------------


class TestAggregateTeamStats:
    def test_team_stats_from_shots(self):
        """Verify xGoals sums and shot counts."""
        fetcher = NHLAdvancedStatsFetcher.__new__(NHLAdvancedStatsFetcher)
        result = fetcher.aggregate_team_stats(SAMPLE_SHOTS, "BOS")

        assert "home" in result
        assert "away" in result

        home = result["home"]
        # BOS (home) xGoals: 0.12 + 0.03 = 0.15
        assert abs(home.xgoals_for - 0.15) < 0.001
        assert home.team == "BOS"
        assert home.is_home is True
        # BOS shots on goal: GOAL counts as SOG
        assert home.shots_on_goal == 1
        # BOS missed shots: MISS = 1
        assert home.missed_shots == 1
        # BOS goals = 1
        assert home.goals == 1

        away = result["away"]
        assert abs(away.xgoals_for - 0.05) < 0.001
        assert away.team == "NYR"
        assert away.is_home is False
        # NYR shots on goal: SHOT = 1
        assert away.shots_on_goal == 1
        assert away.goals == 0

    def test_empty_shots(self):
        """Empty shot list returns aggregates with zero values."""
        fetcher = NHLAdvancedStatsFetcher.__new__(NHLAdvancedStatsFetcher)
        result = fetcher.aggregate_team_stats([], "BOS")
        assert "home" in result
        assert "away" in result
        assert result["home"].shots_on_goal == 0


# ---------------------------------------------------------------------------
# NHLAdvancedStatsFetcher.aggregate_skater_stats
# Returns list[SkaterAggregates]
# ---------------------------------------------------------------------------


class TestAggregateSkaterStats:
    def test_per_player_aggregation(self):
        """Verify per-player stats from shot data."""
        fetcher = NHLAdvancedStatsFetcher.__new__(NHLAdvancedStatsFetcher)
        result = fetcher.aggregate_skater_stats(SAMPLE_SHOTS)

        assert isinstance(result, list)
        assert len(result) == 2

        # Find player 8001
        p8001 = [s for s in result if s.player_id == "8001"]
        assert len(p8001) == 1
        assert p8001[0].shots == 1  # Only GOAL counts as shot (SHOT+GOAL)
        assert p8001[0].goals == 1
        assert abs(p8001[0].xgoals_for - 0.15) < 0.001

        # Find player 8002
        p8002 = [s for s in result if s.player_id == "8002"]
        assert len(p8002) == 1
        assert p8002[0].shots == 1
        assert p8002[0].goals == 0
        assert abs(p8002[0].xgoals_for - 0.05) < 0.001

    def test_empty_shots(self):
        """Empty shot list returns empty list."""
        fetcher = NHLAdvancedStatsFetcher.__new__(NHLAdvancedStatsFetcher)
        result = fetcher.aggregate_skater_stats([])
        assert result == []


# ---------------------------------------------------------------------------
# NHLAdvancedStatsFetcher.aggregate_goalie_stats
# Returns list[GoalieAggregates]
# ---------------------------------------------------------------------------


class TestAggregateGoalieStats:
    def test_per_goalie_aggregation(self):
        """Verify per-goalie stats from shot data."""
        fetcher = NHLAdvancedStatsFetcher.__new__(NHLAdvancedStatsFetcher)
        result = fetcher.aggregate_goalie_stats(SAMPLE_SHOTS)

        assert isinstance(result, list)
        # 2 goalies: 9001 and 9002
        assert len(result) == 2

        # Find goalie 9001 - faced BOS GOAL (15 ft, high danger) and no MISS events
        # MISS is not counted against goalie (only SHOT and GOAL)
        g9001 = [g for g in result if g.player_id == "9001"]
        assert len(g9001) == 1
        # Goalie 9001 only faces GOAL from BOS (MISS doesn't count as shot against goalie)
        assert g9001[0].shots_against >= 1
        assert g9001[0].goals_against == 1
        assert g9001[0].xgoals_against > 0

        # Find goalie 9002 - faced NYR SHOT (40 ft, medium danger)
        g9002 = [g for g in result if g.player_id == "9002"]
        assert len(g9002) == 1
        assert g9002[0].shots_against == 1
        assert g9002[0].goals_against == 0

    def test_empty_shots(self):
        """Empty shot list returns empty list."""
        fetcher = NHLAdvancedStatsFetcher.__new__(NHLAdvancedStatsFetcher)
        result = fetcher.aggregate_goalie_stats([])
        assert result == []


# ---------------------------------------------------------------------------
# ingest_advanced_stats_for_game (NHL)
# ---------------------------------------------------------------------------


class TestNHLIngestAdvancedStats:
    @staticmethod
    def _make_game(
        status="final",
        external_ids=None,
        home_team_id=1,
        away_team_id=2,
    ):
        game = MagicMock()
        game.status = status
        game.league_id = 30
        game.home_team_id = home_team_id
        game.away_team_id = away_team_id
        game.external_ids = external_ids if external_ids is not None else {"nhl_game_pk": "2025020001"}
        game.last_advanced_stats_at = None
        return game

    @staticmethod
    def _make_league(code="NHL"):
        league = MagicMock()
        league.code = code
        return league

    @staticmethod
    def _make_session(game=None, league=None):
        session = MagicMock()

        def get_side_effect(model_id):
            return get_side_effect._results.pop(0)

        results = []
        if game is not None:
            results.append(game)
        if league is not None:
            results.append(league)
        get_side_effect._results = results

        session.query.return_value.get = MagicMock(side_effect=get_side_effect)
        return session

    def test_game_not_found(self):
        session = MagicMock()
        session.query.return_value.get.return_value = None

        result = ingest_advanced_stats_for_game(session, 999)
        assert result["status"] == "not_found"

    def test_game_not_final(self):
        game = self._make_game(status="live")
        session = MagicMock()
        session.query.return_value.get.return_value = game

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_final"

    def test_game_not_nhl(self):
        game = self._make_game()
        league = self._make_league(code="NBA")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_nhl"

    def test_no_game_pk(self):
        game = self._make_game(external_ids={})
        league = self._make_league(code="NHL")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_game_pk"
