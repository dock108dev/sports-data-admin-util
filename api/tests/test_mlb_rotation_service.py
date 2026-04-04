"""Tests for MLB rotation prediction service."""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.analytics.services.mlb_rotation_service import (
    get_team_rotation,
    predict_probable_starter,
)


def _make_start_row(ext_ref: str, name: str, game_date: date):
    """Helper to create a (external_ref, name, game_date) tuple."""
    return (ext_ref, name, game_date)


class TestGetTeamRotation:
    """Tests for get_team_rotation."""

    @pytest.mark.asyncio
    async def test_empty_when_no_starts(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute.return_value = result_mock

        rotation = await get_team_rotation(db, team_id=1)
        assert rotation == []

    @pytest.mark.asyncio
    async def test_identifies_five_man_rotation(self):
        """5 pitchers with 3 starts each should all be in rotation."""
        db = AsyncMock()

        rows = []
        pitchers = [
            ("p1", "Ace"),
            ("p2", "Two"),
            ("p3", "Three"),
            ("p4", "Four"),
            ("p5", "Five"),
        ]
        base = date(2026, 4, 1)
        for i, (ref, name) in enumerate(pitchers):
            for turn in range(3):
                d = base - timedelta(days=i + turn * 5)
                rows.append(_make_start_row(ref, name, d))

        # Sort desc by date (as DB would return)
        rows.sort(key=lambda r: r[2], reverse=True)

        result_mock = MagicMock()
        result_mock.all.return_value = rows[:15]
        db.execute.return_value = result_mock

        rotation = await get_team_rotation(db, team_id=1)
        assert len(rotation) == 5
        refs = [p["external_ref"] for p in rotation]
        assert set(refs) == {"p1", "p2", "p3", "p4", "p5"}
        # Ordered by most recent start
        assert rotation[0]["last_start"] >= rotation[1]["last_start"]

    @pytest.mark.asyncio
    async def test_six_man_rotation(self):
        """6 pitchers with 2+ starts should all be identified."""
        db = AsyncMock()

        rows = []
        base = date(2026, 4, 1)
        for i in range(6):
            ref = f"p{i}"
            name = f"Pitcher {i}"
            for turn in range(2):
                d = base - timedelta(days=i + turn * 6)
                rows.append(_make_start_row(ref, name, d))

        rows.sort(key=lambda r: r[2], reverse=True)

        result_mock = MagicMock()
        result_mock.all.return_value = rows[:15]
        db.execute.return_value = result_mock

        rotation = await get_team_rotation(db, team_id=1)
        assert len(rotation) == 6

    @pytest.mark.asyncio
    async def test_excludes_stale_pitchers(self):
        """A pitcher whose last start was many turns ago is excluded."""
        db = AsyncMock()

        rows = [
            # Active rotation: 4 pitchers with recent starts
            _make_start_row("p1", "Ace", date(2026, 4, 1)),
            _make_start_row("p2", "Two", date(2026, 3, 31)),
            _make_start_row("p3", "Three", date(2026, 3, 30)),
            _make_start_row("p4", "Four", date(2026, 3, 29)),
            _make_start_row("p1", "Ace", date(2026, 3, 26)),
            _make_start_row("p2", "Two", date(2026, 3, 25)),
            _make_start_row("p3", "Three", date(2026, 3, 24)),
            _make_start_row("p4", "Four", date(2026, 3, 23)),
            # Stale pitcher: last start was 20+ days ago
            _make_start_row("p_il", "OnIL", date(2026, 3, 10)),
            _make_start_row("p_il", "OnIL", date(2026, 3, 5)),
        ]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        rotation = await get_team_rotation(db, team_id=1)
        refs = [p["external_ref"] for p in rotation]
        assert "p_il" not in refs
        assert len(rotation) == 4


class TestPredictProbableStarter:
    """Tests for predict_probable_starter."""

    @pytest.mark.asyncio
    async def test_uses_api_when_available(self):
        """Should return MLB Stats API result when available."""
        db = AsyncMock()
        api_result = {"external_ref": "12345", "name": "Max Scherzer"}

        with patch(
            "app.analytics.services.lineup_fetcher.fetch_probable_starter",
            new_callable=AsyncMock,
            return_value=api_result,
        ):
            result = await predict_probable_starter(
                db, team_id=1, game_date=date(2026, 4, 3),
                team_external_ref="147",
            )
            assert result == api_result

    @pytest.mark.asyncio
    async def test_falls_back_to_rotation_when_api_empty(self):
        """When API returns None, should use rotation prediction."""
        db = AsyncMock()

        # Mock the DB queries that get_team_rotation and _project_rotation_to_date use
        rotation_rows = [
            ("p1", "Ace", date(2026, 4, 1)),
            ("p2", "Two", date(2026, 3, 31)),
            ("p3", "Three", date(2026, 3, 30)),
            ("p1", "Ace", date(2026, 3, 26)),
            ("p2", "Two", date(2026, 3, 25)),
            ("p3", "Three", date(2026, 3, 24)),
        ]

        # game dates for projection
        upcoming_dates_mock = MagicMock()
        upcoming_dates_mock.scalars.return_value.all.return_value = [
            date(2026, 4, 2),
            date(2026, 4, 3),
        ]

        rotation_result_mock = MagicMock()
        rotation_result_mock.all.return_value = rotation_rows

        # First call = rotation query, second = projection query
        db.execute = AsyncMock(side_effect=[rotation_result_mock, upcoming_dates_mock])

        with patch(
            "app.analytics.services.lineup_fetcher.fetch_probable_starter",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await predict_probable_starter(
                db, team_id=1, game_date=date(2026, 4, 3),
                team_external_ref="147",
            )
            assert result is not None
            # With 2 game days ahead and rotation [p1, p2, p3],
            # slot = 2 % 3 = 2 → p3
            assert result["external_ref"] == "p3"

    @pytest.mark.asyncio
    async def test_returns_none_when_all_methods_fail(self):
        """Returns None when API and rotation both fail."""
        db = AsyncMock()

        # Empty rotation
        result_mock = MagicMock()
        result_mock.all.return_value = []
        db.execute.return_value = result_mock

        with (
            patch(
                "app.analytics.services.lineup_fetcher.fetch_probable_starter",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.analytics.services.mlb_rotation_service._openai_rotation_tiebreaker",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await predict_probable_starter(
                db, team_id=1, game_date=date(2026, 4, 5),
                team_external_ref="147",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_skips_api_without_external_ref(self):
        """When no team_external_ref, skip API and go straight to rotation."""
        db = AsyncMock()

        rotation_rows = [
            ("p1", "Ace", date(2026, 4, 1)),
            ("p2", "Two", date(2026, 3, 31)),
            ("p3", "Three", date(2026, 3, 30)),
            ("p1", "Ace", date(2026, 3, 26)),
            ("p2", "Two", date(2026, 3, 25)),
            ("p3", "Three", date(2026, 3, 24)),
        ]

        upcoming_dates_mock = MagicMock()
        upcoming_dates_mock.scalars.return_value.all.return_value = [
            date(2026, 4, 2),
        ]

        rotation_result_mock = MagicMock()
        rotation_result_mock.all.return_value = rotation_rows

        db.execute = AsyncMock(side_effect=[rotation_result_mock, upcoming_dates_mock])

        # No team_external_ref — should NOT call fetch_probable_starter
        result = await predict_probable_starter(
            db, team_id=1, game_date=date(2026, 4, 2),
        )
        assert result is not None
