"""Tests for services/timeline_generator.py module."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from sports_scraper.services.timeline_generator import (
    SCHEDULED_DAYS_BACK,
    find_games_missing_timelines,
    find_games_needing_regeneration,
    find_all_games_needing_timelines,
    generate_timeline_for_game,
    generate_missing_timelines,
    generate_all_needed_timelines,
)


class TestScheduledDaysBack:
    """Tests for SCHEDULED_DAYS_BACK constant."""

    def test_default_is_4_days(self):
        """Default window is 4 days."""
        assert SCHEDULED_DAYS_BACK == 4

    def test_is_positive_integer(self):
        """Constant is a positive integer."""
        assert isinstance(SCHEDULED_DAYS_BACK, int)
        assert SCHEDULED_DAYS_BACK > 0


class TestFindGamesMissingTimelines:
    """Tests for find_games_missing_timelines function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty sequence when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = find_games_missing_timelines(mock_session, league_code="UNKNOWN")

        assert len(result) == 0

    def test_returns_empty_when_no_games(self):
        """Returns empty sequence when no games match criteria."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        # Setup mock chain for the complex query
        mock_session.query.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = find_games_missing_timelines(mock_session, league_code="NBA")

        assert len(result) == 0

    def test_returns_games_missing_timelines(self):
        """Returns games with PBP but missing timelines."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        mock_games = [
            (100, datetime(2024, 1, 15, 19, 0, 0, tzinfo=timezone.utc), "Boston Celtics", "Los Angeles Lakers"),
            (101, datetime(2024, 1, 16, 19, 0, 0, tzinfo=timezone.utc), "Miami Heat", "Chicago Bulls"),
        ]
        mock_session.query.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = mock_games

        result = find_games_missing_timelines(mock_session, league_code="NBA")

        assert len(result) == 2

    def test_applies_days_back_filter(self):
        """Applies days_back filter when specified."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.filter.return_value.order_by.return_value.filter.return_value.all.return_value = []

        result = find_games_missing_timelines(mock_session, league_code="NBA", days_back=7)

        # Should complete without error
        assert len(result) == 0


class TestFindGamesNeedingRegeneration:
    """Tests for find_games_needing_regeneration function."""

    def test_returns_empty_when_no_league(self):
        """Returns empty sequence when league not found."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = find_games_needing_regeneration(mock_session, league_code="UNKNOWN")

        assert len(result) == 0

    def test_returns_empty_when_no_games(self):
        """Returns empty sequence when no games need regeneration."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league
        mock_session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = find_games_needing_regeneration(mock_session, league_code="NBA")

        assert len(result) == 0

    def test_returns_games_with_stale_timelines(self):
        """Returns games with timelines older than data."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_league

        now = datetime.now(timezone.utc)
        old_timeline = now - timedelta(hours=2)
        new_pbp = now - timedelta(hours=1)

        mock_games = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers", new_pbp, None, old_timeline),
        ]
        mock_session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = mock_games

        result = find_games_needing_regeneration(mock_session, league_code="NBA")

        assert len(result) == 1
        assert result[0][4] == "pbp_updated"


class TestFindAllGamesNeedingTimelines:
    """Tests for find_all_games_needing_timelines function."""

    @patch("sports_scraper.services.timeline_generator.find_games_needing_regeneration")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_returns_empty_when_no_games(self, mock_missing, mock_stale):
        """Returns empty sequence when no games need timelines."""
        mock_missing.return_value = []
        mock_stale.return_value = []
        mock_session = MagicMock()

        result = find_all_games_needing_timelines(mock_session, league_code="NBA")

        assert len(result) == 0

    @patch("sports_scraper.services.timeline_generator.find_games_needing_regeneration")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_combines_missing_and_stale(self, mock_missing, mock_stale):
        """Combines missing and stale games."""
        mock_missing.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers"),
        ]
        mock_stale.return_value = [
            (101, datetime(2024, 1, 16), "Heat", "Bulls", "pbp_updated"),
        ]
        mock_session = MagicMock()

        result = find_all_games_needing_timelines(mock_session, league_code="NBA")

        assert len(result) == 2

    @patch("sports_scraper.services.timeline_generator.find_games_needing_regeneration")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_deduplicates_by_game_id(self, mock_missing, mock_stale):
        """Deduplicates games that appear in both lists."""
        mock_missing.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers"),
        ]
        mock_stale.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers", "pbp_updated"),  # Same game
        ]
        mock_session = MagicMock()

        result = find_all_games_needing_timelines(mock_session, league_code="NBA")

        # Should deduplicate, preferring missing over stale
        assert len(result) == 1
        assert result[0][4] == "missing"


