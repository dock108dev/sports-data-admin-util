"""Tests for game state updater: promote games through lifecycle states."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from sports_scraper.services.game_state_updater import (
    _ARCHIVE_AFTER_DAYS,
    _promote_final_to_archived,
    _promote_scheduled_to_pregame,
    update_game_states,
)

_MOD = "sports_scraper.services.game_state_updater"
_MOCK_LEAGUE_ID = 10
_PREGAME_WINDOW_HOURS = 6


def _utc_now() -> datetime:
    return datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)


def _make_game(**kwargs) -> MagicMock:
    game = MagicMock()
    game.id = kwargs.get("id", 1)
    game.status = kwargs.get("status", "scheduled")
    game.tip_time = kwargs.get("tip_time")
    game.end_time = kwargs.get("end_time")
    game.updated_at = kwargs.get("updated_at")
    game.closed_at = kwargs.get("closed_at")
    game.league_id = kwargs.get("league_id", _MOCK_LEAGUE_ID)
    game.social_scrape_2_at = kwargs.get("social_scrape_2_at")
    return game


# ---------------------------------------------------------------------------
# update_game_states
# ---------------------------------------------------------------------------
class TestUpdateGameStates:
    @patch(f"{_MOD}._promote_final_to_archived", return_value=0)
    @patch(f"{_MOD}._promote_stale_to_final", return_value=0)
    @patch(f"{_MOD}._promote_scheduled_to_pregame", return_value=0)
    def test_returns_counts_dict(self, mock_sched, mock_stale, mock_final):
        session = MagicMock()
        result = update_game_states(session)
        assert result == {"scheduled_to_pregame": 0, "stale_to_final": 0, "final_to_archived": 0}

    @patch(f"{_MOD}.logger")
    @patch(f"{_MOD}._promote_final_to_archived", return_value=1)
    @patch(f"{_MOD}._promote_stale_to_final", return_value=0)
    @patch(f"{_MOD}._promote_scheduled_to_pregame", return_value=2)
    def test_logs_info_when_transitions(self, mock_sched, mock_stale, mock_final, mock_logger):
        session = MagicMock()
        result = update_game_states(session)
        assert result["scheduled_to_pregame"] == 2
        assert result["final_to_archived"] == 1
        mock_logger.info.assert_called_once()

    @patch(f"{_MOD}.logger")
    @patch(f"{_MOD}._promote_final_to_archived", return_value=0)
    @patch(f"{_MOD}._promote_stale_to_final", return_value=0)
    @patch(f"{_MOD}._promote_scheduled_to_pregame", return_value=0)
    def test_logs_debug_when_no_transitions(self, mock_sched, mock_stale, mock_final, mock_logger):
        session = MagicMock()
        update_game_states(session)
        mock_logger.debug.assert_called_once_with("game_state_updater_no_transitions")


# ---------------------------------------------------------------------------
# _promote_scheduled_to_pregame
# ---------------------------------------------------------------------------
class TestPromoteScheduledToPregame:
    @patch("sports_scraper.services.game_state_updater.LEAGUE_CONFIG")
    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_promotes_game_within_window(self, mock_now, mock_config):
        now = _utc_now()
        config = MagicMock()
        config.pregame_window_hours = _PREGAME_WINDOW_HOURS
        mock_config.items.return_value = [("NBA", config)]

        game = _make_game(
            tip_time=now + timedelta(hours=3),  # within 6-hour window
            status="scheduled",
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = 10
        session.query.return_value.filter.return_value.all.return_value = [game]

        result = _promote_scheduled_to_pregame(session)
        assert result == 1
        assert game.status == "pregame"
        assert game.updated_at == now

    @patch("sports_scraper.services.game_state_updater.LEAGUE_CONFIG")
    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_skips_league_not_in_db(self, mock_now, mock_config):
        config = MagicMock()
        config.pregame_window_hours = _PREGAME_WINDOW_HOURS
        mock_config.items.return_value = [("FAKE", config)]

        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = None

        result = _promote_scheduled_to_pregame(session)
        assert result == 0

    @patch("sports_scraper.services.game_state_updater.LEAGUE_CONFIG")
    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_multiple_games(self, mock_now, mock_config):
        now = _utc_now()
        config = MagicMock()
        config.pregame_window_hours = _PREGAME_WINDOW_HOURS
        mock_config.items.return_value = [("NBA", config)]

        games = [
            _make_game(id=1, tip_time=now + timedelta(hours=2)),
            _make_game(id=2, tip_time=now + timedelta(hours=4)),
        ]

        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = 10
        session.query.return_value.filter.return_value.all.return_value = games

        result = _promote_scheduled_to_pregame(session)
        assert result == 2

    @patch("sports_scraper.services.game_state_updater.LEAGUE_CONFIG")
    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_no_eligible_games(self, mock_now, mock_config):
        config = MagicMock()
        config.pregame_window_hours = _PREGAME_WINDOW_HOURS
        mock_config.items.return_value = [("NBA", config)]

        session = MagicMock()
        session.query.return_value.filter.return_value.scalar.return_value = 10
        session.query.return_value.filter.return_value.all.return_value = []

        result = _promote_scheduled_to_pregame(session)
        assert result == 0


# ---------------------------------------------------------------------------
# _promote_final_to_archived
# ---------------------------------------------------------------------------
class TestPromoteFinalToArchived:
    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_archives_game_with_artifacts_and_social(self, mock_now):
        now = _utc_now()
        game = _make_game(
            status="final",
            end_time=now - timedelta(days=_ARCHIVE_AFTER_DAYS + 1),
            social_scrape_2_at=now - timedelta(days=_ARCHIVE_AFTER_DAYS),
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [game]

        result = _promote_final_to_archived(session)
        assert result == 1
        assert game.status == "archived"
        assert game.closed_at == now
        assert game.updated_at == now

    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_no_eligible_games(self, mock_now):
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []

        result = _promote_final_to_archived(session)
        assert result == 0

    @patch("sports_scraper.services.game_state_updater.now_utc", return_value=_utc_now())
    def test_multiple_games(self, mock_now):
        now = _utc_now()
        games = [
            _make_game(id=1, end_time=now - timedelta(days=10)),
            _make_game(id=2, end_time=now - timedelta(days=14)),
        ]

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = games

        result = _promote_final_to_archived(session)
        assert result == 2
        for g in games:
            assert g.status == "archived"
