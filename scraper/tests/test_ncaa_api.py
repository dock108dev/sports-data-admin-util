"""Tests for NCAA API integration (scoreboard, PBP, boxscore, game matching)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


# ============================================================================
# NCAA Scoreboard Tests
# ============================================================================

from sports_scraper.live.ncaa_scoreboard import NCAAScoreboardClient, NCAAScoreboardGame


class TestNCAAScoreboardClient:
    """Tests for NCAAScoreboardClient."""

    def _make_client(self, response_data: dict, status_code: int = 200) -> NCAAScoreboardClient:
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = response_data
        mock_response.text = str(response_data)
        mock_http.get.return_value = mock_response
        return NCAAScoreboardClient(mock_http)

    def test_parse_live_game(self):
        """Test parsing a live game from scoreboard."""
        data = {
            "games": [
                {
                    "game": {
                        "gameID": "6502231",
                        "gameState": "live",
                        "contestClock": "12:34",
                        "currentPeriod": "2",
                        "startTimeEpoch": "1708466400",
                        "home": {
                            "names": {"short": "Purdue", "seo": "purdue"},
                            "score": "45",
                        },
                        "away": {
                            "names": {"short": "Indiana", "seo": "indiana"},
                            "score": "38",
                        },
                    }
                }
            ]
        }
        client = self._make_client(data)
        results = client.fetch_scoreboard()

        assert len(results) == 1
        game = results[0]
        assert game.ncaa_game_id == "6502231"
        assert game.game_state == "live"
        assert game.home_team_short == "Purdue"
        assert game.away_team_short == "Indiana"
        assert game.home_score == 45
        assert game.away_score == 38
        assert game.current_period == 2
        assert game.contest_clock == "12:34"

    def test_parse_final_game(self):
        """Test that 'final' state is correctly mapped."""
        data = {
            "games": [
                {
                    "game": {
                        "gameID": "123",
                        "gameState": "final",
                        "home": {
                            "names": {"short": "Duke", "seo": "duke"},
                            "score": "82",
                        },
                        "away": {
                            "names": {"short": "UNC", "seo": "north-carolina"},
                            "score": "75",
                        },
                    }
                }
            ]
        }
        client = self._make_client(data)
        results = client.fetch_scoreboard()

        assert len(results) == 1
        assert results[0].game_state == "final"
        assert results[0].home_score == 82
        assert results[0].away_score == 75

    def test_parse_pre_game(self):
        """Test that 'pre' state maps to 'scheduled'."""
        data = {
            "games": [
                {
                    "game": {
                        "gameID": "456",
                        "gameState": "pre",
                        "home": {
                            "names": {"short": "Kansas", "seo": "kansas"},
                            "score": "",
                        },
                        "away": {
                            "names": {"short": "Baylor", "seo": "baylor"},
                            "score": "",
                        },
                    }
                }
            ]
        }
        client = self._make_client(data)
        results = client.fetch_scoreboard()

        assert len(results) == 1
        assert results[0].game_state == "scheduled"
        assert results[0].home_score is None  # empty string -> None
        assert results[0].away_score is None

    def test_empty_scoreboard(self):
        """Test empty games list."""
        client = self._make_client({"games": []})
        results = client.fetch_scoreboard()
        assert results == []

    def test_network_error_returns_empty(self):
        """Test that network errors return empty list."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Connection refused")
        client = NCAAScoreboardClient(mock_http)
        results = client.fetch_scoreboard()
        assert results == []

    def test_non_200_returns_empty(self):
        """Test that non-200 status returns empty list."""
        client = self._make_client({}, status_code=503)
        results = client.fetch_scoreboard()
        assert results == []

    def test_missing_game_id_skipped(self):
        """Test that games without gameID are skipped."""
        data = {
            "games": [
                {
                    "game": {
                        "gameState": "live",
                        "home": {"names": {"short": "Duke"}, "score": "50"},
                        "away": {"names": {"short": "UNC"}, "score": "48"},
                    }
                }
            ]
        }
        client = self._make_client(data)
        results = client.fetch_scoreboard()
        assert results == []

    def test_string_scores_parsed(self):
        """Test that string scores are correctly parsed to int."""
        data = {
            "games": [
                {
                    "game": {
                        "gameID": "789",
                        "gameState": "live",
                        "home": {"names": {"short": "A"}, "score": "0"},
                        "away": {"names": {"short": "B"}, "score": "100"},
                    }
                }
            ]
        }
        client = self._make_client(data)
        results = client.fetch_scoreboard()
        assert results[0].home_score == 0
        assert results[0].away_score == 100


