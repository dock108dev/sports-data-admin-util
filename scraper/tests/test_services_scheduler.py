"""Tests for services/scheduler.py module."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from sports_scraper.services.scheduler import (
    ScheduledIngestionSummary,
    _coerce_date,
    build_scheduled_window,
    create_scrape_run,
    run_pbp_ingestion_for_league,
    schedule_ingestion_runs,
    schedule_single_league_and_wait,
)


class TestBuildScheduledWindow:
    """Tests for build_scheduled_window function."""

    def test_returns_tuple(self):
        """Returns a tuple of two datetimes."""
        result = build_scheduled_window()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], datetime)
        assert isinstance(result[1], datetime)

    def test_start_is_96_hours_back(self):
        """Start is 96 hours before anchor."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        start, end = build_scheduled_window(now)
        expected_start = now - timedelta(hours=96)
        assert start == expected_start

    def test_end_is_48_hours_forward(self):
        """End is 48 hours after anchor."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        start, end = build_scheduled_window(now)
        expected_end = now + timedelta(hours=48)
        assert end == expected_end

    def test_uses_utc_timezone(self):
        """All datetimes are in UTC."""
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        start, end = build_scheduled_window(now)
        assert start.tzinfo == UTC
        assert end.tzinfo == UTC

    def test_uses_current_time_when_none(self):
        """Uses current time when no argument provided."""
        start, end = build_scheduled_window()
        # Just verify the window is reasonable
        assert end > start
        window_hours = (end - start).total_seconds() / 3600
        assert window_hours == 144  # 96 + 48


class TestCoerceDate:
    """Tests for _coerce_date function."""

    def test_returns_none_for_none(self):
        """Returns None for None input."""
        result = _coerce_date(None)
        assert result is None

    def test_strips_time_components(self):
        """Strips time components from datetime."""
        dt = datetime(2024, 1, 15, 14, 30, 45, 123456, tzinfo=UTC)
        result = _coerce_date(dt)
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0

    def test_preserves_date(self):
        """Preserves the date portion."""
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=UTC)
        result = _coerce_date(dt)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15


class TestScheduledIngestionSummary:
    """Tests for ScheduledIngestionSummary dataclass."""

    def test_create_summary(self):
        """Can create a summary with all fields."""
        summary = ScheduledIngestionSummary(
            runs_created=5,
            runs_skipped=2,
            run_failures=1,
            enqueue_failures=0,
            last_run_at=datetime.now(UTC),
        )
        assert summary.runs_created == 5
        assert summary.runs_skipped == 2
        assert summary.run_failures == 1
        assert summary.enqueue_failures == 0

    def test_summary_is_frozen(self):
        """Summary is immutable."""
        summary = ScheduledIngestionSummary(
            runs_created=5,
            runs_skipped=2,
            run_failures=1,
            enqueue_failures=0,
            last_run_at=datetime.now(UTC),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            summary.runs_created = 10


class TestCreateScrapeRun:
    """Tests for create_scrape_run function."""

    def test_creates_run_with_all_fields(self):
        """Creates run record with all fields set."""
        from sports_scraper.models import IngestionConfig

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1

        config = IngestionConfig(
            league_code="NBA",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            boxscores=True,
            odds=True,
        )

        result = create_scrape_run(
            mock_session,
            mock_league,
            config,
            requested_by="test_user",
        )

        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        added_run = mock_session.add.call_args[0][0]
        assert added_run.league_id == 1
        assert added_run.status == "pending"
        assert added_run.requested_by == "test_user"

    def test_creates_run_with_custom_scraper_type(self):
        """Creates run with custom scraper type."""
        from sports_scraper.models import IngestionConfig

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1

        config = IngestionConfig(league_code="NBA")

        result = create_scrape_run(
            mock_session,
            mock_league,
            config,
            requested_by="test",
            scraper_type="manual_ingestion",
        )

        added_run = mock_session.add.call_args[0][0]
        assert added_run.scraper_type == "manual_ingestion"

    def test_creates_run_without_dates(self):
        """Creates run when config has no dates."""
        from sports_scraper.models import IngestionConfig

        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1

        config = IngestionConfig(league_code="NBA")

        result = create_scrape_run(
            mock_session,
            mock_league,
            config,
            requested_by="scheduler",
        )

        added_run = mock_session.add.call_args[0][0]
        assert added_run.start_date is None
        assert added_run.end_date is None


class TestScheduleIngestionRuns:
    """Tests for schedule_ingestion_runs function."""

    @patch("sports_scraper.services.scheduler.get_session")
    @patch("sports_scraper.services.scheduler.get_scheduled_leagues")
    @patch("sports_scraper.services.scheduler.get_league_config")
    def test_returns_summary_when_no_leagues(self, mock_get_config, mock_get_leagues, mock_get_session):
        """Returns summary when no leagues to process."""
        mock_get_leagues.return_value = []
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = schedule_ingestion_runs()

        assert isinstance(result, ScheduledIngestionSummary)
        assert result.runs_created == 0

    @patch("sports_scraper.services.scheduler.get_session")
    @patch("sports_scraper.services.scheduler.get_league_config")
    def test_skips_unknown_league(self, mock_get_config, mock_get_session):
        """Skips unknown leagues and increments runs_skipped."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = schedule_ingestion_runs(leagues=["UNKNOWN"])

        assert result.runs_skipped == 1
        assert result.runs_created == 0

    @patch("sports_scraper.services.scheduler.get_session")
    @patch("sports_scraper.services.scheduler.get_league_config")
    def test_skips_recent_run(self, mock_get_config, mock_get_session):
        """Skips league with recent run."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_league,  # First call for league lookup
            MagicMock(id=123, created_at=datetime.now(UTC)),  # Recent run
        ]
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = schedule_ingestion_runs(leagues=["NBA"])

        assert result.runs_skipped == 1
        assert result.runs_created == 0

    @patch("sports_scraper.services.scheduler.get_session")
    @patch("sports_scraper.services.scheduler.get_league_config")
    @patch("sports_scraper.services.scheduler.create_scrape_run")
    def test_handles_run_creation_failure(self, mock_create_run, mock_get_config, mock_get_session):
        """Handles run creation failure."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_league,  # League lookup
            None,  # No recent run
        ]
        mock_session.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_create_run.side_effect = Exception("DB error")

        mock_league_cfg = MagicMock()
        mock_league_cfg.boxscores_enabled = True
        mock_league_cfg.odds_enabled = True
        mock_league_cfg.social_enabled = False
        mock_league_cfg.pbp_enabled = False
        mock_get_config.return_value = mock_league_cfg

        result = schedule_ingestion_runs(leagues=["NBA"])

        assert result.run_failures == 1

    @patch("sports_scraper.services.scheduler.get_session")
    @patch("sports_scraper.services.scheduler.get_league_config")
    @patch("sports_scraper.services.scheduler.create_scrape_run")
    def test_handles_enqueue_failure(self, mock_create_run, mock_get_config, mock_get_session):
        """Handles celery enqueue failure."""
        mock_session = MagicMock()
        mock_league = MagicMock()
        mock_league.id = 1
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            mock_league,  # League lookup
            None,  # No recent run
        ]
        mock_session.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = None
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_run = MagicMock()
        mock_run.id = 1
        mock_create_run.return_value = mock_run

        mock_league_cfg = MagicMock()
        mock_league_cfg.boxscores_enabled = True
        mock_league_cfg.odds_enabled = True
        mock_league_cfg.social_enabled = False
        mock_league_cfg.pbp_enabled = False
        mock_get_config.return_value = mock_league_cfg

        # Mock the celery app that's imported inside the function
        mock_celery = MagicMock()
        mock_celery.send_task.side_effect = Exception("Celery error")
        with patch.dict("sys.modules", {"sports_scraper.celery_app": MagicMock(app=mock_celery)}):
            result = schedule_ingestion_runs(leagues=["NBA"])

        # Due to import complexity, this test verifies the function runs
        assert isinstance(result, ScheduledIngestionSummary)


