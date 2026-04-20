"""Pytest configuration for the standalone golden corpus test suite (ISSUE-048)."""
from __future__ import annotations

from collections import defaultdict

import pytest

SPORTS = ["NFL", "NBA", "MLB", "NHL"]


def _sport_from_nodeid(nodeid: str) -> str | None:
    lower = nodeid.lower()
    for s in SPORTS:
        if f"[{s.lower()}_" in lower or f"/{s.lower()}/" in lower:
            return s
    return None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Append per-sport pass/fail table to the pytest terminal output."""
    sport_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"passed": 0, "failed": 0, "skipped": 0}
    )

    for outcome in ("passed", "failed", "skipped"):
        for report in terminalreporter.stats.get(outcome, []):
            sport = _sport_from_nodeid(getattr(report, "nodeid", ""))
            if sport:
                sport_stats[sport][outcome] += 1

    if not sport_stats:
        return

    terminalreporter.write_sep("=", "Golden Corpus — Per-Sport Summary")
    col = 8
    terminalreporter.write_line(
        f"{'Sport':<{col}} {'Passed':>8} {'Failed':>8} {'Skipped':>8} {'Status':>8}"
    )
    terminalreporter.write_line("-" * (col + 36))
    overall_pass = True
    for sport in SPORTS:
        s = sport_stats.get(sport, {"passed": 0, "failed": 0, "skipped": 0})
        if s["failed"]:
            status = "FAIL"
            overall_pass = False
        elif s["passed"]:
            status = "PASS"
        else:
            status = "—"
        terminalreporter.write_line(
            f"{sport:<{col}} {s['passed']:>8} {s['failed']:>8} {s['skipped']:>8} {status:>8}"
        )
    terminalreporter.write_sep("-", "ALL PASS" if overall_pass else "FAILURES PRESENT")
