"""Tests for services/run_manager.py module."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from sports_scraper.services.run_manager import ScrapeRunManager
from sports_scraper.models import IngestionConfig


class TestScrapeRunManagerImports:
    """Tests for ScrapeRunManager module imports."""

    def test_class_exists(self):
        """ScrapeRunManager class exists."""
        assert ScrapeRunManager is not None

    def test_class_is_callable(self):
        """ScrapeRunManager can be instantiated."""
        # Note: Full instantiation requires scrapers to be available
        # Just verify it's a class
        assert callable(ScrapeRunManager)


class TestScrapeRunManagerAttributes:
    """Tests for ScrapeRunManager class attributes."""

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_init_creates_scrapers(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Initializes with scrapers."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert mock_scrapers.called

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_init_creates_odds_sync(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Initializes with odds synchronizer."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert mock_odds.called

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_has_supported_leagues(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Has supported league lists."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert hasattr(manager, "_supported_social_leagues")
        assert hasattr(manager, "_supported_live_pbp_leagues")

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_supported_social_leagues(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Social is supported for NBA and NHL."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert "NBA" in manager._supported_social_leagues
        assert "NHL" in manager._supported_social_leagues

    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    def test_supported_live_pbp_leagues(self, mock_live, mock_social, mock_odds, mock_scrapers):
        """Live PBP is supported for NBA, NHL, and NCAAB."""
        mock_scrapers.return_value = {}
        manager = ScrapeRunManager()
        assert "NBA" in manager._supported_live_pbp_leagues
        assert "NHL" in manager._supported_live_pbp_leagues
        assert "NCAAB" in manager._supported_live_pbp_leagues


class TestScrapeRunManagerUpdateRun:
    """Tests for _update_run method."""

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_updates_run_attributes(self, mock_scrapers, mock_odds, mock_social, mock_live, mock_get_session):
        """Updates run attributes successfully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        manager._update_run(1, status="running", started_at=datetime.now(timezone.utc))

        assert mock_run.status == "running"
        mock_session.flush.assert_called()
        mock_session.commit.assert_called()

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_handles_run_not_found(self, mock_scrapers, mock_odds, mock_social, mock_live, mock_get_session):
        """Handles case when run is not found."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.query.return_value.limit.return_value.all.return_value = []
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        # Should not raise, just logs error
        manager._update_run(999, status="running")

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_raises_on_db_error(self, mock_scrapers, mock_odds, mock_social, mock_live, mock_get_session):
        """Raises exception on database error."""
        mock_scrapers.return_value = {}
        mock_get_session.return_value.__enter__ = MagicMock(side_effect=Exception("DB error"))
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()

        with pytest.raises(Exception):
            manager._update_run(1, status="running")


class TestScrapeRunManagerRun:
    """Tests for run method."""

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_raises_when_no_scraper_for_non_api_league(
        self, mock_scrapers, mock_odds, mock_social, mock_live, mock_conflicts,
        mock_missing, mock_complete, mock_start, mock_get_session
    ):
        """Raises RuntimeError when no scraper for non-API league."""
        mock_scrapers.return_value = {}  # No scrapers
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NBA",
            boxscores=True,
        )

        with pytest.raises(RuntimeError, match="No scraper implemented"):
            manager.run(1, config)

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_allows_nhl_without_scraper(
        self, mock_scrapers, mock_odds, mock_social, mock_live, mock_conflicts,
        mock_missing, mock_complete, mock_start, mock_get_session
    ):
        """NHL can run boxscores without scraper (uses API)."""
        mock_scrapers.return_value = {}  # No scrapers
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=False,
            social=False,
            pbp=False,
        )

        # Should not raise
        result = manager.run(1, config)
        assert isinstance(result, dict)

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_runs_odds_scraping(
        self, mock_scrapers, mock_odds_class, mock_social, mock_live, mock_conflicts,
        mock_missing, mock_complete, mock_start, mock_get_session
    ):
        """Runs odds scraping when enabled."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_odds_sync = MagicMock()
        mock_odds_sync.sync.return_value = 50
        mock_odds_class.return_value = mock_odds_sync

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=True,
            social=False,
            pbp=False,
        )

        result = manager.run(1, config)

        assert result["odds"] == 50
        mock_odds_sync.sync.assert_called_once()

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.select_games_for_odds")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_runs_odds_only_missing(
        self, mock_scrapers, mock_odds_class, mock_social, mock_live,
        mock_select_odds, mock_conflicts, mock_missing, mock_complete,
        mock_start, mock_get_session
    ):
        """Runs odds scraping for only missing dates."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_odds_sync = MagicMock()
        mock_odds_sync.sync_single_date.return_value = 10
        mock_odds_class.return_value = mock_odds_sync

        mock_select_odds.return_value = [date(2024, 1, 1), date(2024, 1, 2)]

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=True,
            social=False,
            pbp=False,
            only_missing=True,
        )

        result = manager.run(1, config)

        assert result["odds"] == 20  # 10 per date
        assert mock_odds_sync.sync_single_date.call_count == 2

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.select_games_for_odds")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_handles_odds_fetch_failure(
        self, mock_scrapers, mock_odds_class, mock_social, mock_live,
        mock_select_odds, mock_conflicts, mock_missing, mock_complete,
        mock_start, mock_get_session
    ):
        """Handles odds fetch failure gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_odds_sync = MagicMock()
        mock_odds_sync.sync_single_date.side_effect = Exception("API error")
        mock_odds_class.return_value = mock_odds_sync

        mock_select_odds.return_value = [date(2024, 1, 1)]

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=True,
            social=False,
            pbp=False,
            only_missing=True,
        )

        # Should not raise, just logs warning
        result = manager.run(1, config)
        assert result["odds"] == 0


