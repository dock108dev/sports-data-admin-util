from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the scraper package is importable when running from repo root without installing it.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

# The scraper settings are loaded at import time and require DATABASE_URL.
# For these pure unit tests, a dummy local URL is sufficient.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")

from sports_scraper.live.nba import _parse_nba_clock
from sports_scraper.persistence.games import resolve_status_transition


def test_parse_nba_clock_duration() -> None:
    assert _parse_nba_clock("PT11M32.00S") == "11:32"
    assert _parse_nba_clock("PT0M05.00S") == "0:05"


def test_parse_nba_clock_passthrough() -> None:
    assert _parse_nba_clock("11:32") == "11:32"
    assert _parse_nba_clock(None) is None


def test_resolve_status_transition_final_sticks() -> None:
    assert resolve_status_transition("final", "live") == "final"


def test_resolve_status_transition_promotes_live() -> None:
    assert resolve_status_transition("scheduled", "live") == "live"
    assert resolve_status_transition("live", "scheduled") == "live"


def test_resolve_status_transition_promotes_final() -> None:
    assert resolve_status_transition("live", "final") == "final"
