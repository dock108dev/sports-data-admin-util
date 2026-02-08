"""Celery tasks registry — re-exports all tasks for Celery discovery.

Import directly from specific task modules:
- scrape_tasks: Ingestion, odds sync
- pipeline_tasks: Pipeline triggering
- timeline_tasks: Timeline generation
- story_tasks: Game flow generation
- social_tasks: Team-centric social collection
- polling_tasks: Game-state-machine polling
- flow_trigger_tasks: Edge-triggered flow generation
- sweep_tasks: Daily sweep / truth repair
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
from .social_tasks import (
    collect_social_for_league,
    collect_team_social,
    handle_social_task_failure,
    map_social_to_games,
    get_social_mapping_stats,
)
from .polling_tasks import (
    update_game_states_task,
    poll_live_pbp_task,
    poll_active_odds_task,
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
    "run_scrape_job",
    "run_scheduled_ingestion",
    "run_scheduled_odds_sync",
    "trigger_game_pipelines_task",
    "generate_missing_timelines_task",
    "regenerate_timeline_task",
    "run_scheduled_timeline_generation",
    "run_scheduled_nba_flow_generation",
    "run_scheduled_story_generation",
    "collect_social_for_league",
    "collect_team_social",
    "handle_social_task_failure",
    "map_social_to_games",
    "get_social_mapping_stats",
    "update_game_states_task",
    "poll_live_pbp_task",
    "poll_active_odds_task",
    "trigger_flow_for_game",
    "run_daily_sweep",
    "clear_scraper_cache_task",
]
