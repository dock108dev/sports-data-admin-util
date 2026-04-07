"""Tests for MLB forecast API endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analytics.api.analytics_routes import router
from app.db import get_db
from app.dependencies.roles import require_admin


def _make_client(mock_db=None):
    if mock_db is None:
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        result_mock.scalar.return_value = None
        mock_db.execute.return_value = result_mock

    async def mock_get_db():
        yield mock_db

    app = FastAPI()
    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.include_router(router)
    return TestClient(app), mock_db


def _mock_forecast(**overrides):
    defaults = {
        "id": 1,
        "game_id": 12345,
        "game_date": "2026-04-07",
        "home_team": "New York Yankees",
        "away_team": "Boston Red Sox",
        "home_team_id": 10,
        "away_team_id": 20,
        "home_win_prob": 0.583,
        "away_win_prob": 0.417,
        "predicted_home_score": 4.7,
        "predicted_away_score": 3.8,
        "probability_source": "lineup_matchup",
        "sim_iterations": 5000,
        "sim_wp_std_dev": 0.012,
        "score_std_home": 2.1,
        "score_std_away": 1.9,
        "profile_games_home": 28,
        "profile_games_away": 30,
        "market_home_ml": -145,
        "market_away_ml": 125,
        "market_home_wp": 0.57,
        "market_away_wp": 0.43,
        "home_edge": 0.013,
        "away_edge": -0.013,
        "model_home_line": -152,
        "model_away_line": 132,
        "home_ev_pct": 2.3,
        "away_ev_pct": -1.8,
        "line_provider": "Pinnacle",
        "line_type": "current",
        "model_id": "mlb_pa_v1",
        "event_summary": None,
        "feature_snapshot": None,
        "refreshed_at": datetime(2026, 4, 7, 16, 0, 0, tzinfo=UTC),
        "created_at": datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    obj = MagicMock()
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


class TestGetMlbForecasts:
    @patch("app.utils.datetime_utils.today_et")
    def test_returns_empty_when_no_forecasts(self, mock_today):
        from datetime import date
        mock_today.return_value = date(2026, 4, 7)
        client, _ = _make_client()
        resp = client.get("/api/analytics/forecasts/mlb?date=2026-04-07")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["forecasts"] == []
        assert data["date"] == "2026-04-07"

    def test_returns_forecasts_with_date(self):
        forecast = _mock_forecast()
        mock_db = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [forecast]
        result_mock.scalar.return_value = forecast.refreshed_at
        mock_db.execute.return_value = result_mock

        client, _ = _make_client(mock_db)
        resp = client.get("/api/analytics/forecasts/mlb?date=2026-04-07")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["forecasts"][0]["game_id"] == 12345
        assert data["forecasts"][0]["home_win_prob"] == 0.583
        assert data["forecasts"][0]["line_analysis"]["home_edge"] == 0.013

    def test_line_analysis_null_when_no_odds(self):
        forecast = _mock_forecast(market_home_ml=None)
        mock_db = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [forecast]
        result_mock.scalar.return_value = forecast.refreshed_at
        mock_db.execute.return_value = result_mock

        client, _ = _make_client(mock_db)
        resp = client.get("/api/analytics/forecasts/mlb?date=2026-04-07")
        assert resp.status_code == 200
        assert resp.json()["forecasts"][0]["line_analysis"] is None

    def test_sim_meta_included(self):
        forecast = _mock_forecast()
        mock_db = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [forecast]
        result_mock.scalar.return_value = forecast.refreshed_at
        mock_db.execute.return_value = result_mock

        client, _ = _make_client(mock_db)
        resp = client.get("/api/analytics/forecasts/mlb?date=2026-04-07")
        meta = resp.json()["forecasts"][0]["sim_meta"]
        assert meta["iterations"] == 5000
        assert meta["model_id"] == "mlb_pa_v1"
