"""Common utilities for scrapers and data processing."""

from .cache import HTMLCache
from .date_utils import season_from_date
from .datetime_utils import date_to_datetime_range, date_window_for_matching, now_utc
from .db_queries import (
    count_team_games,
    find_games_in_date_range,
    get_league_id,
    has_odds,
    has_player_boxscores,
)
from .html_parsing import (
    extract_all_stats_from_row,
    extract_team_stats_from_table,
    find_player_table,
    find_table_by_id,
    get_stat_from_row,
    get_table_ids_on_page,
)
from .parsing import parse_float, parse_int, parse_time_to_minutes

__all__ = [
    # Cache
    "HTMLCache",
    # Date utilities
    "season_from_date",
    # Datetime utilities
    "now_utc",
    "date_to_datetime_range",
    "date_window_for_matching",
    # Parsing utilities
    "get_stat_from_row",
    "parse_int",
    "parse_float",
    "parse_time_to_minutes",
    # HTML parsing
    "find_table_by_id",
    "find_player_table",
    "extract_team_stats_from_table",
    "get_table_ids_on_page",
    # Database queries
    "get_league_id",
    "count_team_games",
    "has_player_boxscores",
    "has_odds",
    "find_games_in_date_range",
]

