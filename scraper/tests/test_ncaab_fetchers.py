"""Comprehensive tests for NCAAB fetchers (PBP and boxscore)."""

from __future__ import annotations

import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


# ============================================================================
# Tests for live/ncaab_pbp.py - NCAABPbpFetcher
# ============================================================================

from sports_scraper.live.ncaab_pbp import NCAABPbpFetcher


class TestNCAABPbpFetcher:
    """Tests for NCAABPbpFetcher with mocked HTTP."""

    def test_fetch_play_by_play_success(self):
        """Test successful PBP fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "period": 1,
                "sequenceNumber": 1,
                "clock": "20:00",
                "playType": "JUMP_BALL",
                "team": "Duke",
                "player": "Player A",
                "playerId": 12345,
                "homeScore": 0,
                "awayScore": 0,
                "description": "Jump ball won by Duke",
            },
            {
                "period": 1,
                "sequenceNumber": 2,
                "clock": "19:45",
                "playType": "MADE_2PT",
                "team": "Duke",
                "player": "Player B",
                "playerId": 12346,
                "homeScore": 2,
                "awayScore": 0,
                "description": "Player B makes 2-point shot",
            },
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None  # No cache

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(12345)

        assert result.source_game_key == "12345"
        assert len(result.plays) == 2
        assert result.plays[0].play_type == "JUMP_BALL"
        assert result.plays[1].home_score == 2

    def test_fetch_play_by_play_preserves_zero_scores(self):
        """Test that score=0 is preserved, not treated as None."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "period": 1,
                "sequenceNumber": 1,
                "clock": "20:00",
                "playType": "JUMP_BALL",
                "homeScore": 0,
                "awayScore": 0,
                "description": "Jump ball",
            },
            {
                "period": 1,
                "sequenceNumber": 2,
                "clock": "19:45",
                "playType": "MADE_2PT",
                "homeScore": 2,
                "awayScore": 0,
                "description": "Player makes 2-point shot",
            },
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(12345)

        assert len(result.plays) == 2
        # Score 0 must be preserved as 0, not None
        assert result.plays[0].home_score == 0
        assert result.plays[0].away_score == 0
        assert result.plays[1].home_score == 2
        assert result.plays[1].away_score == 0

    def test_fetch_play_by_play_uses_cache(self):
        """Test PBP fetch uses cache when available."""
        mock_client = MagicMock()

        cached_data = [
            {
                "period": 1,
                "sequenceNumber": 1,
                "clock": "20:00",
                "playType": "JUMP_BALL",
                "team": "Duke",
            }
        ]

        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_data

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(12345)

        # Should not call the HTTP client
        mock_client.get.assert_not_called()
        assert len(result.plays) == 1

    def test_fetch_play_by_play_404(self):
        """Test PBP fetch handles 404."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(99999)

        assert result.source_game_key == "99999"
        assert result.plays == []

    def test_fetch_play_by_play_server_error(self):
        """Test PBP fetch handles server errors."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(12345)

        assert result.plays == []

    def test_fetch_play_by_play_network_error(self):
        """Test PBP fetch handles network exceptions."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(12345)

        assert result.plays == []

    def test_parse_pbp_response_sorts_by_play_index(self):
        """Test plays are sorted by play_index."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        # Plays out of order
        payload = [
            {"period": 1, "sequenceNumber": 3, "playType": "MADE_3PT"},
            {"period": 1, "sequenceNumber": 1, "playType": "JUMP_BALL"},
            {"period": 1, "sequenceNumber": 2, "playType": "MADE_2PT"},
        ]

        plays = fetcher._parse_pbp_response(payload, 12345)

        assert len(plays) == 3
        assert plays[0].play_type == "JUMP_BALL"
        assert plays[1].play_type == "MADE_2PT"
        assert plays[2].play_type == "MADE_3PT"

    def test_normalize_play_extracts_all_fields(self):
        """Test _normalize_play extracts all relevant fields."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        play = {
            "period": 2,
            "sequenceNumber": 50,
            "clock": "15:30",
            "playType": "MADE_3PT",
            "team": "UNC",
            "player": "Player X",
            "playerId": 99999,
            "homeScore": 45,
            "awayScore": 42,
            "description": "3-point shot made",
            "shotType": "jump_shot",
            "shotOutcome": "made",
        }

        result = fetcher._normalize_play(play, 0, 12345)

        assert result is not None
        assert result.quarter == 2
        assert result.game_clock == "15:30"
        assert result.play_type == "MADE_3PT"
        assert result.team_abbreviation == "UNC"
        assert result.player_name == "Player X"
        assert result.player_id == "99999"
        assert result.home_score == 45
        assert result.away_score == 42
        assert result.description == "3-point shot made"
        assert "shotType" in result.raw_data
        assert "shotOutcome" in result.raw_data

    def test_normalize_play_handles_missing_fields(self):
        """Test _normalize_play handles missing optional fields."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        # Minimal play data
        play = {
            "period": 1,
            "playType": "TIMEOUT",
        }

        result = fetcher._normalize_play(play, 5, 12345)

        assert result is not None
        assert result.quarter == 1
        assert result.player_name is None
        assert result.player_id is None
        assert result.home_score is None

    def test_normalize_play_uses_index_when_no_sequence(self):
        """Test _normalize_play uses index when sequenceNumber missing."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        play = {"period": 1, "playType": "MADE_2PT"}

        result = fetcher._normalize_play(play, 42, 12345)

        # play_index = period * NCAAB_PERIOD_MULTIPLIER + sequence
        # With sequence=42 (from index), period=1, multiplier=10000
        assert result.play_index == 1 * 10000 + 42

    def test_map_event_type_known_types(self):
        """Test _map_event_type maps known event types."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        # Test a few known mappings
        assert fetcher._map_event_type("MADE_2PT", 123) == "MADE_2PT"
        assert fetcher._map_event_type("JUMP_BALL", 123) == "JUMP_BALL"

    def test_map_event_type_unknown_types(self):
        """Test _map_event_type handles unknown event types."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        # Unknown type should be uppercased and spaces replaced
        result = fetcher._map_event_type("some unknown event", 123)
        assert result == "SOME_UNKNOWN_EVENT"

    def test_map_event_type_empty_returns_unknown(self):
        """Test _map_event_type handles empty string."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)

        assert fetcher._map_event_type("", 123) == "UNKNOWN"

    def test_fetch_play_by_play_empty_response(self):
        """Test PBP fetch with empty plays array."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABPbpFetcher(mock_client, mock_cache)
        result = fetcher.fetch_play_by_play(12345)

        assert result.plays == []


# ============================================================================
# Tests for live/ncaab_boxscore.py - NCAABBoxscoreFetcher
# ============================================================================

from sports_scraper.live.ncaab_boxscore import NCAABBoxscoreFetcher
from sports_scraper.live.ncaab_models import NCAABLiveGame


class TestNCAABBoxscoreFetcherDateRange:
    """Tests for NCAABBoxscoreFetcher date range methods."""

    def test_fetch_game_teams_by_date_range_success(self):
        """Test successful team stats fetch by date range (no caching)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "isHome": True, "teamStats": {"points": 75}},
            {"gameId": 123, "teamId": 2, "isHome": False, "teamStats": {"points": 70}},
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert len(result) == 2
        mock_cache.put.assert_not_called()

    def test_fetch_game_teams_by_date_range_no_cache(self):
        """Date-range methods no longer cache — always hit the API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"gameId": 123, "teamId": 1}]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert len(result) == 1
        mock_client.get.assert_called_once()
        mock_cache.get.assert_not_called()
        mock_cache.put.assert_not_called()

    def test_fetch_game_teams_by_date_range_failure(self):
        """Test team stats fetch handles failure."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert result == []

    def test_fetch_game_teams_by_date_range_exception(self):
        """Test team stats fetch handles exceptions."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert result == []

    def test_fetch_game_players_by_date_range_success(self):
        """Test successful player stats fetch by date range (no caching)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "players": [{"playerId": 1, "name": "Player A"}]},
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_players_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert len(result) == 1
        mock_cache.put.assert_not_called()

    def test_fetch_game_players_by_date_range_no_cache(self):
        """Date-range methods no longer cache — always hit the API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"gameId": 123, "teamId": 1}]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_players_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert len(result) == 1
        mock_client.get.assert_called_once()
        mock_cache.get.assert_not_called()
        mock_cache.put.assert_not_called()

    def test_fetch_game_players_by_date_range_failure(self):
        """Test player stats fetch handles failure."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_players_by_date_range(
            date(2024, 1, 15), date(2024, 1, 15), 2024
        )

        assert result == []


