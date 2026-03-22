"""Tests for live/nba_advanced.py and services/nba_advanced_stats_ingestion.py."""

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

from sports_scraper.live.nba_advanced import (
    NBAAdvancedStatsFetcher,
    _parse_result_set,
    parse_advanced_boxscore,
    parse_hustle_stats,
    parse_tracking_stats,
)
from sports_scraper.services.nba_advanced_stats_ingestion import (
    ingest_advanced_stats_for_game,
)


# ---------------------------------------------------------------------------
# _parse_result_set
# ---------------------------------------------------------------------------


class TestParseResultSet:
    def test_valid_data(self):
        """Parse a resultSet with headers and rowSet into list of dicts."""
        data = {
            "resultSets": [
                {
                    "name": "PlayerStats",
                    "headers": ["PLAYER_ID", "PLAYER_NAME", "MIN"],
                    "rowSet": [
                        [101, "LeBron James", "36:20"],
                        [102, "Anthony Davis", "34:15"],
                    ],
                }
            ]
        }
        result = _parse_result_set(data, "PlayerStats")
        assert len(result) == 2
        assert result[0]["PLAYER_ID"] == 101
        assert result[1]["PLAYER_NAME"] == "Anthony Davis"

    def test_missing_result_set(self):
        """Return empty list when the named resultSet does not exist."""
        data = {"resultSets": [{"name": "OtherStats", "headers": [], "rowSet": []}]}
        result = _parse_result_set(data, "PlayerStats")
        assert result == []

    def test_empty_rows(self):
        """Return empty list when rowSet is present but empty."""
        data = {
            "resultSets": [
                {
                    "name": "PlayerStats",
                    "headers": ["PLAYER_ID", "MIN"],
                    "rowSet": [],
                }
            ]
        }
        result = _parse_result_set(data, "PlayerStats")
        assert result == []


# ---------------------------------------------------------------------------
# parse_advanced_boxscore
# ---------------------------------------------------------------------------


class TestParseAdvancedBoxscore:
    def test_newer_boxscore_advanced_format(self):
        """Parse the newer boxScoreAdvanced top-level key format.

        Returns (team_rows, player_rows) tuple.
        """
        payload = {
            "boxScoreAdvanced": {
                "homeTeam": {
                    "teamId": 1610612738,
                    "teamTricode": "BOS",
                    "statistics": {
                        "offensiveRating": 115.2,
                        "defensiveRating": 108.5,
                        "netRating": 6.7,
                        "pace": 100.3,
                        "trueShootingPercentage": 0.585,
                        "effectiveFieldGoalPercentage": 0.545,
                        "turnoverPercentage": 12.1,
                        "offensiveReboundPercentage": 28.5,
                    },
                    "players": [],
                },
                "awayTeam": {
                    "teamId": 1610612747,
                    "teamTricode": "LAL",
                    "statistics": {
                        "offensiveRating": 108.5,
                        "defensiveRating": 115.2,
                        "netRating": -6.7,
                        "pace": 100.3,
                        "trueShootingPercentage": 0.520,
                        "effectiveFieldGoalPercentage": 0.480,
                        "turnoverPercentage": 14.3,
                        "offensiveReboundPercentage": 22.0,
                    },
                    "players": [],
                },
            }
        }
        team_rows, player_rows = parse_advanced_boxscore(payload)
        assert len(team_rows) == 2
        # Home team is first
        assert team_rows[0]["OFF_RATING"] == 115.2
        assert team_rows[0]["is_home"] is True
        # Away team second
        assert team_rows[1]["NET_RATING"] == -6.7
        assert team_rows[1]["is_home"] is False

    def test_legacy_result_sets_format(self):
        """Parse legacy resultSets format with headers + rowSet."""
        payload = {
            "resultSets": [
                {
                    "name": "TeamStats",
                    "headers": [
                        "GAME_ID", "TEAM_ID", "OFF_RATING", "DEF_RATING",
                        "NET_RATING", "PACE", "TS_PCT", "EFG_PCT",
                    ],
                    "rowSet": [
                        ["0022400100", 1610612738, 115.2, 108.5, 6.7, 100.3, 0.585, 0.545],
                        ["0022400100", 1610612747, 108.5, 115.2, -6.7, 100.3, 0.520, 0.480],
                    ],
                }
            ]
        }
        team_rows, player_rows = parse_advanced_boxscore(payload)
        assert len(team_rows) == 2
        assert team_rows[0]["OFF_RATING"] == 115.2


# ---------------------------------------------------------------------------
# parse_hustle_stats
# ---------------------------------------------------------------------------


