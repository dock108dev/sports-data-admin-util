"""Tests for OpenTelemetry SDK initialization module (scraper/sports_scraper/telemetry.py).

Loads the module directly with importlib to bypass sports_scraper/__init__.py,
which requires full env-var validation. Tests only the no-op path so they run
without opentelemetry-sdk packages installed.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load sports_scraper/telemetry.py directly to avoid triggering the package
# __init__.py, which requires DATABASE_URL/REDIS_URL validation at import time.
_TELEMETRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "scraper"
    / "sports_scraper"
    / "telemetry.py"
)


def _load_telemetry_module():
    spec = importlib.util.spec_from_file_location("sports_scraper.telemetry", _TELEMETRY_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestScraperTelemetryNoop:
    def test_noop_when_endpoint_unset(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        mod = _load_telemetry_module()
        mod._configured = False
        mod.init_telemetry(environment="test")
        assert mod._configured is True

    def test_idempotent(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        mod = _load_telemetry_module()
        mod._configured = False
        mod.init_telemetry()
        mod.init_telemetry()
        assert mod._configured is True