# ============================================================================
# NCAA PBP Tests
# ============================================================================

from sports_scraper.live.ncaa_pbp import NCAAPbpFetcher


class TestNCAAPbpFetcher:
    """Tests for NCAAPbpFetcher."""

    def _make_fetcher(self, response_data: dict | None = None, status_code: int = 200) -> tuple:
        mock_http = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        if response_data is not None:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = response_data
            mock_response.text = str(response_data)
            mock_http.get.return_value = mock_response

        return NCAAPbpFetcher(mock_http, mock_cache), mock_http, mock_cache

    def test_parse_periods_and_plays(self):
        """Test parsing PBP with multiple periods."""
        data = {
            "periods": [
                {
                    "periodNumber": "1",
                    "playbyplayStats": [
                        {
                            "homeScore": "0",
                            "visitorScore": "0",
                            "clock": "20:00",
                            "firstName": "John",
                            "lastName": "Doe",
                            "eventDescription": "Jump ball won",
                            "isHome": True,
                            "homeText": "Jump ball won by John Doe",
                            "visitorText": "",
                        },
                        {
                            "homeScore": "2",
                            "visitorScore": "0",
                            "clock": "19:30",
                            "firstName": "Jane",
                            "lastName": "Smith",
                            "eventDescription": "Layup made by Smith",
                            "isHome": True,
                            "homeText": "Layup made by Jane Smith",
                            "visitorText": "",
                        },
                    ],
                },
                {
                    "periodNumber": "2",
                    "playbyplayStats": [
                        {
                            "homeScore": "35",
                            "visitorScore": "30",
                            "clock": "20:00",
                            "firstName": "Bob",
                            "lastName": "Jones",
                            "eventDescription": "Three point jumper made",
                            "isHome": False,
                            "homeText": "",
                            "visitorText": "Three point jumper made by Bob Jones",
                        },
                    ],
                },
            ]
        }
        fetcher, _, _ = self._make_fetcher(data)
        result = fetcher.fetch_play_by_play("123456")

        assert result.source_game_key == "123456"
        assert len(result.plays) == 3

        # First period plays
        assert result.plays[0].quarter == 1
        assert result.plays[0].home_score == 0
        assert result.plays[0].away_score == 0
        assert result.plays[0].player_name == "John Doe"

        # Second play
        assert result.plays[1].quarter == 1
        assert result.plays[1].home_score == 2

        # Second period play
        assert result.plays[2].quarter == 2
        assert result.plays[2].home_score == 35

    def test_play_index_ordering(self):
        """Test that play_index ensures cross-period ordering."""
        data = {
            "periods": [
                {
                    "periodNumber": "1",
                    "playbyplayStats": [{"clock": "20:00", "homeScore": "0", "visitorScore": "0"}],
                },
                {
                    "periodNumber": "2",
                    "playbyplayStats": [{"clock": "20:00", "homeScore": "30", "visitorScore": "25"}],
                },
            ]
        }
        fetcher, _, _ = self._make_fetcher(data)
        result = fetcher.fetch_play_by_play("111")

        assert result.plays[0].play_index < result.plays[1].play_index
        # Period 1 play_index = 1 * 10000 + 0 = 10000
        # Period 2 play_index = 2 * 10000 + 0 = 20000
        assert result.plays[0].play_index == 10000
        assert result.plays[1].play_index == 20000

    def test_classify_play_types(self):
        """Test regex-based play type classification."""
        fetcher, _, _ = self._make_fetcher({"periods": []})

        assert fetcher._classify_play_type("Layup made by John Doe") == "MADE_SHOT"
        assert fetcher._classify_play_type("Jumper missed by Jane Smith") == "MISSED_SHOT"
        assert fetcher._classify_play_type("Three point jumper made") == "MADE_THREE"
        assert fetcher._classify_play_type("Free throw made") == "MADE_FREE_THROW"
        assert fetcher._classify_play_type("Free throw missed") == "MISSED_FREE_THROW"
        assert fetcher._classify_play_type("Offensive rebound by Doe") == "OFFENSIVE_REBOUND"
        assert fetcher._classify_play_type("Defensive rebound") == "DEFENSIVE_REBOUND"
        assert fetcher._classify_play_type("Turnover by Smith") == "TURNOVER"
        assert fetcher._classify_play_type("Steal by Jones") == "STEAL"
        assert fetcher._classify_play_type("Blocked shot") == "BLOCK"
        assert fetcher._classify_play_type("Personal foul on Smith") == "PERSONAL_FOUL"
        assert fetcher._classify_play_type("Timeout called") == "TIMEOUT"
        assert fetcher._classify_play_type("") == "UNKNOWN"
        assert fetcher._classify_play_type("Some unknown event text") == "UNKNOWN"

    def test_home_text_preferred_for_home_plays(self):
        """Test that homeText is used for home team plays."""
        data = {
            "periods": [
                {
                    "periodNumber": "1",
                    "playbyplayStats": [
                        {
                            "homeScore": "2",
                            "visitorScore": "0",
                            "clock": "19:00",
                            "firstName": "John",
                            "lastName": "Doe",
                            "eventDescription": "Generic description",
                            "isHome": True,
                            "homeText": "Layup made by John Doe",
                            "visitorText": "",
                        },
                    ],
                }
            ]
        }
        fetcher, _, _ = self._make_fetcher(data)
        result = fetcher.fetch_play_by_play("222")
        assert result.plays[0].description == "Layup made by John Doe"

    def test_visitor_text_preferred_for_away_plays(self):
        """Test that visitorText is used for away team plays."""
        data = {
            "periods": [
                {
                    "periodNumber": "1",
                    "playbyplayStats": [
                        {
                            "homeScore": "0",
                            "visitorScore": "3",
                            "clock": "18:00",
                            "firstName": "Jane",
                            "lastName": "Smith",
                            "eventDescription": "Generic",
                            "isHome": False,
                            "homeText": "",
                            "visitorText": "Three point jumper made by Jane Smith",
                        },
                    ],
                }
            ]
        }
        fetcher, _, _ = self._make_fetcher(data)
        result = fetcher.fetch_play_by_play("333")
        assert result.plays[0].description == "Three point jumper made by Jane Smith"

    def test_404_returns_empty(self):
        """Test that 404 returns empty PBP."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_http.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAAPbpFetcher(mock_http, mock_cache)
        result = fetcher.fetch_play_by_play("999")
        assert result.plays == []

    def test_cache_used_when_available(self):
        """Test that cached data is used when available."""
        cached_data = {
            "periods": [
                {
                    "periodNumber": "1",
                    "playbyplayStats": [
                        {"clock": "20:00", "homeScore": "0", "visitorScore": "0"},
                    ],
                }
            ]
        }
        mock_http = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_data

        fetcher = NCAAPbpFetcher(mock_http, mock_cache)
        result = fetcher.fetch_play_by_play("444")

        assert len(result.plays) == 1
        mock_http.get.assert_not_called()  # Should not make HTTP call

    def test_network_error_returns_empty(self):
        """Test that network errors return empty PBP."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("timeout")

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAAPbpFetcher(mock_http, mock_cache)
        result = fetcher.fetch_play_by_play("555")
        assert result.plays == []