class TestParseHustleStats:
    def test_newer_format(self):
        """Parse hustle stats from the newer nested format.

        Returns a list of player dicts (one per player per team).
        The newer format uses boxScoreHustle key with homeTeam/awayTeam.players[].
        """
        payload = {
            "boxScoreHustle": {
                "homeTeam": {
                    "teamId": 1610612738,
                    "players": [
                        {
                            "personId": 101,
                            "firstName": "Jayson",
                            "familyName": "Tatum",
                            "statistics": {
                                "contestedShots": 8,
                                "deflections": 3,
                                "looseBallsRecovered": 2,
                                "chargesDrawn": 1,
                                "screenAssists": 2,
                            },
                        },
                    ],
                },
                "awayTeam": {
                    "teamId": 1610612747,
                    "players": [
                        {
                            "personId": 201,
                            "firstName": "LeBron",
                            "familyName": "James",
                            "statistics": {
                                "contestedShots": 6,
                                "deflections": 2,
                                "looseBallsRecovered": 1,
                                "chargesDrawn": 0,
                                "screenAssists": 1,
                            },
                        },
                    ],
                },
            }
        }
        result = parse_hustle_stats(payload)
        assert isinstance(result, list)
        assert len(result) == 2
        # Home player
        assert result[0]["DEFLECTIONS"] == 3
        assert result[0]["is_home"] is True
        # Away player
        assert result[1]["CONTESTED_SHOTS"] == 6
        assert result[1]["is_home"] is False

    def test_legacy_result_sets_format(self):
        """Parse hustle stats from legacy resultSets format."""
        payload = {
            "resultSets": [
                {
                    "name": "PlayerStats",
                    "headers": [
                        "GAME_ID", "TEAM_ID", "CONTESTED_SHOTS",
                        "DEFLECTIONS", "LOOSE_BALLS_RECOVERED",
                    ],
                    "rowSet": [
                        ["0022400100", 1610612738, 32, 10, 5],
                        ["0022400100", 1610612747, 28, 7, 3],
                    ],
                }
            ]
        }
        result = parse_hustle_stats(payload)
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# parse_tracking_stats
# ---------------------------------------------------------------------------


class TestParseTrackingStats:
    def test_newer_format(self):
        """Parse tracking stats from the newer nested format.

        Returns a list of player dicts. Uses boxScorePlayerTrack key.
        """
        payload = {
            "boxScorePlayerTrack": {
                "homeTeam": {
                    "teamId": 1610612738,
                    "players": [
                        {
                            "personId": 101,
                            "firstName": "Jayson",
                            "familyName": "Tatum",
                            "statistics": {
                                "speed": 4.32,
                                "distance": 2.5,
                                "touches": 80,
                                "possessionTime": 5.2,
                            },
                        },
                    ],
                },
                "awayTeam": {
                    "teamId": 1610612747,
                    "players": [
                        {
                            "personId": 201,
                            "firstName": "LeBron",
                            "familyName": "James",
                            "statistics": {
                                "speed": 4.28,
                                "distance": 2.4,
                                "touches": 75,
                                "possessionTime": 4.8,
                            },
                        },
                    ],
                },
            }
        }
        result = parse_tracking_stats(payload)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["SPD"] == 4.32
        assert result[0]["is_home"] is True
        assert result[1]["DIST"] == 2.4
        assert result[1]["is_home"] is False

    def test_legacy_result_sets_format(self):
        """Parse tracking stats from legacy resultSets format."""
        payload = {
            "resultSets": [
                {
                    "name": "PlayerStats",
                    "headers": [
                        "GAME_ID", "TEAM_ID", "DIST_MILES",
                        "AVG_SPEED", "TOUCHES", "PASSES",
                    ],
                    "rowSet": [
                        ["0022400100", 1610612738, 250.5, 4.32, 300, 280],
                        ["0022400100", 1610612747, 245.0, 4.28, 290, 270],
                    ],
                }
            ]
        }
        result = parse_tracking_stats(payload)
        assert isinstance(result, list)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# NBAAdvancedStatsFetcher
# ---------------------------------------------------------------------------


