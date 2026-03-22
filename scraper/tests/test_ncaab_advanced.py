"""Tests for live/ncaab_advanced.py and services/ncaab_advanced_stats_ingestion.py."""

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

from sports_scraper.live.ncaab_advanced import (
    FTA_COEFF,
    NCAABAdvancedStatsFetcher,
    _compute_single_player_stats,
    _extract_stat,
)
from sports_scraper.services.ncaab_advanced_stats_ingestion import (
    ingest_advanced_stats_for_game,
)

# ---------------------------------------------------------------------------
# Sample boxscore data matching the CBB API JSONB format
# ---------------------------------------------------------------------------

HOME_BOXSCORE = {
    "fieldGoalsMade": 25,
    "fieldGoalsAttempted": 55,
    "threePointsMade": 8,
    "threePointsAttempted": 20,
    "freeThrowsMade": 12,
    "freeThrowsAttempted": 16,
    "offensiveRebounds": 10,
    "defensiveRebounds": 22,
    "turnovers": 12,
    "points": 70,
    "assists": 15,
    "steals": 7,
    "blocks": 3,
    "personalFouls": 18,
}

AWAY_BOXSCORE = {
    "fieldGoalsMade": 22,
    "fieldGoalsAttempted": 60,
    "threePointsMade": 6,
    "threePointsAttempted": 22,
    "freeThrowsMade": 15,
    "freeThrowsAttempted": 20,
    "offensiveRebounds": 8,
    "defensiveRebounds": 25,
    "turnovers": 15,
    "points": 65,
    "assists": 12,
    "steals": 5,
    "blocks": 4,
    "personalFouls": 20,
}

SAMPLE_PLAYER_BOXSCORE = {
    "minutes": 32,
    "fieldGoalsMade": 8,
    "fieldGoalsAttempted": 15,
    "threePointsMade": 3,
    "threePointsAttempted": 7,
    "freeThrowsMade": 4,
    "freeThrowsAttempted": 5,
    "offensiveRebounds": 2,
    "defensiveRebounds": 5,
    "turnovers": 3,
    "points": 23,
    "assists": 4,
    "steals": 2,
    "blocks": 1,
    "personalFouls": 2,
}


# ---------------------------------------------------------------------------
# _extract_stat
# ---------------------------------------------------------------------------


class TestExtractStat:
    def test_existing_key(self):
        """Extract a stat that exists in the dict."""
        data = {"fieldGoalsMade": 25}
        assert _extract_stat(data, "fieldGoalsMade") == 25

    def test_missing_key_returns_default(self):
        """Missing key returns 0 by default."""
        data = {"fieldGoalsMade": 25}
        assert _extract_stat(data, "nonexistent") == 0

    def test_custom_default(self):
        """Missing key with custom default."""
        data = {}
        assert _extract_stat(data, "fieldGoalsMade", default=99) == 99

    def test_none_value_returns_default(self):
        """None value in dict returns the default."""
        data = {"fieldGoalsMade": None}
        assert _extract_stat(data, "fieldGoalsMade") == 0

    def test_string_value_coerced(self):
        """String numeric values should be coerced to int."""
        data = {"fieldGoalsMade": "25"}
        result = _extract_stat(data, "fieldGoalsMade")
        assert result == 25


# ---------------------------------------------------------------------------
# NCAABAdvancedStatsFetcher.compute_team_advanced_stats
# Returns {"home": {...}, "away": {...}} with keys like:
#   off_efg_pct, off_tov_pct, off_orb_pct, off_ft_rate,
#   def_efg_pct, def_tov_pct, def_orb_pct, def_ft_rate,
#   off_rating, def_rating, net_rating, pace, possessions
# ---------------------------------------------------------------------------


class TestComputeTeamAdvancedStats:
    def _get_fetcher(self):
        return NCAABAdvancedStatsFetcher()

    def test_effective_field_goal_pct(self):
        """off_efg_pct = (FGM + 0.5 * 3PM) / FGA."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        home = result["home"]
        # off_efg_pct = (25 + 0.5 * 8) / 55 = 29 / 55 = 0.5273
        assert abs(home["off_efg_pct"] - 0.5273) < 0.01

    def test_turnover_pct(self):
        """off_tov_pct = TOV / (FGA + 0.475 * FTA + TOV)."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        home = result["home"]
        # off_tov_pct = 12 / (55 + 0.475 * 16 + 12) = 12 / 74.6 = 0.1608
        expected = 12 / (55 + FTA_COEFF * 16 + 12)
        assert abs(home["off_tov_pct"] - expected) < 0.01

    def test_offensive_rebound_pct(self):
        """off_orb_pct = ORB / (ORB + opponent DRB)."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        home = result["home"]
        # off_orb_pct = 10 / (10 + 25) = 10/35 = 0.2857
        assert abs(home["off_orb_pct"] - 0.2857) < 0.01

    def test_free_throw_rate(self):
        """off_ft_rate = FTA / FGA."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        home = result["home"]
        # off_ft_rate = 16 / 55 = 0.2909
        assert abs(home["off_ft_rate"] - 0.2909) < 0.01

    def test_pace_calculation(self):
        """Pace estimate uses possessions formula."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        assert result["home"]["pace"] is not None
        assert result["home"]["pace"] > 0

    def test_efficiency_ratings(self):
        """Offensive and defensive efficiency should be computed."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        home = result["home"]
        away = result["away"]
        # off_rating = points per 100 possessions
        assert home["off_rating"] is not None
        assert home["off_rating"] > 0
        assert away["off_rating"] is not None
        assert away["off_rating"] > 0
        # def_rating = opponent points per 100 possessions
        assert home["def_rating"] is not None
        assert home["def_rating"] > 0

    def test_away_four_factors(self):
        """Away team four factors are also computed."""
        fetcher = self._get_fetcher()
        result = fetcher.compute_team_advanced_stats(HOME_BOXSCORE, AWAY_BOXSCORE)

        away = result["away"]
        # off_efg_pct = (22 + 0.5 * 6) / 60 = 25 / 60 = 0.4167
        assert abs(away["off_efg_pct"] - 0.4167) < 0.01

        # off_orb_pct = 8 / (8 + 22) = 8/30 = 0.2667
        assert abs(away["off_orb_pct"] - 0.2667) < 0.01


