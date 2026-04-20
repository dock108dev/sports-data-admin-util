"""Contract tests for GET /api/admin/quality/summary."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db import get_db
from app.dependencies.roles import require_admin
from app.routers.admin.quality_summary import router


def _make_client(rows=None):
    mock_db = AsyncMock()
    mapping_mock = MagicMock()
    mapping_mock.all.return_value = rows or []
    result_mock = MagicMock()
    result_mock.mappings.return_value = mapping_mock
    mock_db.execute.return_value = result_mock

    async def _get_db():
        yield mock_db

    app = FastAPI()
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[require_admin] = lambda: "admin"
    app.include_router(router)
    return TestClient(app), mock_db


_SAMPLE_ROWS = [
    {
        "sport": "NBA",
        "flow_source": "LLM",
        "p25": 62.50,
        "p50": 75.00,
        "p75": 87.50,
        "flow_count": 8,
    },
    {
        "sport": "NBA",
        "flow_source": "TEMPLATE",
        "p25": 5.00,
        "p50": 5.00,
        "p75": 5.00,
        "flow_count": 2,
    },
    {
        "sport": "NFL",
        "flow_source": "LLM",
        "p25": 50.00,
        "p50": 62.50,
        "p75": 75.00,
        "flow_count": 4,
    },
]


def test_response_shape():
    client, _ = _make_client(_SAMPLE_ROWS)
    resp = client.get("/quality/summary")
    assert resp.status_code == 200
    body = resp.json()

    # Top-level camelCase fields
    assert "generatedAt" in body
    assert body["windowDays"] == 7
    assert isinstance(body["rows"], list)
    assert len(body["rows"]) == 3


def test_row_fields():
    client, _ = _make_client(_SAMPLE_ROWS)
    body = client.get("/quality/summary").json()
    first = body["rows"][0]
    assert first["sport"] == "NBA"
    assert first["flowSource"] == "LLM"
    assert isinstance(first["p25"], float)
    assert isinstance(first["p50"], float)
    assert isinstance(first["p75"], float)
    assert isinstance(first["flowCount"], int)
    assert first["flowCount"] == 8


def test_empty_response():
    client, _ = _make_client([])
    body = client.get("/quality/summary").json()
    assert body["windowDays"] == 7
    assert body["rows"] == []


def test_p50_value_passed_through():
    client, _ = _make_client(_SAMPLE_ROWS)
    body = client.get("/quality/summary").json()
    nba_llm = next(r for r in body["rows"] if r["sport"] == "NBA" and r["flowSource"] == "LLM")
    assert nba_llm["p50"] == pytest.approx(75.0)


def test_template_row_present():
    client, _ = _make_client(_SAMPLE_ROWS)
    body = client.get("/quality/summary").json()
    template_rows = [r for r in body["rows"] if r["flowSource"] == "TEMPLATE"]
    assert len(template_rows) == 1
    assert template_rows[0]["sport"] == "NBA"


def test_db_query_executed():
    """Verifies that the endpoint actually calls the DB."""
    client, mock_db = _make_client(_SAMPLE_ROWS)
    client.get("/quality/summary")
    mock_db.execute.assert_called_once()