class TestNBAAdvancedStatsFetcher:
    @patch("sports_scraper.live.nba_advanced.settings")
    def test_fetch_advanced_boxscore_success(self, mock_settings):
        """Fetch advanced boxscore with mocked httpx response."""
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        response_data = {
            "boxScoreAdvanced": {
                "homeTeam": {
                    "teamId": 1,
                    "statistics": {"offensiveRating": 110.0, "defensiveRating": 105.0},
                },
                "awayTeam": {
                    "teamId": 2,
                    "statistics": {"offensiveRating": 105.0, "defensiveRating": 110.0},
                },
            }
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data

        fetcher = NBAAdvancedStatsFetcher()
        fetcher._client = MagicMock()
        fetcher._client.get.return_value = mock_response
        fetcher._cache = MagicMock()
        fetcher._cache.get.return_value = None

        result = fetcher.fetch_advanced_boxscore("0022400100")

        assert result is not None
        fetcher._client.get.assert_called_once()

    @patch("sports_scraper.live.nba_advanced.settings")
    def test_fetch_advanced_boxscore_cache_hit(self, mock_settings):
        """Return cached data without making HTTP call."""
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        cached_data = {
            "boxScoreAdvanced": {
                "homeTeam": {"teamId": 1, "statistics": {"offensiveRating": 110.0}},
                "awayTeam": {"teamId": 2, "statistics": {"offensiveRating": 105.0}},
            }
        }

        fetcher = NBAAdvancedStatsFetcher()
        fetcher._client = MagicMock()
        fetcher._cache = MagicMock()
        fetcher._cache.get.return_value = cached_data

        result = fetcher.fetch_advanced_boxscore("0022400100")

        assert result is not None
        fetcher._client.get.assert_not_called()

    @patch("sports_scraper.live.nba_advanced.settings")
    def test_fetch_advanced_boxscore_403_handling(self, mock_settings):
        """Handle 403 Forbidden gracefully."""
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        mock_response = MagicMock()
        mock_response.status_code = 403

        fetcher = NBAAdvancedStatsFetcher()
        fetcher._client = MagicMock()
        fetcher._client.get.return_value = mock_response
        fetcher._cache = MagicMock()
        fetcher._cache.get.return_value = None

        result = fetcher.fetch_advanced_boxscore("0022400100")

        assert result is None

    @patch("sports_scraper.live.nba_advanced.settings")
    def test_fetch_advanced_boxscore_429_handling(self, mock_settings):
        """Handle 429 Too Many Requests gracefully."""
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        mock_response = MagicMock()
        mock_response.status_code = 429

        fetcher = NBAAdvancedStatsFetcher()
        fetcher._client = MagicMock()
        fetcher._client.get.return_value = mock_response
        fetcher._cache = MagicMock()
        fetcher._cache.get.return_value = None

        result = fetcher.fetch_advanced_boxscore("0022400100")

        assert result is None


# ---------------------------------------------------------------------------
# ingest_advanced_stats_for_game (NBA)
# ---------------------------------------------------------------------------


class TestNBAIngestAdvancedStats:
    @staticmethod
    def _make_game(
        status="final",
        league_code="NBA",
        external_ids=None,
        home_team_id=1,
        away_team_id=2,
    ):
        game = MagicMock()
        game.status = status
        game.league_id = 20
        game.home_team_id = home_team_id
        game.away_team_id = away_team_id
        game.external_ids = external_ids if external_ids is not None else {"nba_game_id": "0022400100"}
        game.last_advanced_stats_at = None
        return game

    @staticmethod
    def _make_league(code="NBA"):
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

    def test_game_not_nba(self):
        game = self._make_game()
        league = self._make_league(code="MLB")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "not_nba"

    def test_no_game_id(self):
        game = self._make_game(external_ids={})
        league = self._make_league(code="NBA")
        session = self._make_session(game, league)

        result = ingest_advanced_stats_for_game(session, 1)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_nba_game_id"

    @patch("sports_scraper.live.nba_advanced.NBAAdvancedStatsFetcher")
    @patch("sports_scraper.live.nba_advanced.parse_advanced_boxscore")
    @patch("sports_scraper.live.nba_advanced.parse_hustle_stats")
    @patch("sports_scraper.live.nba_advanced.parse_tracking_stats")
    def test_successful_ingestion(self, mock_parse_tracking, mock_parse_hustle, mock_parse_adv, MockFetcher):
        game = self._make_game()
        league = self._make_league(code="NBA")
        session = self._make_session(game, league)

        mock_fetcher = MagicMock()
        # The fetcher returns raw API response dicts
        mock_fetcher.fetch_advanced_boxscore.return_value = {"boxScoreAdvanced": {}}
        mock_fetcher.fetch_hustle_stats.return_value = {"boxScoreHustle": {}}
        mock_fetcher.fetch_tracking_stats.return_value = {"boxScorePlayerTrack": {}}
        MockFetcher.return_value = mock_fetcher

        # The parse functions are called on the raw data
        mock_parse_adv.return_value = (
            [
                {"TEAM_ID": 1, "is_home": True, "OFF_RATING": 115.2},
                {"TEAM_ID": 2, "is_home": False, "OFF_RATING": 108.5},
            ],
            [],  # player_rows
        )
        mock_parse_hustle.return_value = []
        mock_parse_tracking.return_value = []

        result = ingest_advanced_stats_for_game(session, 1)

        assert result["status"] == "success"
        assert result["rows_upserted"] == 2
        assert game.last_advanced_stats_at is not None
        session.flush.assert_called_once()
