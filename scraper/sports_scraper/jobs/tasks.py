"""Celery tasks for triggering scrape runs.

This module re-exports all tasks from specialized modules for Celery discovery.
New code should import directly from the specific task modules:
- scrape_tasks: Basic scrape job execution
- pipeline_tasks: Pipeline triggering
- timeline_tasks: Timeline generation
- story_tasks: Story generation
- social_tasks: Team-centric social collection
- polling_tasks: Game-state-machine polling (Phase 2)
- flow_trigger_tasks: Edge-triggered flow generation (Phase 3)
- sweep_tasks: Daily sweep / truth repair (Phase 4)
- utility_tasks: Cache clearing and utilities
"""

from __future__ import annotations

# Re-export all tasks for Celery discovery
from .scrape_tasks import (
    run_scrape_job,
    run_scheduled_ingestion,
    run_scheduled_odds_sync,
    run_scheduled_nba_social,
    run_scheduled_nhl_social,
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
from .social_tasks import (
    collect_social_for_league,
    collect_team_social,
    map_social_to_games,
    get_social_mapping_stats,
)
from .polling_tasks import (
    update_game_states_task,
    poll_live_pbp_task,
    poll_active_odds_task,
    poll_active_social_task,
)
from .flow_trigger_tasks import (
    trigger_flow_for_game,
)
from .sweep_tasks import (
    run_daily_sweep,
)
from .utility_tasks import (
    clear_scraper_cache_task,
)

__all__ = [
    # Scrape tasks
    "run_scrape_job",
    "run_scheduled_ingestion",
    "run_scheduled_odds_sync",
    "run_scheduled_nba_social",
    "run_scheduled_nhl_social",
    # Pipeline tasks
    "trigger_game_pipelines_task",
    # Timeline tasks
    "generate_missing_timelines_task",
    "regenerate_timeline_task",
    "run_scheduled_timeline_generation",
    # Story/Flow tasks
    "run_scheduled_nba_flow_generation",
    "run_scheduled_story_generation",
    # Social collection tasks (run on dedicated social-scraper worker)
    "collect_social_for_league",
    "collect_team_social",
    "map_social_to_games",
    "get_social_mapping_stats",
    # Game-state-machine polling tasks (Phase 2)
    "update_game_states_task",
    "poll_live_pbp_task",
    "poll_active_odds_task",
    "poll_active_social_task",
    # Edge-triggered flow generation (Phase 3)
    "trigger_flow_for_game",
    # Daily sweep (Phase 4)
    "run_daily_sweep",
    # Utility tasks
    "clear_scraper_cache_task",
]
