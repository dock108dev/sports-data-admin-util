"""Unit tests for social scraping OTel metrics (ISSUE-034).

Loads sports_scraper/social/metrics.py directly via importlib to bypass
the social package __init__.py, which pulls in structlog/db dependencies
not present in the minimal test venv.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
_METRICS_PATH = REPO_ROOT / "scraper" / "sports_scraper" / "social" / "metrics.py"


def _load_metrics_module():
    spec = importlib.util.spec_from_file_location(
        "sports_scraper.social.metrics", _METRICS_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _reset(mod) -> None:
    mod._initialized = False
    mod._scrape_result = None


class TestIncrementScrapeResult:
    def test_success_emits_correct_attributes(self):
        m = _load_metrics_module()
        _reset(m)
        counter = MagicMock()
        with patch.object(m, "_instruments", return_value=counter):
            m.increment_scrape_result(42, success=True)
        counter.add.assert_called_once_with(
            1, attributes={"success": True, "team_id": "42"}
        )

    def test_failure_emits_correct_attributes(self):
        m = _load_metrics_module()
        _reset(m)
        counter = MagicMock()
        with patch.object(m, "_instruments", return_value=counter):
            m.increment_scrape_result(7, success=False)
        counter.add.assert_called_once_with(
            1, attributes={"success": False, "team_id": "7"}
        )

    def test_team_id_is_string_in_attributes(self):
        m = _load_metrics_module()
        _reset(m)
        counter = MagicMock()
        with patch.object(m, "_instruments", return_value=counter):
            m.increment_scrape_result(99, success=True)
        _, kwargs = counter.add.call_args
        assert isinstance(kwargs["attributes"]["team_id"], str)


class TestAlertThreshold:
    """Verify that 15 failures + 5 successes would trigger the < 90% alert."""

    def test_fifteen_failures_five_successes_fires_alert(self):
        m = _load_metrics_module()
        _reset(m)
        counter = MagicMock()

        with patch.object(m, "_instruments", return_value=counter):
            for _ in range(15):
                m.increment_scrape_result(1, success=False)
            for _ in range(5):
                m.increment_scrape_result(1, success=True)

        assert counter.add.call_count == 20

        # Count how many calls had success=True vs False
        calls = counter.add.call_args_list
        success_count = sum(
            1 for c in calls if c[1]["attributes"]["success"] is True
        )
        total_count = len(calls)
        success_rate = success_count / total_count

        # 5/20 = 0.25 — well below the 0.90 threshold → alert fires
        assert success_rate < 0.90, (
            f"Expected success_rate < 0.90 but got {success_rate:.2f} "
            f"({success_count}/{total_count})"
        )

    def test_nineteen_successes_one_failure_does_not_fire(self):
        m = _load_metrics_module()
        _reset(m)
        counter = MagicMock()

        with patch.object(m, "_instruments", return_value=counter):
            for _ in range(19):
                m.increment_scrape_result(2, success=True)
            m.increment_scrape_result(2, success=False)

        calls = counter.add.call_args_list
        success_count = sum(
            1 for c in calls if c[1]["attributes"]["success"] is True
        )
        total_count = len(calls)
        success_rate = success_count / total_count

        # 19/20 = 0.95 — above the 0.90 threshold → alert does not fire
        assert success_rate >= 0.90


class TestNoopWhenOtelMissing:
    def test_noop_on_import_error(self):
        import builtins

        m = _load_metrics_module()
        _reset(m)

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "opentelemetry":
                raise ImportError("no opentelemetry")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            counter = m._instruments()

        # Should not raise — calls are silently dropped
        counter.add(1, attributes={"success": True, "team_id": "1"})
