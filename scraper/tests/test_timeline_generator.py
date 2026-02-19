"""Tests for services/timeline_generator.py module."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


from sports_scraper.services.timeline_generator import (
    SCHEDULED_DAYS_BACK,
)


class TestScheduledDaysBack:
    """Tests for SCHEDULED_DAYS_BACK constant."""

    def test_default_is_4_days(self):
        """Default window is 4 days (96 hours)."""
        assert SCHEDULED_DAYS_BACK == 4

    def test_is_positive_integer(self):
        """Constant is a positive integer."""
        assert isinstance(SCHEDULED_DAYS_BACK, int)
        assert SCHEDULED_DAYS_BACK > 0


class TestTimelineGeneratorModuleImports:
    """Tests for timeline generator module imports."""

    def test_has_find_functions(self):
        """Module has find functions."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'find_games_missing_timelines')
        assert hasattr(timeline_generator, 'find_games_needing_regeneration')
        assert hasattr(timeline_generator, 'find_all_games_needing_timelines')

    def test_has_generate_functions(self):
        """Module has generate functions."""
        from sports_scraper.services import timeline_generator
        assert hasattr(timeline_generator, 'generate_timeline_for_game')
        assert hasattr(timeline_generator, 'generate_missing_timelines')
        assert hasattr(timeline_generator, 'generate_all_needed_timelines')