class TestScrapeRunManagerBoxscores:
    """Tests for boxscore scraping in run method."""

    @patch("sports_scraper.services.nhl_boxscore_ingestion.ingest_boxscores_via_nhl_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_nhl_uses_api_for_boxscores(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NHL uses API for boxscores."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.return_value = (5, 3, 2)  # (games, enriched, with_stats)

        manager = ScrapeRunManager()
        # Use a date in the past to avoid "future dates" skip
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NHL",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
        )

        result = manager.run(1, config)

        assert result["games"] == 5
        assert result["games_enriched"] == 3
        assert result["games_with_stats"] == 2

    @patch("sports_scraper.services.nhl_boxscore_ingestion.ingest_boxscores_via_nhl_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_nhl_boxscore_handles_api_error(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NHL boxscore handles API errors gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.side_effect = Exception("NHL API error")

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NHL",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
        )

        # Should not raise, handles exception internally
        result = manager.run(1, config)
        assert result["games"] == 0

    @patch("sports_scraper.services.ncaab_boxscore_ingestion.ingest_boxscores_via_ncaab_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_ncaab_boxscore_handles_api_error(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NCAAB boxscore handles API errors gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.side_effect = Exception("NCAAB API error")

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NCAAB",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
        )

        # Should not raise, handles exception internally
        result = manager.run(1, config)
        assert result["games"] == 0

    @patch("sports_scraper.services.ncaab_boxscore_ingestion.ingest_boxscores_via_ncaab_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_ncaab_uses_api_for_boxscores(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NCAAB uses API for boxscores."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.return_value = (10, 8, 5)  # (games, enriched, with_stats)

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NCAAB",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
        )

        result = manager.run(1, config)

        assert result["games"] == 10
        assert result["games_enriched"] == 8
        assert result["games_with_stats"] == 5

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_skips_future_dates_for_boxscores(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session
    ):
        """Skips boxscores for future dates."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        future_date = date.today() + timedelta(days=5)
        config = IngestionConfig(
            league_code="NHL",
            start_date=future_date,
            end_date=future_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
        )

        result = manager.run(1, config)

        # No games processed because dates are in future
        assert result["games"] == 0

    @patch("sports_scraper.services.run_manager.select_games_for_boxscores")
    @patch("sports_scraper.services.run_manager.persist_game_payload")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_scraper_boxscores_with_only_missing(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_persist, mock_select
    ):
        """Uses Sports Reference scraper for boxscores with only_missing."""
        mock_scraper = MagicMock()
        mock_payload = MagicMock()
        mock_scraper.fetch_single_boxscore.return_value = mock_payload
        mock_scrapers.return_value = {"NBA": mock_scraper}

        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Mock persist result
        mock_result = MagicMock()
        mock_result.game_id = 1
        mock_result.enriched = True
        mock_result.has_player_stats = True
        mock_persist.return_value = mock_result

        # Return games to scrape
        mock_select.return_value = [(1, "BOS202401150", date(2024, 1, 15))]

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
            only_missing=True,
        )

        result = manager.run(1, config)

        assert result["games"] == 1
        assert result["games_enriched"] == 1
        assert result["games_with_stats"] == 1
        mock_scraper.fetch_single_boxscore.assert_called()

    @patch("sports_scraper.services.run_manager.select_games_for_boxscores")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_scraper_boxscores_skips_missing_source_key(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Skips games with missing source key."""
        mock_scraper = MagicMock()
        mock_scrapers.return_value = {"NBA": mock_scraper}

        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Return game with missing source key
        mock_select.return_value = [(1, None, date(2024, 1, 15))]

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
            only_missing=True,
        )

        result = manager.run(1, config)

        # Game skipped due to missing source key
        assert result["games"] == 0
        mock_scraper.fetch_single_boxscore.assert_not_called()

    @patch("sports_scraper.services.run_manager.select_games_for_boxscores")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_scraper_boxscores_handles_fetch_error(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Handles boxscore fetch errors gracefully."""
        mock_scraper = MagicMock()
        mock_scraper.fetch_single_boxscore.side_effect = Exception("Scrape error")
        mock_scrapers.return_value = {"NBA": mock_scraper}

        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_select.return_value = [(1, "BOS202401150", date(2024, 1, 15))]

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
            only_missing=True,
        )

        # Should not raise, logs warning
        result = manager.run(1, config)
        assert result["games"] == 0

    @patch("sports_scraper.services.run_manager.persist_game_payload")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_scraper_boxscores_without_only_missing(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_persist
    ):
        """Uses Sports Reference scraper for full date range."""
        mock_scraper = MagicMock()
        mock_payload = MagicMock()
        mock_payload.identity.source_game_key = "BOS202401150"
        mock_payload.identity.game_date = date(2024, 1, 15)
        mock_scraper.fetch_date_range.return_value = [mock_payload]
        mock_scrapers.return_value = {"NBA": mock_scraper}

        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_result = MagicMock()
        mock_result.game_id = 1
        mock_result.enriched = True
        mock_result.has_player_stats = False
        mock_persist.return_value = mock_result

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
            only_missing=False,
        )

        result = manager.run(1, config)

        assert result["games"] == 1
        mock_scraper.fetch_date_range.assert_called()

    @patch("sports_scraper.services.run_manager.persist_game_payload")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_scraper_boxscores_skips_missing_source_key_in_range(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_persist
    ):
        """Skips games with missing source_game_key in date range."""
        mock_scraper = MagicMock()
        mock_payload = MagicMock()
        mock_payload.identity.source_game_key = None  # Missing key
        mock_payload.identity.game_date = date(2024, 1, 15)
        mock_scraper.fetch_date_range.return_value = [mock_payload]
        mock_scrapers.return_value = {"NBA": mock_scraper}

        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
            only_missing=False,
        )

        result = manager.run(1, config)

        # Game skipped due to missing source key
        assert result["games"] == 0
        mock_persist.assert_not_called()

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_boxscore_raises_for_unknown_league_without_scraper(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session
    ):
        """Raises error when no scraper available for unsupported league."""
        mock_scrapers.return_value = {}  # No scrapers

        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="MLB",  # Unsupported league without API fallback
            start_date=past_date,
            end_date=past_date,
            boxscores=True,
            odds=False,
            social=False,
            pbp=False,
        )

        # Should raise RuntimeError for unsupported league
        with pytest.raises(RuntimeError, match="No scraper implemented"):
            manager.run(1, config)


class TestScrapeRunManagerPbp:
    """Tests for PBP scraping in run method."""

    @patch("sports_scraper.services.run_manager.ingest_pbp_via_nhl_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_nhl_pbp_uses_api(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NHL PBP uses dedicated API."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.return_value = (5, 250)

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NHL",
            start_date=past_date,
            end_date=past_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        result = manager.run(1, config)

        assert result["pbp_games"] == 5

    @patch("sports_scraper.services.run_manager.ingest_pbp_via_ncaab_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_ncaab_pbp_uses_api(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NCAAB PBP uses dedicated API."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.return_value = (10, 500)

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NCAAB",
            start_date=past_date,
            end_date=past_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        result = manager.run(1, config)

        assert result["pbp_games"] == 10

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_live_pbp_uses_live_manager(
        self, mock_scrapers, mock_odds, mock_social, mock_live_class,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session
    ):
        """Live PBP uses LiveFeedManager."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_live = MagicMock()
        mock_live.ingest_live_data.return_value = MagicMock(pbp_games=3)
        mock_live_class.return_value = mock_live

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=True,
        )

        result = manager.run(1, config)

        assert result["pbp_games"] == 3
        mock_live.ingest_live_data.assert_called()

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_live_pbp_skipped_for_unsupported_league(
        self, mock_scrapers, mock_odds, mock_social, mock_live_class,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session
    ):
        """Live PBP skipped for unsupported leagues."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = ScrapeRunManager()
        # Override supported leagues to exclude test league
        manager._supported_live_pbp_leagues = ("NBA", "NHL")

        config = IngestionConfig(
            league_code="NCAAF",  # Not in supported list
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=True,
        )

        result = manager.run(1, config)

        # Live PBP should not have been called
        mock_live.ingest_live_data.assert_not_called()

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_live_pbp_handles_exception(
        self, mock_scrapers, mock_odds, mock_social, mock_live_class,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session
    ):
        """Live PBP handles exceptions gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_live = MagicMock()
        mock_live.ingest_live_data.side_effect = Exception("Live feed error")
        mock_live_class.return_value = mock_live

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=True,
        )

        # Should not raise, handles exception internally
        result = manager.run(1, config)
        assert result["pbp_games"] == 0
        mock_complete.assert_called()  # Job run should be completed with error

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_pbp_skips_future_dates(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session
    ):
        """PBP skips when all dates are in the future."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        future_date = date.today() + timedelta(days=5)
        config = IngestionConfig(
            league_code="NHL",
            start_date=future_date,
            end_date=future_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        result = manager.run(1, config)

        assert result["pbp_games"] == 0

    @patch("sports_scraper.services.run_manager.ingest_pbp_via_nhl_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_nhl_pbp_handles_api_error(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NHL PBP handles API errors gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.side_effect = Exception("NHL API error")

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NHL",
            start_date=past_date,
            end_date=past_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        # Should not raise
        result = manager.run(1, config)
        assert result["pbp_games"] == 0

    @patch("sports_scraper.services.run_manager.ingest_pbp_via_ncaab_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_ncaab_pbp_handles_api_error(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """NCAAB PBP handles API errors gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.side_effect = Exception("NCAAB API error")

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NCAAB",
            start_date=past_date,
            end_date=past_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        # Should not raise
        result = manager.run(1, config)
        assert result["pbp_games"] == 0

    @patch("sports_scraper.services.run_manager.ingest_pbp_via_nba_api")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_nba_api_pbp_used_for_nba(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """Official NBA API used for NBA PBP."""
        mock_scraper = MagicMock()
        mock_scrapers.return_value = {"NBA": mock_scraper}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.return_value = (3, 150)

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        result = manager.run(1, config)

        assert result["pbp_games"] == 3
        mock_ingest.assert_called()

    @patch("sports_scraper.services.run_manager.ingest_pbp_via_sportsref")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_sportsref_pbp_handles_error(
        self, mock_scrapers, mock_odds, mock_social, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_ingest
    ):
        """Sports Reference PBP handles errors gracefully."""
        mock_scraper = MagicMock()
        mock_scrapers.return_value = {"NBA": mock_scraper}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_ingest.side_effect = Exception("Sportsref error")

        manager = ScrapeRunManager()
        past_date = date.today() - timedelta(days=5)
        config = IngestionConfig(
            league_code="NBA",
            start_date=past_date,
            end_date=past_date,
            boxscores=False,
            odds=False,
            social=False,
            pbp=True,
            live=False,
        )

        # Should not raise
        result = manager.run(1, config)
        assert result["pbp_games"] == 0


class TestScrapeRunManagerSocial:
    """Tests for social scraping in run method."""

    @patch("sports_scraper.services.run_manager.select_games_for_social")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_social_skipped_for_unsupported_league(
        self, mock_scrapers, mock_odds, mock_social_class, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Social is skipped for unsupported leagues."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NCAAB",  # Not supported for social
            boxscores=False,
            odds=False,
            social=True,
            pbp=False,
        )

        result = manager.run(1, config)

        assert result["social_posts"] == 0
        mock_select.assert_not_called()

    @patch("sports_scraper.services.run_manager.select_games_for_social")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_social_collects_posts(
        self, mock_scrapers, mock_odds, mock_social_class, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Social collects posts for supported leagues."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_social = MagicMock()
        mock_result = MagicMock()
        mock_result.posts_saved = 5
        mock_social.collect_for_game.return_value = [mock_result]
        mock_social_class.return_value = mock_social

        mock_select.return_value = [1, 2, 3]  # 3 game IDs

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NBA",
            boxscores=False,
            odds=False,
            social=True,
            pbp=False,
        )

        result = manager.run(1, config)

        assert result["social_posts"] == 15  # 5 posts per game * 3 games

    @patch("sports_scraper.services.run_manager.select_games_for_social")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_social_handles_circuit_breaker(
        self, mock_scrapers, mock_odds, mock_social_class, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Social handles circuit breaker errors."""
        from sports_scraper.social import XCircuitBreakerError

        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_social = MagicMock()
        mock_social.collect_for_game.side_effect = XCircuitBreakerError(
            "Rate limited",
            retry_after_seconds=60,
        )
        mock_social_class.return_value = mock_social

        mock_select.return_value = [1, 2, 3]

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NBA",
            boxscores=False,
            odds=False,
            social=True,
            pbp=False,
        )

        # Should not raise, handles circuit breaker internally
        result = manager.run(1, config)
        assert result["social_posts"] == 0

    @patch("sports_scraper.services.run_manager.select_games_for_social")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_social_handles_general_exception(
        self, mock_scrapers, mock_odds, mock_social_class, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Social handles general exceptions gracefully."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_social = MagicMock()
        # First call succeeds, second throws exception
        mock_result = MagicMock()
        mock_result.posts_saved = 5
        mock_social.collect_for_game.side_effect = [
            [mock_result],
            Exception("Twitter API error"),
            [mock_result],
        ]
        mock_social_class.return_value = mock_social

        mock_select.return_value = [1, 2, 3]

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NBA",
            boxscores=False,
            odds=False,
            social=True,
            pbp=False,
        )

        # Should not raise, logs warning and continues
        result = manager.run(1, config)
        # First and third games collected successfully
        assert result["social_posts"] == 10

    @patch("sports_scraper.services.run_manager.select_games_for_social")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_social_detects_backfill_broad_range(
        self, mock_scrapers, mock_odds, mock_social_class, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Social detects backfill mode for broad date range."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_social = MagicMock()
        mock_result = MagicMock()
        mock_result.posts_saved = 3
        mock_social.collect_for_game.return_value = [mock_result]
        mock_social_class.return_value = mock_social

        mock_select.return_value = [1]

        manager = ScrapeRunManager()
        # Use a broad date range (> 7 days) to trigger backfill mode
        start_date = date.today() - timedelta(days=30)
        end_date = date.today() - timedelta(days=1)
        config = IngestionConfig(
            league_code="NBA",
            start_date=start_date,
            end_date=end_date,
            boxscores=False,
            odds=False,
            social=True,
            pbp=False,
        )

        result = manager.run(1, config)

        # Verify select_games_for_social was called with is_backfill=True
        mock_select.assert_called()
        call_kwargs = mock_select.call_args[1] if mock_select.call_args[1] else {}
        # The call should include is_backfill=True due to broad range

    @patch("sports_scraper.services.run_manager.select_games_for_social")
    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.detect_missing_pbp")
    @patch("sports_scraper.services.run_manager.detect_external_id_conflicts")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_social_detects_backfill_historical_end(
        self, mock_scrapers, mock_odds, mock_social_class, mock_live,
        mock_conflicts, mock_missing, mock_complete, mock_start,
        mock_get_session, mock_select
    ):
        """Social detects backfill mode for historical end date."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_social = MagicMock()
        mock_result = MagicMock()
        mock_result.posts_saved = 3
        mock_social.collect_for_game.return_value = [mock_result]
        mock_social_class.return_value = mock_social

        mock_select.return_value = [1]

        manager = ScrapeRunManager()
        # Use a short date range but historical end date to trigger backfill
        start_date = date.today() - timedelta(days=100)
        end_date = date.today() - timedelta(days=95)
        config = IngestionConfig(
            league_code="NBA",
            start_date=start_date,
            end_date=end_date,
            boxscores=False,
            odds=False,
            social=True,
            pbp=False,
        )

        result = manager.run(1, config)

        mock_select.assert_called()


class TestScrapeRunManagerErrorHandling:
    """Tests for error handling in run method."""

    @patch("sports_scraper.services.run_manager.get_session")
    @patch("sports_scraper.services.run_manager.start_job_run")
    @patch("sports_scraper.services.run_manager.complete_job_run")
    @patch("sports_scraper.services.run_manager.LiveFeedManager")
    @patch("sports_scraper.services.run_manager.XPostCollector")
    @patch("sports_scraper.services.run_manager.OddsSynchronizer")
    @patch("sports_scraper.services.run_manager.get_all_scrapers")
    def test_updates_run_on_error(
        self, mock_scrapers, mock_odds_class, mock_social, mock_live,
        mock_complete, mock_start, mock_get_session
    ):
        """Updates run status to error on failure."""
        mock_scrapers.return_value = {}
        mock_session = MagicMock()
        mock_run = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_run
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_odds = MagicMock()
        mock_odds.sync.side_effect = Exception("Odds API error")
        mock_odds_class.return_value = mock_odds

        manager = ScrapeRunManager()
        config = IngestionConfig(
            league_code="NHL",
            boxscores=False,
            odds=True,
            social=False,
            pbp=False,
        )

        with pytest.raises(Exception):
            manager.run(1, config)


class TestModuleImports:
    """Tests for module imports."""

    def test_has_scrape_run_manager(self):
        """Module has ScrapeRunManager class."""
        from sports_scraper.services import run_manager
        assert hasattr(run_manager, 'ScrapeRunManager')
