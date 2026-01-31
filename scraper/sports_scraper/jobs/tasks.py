"""Celery tasks for triggering scrape runs.

This module re-exports all tasks from specialized modules for Celery discovery.
New code should import directly from the specific task modules:
- scrape_tasks: Basic scrape job execution
- pipeline_tasks: Pipeline triggering
- timeline_tasks: Timeline generation
- story_tasks: Story generation
- utility_tasks: Cache clearing and utilities
"""

from __future__ import annotations

# Re-export all tasks for Celery discovery
from .scrape_tasks import (
    run_scrape_job,
    run_scheduled_ingestion,
    run_scheduled_odds_sync,
)
from .pipeline_tasks import (
    trigger_game_pipelines_task,
)
from .timeline_tasks import (
    generate_missing_timelines_task,
    regenerate_timeline_task,
    run_scheduled_timeline_generation,
)
from .story_tasks import (
    run_scheduled_nba_flow_generation,
    run_scheduled_story_generation,
)
from .utility_tasks import (
    clear_scraper_cache_task,
)

__all__ = [
    # Scrape tasks
    "run_scrape_job",
    "run_scheduled_ingestion",
    "run_scheduled_odds_sync",
    # Pipeline tasks
    "trigger_game_pipelines_task",
    # Timeline tasks
    "generate_missing_timelines_task",
    "regenerate_timeline_task",
    "run_scheduled_timeline_generation",
    # Story/Flow tasks
    "run_scheduled_nba_flow_generation",
    "run_scheduled_story_generation",
    # Utility tasks
    "clear_scraper_cache_task",
]
