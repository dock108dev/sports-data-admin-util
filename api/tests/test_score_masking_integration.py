"""Integration tests for score masking at the dependency and serialization layer."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dependencies.score_preferences import resolve_score_preferences
from app.services.score_masking import UserScorePreferences


class TestResolveScorePreferences:
    """Tests for the resolve_score_preferences FastAPI dependency."""

    @pytest.fixture
    def mock_request(self) -> MagicMock:
        request = MagicMock()
        request.state = MagicMock()
        request.state.user_id = 1
        return request

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_admin_returns_none(self, mock_request: MagicMock, mock_session: AsyncMock) -> None:
        result = await resolve_score_preferences(mock_request, role="admin", session=mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_guest_returns_none(self, mock_request: MagicMock, mock_session: AsyncMock) -> None:
        result = await resolve_score_preferences(mock_request, role="guest", session=mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_user_no_user_id_returns_none(self, mock_session: AsyncMock) -> None:
        request = MagicMock()
        request.state = MagicMock(spec=[])
        result = await resolve_score_preferences(request, role="user", session=mock_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_user_no_prefs_row_returns_defaults(
        self, mock_request: MagicMock, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await resolve_score_preferences(mock_request, role="user", session=mock_session)

        assert result is not None
        assert result.user_id == 1
        assert result.score_reveal_mode == "onMarkRead"
        assert result.score_hide_leagues == []
        assert result.score_hide_teams == []
        assert result.revealed_game_ids == set()

    @pytest.mark.asyncio
    async def test_user_with_prefs_row(
        self, mock_request: MagicMock, mock_session: AsyncMock
    ) -> None:
        mock_prefs = MagicMock()
        mock_prefs.score_reveal_mode = "blacklist"
        mock_prefs.score_hide_leagues = ["NBA", "NFL"]
        mock_prefs.score_hide_teams = ["LAL"]
        mock_prefs.revealed_game_ids = [10, 20, 30]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prefs
        mock_session.execute.return_value = mock_result

        result = await resolve_score_preferences(mock_request, role="user", session=mock_session)

        assert result is not None
        assert result.score_reveal_mode == "blacklist"
        assert result.score_hide_leagues == ["NBA", "NFL"]
        assert result.score_hide_teams == ["LAL"]
        assert result.revealed_game_ids == {10, 20, 30}

    @pytest.mark.asyncio
    async def test_user_with_none_collections(
        self, mock_request: MagicMock, mock_session: AsyncMock
    ) -> None:
        mock_prefs = MagicMock()
        mock_prefs.score_reveal_mode = "always"
        mock_prefs.score_hide_leagues = None
        mock_prefs.score_hide_teams = None
        mock_prefs.revealed_game_ids = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prefs
        mock_session.execute.return_value = mock_result

        result = await resolve_score_preferences(mock_request, role="user", session=mock_session)

        assert result is not None
        assert result.score_hide_leagues == []
        assert result.score_hide_teams == []
        assert result.revealed_game_ids == set()


class TestSummarizeGameMasking:
    """Tests verifying that summarize_game applies score masking correctly."""

    def _make_game(self, game_id: int = 1, home_score: int = 110, away_score: int = 105) -> MagicMock:
        game = MagicMock()
        game.id = game_id
        game.home_score = home_score
        game.away_score = away_score
        game.status = "final"
        game.game_date = datetime(2026, 4, 10, 20, 0, tzinfo=UTC)
        game.season = 2026

        league = MagicMock()
        league.code = "NBA"
        game.league = league

        home_team = MagicMock()
        home_team.name = "Los Angeles Lakers"
        home_team.abbreviation = "LAL"
        home_team.short_name = "Lakers"
        home_team.color_light_hex = "#FDB927"
        home_team.color_dark_hex = "#552583"
        home_team.color_secondary_light_hex = None
        home_team.color_secondary_dark_hex = None
        game.home_team = home_team

        away_team = MagicMock()
        away_team.name = "Boston Celtics"
        away_team.abbreviation = "BOS"
        away_team.short_name = "Celtics"
        away_team.color_light_hex = "#007A33"
        away_team.color_dark_hex = "#BA9653"
        away_team.color_secondary_light_hex = None
        away_team.color_secondary_dark_hex = None
        game.away_team = away_team

        game.team_boxscores = []
        game.player_boxscores = []
        game.odds = []
        game.social_posts = []
        game.plays = []
        game.timeline_artifacts = []
        game.last_scraped_at = None
        game.last_ingested_at = None
        game.last_pbp_at = None
        game.last_social_at = None
        game.last_odds_at = None
        game.last_advanced_stats_at = None
        game.scrape_version = None

        return game

    def test_no_masking_scores_pass_through(self) -> None:
        from app.routers.sports.game_helpers import summarize_game

        game = self._make_game()
        summary = summarize_game(game, has_flow=False, score_prefs=None)

        assert summary.home_score == 110
        assert summary.away_score == 105

    def test_masking_replaces_scores_with_none(self) -> None:
        from app.routers.sports.game_helpers import summarize_game

        prefs = UserScorePreferences(
            user_id=1,
            role="user",
            score_reveal_mode="onMarkRead",
            score_hide_leagues=[],
            score_hide_teams=[],
            revealed_game_ids=set(),
        )
        game = self._make_game()
        summary = summarize_game(game, has_flow=False, score_prefs=prefs)

        assert summary.home_score is None
        assert summary.away_score is None

    def test_revealed_game_scores_visible(self) -> None:
        from app.routers.sports.game_helpers import summarize_game

        prefs = UserScorePreferences(
            user_id=1,
            role="user",
            score_reveal_mode="onMarkRead",
            score_hide_leagues=[],
            score_hide_teams=[],
            revealed_game_ids={1},
        )
        game = self._make_game(game_id=1)
        summary = summarize_game(game, has_flow=False, score_prefs=prefs)

        assert summary.home_score == 110
        assert summary.away_score == 105

    def test_blacklist_team_masked(self) -> None:
        from app.routers.sports.game_helpers import summarize_game

        prefs = UserScorePreferences(
            user_id=1,
            role="user",
            score_reveal_mode="blacklist",
            score_hide_leagues=[],
            score_hide_teams=["LAL"],
            revealed_game_ids=set(),
        )
        game = self._make_game()
        summary = summarize_game(game, has_flow=False, score_prefs=prefs)

        assert summary.home_score is None
        assert summary.away_score is None

    def test_admin_bypass_always_visible(self) -> None:
        from app.routers.sports.game_helpers import summarize_game

        prefs = UserScorePreferences(
            user_id=1,
            role="admin",
            score_reveal_mode="onMarkRead",
            score_hide_leagues=[],
            score_hide_teams=[],
            revealed_game_ids=set(),
        )
        game = self._make_game()
        summary = summarize_game(game, has_flow=False, score_prefs=prefs)

        assert summary.home_score == 110
        assert summary.away_score == 105