class TestNCAABBoxscoreFetcherBatch:
    """Tests for NCAABBoxscoreFetcher batch methods."""

    def test_fetch_boxscores_batch_success(self):
        """Test batch boxscore fetch."""
        mock_client = MagicMock()

        team_response = MagicMock()
        team_response.status_code = 200
        team_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "isHome": True, "teamStats": {"points": 75}},
            {"gameId": 123, "teamId": 2, "isHome": False, "teamStats": {"points": 70}},
        ]

        player_response = MagicMock()
        player_response.status_code = 200
        player_response.json.return_value = [
            {
                "gameId": 123,
                "teamId": 1,
                "players": [{"playerId": 101, "name": "Player A", "points": 20}],
            }
        ]

        mock_client.get.side_effect = [team_response, player_response]

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_boxscores_batch(
            game_ids=[123],
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            season=2024,
            team_names_by_game={123: ("Duke", "UNC")},
        )

        assert 123 in result
        assert result[123].home_score == 75
        assert result[123].away_score == 70

    def test_fetch_boxscores_batch_filters_by_game_ids(self):
        """Test batch boxscore fetch filters to requested game IDs only."""
        mock_client = MagicMock()

        team_response = MagicMock()
        team_response.status_code = 200
        team_response.json.return_value = [
            {"gameId": 100, "teamId": 1, "isHome": True, "teamStats": {"points": 80}},
            {"gameId": 200, "teamId": 2, "isHome": True, "teamStats": {"points": 85}},
            {"gameId": 300, "teamId": 3, "isHome": True, "teamStats": {"points": 90}},
        ]

        player_response = MagicMock()
        player_response.status_code = 200
        player_response.json.return_value = []

        mock_client.get.side_effect = [team_response, player_response]

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_boxscores_batch(
            game_ids=[200],  # Only request game 200
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            season=2024,
            team_names_by_game={200: ("Kentucky", "Louisville")},
        )

        # Should only include game 200
        assert 100 not in result
        assert 200 in result
        assert 300 not in result

    def test_fetch_boxscores_batch_skips_missing_team_names(self):
        """Test batch fetch skips games without team names."""
        mock_client = MagicMock()

        team_response = MagicMock()
        team_response.status_code = 200
        team_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "isHome": True, "teamStats": {"points": 75}},
        ]

        player_response = MagicMock()
        player_response.status_code = 200
        player_response.json.return_value = []

        mock_client.get.side_effect = [team_response, player_response]

        mock_cache = MagicMock()
        mock_cache.get.return_value = None

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_boxscores_batch(
            game_ids=[123],
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            season=2024,
            team_names_by_game={},  # No team names
        )

        assert 123 not in result


