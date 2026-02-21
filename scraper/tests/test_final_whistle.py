"""Tests for Social Scrape #1: final-whistle social collection."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


def _make_game(
    game_id: int = 1,
    status: str = "final",
    social_scrape_1_at=None,
    home_team_id: int = 10,
    away_team_id: int = 20,
    game_date: datetime | None = None,
):
    """Create a mock game object for testing."""
    game = MagicMock()
    game.id = game_id
    game.status = status
    game.social_scrape_1_at = social_scrape_1_at
    game.home_team_id = home_team_id
    game.away_team_id = away_team_id
    game.game_date = game_date or datetime(2026, 2, 5, 0, 0, tzinfo=UTC)
    game.last_social_at = None
    return game


class TestFinalWhistleSocial:
    """Tests for run_final_whistle_social task."""

    @patch("sports_scraper.jobs.final_whistle_tasks.get_session")
    def test_skips_if_already_scraped(self, mock_get_session):
        """Game with social_scrape_1_at set returns early."""
        from sports_scraper.jobs.final_whistle_tasks import run_final_whistle_social

        game = _make_game(
            social_scrape_1_at=datetime(2026, 2, 5, 3, 0, tzinfo=UTC)
        )
        session = MagicMock()
        session.query.return_value.get.return_value = game
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_final_whistle_social(1)

        assert result["status"] == "skipped"
        assert result["reason"] == "already_scraped"

    @patch("sports_scraper.jobs.final_whistle_tasks.get_session")
    def test_skips_non_final_game(self, mock_get_session):
        """Game not FINAL returns early."""
        from sports_scraper.jobs.final_whistle_tasks import run_final_whistle_social

        game = _make_game(status="live")
        session = MagicMock()
        session.query.return_value.get.return_value = game
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_final_whistle_social(1)

        assert result["status"] == "skipped"
        assert result["reason"] == "not_final"

    @patch("sports_scraper.jobs.final_whistle_tasks.get_session")
    def test_skips_game_not_found(self, mock_get_session):
        """Missing game returns not_found."""
        from sports_scraper.jobs.final_whistle_tasks import run_final_whistle_social

        session = MagicMock()
        session.query.return_value.get.return_value = None
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        result = run_final_whistle_social(999)

        assert result["status"] == "not_found"

    @patch("sports_scraper.services.job_runs.complete_job_run")
    @patch("sports_scraper.services.job_runs.start_job_run", return_value=1)
    @patch("sports_scraper.jobs.final_whistle_tasks.time")
    @patch("sports_scraper.jobs.final_whistle_tasks.get_session")
    def test_collects_and_completes(self, mock_get_session, mock_time, mock_start, mock_complete):
        """Successful scrape sets social_scrape_1_at and logs job run."""
        from sports_scraper.jobs.final_whistle_tasks import run_final_whistle_social

        game = _make_game()
        session = MagicMock()
        session.query.return_value.get.return_value = game
        session.query.return_value.filter.return_value.update.return_value = 0
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "sports_scraper.social.team_collector.TeamTweetCollector"
        ) as MockCollector:
            collector_instance = MockCollector.return_value
            collector_instance.collect_team_tweets.return_value = 5

            with patch(
                "sports_scraper.social.tweet_mapper.map_tweets_for_team"
            ) as mock_map:
                mock_map.return_value = {"mapped": 3, "no_game": 2}

                result = run_final_whistle_social(1)

                assert result["status"] == "success"
                assert result["teams_scraped"] == 2
                assert game.social_scrape_1_at is not None
                # Verify job run tracking
                mock_start.assert_called_once_with("final_whistle_social", [])
                mock_complete.assert_called_once()
                # Verify inter-game cooldown
                mock_time.sleep.assert_called_once_with(180)

    @patch("sports_scraper.services.job_runs.complete_job_run")
    @patch("sports_scraper.services.job_runs.start_job_run", return_value=1)
    @patch("sports_scraper.jobs.final_whistle_tasks.time")
    @patch("sports_scraper.jobs.final_whistle_tasks.get_session")
    def test_discards_postgame_tweets(self, mock_get_session, mock_time, mock_start, mock_complete):
        """Postgame tweets are unmapped after collection."""
        from sports_scraper.jobs.final_whistle_tasks import run_final_whistle_social

        game = _make_game()
        session = MagicMock()
        session.query.return_value.get.return_value = game
        # Simulate 2 postgame tweets being discarded
        session.query.return_value.filter.return_value.update.return_value = 2
        mock_get_session.return_value.__enter__ = MagicMock(return_value=session)
        mock_get_session.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "sports_scraper.social.team_collector.TeamTweetCollector"
        ) as MockCollector:
            collector_instance = MockCollector.return_value
            collector_instance.collect_team_tweets.return_value = 3

            with patch(
                "sports_scraper.social.tweet_mapper.map_tweets_for_team"
            ) as mock_map:
                mock_map.return_value = {"mapped": 3}

                result = run_final_whistle_social(1)

                assert result["postgame_discarded"] == 2
