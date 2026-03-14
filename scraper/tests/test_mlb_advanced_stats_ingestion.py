"""Tests for services/mlb_advanced_stats_ingestion.py."""

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

from sports_scraper.live.mlb_statcast import (
    PitcherStatcastAggregates,
    PlayerStatcastAggregates,
    TeamStatcastAggregates,
)
from sports_scraper.services.mlb_advanced_stats_ingestion import (
    _extract_pitcher_boxscore_data,
    _parse_ip,
    _safe_div,
    ingest_advanced_stats_for_game,
)

# ---------------------------------------------------------------------------
# _safe_div
# ---------------------------------------------------------------------------


class TestSafeDiv:
    def test_normal_division(self):
        assert _safe_div(10, 5) == 2.0

    def test_zero_denominator_returns_none(self):
        assert _safe_div(10, 0) is None

    def test_zero_numerator(self):
        assert _safe_div(0, 5) == 0.0

    def test_float_division(self):
        result = _safe_div(1, 3)
        assert result is not None
        assert abs(result - 0.3333) < 0.01


# ---------------------------------------------------------------------------
# _parse_ip
# ---------------------------------------------------------------------------


class TestParseIp:
    def test_full_innings(self):
        assert _parse_ip("6.0") == 6.0

    def test_one_third(self):
        result = _parse_ip("1.1")
        assert abs(result - 1.333) < 0.01

    def test_two_thirds(self):
        result = _parse_ip("6.2")
        assert abs(result - 6.667) < 0.01

    def test_zero(self):
        assert _parse_ip("0.0") == 0.0

    def test_empty_string(self):
        assert _parse_ip("") == 0.0

    def test_whole_only(self):
        assert _parse_ip("5") == 5.0


# ---------------------------------------------------------------------------
# _extract_pitcher_boxscore_data
# ---------------------------------------------------------------------------


class TestExtractPitcherBoxscoreData:
    def test_extracts_starter_and_reliever(self):
        boxscore_raw = {
            "teams": {
                "home": {
                    "pitchers": [501, 502],
                    "players": {
                        "ID501": {
                            "stats": {
                                "pitching": {
                                    "inningsPitched": "6.0",
                                    "hits": 5, "runs": 2, "earnedRuns": 2,
                                    "baseOnBalls": 1, "strikeOuts": 7,
                                    "homeRuns": 1, "numberOfPitches": 90,
                                    "strikes": 60, "balls": 30,
                                    "battersFaced": 24,
                                }
                            }
                        },
                        "ID502": {
                            "stats": {
                                "pitching": {
                                    "inningsPitched": "3.0",
                                    "hits": 2, "runs": 1, "earnedRuns": 1,
                                    "baseOnBalls": 0, "strikeOuts": 4,
                                    "homeRuns": 0, "numberOfPitches": 40,
                                    "strikes": 28, "balls": 12,
                                    "battersFaced": 10,
                                }
                            }
                        },
                    },
                },
                "away": {
                    "pitchers": [601],
                    "players": {
                        "ID601": {
                            "stats": {
                                "pitching": {
                                    "inningsPitched": "9.0",
                                    "hits": 4, "runs": 0, "earnedRuns": 0,
                                    "baseOnBalls": 2, "strikeOuts": 10,
                                    "homeRuns": 0, "numberOfPitches": 110,
                                    "strikes": 75, "balls": 35,
                                    "battersFaced": 30,
                                }
                            }
                        },
                    },
                },
            }
        }
        result = _extract_pitcher_boxscore_data(boxscore_raw)

        assert result["501"]["is_starter"] is True
        assert result["501"]["innings_pitched"] == 6.0
        assert result["501"]["strikeouts"] == 7

        assert result["502"]["is_starter"] is False
        assert result["502"]["innings_pitched"] == 3.0

        assert result["601"]["is_starter"] is True
        assert result["601"]["strikeouts"] == 10

    def test_empty_teams(self):
        result = _extract_pitcher_boxscore_data({"teams": {}})
        assert result == {}


# ---------------------------------------------------------------------------
# ingest_advanced_stats_for_game
# ---------------------------------------------------------------------------