# ---------------------------------------------------------------------------
# _compute_single_player_stats (called internally by compute_player_advanced_stats)
# ---------------------------------------------------------------------------


class TestComputePlayerAdvancedStats:
    def test_true_shooting_pct(self):
        """ts_pct = PTS / (2 * (FGA + 0.44 * FTA))."""
        result = _compute_single_player_stats(
            SAMPLE_PLAYER_BOXSCORE,
            team_possessions=65.0,
            team_minutes=200.0,
        )

        # ts_pct = 23 / (2 * (15 + 0.44 * 5)) = 23 / (2 * 17.2) = 23 / 34.4 = 0.6686
        assert result["ts_pct"] is not None
        assert abs(result["ts_pct"] - 0.6686) < 0.01

    def test_effective_field_goal_pct(self):
        """efg_pct = (FGM + 0.5 * 3PM) / FGA."""
        result = _compute_single_player_stats(
            SAMPLE_PLAYER_BOXSCORE,
            team_possessions=65.0,
            team_minutes=200.0,
        )

        # efg_pct = (8 + 0.5 * 3) / 15 = 9.5 / 15 = 0.6333
        assert result["efg_pct"] is not None
        assert abs(result["efg_pct"] - 0.6333) < 0.01

    def test_game_score(self):
        """Game Score = PTS + 0.4*FGM - 0.7*FGA - 0.4*(FTA-FTM) + 0.7*ORB +
        0.3*DRB + STL + 0.7*AST + 0.7*BLK - 0.4*PF - TOV."""
        result = _compute_single_player_stats(
            SAMPLE_PLAYER_BOXSCORE,
            team_possessions=65.0,
            team_minutes=200.0,
        )

        # Game Score = 23 + 0.4*8 - 0.7*15 - 0.4*(5-4) + 0.7*2 + 0.3*5
        #            + 2 + 0.7*4 + 0.7*1 - 0.4*2 - 3
        # = 23 + 3.2 - 10.5 - 0.4 + 1.4 + 1.5 + 2 + 2.8 + 0.7 - 0.8 - 3
        # = 19.9
        assert result["game_score"] is not None
        assert abs(result["game_score"] - 19.9) < 0.5

    def test_zero_fga_handles_gracefully(self):
        """Player with 0 FGA should not cause division by zero."""
        player = {
            "minutes": 2,
            "fieldGoalsMade": 0,
            "fieldGoalsAttempted": 0,
            "threePointsMade": 0,
            "threePointsAttempted": 0,
            "freeThrowsMade": 0,
            "freeThrowsAttempted": 0,
            "offensiveRebounds": 0,
            "defensiveRebounds": 1,
            "turnovers": 0,
            "points": 0,
            "assists": 0,
            "steals": 0,
            "blocks": 0,
            "personalFouls": 1,
        }
        result = _compute_single_player_stats(
            player,
            team_possessions=65.0,
            team_minutes=200.0,
        )
        # Should not raise; ts_pct and efg_pct should be None with 0 FGA
        assert result["ts_pct"] is None or result["ts_pct"] == 0
        assert result["efg_pct"] is None


# ---------------------------------------------------------------------------
# ingest_advanced_stats_for_game (NCAAB)
# NCAAB does NOT check external_ids - it loads boxscores from the DB.
# The "missing_boxscores" check replaces any "no_game_id" check.
# ---------------------------------------------------------------------------


class TestNCAABIngestAdvancedStats:
    @staticmethod
    def _make_game(
        status="final",
        home_team_id=1,
        away_team_id=2,
    ):
        game = MagicMock()
        game.status = status
        game.league_id = 50
        game.home_team_id = home_team_id
        game.away_team_id = away_team_id
        game.external_ids = {}
        game.last_advanced_stats_at = None
        return game

    @staticmethod
    def _make_league(code="NCAAB"):
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

    def test_game_not_ncaab(self):
        game = self._make_game()
        league = self._make_league(code="NBA")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_ncaab"

    def test_missing_boxscores(self):
        """When no team boxscores in DB, returns missing_boxscores."""
        game = self._make_game()
        league = self._make_league(code="NCAAB")
        session = self._make_session(game, league)
        # Mock the boxscore query to return empty
        session.query.return_value.filter.return_value.all.return_value = []

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "missing_boxscores"