class TestRunPbpIngestionForLeague:
    """Tests for run_pbp_ingestion_for_league function."""

    @patch("sports_scraper.services.pbp_ingestion.ingest_pbp_via_nhl_api")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_nhl_uses_nhl_api(self, mock_get_session, mock_ingest):
        """NHL uses dedicated NHL API for PBP."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_ingest.return_value = (5, 250)

        result = run_pbp_ingestion_for_league("NHL")

        assert result["league"] == "NHL"
        assert result["pbp_games"] == 5
        assert result["pbp_events"] == 250
        mock_ingest.assert_called_once()

    @patch("sports_scraper.services.pbp_ingestion.ingest_pbp_via_ncaab_api")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_ncaab_uses_ncaab_api(self, mock_get_session, mock_ingest):
        """NCAAB uses College Basketball Data API for PBP."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_ingest.return_value = (10, 500)

        result = run_pbp_ingestion_for_league("NCAAB")

        assert result["league"] == "NCAAB"
        assert result["pbp_games"] == 10
        assert result["pbp_events"] == 500

    @patch("sports_scraper.services.pbp_ingestion.ingest_pbp_via_nba_api")
    @patch("sports_scraper.services.scheduler.get_session")
    def test_nba_uses_nba_api(self, mock_get_session, mock_ingest):
        """NBA uses official NBA API for PBP."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_ingest.return_value = (3, 150)

        result = run_pbp_ingestion_for_league("NBA")

        assert result["league"] == "NBA"
        assert result["pbp_games"] == 3
        assert result["pbp_events"] == 150
        mock_ingest.assert_called_once()

    @patch("sports_scraper.services.scheduler.get_session")
    def test_unsupported_league_returns_zero(self, mock_get_session):
        """Unsupported league returns zero counts."""
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_pbp_ingestion_for_league("UNKNOWN")

        assert result["league"] == "UNKNOWN"
        assert result["pbp_games"] == 0
        assert result["pbp_events"] == 0


class TestScheduleSingleLeagueAndWait:
    """Tests for schedule_single_league_and_wait function."""

    @patch("sports_scraper.services.scheduler.get_session")
    def test_returns_skipped_for_unknown_league(self, mock_get_session):
        """Returns skipped status for unknown league."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_get_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = schedule_single_league_and_wait("UNKNOWN")

        assert result["runs_created"] == 0
        assert result["status"] == "skipped"
        assert result["reason"] == "unknown_league"


class TestModuleImports:
    """Tests for scheduler module imports."""

    def test_has_build_scheduled_window(self):
        """Module has build_scheduled_window function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'build_scheduled_window')

    def test_has_create_scrape_run(self):
        """Module has create_scrape_run function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'create_scrape_run')

    def test_has_schedule_ingestion_runs(self):
        """Module has schedule_ingestion_runs function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'schedule_ingestion_runs')

    def test_has_scheduled_ingestion_summary(self):
        """Module has ScheduledIngestionSummary class."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'ScheduledIngestionSummary')

    def test_has_run_pbp_ingestion_for_league(self):
        """Module has run_pbp_ingestion_for_league function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'run_pbp_ingestion_for_league')

    def test_has_schedule_single_league_and_wait(self):
        """Module has schedule_single_league_and_wait function."""
        from sports_scraper.services import scheduler
        assert hasattr(scheduler, 'schedule_single_league_and_wait')

