"""Tests for SOCIAL_EMBEDS_ENABLED feature flag behavior."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.social_events import build_social_events


def _make_mock_post(
    post_id: int,
    text: str,
    posted_at: datetime,
    source_handle: str = "team_account",
) -> MagicMock:
    post = MagicMock()
    post.id = post_id
    post.tweet_text = text
    post.posted_at = posted_at
    post.source_handle = source_handle
    post.media_type = None
    return post


def _settings_with(*, social_embeds_enabled: bool) -> Settings:
    """Build Settings with the social flag controlled via env var."""
    env_val = "true" if social_embeds_enabled else "false"
    with patch.dict(os.environ, {"SOCIAL_EMBEDS_ENABLED": env_val}):
        return Settings(_env_file=None)


@pytest.fixture()
def game_start() -> datetime:
    return datetime(2026, 4, 10, 19, 0, 0, tzinfo=UTC)


@pytest.fixture()
def sample_posts(game_start: datetime) -> list[MagicMock]:
    return [
        _make_mock_post(1, "Game day!", game_start - timedelta(hours=1)),
        _make_mock_post(2, "Let's go!", game_start + timedelta(minutes=10)),
    ]


class TestSocialEmbedsEnabledConfig:
    def test_defaults_to_false(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOCIAL_EMBEDS_ENABLED", None)
            settings = Settings(_env_file=None)
        assert settings.social_embeds_enabled is False

    def test_can_be_enabled_via_env(self) -> None:
        settings = _settings_with(social_embeds_enabled=True)
        assert settings.social_embeds_enabled is True

    def test_can_be_disabled_via_env(self) -> None:
        settings = _settings_with(social_embeds_enabled=False)
        assert settings.social_embeds_enabled is False


class TestBuildSocialEventsFlag:
    def test_returns_empty_when_disabled(
        self,
        game_start: datetime,
        sample_posts: list[MagicMock],
    ) -> None:
        disabled = _settings_with(social_embeds_enabled=False)
        with patch("app.services.social_events.get_settings", return_value=disabled):
            result = build_social_events(
                posts=sample_posts,
                phase_boundaries={},
                game_start=game_start,
                league_code="NBA",
            )
        assert result == []

    def test_returns_events_when_enabled(
        self,
        game_start: datetime,
        sample_posts: list[MagicMock],
    ) -> None:
        enabled = _settings_with(social_embeds_enabled=True)
        with patch("app.services.social_events.get_settings", return_value=enabled):
            result = build_social_events(
                posts=sample_posts,
                phase_boundaries={},
                game_start=game_start,
                league_code="NBA",
            )
        assert len(result) == 2
        assert result[0][1]["event_type"] == "tweet"
        assert result[0][1]["text"] == "Game day!"

    def test_no_external_calls_when_disabled(
        self,
        game_start: datetime,
        sample_posts: list[MagicMock],
    ) -> None:
        disabled = _settings_with(social_embeds_enabled=False)
        with (
            patch("app.services.social_events.get_settings", return_value=disabled),
            patch("app.services.social_events.assign_social_phase_time_based") as mock_phase,
            patch("app.services.social_events.assign_social_role") as mock_role,
        ):
            build_social_events(
                posts=sample_posts,
                phase_boundaries={},
                game_start=game_start,
                league_code="NBA",
            )
        mock_phase.assert_not_called()
        mock_role.assert_not_called()