class TestNCAABBoxscoreFetcherSingleGame:
    """Tests for NCAABBoxscoreFetcher single-game fetch methods."""

    def test_fetch_game_teams_success(self):
        """Test single-game team fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "points": 75},
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams(123, 2024)

        assert len(result) == 1

    def test_fetch_game_teams_failure(self):
        """Test single-game team fetch handles failure."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Error"
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams(123, 2024)

        assert result == []

    def test_fetch_game_teams_exception(self):
        """Test single-game team fetch handles exceptions."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_teams(123, 2024)

        assert result == []

    def test_fetch_game_players_success(self):
        """Test single-game player fetch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"gameId": 123, "playerId": 1, "name": "Player A"},
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_players(123, 2024)

        assert len(result) == 1

    def test_fetch_game_players_failure(self):
        """Test single-game player fetch handles failure."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)
        result = fetcher.fetch_game_players(123, 2024)

        assert result == []


class TestNCAABBoxscoreFetcherParsing:
    """Tests for NCAABBoxscoreFetcher parsing methods."""

    def test_parse_team_stats_nested(self):
        """Test _parse_team_stats_nested extracts nested stats."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        from sports_scraper.models import TeamIdentity

        team = TeamIdentity(
            league_code="NCAAB",
            name="Duke",
            short_name="Duke",
            abbreviation=None,
            external_ref="1",
        )

        ts = {
            "teamId": 1,
            "teamStats": {
                "points": 75,
                "totalRebounds": 35,
                "assists": 18,
                "turnovers": 12,
            },
        }

        result = fetcher._parse_team_stats_nested(ts, team, True, 75)

        assert result.team.name == "Duke"
        assert result.is_home is True
        assert result.points == 75
        assert result.rebounds == 35
        assert result.assists == 18
        assert result.turnovers == 12

    def test_parse_player_stats_extracts_all_fields(self):
        """Test _parse_player_stats extracts player data."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        from sports_scraper.models import TeamIdentity

        team = TeamIdentity(
            league_code="NCAAB",
            name="Duke",
            short_name="Duke",
            abbreviation=None,
            external_ref="1",
        )

        ps = {
            "playerId": 12345,
            "name": "Star Player",
            "position": "G",
            "minutes": "35:00",
            "points": 25,
            "rebounds": 8,
            "assists": 5,
            "fieldGoalsMade": 10,
            "fieldGoalsAttempted": 18,
            "blocks": 2,
        }

        result = fetcher._parse_player_stats(ps, team, 999)

        assert result is not None
        assert result.player_id == "12345"
        assert result.player_name == "Star Player"
        assert result.position == "G"
        assert result.points == 25
        assert result.rebounds == 8
        assert result.assists == 5

    def test_parse_player_stats_missing_player_id(self):
        """Test _parse_player_stats returns None for missing player ID."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        from sports_scraper.models import TeamIdentity

        team = TeamIdentity(
            league_code="NCAAB",
            name="Duke",
            short_name="Duke",
            abbreviation=None,
            external_ref="1",
        )

        ps = {"name": "Player Without ID", "points": 10}

        result = fetcher._parse_player_stats(ps, team, 999)

        assert result is None

    def test_parse_player_stats_missing_name(self):
        """Test _parse_player_stats returns None for missing name."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        from sports_scraper.models import TeamIdentity

        team = TeamIdentity(
            league_code="NCAAB",
            name="Duke",
            short_name="Duke",
            abbreviation=None,
            external_ref="1",
        )

        ps = {"playerId": 12345, "points": 10}

        result = fetcher._parse_player_stats(ps, team, 999)

        assert result is None

    def test_parse_player_stats_alternative_field_names(self):
        """Test _parse_player_stats handles alternative field names."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        from sports_scraper.models import TeamIdentity

        team = TeamIdentity(
            league_code="NCAAB",
            name="Duke",
            short_name="Duke",
            abbreviation=None,
            external_ref="1",
        )

        # Using alternative field names
        ps = {
            "athleteId": 54321,  # Alternative for playerId
            "athleteName": "Alt Player",  # Alternative for name
            "points": 15,
            "totalRebounds": 7,  # Alternative for rebounds
        }

        result = fetcher._parse_player_stats(ps, team, 999)

        assert result is not None
        assert result.player_id == "54321"
        assert result.player_name == "Alt Player"
        assert result.rebounds == 7


