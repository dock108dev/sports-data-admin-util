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

    @patch("sports_scraper.services.boxscore_ingestion.ingest_boxscores_via_nhl_api")
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

        mock_ingest.return_value = (5, 3)

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

    @patch("sports_scraper.services.boxscore_ingestion.ingest_boxscores_via_ncaab_api")
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

        mock_ingest.return_value = (10, 8)

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