# ============================================================================
# NCAA Boxscore Tests
# ============================================================================

from sports_scraper.live.ncaa_boxscore import NCAABoxscoreFetcher


class TestNCAABoxscoreFetcher:
    """Tests for NCAABoxscoreFetcher."""

    SAMPLE_BOXSCORE = {
        "teams": [
            {
                "isHome": True,
                "teamId": "101",
                "nameShort": "PUR",
            },
            {
                "isHome": False,
                "teamId": "102",
                "nameShort": "IND",
            },
        ],
        "teamBoxscore": [
            {
                "teamStats": {
                    "fieldGoalsMade": "25",
                    "fieldGoalsAttempted": "55",
                    "totalRebounds": "35",
                    "assists": "15",
                    "turnovers": "10",
                    "steals": "5",
                    "blockedShots": "3",
                    "personalFouls": "18",
                    "points": "72",
                },
                "playerStats": [
                    {
                        "id": "12345",
                        "firstName": "Zach",
                        "lastName": "Edey",
                        "position": "C",
                        "starter": True,
                        "minutesPlayed": "32:00",
                        "points": "25",
                        "rebounds": "12",
                        "assists": "1",
                        "steals": "0",
                        "blockedShots": "3",
                        "turnovers": "2",
                        "personalFouls": "3",
                        "fieldGoalsMade": "10",
                        "fieldGoalsAttempted": "15",
                        "threePointsMade": "0",
                        "threePointsAttempted": "0",
                        "freeThrowsMade": "5",
                        "freeThrowsAttempted": "7",
                    },
                ],
            },
            {
                "teamStats": {
                    "fieldGoalsMade": "22",
                    "fieldGoalsAttempted": "58",
                    "totalRebounds": "30",
                    "assists": "12",
                    "turnovers": "14",
                    "steals": "3",
                    "blockedShots": "2",
                    "personalFouls": "20",
                    "points": "65",
                },
                "playerStats": [
                    {
                        "id": "67890",
                        "firstName": "Trayce",
                        "lastName": "Jackson-Davis",
                        "position": "F",
                        "starter": True,
                        "minutesPlayed": "35:00",
                        "points": "20",
                        "rebounds": "10",
                        "assists": "3",
                        "steals": "1",
                        "blockedShots": "2",
                        "turnovers": "3",
                        "personalFouls": "4",
                        "fieldGoalsMade": "8",
                        "fieldGoalsAttempted": "14",
                    },
                ],
            },
        ],
    }

    def _make_fetcher(self, response_data: dict | None = None, status_code: int = 200) -> tuple:
        mock_http = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        if response_data is not None:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = response_data
            mock_response.text = str(response_data)
            mock_http.get.return_value = mock_response

        return NCAABoxscoreFetcher(mock_http, mock_cache), mock_http, mock_cache

    def test_parse_team_stats(self):
        """Test parsing team-level stats from boxscore."""
        fetcher, _, _ = self._make_fetcher(self.SAMPLE_BOXSCORE)
        result = fetcher.fetch_boxscore(
            "6502231", "Purdue Boilermakers", "Indiana Hoosiers",
        )

        assert result is not None
        assert result.home_score == 72
        assert result.away_score == 65
        assert len(result.team_boxscores) == 2

        home_box = result.team_boxscores[0]
        assert home_box.is_home is True
        assert home_box.points == 72
        assert home_box.rebounds == 35
        assert home_box.assists == 15
        assert home_box.turnovers == 10

    def test_parse_player_stats(self):
        """Test parsing player stats with all string fields."""
        fetcher, _, _ = self._make_fetcher(self.SAMPLE_BOXSCORE)
        result = fetcher.fetch_boxscore(
            "6502231", "Purdue Boilermakers", "Indiana Hoosiers",
        )

        assert result is not None
        assert len(result.player_boxscores) == 2

        # Find Edey
        edey = next(p for p in result.player_boxscores if p.player_name == "Zach Edey")
        assert edey.player_id == "12345"
        assert edey.position == "C"
        assert edey.points == 25
        assert edey.rebounds == 12
        assert edey.assists == 1
        assert edey.minutes == pytest.approx(32.0, abs=0.01)
        assert edey.raw_stats.get("fgMade") == 10
        assert edey.raw_stats.get("fgAttempted") == 15

    def test_404_returns_none(self):
        """Test that 404 returns None."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_http.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABoxscoreFetcher(mock_http, mock_cache)
        result = fetcher.fetch_boxscore("999", "Team A", "Team B")
        assert result is None

    def test_empty_teams_returns_none(self):
        """Test that response with no teams returns None."""
        fetcher, _, _ = self._make_fetcher({"teams": [], "teamBoxscore": []})
        result = fetcher.fetch_boxscore("111", "Team A", "Team B")
        assert result is None

    def test_is_home_flag_respected(self):
        """Test that isHome boolean determines home/away correctly."""
        # Flip isHome: second team is now home
        data = {
            "teams": [
                {"isHome": False, "teamId": "101", "nameShort": "PUR"},
                {"isHome": True, "teamId": "102", "nameShort": "IND"},
            ],
            "teamBoxscore": [
                {
                    "teamStats": {"points": "72", "totalRebounds": "35", "assists": "15", "turnovers": "10"},
                    "playerStats": [],
                },
                {
                    "teamStats": {"points": "65", "totalRebounds": "30", "assists": "12", "turnovers": "14"},
                    "playerStats": [],
                },
            ],
        }

        fetcher, _, _ = self._make_fetcher(data)
        result = fetcher.fetch_boxscore(
            "6502231", "Indiana Hoosiers", "Purdue Boilermakers",
        )

        assert result is not None
        # With isHome on index 1, Indiana (index 1) is home
        assert result.home_score == 65  # Indiana's points
        assert result.away_score == 72  # Purdue's points

    def test_cache_used(self):
        """Test cached boxscore is used."""
        mock_http = MagicMock()
        mock_cache = MagicMock()
        mock_cache.get.return_value = self.SAMPLE_BOXSCORE

        fetcher = NCAABoxscoreFetcher(mock_http, mock_cache)
        result = fetcher.fetch_boxscore(
            "6502231", "Purdue Boilermakers", "Indiana Hoosiers",
        )

        assert result is not None
        assert result.home_score == 72
        mock_http.get.assert_not_called()

    def test_network_error_returns_none(self):
        """Test that network errors return None."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("timeout")
        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABoxscoreFetcher(mock_http, mock_cache)
        result = fetcher.fetch_boxscore("555", "A", "B")
        assert result is None


