"""Tests for NFL live feed modules.

Covers:
- nfl_helpers.py: build_team_identity_from_espn, map_espn_game_status,
  map_espn_season_type, parse_espn_datetime
- nfl_pbp.py: NFLPbpFetcher
- nfl_boxscore.py: NFLBoxscoreFetcher
- nfl.py: NFLLiveFeedClient
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from sports_scraper.live.nfl_boxscore import NFLBoxscoreFetcher
from sports_scraper.live.nfl_helpers import (
    build_team_identity_from_espn,
    map_espn_game_status,
    map_espn_season_type,
    parse_espn_datetime,
)
from sports_scraper.live.nfl_pbp import NFL_PERIOD_MULTIPLIER, NFLPbpFetcher

# ---------------------------------------------------------------------------
# Shared mock data
# ---------------------------------------------------------------------------

MOCK_SCOREBOARD = {
    "events": [
        {
            "id": "401547417",
            "date": "2025-09-07T17:00Z",
            "status": {"type": {"name": "STATUS_FINAL", "shortDetail": "Final"}},
            "season": {"type": 2},
            "competitions": [
                {
                    "competitors": [
                        {
                            "team": {
                                "id": "1",
                                "abbreviation": "KC",
                                "displayName": "Kansas City Chiefs",
                                "shortDisplayName": "Chiefs",
                            },
                            "homeAway": "home",
                            "score": "27",
                        },
                        {
                            "team": {
                                "id": "2",
                                "abbreviation": "DET",
                                "displayName": "Detroit Lions",
                                "shortDisplayName": "Lions",
                            },
                            "homeAway": "away",
                            "score": "20",
                        },
                    ]
                }
            ],
        },
        {
            "id": "401547418",
            "date": "2025-08-10T19:00Z",
            "status": {"type": {"name": "STATUS_FINAL", "shortDetail": "Final"}},
            "season": {"type": 1},
            "competitions": [
                {
                    "competitors": [
                        {
                            "team": {
                                "id": "3",
                                "abbreviation": "GB",
                                "displayName": "Green Bay Packers",
                                "shortDisplayName": "Packers",
                            },
                            "homeAway": "home",
                            "score": "14",
                        },
                        {
                            "team": {
                                "id": "4",
                                "abbreviation": "CHI",
                                "displayName": "Chicago Bears",
                                "shortDisplayName": "Bears",
                            },
                            "homeAway": "away",
                            "score": "10",
                        },
                    ]
                }
            ],
        },
    ]
}


def _make_summary_payload(
    *,
    status_name: str = "STATUS_FINAL",
    drives: dict | None = None,
    boxscore: dict | None = None,
) -> dict:
    """Build a realistic ESPN summary payload for testing PBP and boxscore."""
    return {
        "header": {
            "competitions": [
                {
                    "status": {"type": {"name": status_name}},
                    "date": "2025-09-07T17:00Z",
                    "competitors": [
                        {
                            "team": {
                                "id": "1",
                                "abbreviation": "KC",
                                "displayName": "Kansas City Chiefs",
                                "shortDisplayName": "Chiefs",
                            },
                            "homeAway": "home",
                            "score": "27",
                        },
                        {
                            "team": {
                                "id": "2",
                                "abbreviation": "DET",
                                "displayName": "Detroit Lions",
                                "shortDisplayName": "Lions",
                            },
                            "homeAway": "away",
                            "score": "20",
                        },
                    ],
                }
            ]
        },
        "drives": drives or {"previous": []},
        "boxscore": boxscore or {"teams": [], "players": []},
    }


MOCK_DRIVES = {
    "previous": [
        {
            "plays": [
                {
                    "id": "1",
                    "type": {"id": "5", "text": "Rush"},
                    "text": "Player rushes for 5 yards",
                    "period": {"number": 1},
                    "clock": {"displayValue": "15:00"},
                    "start": {
                        "down": 1,
                        "distance": 10,
                        "yardLine": 25,
                        "team": {"abbreviation": "KC"},
                    },
                    "statYardage": 5,
                    "scoringPlay": False,
                    "homeScore": 0,
                    "awayScore": 0,
                },
                {
                    "id": "2",
                    "type": {"id": "24", "text": "Pass"},
                    "text": "QB completes pass for 15 yards",
                    "period": {"number": 1},
                    "clock": {"displayValue": "14:35"},
                    "start": {
                        "down": 2,
                        "distance": 5,
                        "yardLine": 30,
                        "team": {"abbreviation": "KC"},
                    },
                    "statYardage": 15,
                    "scoringPlay": False,
                    "homeScore": 0,
                    "awayScore": 0,
                },
            ]
        },
        {
            "plays": [
                {
                    "id": "3",
                    "type": {"id": "67", "text": "Touchdown"},
                    "text": "RB rushes for 2 yard TD",
                    "period": {"number": 2},
                    "clock": {"displayValue": "8:22"},
                    "start": {
                        "down": 1,
                        "distance": 2,
                        "yardLine": 2,
                        "team": {"abbreviation": "DET"},
                    },
                    "statYardage": 2,
                    "scoringPlay": True,
                    "homeScore": 0,
                    "awayScore": 7,
                },
            ]
        },
    ]
}

MOCK_BOXSCORE = {
    "teams": [
        {
            "team": {"abbreviation": "KC", "displayName": "Kansas City Chiefs"},
            "statistics": [
                {"name": "totalYards", "displayValue": "350"},
                {"name": "turnovers", "displayValue": "1"},
            ],
        },
        {
            "team": {"abbreviation": "DET", "displayName": "Detroit Lions"},
            "statistics": [
                {"name": "totalYards", "displayValue": "280"},
                {"name": "turnovers", "displayValue": "2"},
            ],
        },
    ],
    "players": [
        {
            "team": {"abbreviation": "KC", "displayName": "Kansas City Chiefs"},
            "statistics": [
                {
                    "name": "passing",
                    "labels": ["C/ATT", "YDS", "TD", "INT"],
                    "athletes": [
                        {
                            "athlete": {
                                "id": "1234",
                                "displayName": "Patrick Mahomes",
                                "position": {"abbreviation": "QB"},
                            },
                            "stats": ["25/35", "300", "3", "1"],
                        }
                    ],
                },
                {
                    "name": "rushing",
                    "labels": ["CAR", "YDS", "TD", "LONG"],
                    "athletes": [
                        {
                            "athlete": {
                                "id": "5678",
                                "displayName": "Isiah Pacheco",
                                "position": {"abbreviation": "RB"},
                            },
                            "stats": ["18", "95", "1", "22"],
                        }
                    ],
                },
            ],
        },
        {
            "team": {"abbreviation": "DET", "displayName": "Detroit Lions"},
            "statistics": [
                {
                    "name": "passing",
                    "labels": ["C/ATT", "YDS", "TD", "INT"],
                    "athletes": [
                        {
                            "athlete": {
                                "id": "9012",
                                "displayName": "Jared Goff",
                                "position": {"abbreviation": "QB"},
                            },
                            "stats": ["22/30", "240", "2", "1"],
                        }
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# nfl_helpers.py
# ---------------------------------------------------------------------------


class TestBuildTeamIdentityFromEspn:
    """Tests for build_team_identity_from_espn."""

    def test_builds_identity_from_team_data(self):
        team_data = {
            "id": "12",
            "abbreviation": "KC",
            "displayName": "Kansas City Chiefs",
            "shortDisplayName": "Chiefs",
        }
        identity = build_team_identity_from_espn(team_data)
        assert identity.league_code == "NFL"
        assert "Kansas City" in identity.name or "Chiefs" in identity.name
        assert identity.external_ref == "12"

    def test_handles_empty_team_data(self):
        identity = build_team_identity_from_espn({})
        assert identity.league_code == "NFL"
        # Should not crash with empty data
        assert identity.name is not None

    def test_handles_missing_team_key(self):
        comp = {}
        identity = build_team_identity_from_espn(comp)
        assert identity.league_code == "NFL"


class TestMapEspnGameStatus:
    """Tests for map_espn_game_status."""

    def test_final(self):
        assert map_espn_game_status("STATUS_FINAL") == "final"

    def test_end_period(self):
        assert map_espn_game_status("STATUS_END_PERIOD") == "live"

    def test_in_progress(self):
        assert map_espn_game_status("STATUS_IN_PROGRESS") == "live"

    def test_halftime(self):
        assert map_espn_game_status("STATUS_HALFTIME") == "live"

    def test_scheduled(self):
        assert map_espn_game_status("STATUS_SCHEDULED") == "scheduled"

    def test_postponed(self):
        assert map_espn_game_status("STATUS_POSTPONED") == "postponed"

    def test_unknown_defaults_to_scheduled(self):
        assert map_espn_game_status("STATUS_UNKNOWN_BLAH") == "scheduled"

    def test_empty_string_defaults_to_scheduled(self):
        assert map_espn_game_status("") == "scheduled"


class TestMapEspnSeasonType:
    """Tests for map_espn_season_type."""

    def test_preseason(self):
        assert map_espn_season_type(1) == "preseason"

    def test_regular_season(self):
        assert map_espn_season_type(2) == "regular"

    def test_postseason(self):
        assert map_espn_season_type(3) == "postseason"

    def test_unknown_defaults_to_regular(self):
        assert map_espn_season_type(99) == "regular"


class TestParseEspnDatetime:
    """Tests for parse_espn_datetime."""

    def test_parses_espn_format(self):
        result = parse_espn_datetime("2025-09-07T17:00Z")
        assert result.year == 2025
        assert result.month == 9
        assert result.day == 7
        assert result.hour == 17
        assert result.tzinfo is not None

    def test_none_returns_now_utc(self):
        result = parse_espn_datetime(None)
        assert result.tzinfo is not None
        # Should be close to now
        diff = abs((datetime.now(UTC) - result).total_seconds())
        assert diff < 5

    def test_empty_string_returns_now_utc(self):
        result = parse_espn_datetime("")
        assert result.tzinfo is not None

    def test_invalid_string_returns_now_utc(self):
        result = parse_espn_datetime("not-a-date")
        assert result.tzinfo is not None

    def test_iso_format_with_offset(self):
        result = parse_espn_datetime("2025-09-07T13:00:00-04:00")
        assert result.year == 2025
        assert result.tzinfo is not None


# ---------------------------------------------------------------------------
# nfl_pbp.py - NFLPbpFetcher
# ---------------------------------------------------------------------------


class TestNFLPbpFetcherInit:
    """Tests for NFLPbpFetcher initialization."""

    def test_stores_client_and_cache(self):
        client = MagicMock()
        cache = MagicMock()
        fetcher = NFLPbpFetcher(client, cache)
        assert fetcher.client is client
        assert fetcher._cache is cache


class TestNFLPbpFetcherCacheHit:
    """Tests for PBP cache behavior."""

    def test_returns_cached_data(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = _make_summary_payload(drives=MOCK_DRIVES)

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("401547417")

        assert result.source_game_key == "401547417"
        assert len(result.plays) == 3
        # Client should NOT be called when cache hits
        client.get.assert_not_called()

    def test_cache_miss_fetches_from_api(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _make_summary_payload(drives=MOCK_DRIVES)
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("401547417")

        assert len(result.plays) == 3
        client.get.assert_called_once()


class TestNFLPbpFetcherParsing:
    """Tests for PBP parsing logic."""

    def _make_fetcher(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _make_summary_payload(drives=MOCK_DRIVES)
        client.get.return_value = response
        return NFLPbpFetcher(client, cache)

    def test_play_count(self):
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        assert len(result.plays) == 3

    def test_play_index_calculation(self):
        """play_index = period * 10000 + seq."""
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        plays = result.plays

        # First two plays are period 1 (seq 0, 1)
        assert plays[0].play_index == 1 * NFL_PERIOD_MULTIPLIER + 0
        assert plays[1].play_index == 1 * NFL_PERIOD_MULTIPLIER + 1
        # Third play is period 2 (seq 0 within period 2)
        assert plays[2].play_index == 2 * NFL_PERIOD_MULTIPLIER + 0

    def test_play_type_extracted(self):
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        assert result.plays[0].play_type == "RUSH"
        assert result.plays[1].play_type == "PASS"
        assert result.plays[2].play_type == "TOUCHDOWN"

    def test_team_abbreviation_from_start_block(self):
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        assert result.plays[0].team_abbreviation == "KC"
        assert result.plays[2].team_abbreviation == "DET"

    def test_description_populated(self):
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        assert result.plays[0].description == "Player rushes for 5 yards"

    def test_scores_populated(self):
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        # Scoring touchdown
        td_play = result.plays[2]
        assert td_play.home_score == 0
        assert td_play.away_score == 7

    def test_raw_data_contains_down_distance(self):
        fetcher = self._make_fetcher()
        result = fetcher.fetch_play_by_play("401547417")
        raw = result.plays[0].raw_data
        assert raw["start_down"] == 1
        assert raw["start_distance"] == 10
        assert raw["start_yard_line"] == 25
        assert raw["yards"] == 5
        assert raw["scoring_play"] is False

    def test_deduplication(self):
        """Duplicate plays with same (period, clock, type, team) are removed."""
        duplicate_drives = {
            "previous": [
                {
                    "plays": [
                        {
                            "id": "1",
                            "type": {"id": "5", "text": "Rush"},
                            "text": "Same play",
                            "period": {"number": 1},
                            "clock": {"displayValue": "15:00"},
                            "start": {"team": {"abbreviation": "KC"}},
                            "homeScore": 0,
                            "awayScore": 0,
                        },
                        {
                            "id": "1b",
                            "type": {"id": "5", "text": "Rush"},
                            "text": "Same play",
                            "period": {"number": 1},
                            "clock": {"displayValue": "15:00"},
                            "start": {"team": {"abbreviation": "KC"}},
                            "homeScore": 0,
                            "awayScore": 0,
                        },
                    ]
                }
            ]
        }
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _make_summary_payload(drives=duplicate_drives)
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("401547417")
        # Should be deduped to 1
        assert len(result.plays) == 1


class TestNFLPbpFetcherErrors:
    """Tests for PBP error handling."""

    def test_404_returns_empty_plays(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 404
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("999999")

        assert result.source_game_key == "999999"
        assert result.plays == []

    def test_500_returns_empty_plays(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("999999")
        assert result.plays == []

    def test_network_exception_returns_empty_plays(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        client.get.side_effect = Exception("Connection timeout")

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("401547417")
        assert result.plays == []

    def test_empty_drives_returns_empty_plays(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _make_summary_payload(drives={"previous": []})
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        result = fetcher.fetch_play_by_play("401547417")
        assert result.plays == []


class TestNFLPbpCaching:
    """Tests for PBP caching behavior."""

    def test_caches_final_game_with_plays(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None

        response = MagicMock()
        response.status_code = 200
        payload = _make_summary_payload(
            drives=MOCK_DRIVES, status_name="STATUS_FINAL"
        )
        response.json.return_value = payload
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        fetcher.fetch_play_by_play("401547417")

        cache.put.assert_called_once()
        args = cache.put.call_args[0]
        assert args[0] == "pbp_401547417"

    def test_does_not_cache_live_game(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None

        response = MagicMock()
        response.status_code = 200
        payload = _make_summary_payload(
            drives=MOCK_DRIVES, status_name="STATUS_IN_PROGRESS"
        )
        response.json.return_value = payload
        client.get.return_value = response

        fetcher = NFLPbpFetcher(client, cache)
        fetcher.fetch_play_by_play("401547417")

        cache.put.assert_not_called()


# ---------------------------------------------------------------------------
# nfl_boxscore.py - NFLBoxscoreFetcher
# ---------------------------------------------------------------------------


class TestNFLBoxscoreFetcherInit:
    """Tests for NFLBoxscoreFetcher initialization."""

    def test_stores_client_and_cache(self):
        client = MagicMock()
        cache = MagicMock()
        fetcher = NFLBoxscoreFetcher(client, cache)
        assert fetcher.client is client
        assert fetcher._cache is cache


class TestNFLBoxscoreFetcherParsing:
    """Tests for boxscore parsing."""

    def _fetch(self, boxscore=None):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _make_summary_payload(
            boxscore=boxscore or MOCK_BOXSCORE
        )
        client.get.return_value = response
        fetcher = NFLBoxscoreFetcher(client, cache)
        return fetcher.fetch_boxscore("401547417")

    def test_extracts_home_and_away_teams(self):
        result = self._fetch()
        assert result is not None
        assert "Kansas City" in result.home_team.name or "Chiefs" in result.home_team.name
        assert "Detroit" in result.away_team.name or "Lions" in result.away_team.name

    def test_extracts_scores(self):
        result = self._fetch()
        assert result.home_score == 27
        assert result.away_score == 20

    def test_status_mapped(self):
        result = self._fetch()
        assert result.status == "final"

    def test_team_boxscores_extracted(self):
        result = self._fetch()
        assert len(result.team_boxscores) == 2

        # Find KC team boxscore
        kc_box = [t for t in result.team_boxscores if t.team.abbreviation in ("KC", "KAN")]
        assert len(kc_box) == 1
        assert kc_box[0].raw_stats.get("totalYards") == "350"
        assert kc_box[0].raw_stats.get("turnovers") == "1"

    def test_player_boxscores_extracted(self):
        result = self._fetch()
        # 3 players total: Mahomes (passing), Pacheco (rushing), Goff (passing)
        assert len(result.player_boxscores) == 3

    def test_player_stats_labels_mapped(self):
        result = self._fetch()
        mahomes = [p for p in result.player_boxscores if p.player_name == "Patrick Mahomes"]
        assert len(mahomes) == 1
        assert mahomes[0].raw_stats["C/ATT"] == "25/35"
        assert mahomes[0].raw_stats["YDS"] == "300"
        assert mahomes[0].raw_stats["TD"] == "3"
        assert mahomes[0].raw_stats["INT"] == "1"
        assert mahomes[0].raw_stats["category"] == "passing"

    def test_player_position_extracted(self):
        result = self._fetch()
        mahomes = [p for p in result.player_boxscores if p.player_name == "Patrick Mahomes"]
        assert mahomes[0].position == "QB"

    def test_player_team_assigned(self):
        result = self._fetch()
        goff = [p for p in result.player_boxscores if p.player_name == "Jared Goff"]
        assert len(goff) == 1
        # Goff should be on away team (DET)
        assert goff[0].team.abbreviation in ("DET",) or "Detroit" in goff[0].team.name


class TestNFLBoxscoreFetcherErrors:
    """Tests for boxscore error handling."""

    def test_404_returns_none(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 404
        client.get.return_value = response

        fetcher = NFLBoxscoreFetcher(client, cache)
        result = fetcher.fetch_boxscore("999999")
        assert result is None

    def test_500_returns_none(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 500
        response.text = "Server Error"
        client.get.return_value = response

        fetcher = NFLBoxscoreFetcher(client, cache)
        result = fetcher.fetch_boxscore("999999")
        assert result is None

    def test_network_exception_returns_none(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        client.get.side_effect = Exception("DNS failure")

        fetcher = NFLBoxscoreFetcher(client, cache)
        result = fetcher.fetch_boxscore("401547417")
        assert result is None

    def test_returns_cached_boxscore(self):
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = _make_summary_payload(boxscore=MOCK_BOXSCORE)

        fetcher = NFLBoxscoreFetcher(client, cache)
        result = fetcher.fetch_boxscore("401547417")

        assert result is not None
        assert result.home_score == 27
        client.get.assert_not_called()

    def test_empty_boxscore_players(self):
        """When players section is empty, still returns result with empty player list."""
        client = MagicMock()
        cache = MagicMock()
        cache.get.return_value = None
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = _make_summary_payload(
            boxscore={"teams": [], "players": []}
        )
        client.get.return_value = response

        fetcher = NFLBoxscoreFetcher(client, cache)
        result = fetcher.fetch_boxscore("401547417")
        assert result is not None
        assert result.player_boxscores == []


# ---------------------------------------------------------------------------
# nfl.py - NFLLiveFeedClient
# ---------------------------------------------------------------------------


class TestNFLLiveFeedClientScoreboard:
    """Tests for NFLLiveFeedClient scoreboard parsing."""

    @patch("sports_scraper.live.nfl.settings")
    def test_parse_scoreboard_games(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()

        # _parse_scoreboard_response requires (payload, target_date)
        games = client_obj._parse_scoreboard_response(MOCK_SCOREBOARD, date(2025, 9, 7))

        assert len(games) == 2

    @patch("sports_scraper.live.nfl.settings")
    def test_regular_season_game(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        games = client_obj._parse_scoreboard_response(MOCK_SCOREBOARD, date(2025, 9, 7))

        # game_id is an int
        regular = [g for g in games if g.game_id == 401547417]
        assert len(regular) == 1
        assert regular[0].season_type == "regular"
        assert regular[0].status == "final"
        assert regular[0].home_score == 27
        assert regular[0].away_score == 20

    @patch("sports_scraper.live.nfl.settings")
    def test_preseason_game_season_type(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        games = client_obj._parse_scoreboard_response(MOCK_SCOREBOARD, date(2025, 9, 7))

        preseason = [g for g in games if g.game_id == 401547418]
        assert len(preseason) == 1
        assert preseason[0].season_type == "preseason"

    @patch("sports_scraper.live.nfl.settings")
    def test_game_date_parsed(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        games = client_obj._parse_scoreboard_response(MOCK_SCOREBOARD, date(2025, 9, 7))

        game = games[0]
        assert game.game_date.year == 2025
        assert game.game_date.month == 9
        assert game.game_date.day == 7

    @patch("sports_scraper.live.nfl.settings")
    def test_status_text_populated(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        games = client_obj._parse_scoreboard_response(MOCK_SCOREBOARD, date(2025, 9, 7))
        assert games[0].status_text == "Final"

    @patch("sports_scraper.live.nfl.settings")
    def test_empty_events_returns_empty_list(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        games = client_obj._parse_scoreboard_response({"events": []}, date(2025, 9, 7))
        assert games == []

    @patch("sports_scraper.live.nfl.settings")
    def test_event_without_competitions_skipped(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        bad_payload = {
            "events": [
                {
                    "id": "999",
                    "date": "2025-09-07T17:00Z",
                    "status": {"type": {"name": "STATUS_FINAL"}},
                    "season": {"type": 2},
                    "competitions": [],
                }
            ]
        }
        games = client_obj._parse_scoreboard_response(bad_payload, date(2025, 9, 7))
        assert games == []

    @patch("sports_scraper.live.nfl.settings")
    def test_live_status_mapped(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        live_payload = {
            "events": [
                {
                    "id": "401547420",
                    "date": "2025-09-07T20:00Z",
                    "status": {
                        "type": {
                            "name": "STATUS_IN_PROGRESS",
                            "shortDetail": "Q3 8:22",
                        }
                    },
                    "season": {"type": 2},
                    "competitions": [
                        {
                            "competitors": [
                                {
                                    "team": {
                                        "id": "5",
                                        "abbreviation": "BUF",
                                        "displayName": "Buffalo Bills",
                                        "shortDisplayName": "Bills",
                                    },
                                    "homeAway": "home",
                                    "score": "17",
                                },
                                {
                                    "team": {
                                        "id": "6",
                                        "abbreviation": "MIA",
                                        "displayName": "Miami Dolphins",
                                        "shortDisplayName": "Dolphins",
                                    },
                                    "homeAway": "away",
                                    "score": "14",
                                },
                            ]
                        }
                    ],
                }
            ]
        }

        client_obj = NFLLiveFeedClient()
        games = client_obj._parse_scoreboard_response(live_payload, date(2025, 9, 7))
        assert len(games) == 1
        assert games[0].status == "live"
        assert games[0].status_text == "Q3 8:22"


class TestNFLLiveFeedClientFetchSchedule:
    """Tests for the full fetch_schedule flow with mocked HTTP."""

    @patch("sports_scraper.live.nfl.settings")
    def test_fetch_schedule_success(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = MOCK_SCOREBOARD
        client_obj.client = MagicMock()
        client_obj.client.get.return_value = mock_response

        games = client_obj.fetch_schedule(date(2025, 9, 7), date(2025, 9, 7))
        assert len(games) == 2

    @patch("sports_scraper.live.nfl.settings")
    def test_fetch_schedule_non_200_returns_empty(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()

        mock_response = MagicMock()
        mock_response.status_code = 503
        client_obj.client = MagicMock()
        client_obj.client.get.return_value = mock_response

        games = client_obj.fetch_schedule(date(2025, 9, 7), date(2025, 9, 7))
        assert games == []

    @patch("sports_scraper.live.nfl.settings")
    def test_fetch_schedule_exception_returns_empty(self, mock_settings):
        mock_settings.scraper_config.request_timeout_seconds = 10
        mock_settings.scraper_config.html_cache_dir = "/tmp/test_cache"

        from sports_scraper.live.nfl import NFLLiveFeedClient
        from datetime import date

        client_obj = NFLLiveFeedClient()
        client_obj.client = MagicMock()
        client_obj.client.get.side_effect = Exception("Network error")

        games = client_obj.fetch_schedule(date(2025, 9, 7), date(2025, 9, 7))
        assert games == []