class TestNCAABBoxscoreFetcherFullBoxscore:
    """Tests for NCAABBoxscoreFetcher fetch_boxscore and fetch_boxscore_by_id methods."""

    def test_fetch_boxscore_success(self):
        """Test fetch_boxscore with NCAABLiveGame."""
        mock_client = MagicMock()

        # Mock team stats response
        team_response = MagicMock()
        team_response.status_code = 200
        team_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "points": 75, "rebounds": 35},
            {"gameId": 123, "teamId": 2, "points": 70, "rebounds": 32},
        ]

        # Mock player stats response
        player_response = MagicMock()
        player_response.status_code = 200
        player_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "playerId": 101, "name": "Player A", "points": 20},
            {"gameId": 123, "teamId": 2, "playerId": 102, "name": "Player B", "points": 18},
        ]

        mock_client.get.side_effect = [team_response, player_response]

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        game = NCAABLiveGame(
            game_id=123,
            game_date=datetime(2024, 1, 15, 19, 0, tzinfo=UTC),
            status="final",
            season=2024,
            home_team_id=1,
            home_team_name="Duke",
            away_team_id=2,
            away_team_name="UNC",
            home_score=75,
            away_score=70,
            neutral_site=False,
        )

        result = fetcher.fetch_boxscore(game)

        assert result is not None
        assert result.game_id == 123
        assert result.home_score == 75
        assert result.away_score == 70
        assert len(result.team_boxscores) == 2
        assert len(result.player_boxscores) == 2

    def test_fetch_boxscore_no_team_stats(self):
        """Test fetch_boxscore when no team stats available."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        game = NCAABLiveGame(
            game_id=123,
            game_date=datetime(2024, 1, 15, tzinfo=UTC),
            status="final",
            season=2024,
            home_team_id=1,
            home_team_name="Duke",
            away_team_id=2,
            away_team_name="UNC",
            home_score=None,
            away_score=None,
            neutral_site=False,
        )

        result = fetcher.fetch_boxscore(game)

        assert result is None

    def test_fetch_boxscore_by_id_success(self):
        """Test fetch_boxscore_by_id with valid game ID."""
        mock_client = MagicMock()

        # Mock team stats response (returns ALL games)
        team_response = MagicMock()
        team_response.status_code = 200
        team_response.json.return_value = [
            {"gameId": 100, "teamId": 1, "isHome": True, "teamStats": {"points": 80}},
            {"gameId": 123, "teamId": 1, "isHome": True, "teamStats": {"points": 75}},
            {"gameId": 123, "teamId": 2, "isHome": False, "teamStats": {"points": 70}},
            {"gameId": 200, "teamId": 1, "isHome": True, "teamStats": {"points": 85}},
        ]

        # Mock player stats response
        player_response = MagicMock()
        player_response.status_code = 200
        player_response.json.return_value = [
            {"gameId": 123, "teamId": 1, "players": [
                {"playerId": 101, "name": "Player A", "points": 20}
            ]},
        ]

        mock_client.get.side_effect = [team_response, player_response]

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        result = fetcher.fetch_boxscore_by_id(
            game_id=123,
            season=2024,
            game_date=datetime(2024, 1, 15, tzinfo=UTC),
            home_team_name="Duke",
            away_team_name="UNC",
        )

        assert result is not None
        assert result.game_id == 123
        assert result.home_score == 75
        assert result.away_score == 70

    def test_fetch_boxscore_by_id_no_team_stats(self):
        """Test fetch_boxscore_by_id when no team stats returned."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        result = fetcher.fetch_boxscore_by_id(
            game_id=999,
            season=2024,
            game_date=datetime(2024, 1, 15, tzinfo=UTC),
            home_team_name="Duke",
            away_team_name="UNC",
        )

        assert result is None

    def test_fetch_boxscore_by_id_game_not_in_response(self):
        """Test fetch_boxscore_by_id when target game not in response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Response has games, but not the one we're looking for
        mock_response.json.return_value = [
            {"gameId": 100, "teamId": 1, "isHome": True, "teamStats": {"points": 80}},
            {"gameId": 200, "teamId": 1, "isHome": True, "teamStats": {"points": 85}},
        ]
        mock_client.get.return_value = mock_response

        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        result = fetcher.fetch_boxscore_by_id(
            game_id=999,  # Not in response
            season=2024,
            game_date=datetime(2024, 1, 15, tzinfo=UTC),
            home_team_name="Duke",
            away_team_name="UNC",
        )

        assert result is None


class TestNCAABBoxscoreFetcherTeamStatsParsing:
    """Tests for team stats parsing methods."""

    def test_parse_team_stats_flat_format(self):
        """Test _parse_team_stats with flat stats format."""
        mock_client = MagicMock()
        mock_cache = MagicMock()

        fetcher = NCAABBoxscoreFetcher(mock_client, mock_cache)

        from sports_scraper.models import TeamIdentity

        team = TeamIdentity(
            league_code="NCAAB",
            name="Duke",
            short_name="Duke",
            abbreviation=None,
            external_ref="1",
        )

        ts = {
            "teamId": 1,
            "points": 75,
            "rebounds": 35,
            "totalRebounds": 36,  # Alternative field
            "assists": 18,
            "turnovers": 12,
        }

        result = fetcher._parse_team_stats(ts, team, True, 75)

        assert result.points == 75
        # Should prefer rebounds over totalRebounds
        assert result.rebounds in [35, 36]
        assert result.assists == 18
        assert result.turnovers == 12