# ============================================================================
# NCAA Team Name Matching Tests
# ============================================================================

from sports_scraper.normalization import normalize_team_name


class TestNCAATeamNameMatching:
    """Test NCAA scoreboard team names resolve via normalize_team_name."""

    def test_short_name_match(self):
        """NCAA short names like 'Purdue' should match."""
        canonical, abbr = normalize_team_name("NCAAB", "Purdue")
        assert canonical == "Purdue Boilermakers"
        assert abbr == "PUR"

    def test_seo_name_match(self):
        """NCAA seo names like 'michigan-st' should match."""
        canonical, abbr = normalize_team_name("NCAAB", "michigan-st")
        assert canonical == "Michigan St Spartans"
        assert abbr == "MSU"

    def test_short_name_multi_word(self):
        """NCAA short names like 'North Carolina' should match via existing variations."""
        canonical, abbr = normalize_team_name("NCAAB", "North Carolina")
        assert canonical == "North Carolina Tar Heels"
        assert abbr == "UNC"

    def test_exact_canonical_match(self):
        """Full canonical name should match exactly."""
        canonical, abbr = normalize_team_name("NCAAB", "Duke Blue Devils")
        assert canonical == "Duke Blue Devils"
        assert abbr == "DUKE"

    def test_abbreviation_match(self):
        """Abbreviation should match."""
        canonical, abbr = normalize_team_name("NCAAB", "KU")
        assert canonical == "Kansas Jayhawks"
        assert abbr == "KU"

    def test_common_variation_match(self):
        """Well-known variations should match."""
        canonical, abbr = normalize_team_name("NCAAB", "Bama")
        assert canonical == "Alabama Crimson Tide"
        assert abbr == "ALA"

    def test_unknown_team_returns_input(self):
        """Unknown team should return the input name."""
        canonical, abbr = normalize_team_name("NCAAB", "Nonexistent University")
        # Should not match any team, returns fallback
        assert "Nonexistent" in canonical