class TestGenerateTimelineForGame:
    """Tests for generate_timeline_for_game function."""

    @patch("sports_scraper.services.timeline_generator.httpx.Client")
    def test_successful_generation(self, mock_client_class):
        """Successfully generates timeline via API."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_timeline_for_game(
            game_id=100,
            timeline_version="v1",
            api_base_url="http://localhost:8000",
        )

        assert result is True
        mock_client.post.assert_called_once()

    @patch("sports_scraper.services.timeline_generator.httpx.Client")
    def test_handles_http_error(self, mock_client_class):
        """Handles HTTP errors gracefully."""
        import httpx

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=mock_response,
        )
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_timeline_for_game(game_id=100)

        assert result is False

    @patch("sports_scraper.services.timeline_generator.httpx.Client")
    def test_handles_connection_error(self, mock_client_class):
        """Handles connection errors gracefully."""
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("Connection refused")
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_timeline_for_game(game_id=100)

        assert result is False

    @patch("sports_scraper.services.timeline_generator.settings")
    @patch("sports_scraper.services.timeline_generator.httpx.Client")
    def test_uses_settings_url_when_no_url_provided(self, mock_client_class, mock_settings):
        """Uses settings API URL when none provided."""
        mock_settings.api_internal_url = "http://api:8000"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_class.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_timeline_for_game(game_id=100)

        assert result is True


class TestGenerateMissingTimelines:
    """Tests for generate_missing_timelines function."""

    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_returns_zero_when_no_games(self, mock_find, mock_get_session):
        """Returns zero counts when no games found."""
        mock_find.return_value = []
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_missing_timelines(league_code="NBA")

        assert result["games_found"] == 0
        assert result["games_processed"] == 0
        assert result["games_successful"] == 0
        assert result["games_failed"] == 0

    @patch("sports_scraper.services.timeline_generator.time.sleep")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_processes_found_games(self, mock_find, mock_get_session, mock_generate, mock_sleep):
        """Processes found games and returns counts."""
        mock_find.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers"),
            (101, datetime(2024, 1, 16), "Heat", "Bulls"),
        ]
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_generate.return_value = True

        result = generate_missing_timelines(league_code="NBA")

        assert result["games_found"] == 2
        assert result["games_processed"] == 2
        assert result["games_successful"] == 2
        assert result["games_failed"] == 0

    @patch("sports_scraper.services.timeline_generator.time.sleep")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_respects_max_games_limit(self, mock_find, mock_get_session, mock_generate, mock_sleep):
        """Respects max_games limit."""
        mock_find.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers"),
            (101, datetime(2024, 1, 16), "Heat", "Bulls"),
            (102, datetime(2024, 1, 17), "Nets", "Knicks"),
        ]
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_generate.return_value = True

        result = generate_missing_timelines(league_code="NBA", max_games=2)

        assert result["games_found"] == 3
        assert result["games_processed"] == 2

    @patch("sports_scraper.services.timeline_generator.time.sleep")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_games_missing_timelines")
    def test_counts_failed_games(self, mock_find, mock_get_session, mock_generate, mock_sleep):
        """Counts failed game generations."""
        mock_find.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers"),
            (101, datetime(2024, 1, 16), "Heat", "Bulls"),
        ]
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_generate.side_effect = [True, False]  # First succeeds, second fails

        result = generate_missing_timelines(league_code="NBA")

        assert result["games_successful"] == 1
        assert result["games_failed"] == 1


class TestGenerateAllNeededTimelines:
    """Tests for generate_all_needed_timelines function."""

    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_all_games_needing_timelines")
    def test_returns_zero_when_no_games(self, mock_find, mock_get_session):
        """Returns zero counts when no games found."""
        mock_find.return_value = []
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = generate_all_needed_timelines(league_code="NBA")

        assert result["games_found"] == 0
        assert result["games_missing"] == 0
        assert result["games_stale"] == 0
        assert result["games_processed"] == 0

    @patch("sports_scraper.services.timeline_generator.time.sleep")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_all_games_needing_timelines")
    def test_processes_all_games(self, mock_find, mock_get_session, mock_generate, mock_sleep):
        """Processes all found games."""
        mock_find.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers", "missing"),
            (101, datetime(2024, 1, 16), "Heat", "Bulls", "pbp_updated"),
        ]
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_generate.return_value = True

        result = generate_all_needed_timelines(league_code="NBA")

        assert result["games_found"] == 2
        assert result["games_missing"] == 1
        assert result["games_stale"] == 1
        assert result["games_processed"] == 2
        assert result["games_successful"] == 2

    @patch("sports_scraper.services.timeline_generator.time.sleep")
    @patch("sports_scraper.services.timeline_generator.generate_timeline_for_game")
    @patch("sports_scraper.services.timeline_generator.get_session")
    @patch("sports_scraper.services.timeline_generator.find_all_games_needing_timelines")
    def test_respects_max_games(self, mock_find, mock_get_session, mock_generate, mock_sleep):
        """Respects max_games limit."""
        mock_find.return_value = [
            (100, datetime(2024, 1, 15), "Celtics", "Lakers", "missing"),
            (101, datetime(2024, 1, 16), "Heat", "Bulls", "missing"),
            (102, datetime(2024, 1, 17), "Nets", "Knicks", "pbp_updated"),
        ]
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_generate.return_value = True

        result = generate_all_needed_timelines(league_code="NBA", max_games=2)

        assert result["games_found"] == 3
        assert result["games_processed"] == 2


class TestModuleImports:
    """Tests for module imports."""

    def test_has_find_functions(self):
        """Module has find functions."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'find_games_missing_timelines')
        assert hasattr(timeline_generator, 'find_games_needing_regeneration')
        assert hasattr(timeline_generator, 'find_all_games_needing_timelines')

    def test_has_generate_functions(self):
        """Module has generate functions."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'generate_timeline_for_game')
        assert hasattr(timeline_generator, 'generate_missing_timelines')
        assert hasattr(timeline_generator, 'generate_all_needed_timelines')

    def test_has_constants(self):
        """Module has required constants."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'SCHEDULED_DAYS_BACK')