class TestIngestAdvancedStatsForGame:
    @staticmethod
    def _make_game(
        status="final",
        league_code="MLB",
        external_ids=None,
        home_team_id=1,
        away_team_id=2,
    ):
        """Create a mock game object."""
        game = MagicMock()
        game.status = status
        game.league_id = 10
        game.home_team_id = home_team_id
        game.away_team_id = away_team_id
        game.external_ids = external_ids if external_ids is not None else {"mlb_game_pk": 12345}
        game.last_advanced_stats_at = None
        return game

    @staticmethod
    def _make_league(code="MLB"):
        league = MagicMock()
        league.code = code
        return league

    @staticmethod
    def _make_session(game=None, league=None):
        session = MagicMock()

        def get_side_effect(model_id):
            # Route based on call order: first call gets game, second gets league
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

    def test_game_not_mlb(self):
        game = self._make_game()
        league = self._make_league(code="NBA")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_mlb"

    def test_no_game_pk(self):
        game = self._make_game(external_ids={})
        league = self._make_league(code="MLB")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_game_pk"

    @patch("sports_scraper.live.mlb.MLBLiveFeedClient")
    def test_successful_ingestion_with_player_and_pitcher_stats(self, MockClient):
        game = self._make_game()
        league = self._make_league(code="MLB")
        session = self._make_session(game, league)

        # Mock statcast aggregates
        home_agg = TeamStatcastAggregates(
            total_pitches=100,
            zone_pitches=50,
            zone_swings=30,
            zone_contact=25,
            outside_pitches=40,
            outside_swings=10,
            outside_contact=5,
            balls_in_play=20,
            total_exit_velo=1800.0,
            hard_hit_count=8,
            barrel_count=3,
        )
        away_agg = TeamStatcastAggregates(
            total_pitches=95,
            zone_pitches=45,
            zone_swings=25,
            zone_contact=20,
            outside_pitches=38,
            outside_swings=12,
            outside_contact=4,
            balls_in_play=18,
            total_exit_velo=1600.0,
            hard_hit_count=6,
            barrel_count=2,
        )

        # Mock player-level aggregates
        player_agg_home = PlayerStatcastAggregates(
            batter_id=100,
            batter_name="Home Batter",
            side="home",
            stats=TeamStatcastAggregates(
                total_pitches=50, zone_pitches=25, zone_swings=15, zone_contact=12,
                outside_pitches=20, outside_swings=5, outside_contact=2,
                balls_in_play=10, total_exit_velo=900.0, hard_hit_count=4, barrel_count=1,
            ),
        )
        player_agg_away = PlayerStatcastAggregates(
            batter_id=200,
            batter_name="Away Batter",
            side="away",
            stats=TeamStatcastAggregates(
                total_pitches=45, zone_pitches=20, zone_swings=10, zone_contact=8,
                outside_pitches=18, outside_swings=6, outside_contact=2,
                balls_in_play=8, total_exit_velo=700.0, hard_hit_count=3, barrel_count=1,
            ),
        )

        # Mock pitcher-level aggregates
        pitcher_agg_home = PitcherStatcastAggregates(
            pitcher_id=300,
            pitcher_name="Home Pitcher",
            side="home",
            total_batters_faced=15,
            stats=TeamStatcastAggregates(
                total_pitches=80, zone_pitches=40, zone_swings=20, zone_contact=15,
                outside_pitches=30, outside_swings=8, outside_contact=3,
                balls_in_play=12, total_exit_velo=1000.0, hard_hit_count=5, barrel_count=2,
            ),
        )
        pitcher_agg_away = PitcherStatcastAggregates(
            pitcher_id=400,
            pitcher_name="Away Pitcher",
            side="away",
            total_batters_faced=12,
            stats=TeamStatcastAggregates(
                total_pitches=70, zone_pitches=35, zone_swings=18, zone_contact=14,
                outside_pitches=28, outside_swings=7, outside_contact=3,
                balls_in_play=10, total_exit_velo=850.0, hard_hit_count=4, barrel_count=1,
            ),
        )

        mock_client = MagicMock()
        mock_client.fetch_statcast_aggregates.return_value = {
            "home": home_agg,
            "away": away_agg,
        }
        mock_client.fetch_player_statcast_aggregates.return_value = [
            player_agg_home, player_agg_away,
        ]
        mock_client.fetch_pitcher_statcast_aggregates.return_value = [
            pitcher_agg_home, pitcher_agg_away,
        ]

        # Mock raw boxscore with pitcher lines
        mock_client.fetch_boxscore_raw.return_value = {
            "teams": {
                "home": {
                    "pitchers": [300, 301],
                    "players": {
                        "ID300": {
                            "stats": {
                                "pitching": {
                                    "inningsPitched": "6.2", "hits": 5,
                                    "runs": 2, "earnedRuns": 2,
                                    "baseOnBalls": 1, "strikeOuts": 8,
                                    "homeRuns": 1, "numberOfPitches": 95,
                                    "strikes": 62, "balls": 33,
                                    "battersFaced": 25,
                                }
                            }
                        },
                        "ID301": {"stats": {"pitching": {
                            "inningsPitched": "2.1", "hits": 1,
                            "runs": 0, "earnedRuns": 0,
                            "baseOnBalls": 0, "strikeOuts": 3,
                            "homeRuns": 0, "numberOfPitches": 30,
                            "strikes": 20, "balls": 10,
                            "battersFaced": 8,
                        }}},
                    },
                },
                "away": {
                    "pitchers": [400],
                    "players": {
                        "ID400": {
                            "stats": {
                                "pitching": {
                                    "inningsPitched": "9.0", "hits": 4,
                                    "runs": 1, "earnedRuns": 1,
                                    "baseOnBalls": 2, "strikeOuts": 10,
                                    "homeRuns": 0, "numberOfPitches": 110,
                                    "strikes": 75, "balls": 35,
                                    "battersFaced": 30,
                                }
                            }
                        },
                    },
                },
            }
        }

        MockClient.return_value = mock_client

        result = ingest_advanced_stats_for_game(session, 1)

        assert result["status"] == "success"
        assert result["rows_upserted"] == 2
        assert result["player_rows_upserted"] == 2
        assert result["pitcher_rows_upserted"] == 2

        # Verify the client was called with the right game_pk
        mock_client.fetch_statcast_aggregates.assert_called_once_with(12345, game_status="final")
        mock_client.fetch_player_statcast_aggregates.assert_called_once_with(
            12345, game_status="final"
        )
        mock_client.fetch_pitcher_statcast_aggregates.assert_called_once_with(
            12345, game_status="final"
        )
        mock_client.fetch_boxscore_raw.assert_called_once_with(12345, game_status="final")

        # 2 team rows + 2 player rows + 2 pitcher rows = 6 execute calls
        assert session.execute.call_count == 6

        # Verify game timestamp was updated
        assert game.last_advanced_stats_at is not None

        # Verify flush was called
        session.flush.assert_called_once()

    @patch("sports_scraper.live.mlb.MLBLiveFeedClient")
    def test_boxscore_fetch_returns_none(self, MockClient):
        """Pitcher stats still upserted with Statcast-only when boxscore fails."""
        game = self._make_game()
        league = self._make_league(code="MLB")
        session = self._make_session(game, league)

        home_agg = TeamStatcastAggregates(total_pitches=100)
        away_agg = TeamStatcastAggregates(total_pitches=95)

        pitcher_agg = PitcherStatcastAggregates(
            pitcher_id=300,
            pitcher_name="Home Pitcher",
            side="home",
            total_batters_faced=15,
            stats=TeamStatcastAggregates(
                total_pitches=80, zone_pitches=40, zone_swings=20, zone_contact=15,
                outside_pitches=30, outside_swings=8, outside_contact=3,
                balls_in_play=12, total_exit_velo=1000.0, hard_hit_count=5, barrel_count=2,
            ),
        )

        mock_client = MagicMock()
        mock_client.fetch_statcast_aggregates.return_value = {"home": home_agg, "away": away_agg}
        mock_client.fetch_player_statcast_aggregates.return_value = []
        mock_client.fetch_pitcher_statcast_aggregates.return_value = [pitcher_agg]
        mock_client.fetch_boxscore_raw.return_value = None
        MockClient.return_value = mock_client

        result = ingest_advanced_stats_for_game(session, 1)

        assert result["status"] == "success"
        assert result["pitcher_rows_upserted"] == 1
        # 2 team + 0 player + 1 pitcher = 3
        assert session.execute.call_count == 3

    @patch("sports_scraper.live.mlb.MLBLiveFeedClient")
    def test_ingestion_no_players_or_pitchers(self, MockClient):
        """Test when there are no player or pitcher aggregates."""
        game = self._make_game()
        league = self._make_league(code="MLB")
        session = self._make_session(game, league)

        home_agg = TeamStatcastAggregates(total_pitches=10)
        away_agg = TeamStatcastAggregates(total_pitches=8)

        mock_client = MagicMock()
        mock_client.fetch_statcast_aggregates.return_value = {
            "home": home_agg,
            "away": away_agg,
        }
        mock_client.fetch_player_statcast_aggregates.return_value = []
        mock_client.fetch_pitcher_statcast_aggregates.return_value = []
        MockClient.return_value = mock_client

        result = ingest_advanced_stats_for_game(session, 1)

        assert result["status"] == "success"
        assert result["rows_upserted"] == 2
        assert result["player_rows_upserted"] == 0
        assert result["pitcher_rows_upserted"] == 0
        # 2 team rows only
        assert session.execute.call_count == 2