# ============================================================================
# Game Matching Logic Tests
# ============================================================================

from sports_scraper.jobs.polling_helpers_ncaab import _match_ncaa_scoreboard_to_games


class TestNCAAGameMatching:
    """Test matching NCAA scoreboard games to DB games."""

    def _make_db_game(self, game_id: int, home_team_id: int, away_team_id: int, external_ids: dict | None = None):
        """Create a mock DB game."""
        game = MagicMock()
        game.id = game_id
        game.home_team_id = home_team_id
        game.away_team_id = away_team_id
        game.external_ids = external_ids or {}
        return game

    def _make_scoreboard_game(self, ncaa_game_id: str, home_short: str, away_short: str) -> NCAAScoreboardGame:
        return NCAAScoreboardGame(
            ncaa_game_id=ncaa_game_id,
            game_state="live",
            home_team_short=home_short,
            away_team_short=away_short,
            home_team_seo="",
            away_team_seo="",
            home_score=50,
            away_score=45,
            current_period=2,
            contest_clock="10:00",
            start_time_epoch=None,
        )

    def _make_mock_session(self, teams: dict):
        """Create a mock session with team lookup."""
        session = MagicMock()

        def get_team(team_id):
            return teams.get(team_id)

        # Mock the query chain: session.query(SportsTeam).get(id)
        mock_query = MagicMock()
        mock_query.get = get_team
        session.query.return_value = mock_query

        return session

    def test_exact_name_match(self):
        """Test matching when team names normalize to the same canonical."""
        home_team = MagicMock()
        home_team.name = "Purdue Boilermakers"
        away_team = MagicMock()
        away_team.name = "Indiana Hoosiers"

        session = self._make_mock_session({1: home_team, 2: away_team})
        games = [self._make_db_game(100, 1, 2)]
        scoreboard = [self._make_scoreboard_game("6502231", "Purdue", "Indiana")]

        matches = _match_ncaa_scoreboard_to_games(session, games, scoreboard)

        assert 100 in matches
        assert matches[100].ncaa_game_id == "6502231"

    def test_no_match_returns_empty(self):
        """Test that non-matching teams return no matches."""
        home_team = MagicMock()
        home_team.name = "Duke Blue Devils"
        away_team = MagicMock()
        away_team.name = "UNC Tar Heels"

        session = self._make_mock_session({1: home_team, 2: away_team})
        games = [self._make_db_game(100, 1, 2)]
        scoreboard = [self._make_scoreboard_game("999", "Kansas", "Baylor")]

        matches = _match_ncaa_scoreboard_to_games(session, games, scoreboard)

        assert 100 not in matches

    def test_reversed_home_away_matches(self):
        """Test matching when home/away are reversed (neutral site)."""
        home_team = MagicMock()
        home_team.name = "Purdue Boilermakers"
        away_team = MagicMock()
        away_team.name = "Indiana Hoosiers"

        session = self._make_mock_session({1: home_team, 2: away_team})
        games = [self._make_db_game(100, 1, 2)]
        # Scoreboard has Purdue/Indiana reversed
        scoreboard = [self._make_scoreboard_game("6502231", "Indiana", "Purdue")]

        matches = _match_ncaa_scoreboard_to_games(session, games, scoreboard)

        assert 100 in matches

    def test_skip_games_with_existing_ncaa_id(self):
        """Test that games already having ncaa_game_id are skipped."""
        home_team = MagicMock()
        home_team.name = "Purdue Boilermakers"
        away_team = MagicMock()
        away_team.name = "Indiana Hoosiers"

        session = self._make_mock_session({1: home_team, 2: away_team})
        games = [self._make_db_game(100, 1, 2, external_ids={"ncaa_game_id": "existing"})]
        scoreboard = [self._make_scoreboard_game("6502231", "Purdue", "Indiana")]

        matches = _match_ncaa_scoreboard_to_games(session, games, scoreboard)

        assert 100 not in matches  # Should be skipped


# ============================================================================
# NCAA Constants Tests
# ============================================================================

from sports_scraper.live.ncaa_constants import (
    NCAA_API_BASE,
    NCAA_EVENT_PATTERNS,
    NCAA_GAME_STATE_MAP,
    NCAA_MIN_REQUEST_INTERVAL,
)


class TestNCAAConstants:
    """Test NCAA constants are properly configured."""

    def test_api_base_url(self):
        assert NCAA_API_BASE == "https://ncaa-api.henrygd.me"

    def test_game_state_map_complete(self):
        assert NCAA_GAME_STATE_MAP["live"] == "live"
        assert NCAA_GAME_STATE_MAP["final"] == "final"
        assert NCAA_GAME_STATE_MAP["pre"] == "scheduled"

    def test_rate_limit_interval(self):
        assert NCAA_MIN_REQUEST_INTERVAL == 0.25

    def test_event_patterns_not_empty(self):
        assert len(NCAA_EVENT_PATTERNS) > 10

    def test_event_patterns_are_compiled_regex(self):
        import re
        for pattern, play_type in NCAA_EVENT_PATTERNS:
            assert isinstance(pattern, re.Pattern)
            assert isinstance(play_type, str)
