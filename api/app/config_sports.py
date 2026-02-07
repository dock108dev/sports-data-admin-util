"""
Single Source of Truth (SSOT) for enabled sports/leagues.

All scheduled jobs, post-scrape triggers, and pipelines should reference
this configuration. Never hardcode league strings elsewhere.

To add a new sport:
1. Add entry to LEAGUE_CONFIG with appropriate feature flags
2. Run: no other code changes needed for basic ingestion
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueConfig:
    """Configuration for a single league/sport."""

    code: str  # "NBA", "NHL", "NCAAB"
    display_name: str  # "NBA Basketball"

    # Pipeline feature flags
    boxscores_enabled: bool = True
    player_stats_enabled: bool = True
    team_stats_enabled: bool = True
    odds_enabled: bool = True
    social_enabled: bool = True  # X/Twitter integration
    pbp_enabled: bool = True  # Play-by-play
    timeline_enabled: bool = True  # Timeline/moments generation

    # Scheduling
    scheduled_ingestion: bool = True  # Include in daily scheduled runs


# Master configuration for all leagues
LEAGUE_CONFIG: dict[str, LeagueConfig] = {
    "NBA": LeagueConfig(
        code="NBA",
        display_name="NBA Basketball",
        boxscores_enabled=True,
        player_stats_enabled=True,
        team_stats_enabled=True,
        odds_enabled=True,
        social_enabled=True,
        pbp_enabled=True,
        timeline_enabled=True,
        scheduled_ingestion=True,
    ),
    "NHL": LeagueConfig(
        code="NHL",
        display_name="NHL Hockey",
        boxscores_enabled=True,
        player_stats_enabled=True,
        team_stats_enabled=True,
        odds_enabled=True,
        social_enabled=True,
        pbp_enabled=True,
        timeline_enabled=True,
        scheduled_ingestion=False,  # Not yet scheduled
    ),
    "NCAAB": LeagueConfig(
        code="NCAAB",
        display_name="NCAA Basketball",
        boxscores_enabled=True,
        player_stats_enabled=True,
        team_stats_enabled=True,
        odds_enabled=True,
        social_enabled=False,  # No social integration yet
        pbp_enabled=True,
        timeline_enabled=True,
        scheduled_ingestion=False,  # Not yet scheduled
    ),
}


def get_league_config(league_code: str) -> LeagueConfig:
    """
    Get configuration for a specific league.

    Raises:
        ValueError: If league_code is not in LEAGUE_CONFIG
    """
    if league_code not in LEAGUE_CONFIG:
        valid = ", ".join(LEAGUE_CONFIG.keys())
        raise ValueError(f"Unknown league '{league_code}'. Valid leagues: {valid}")
    return LEAGUE_CONFIG[league_code]


def get_scheduled_leagues() -> list[str]:
    """Get leagues enabled for scheduled daily ingestion."""
    return [code for code, cfg in LEAGUE_CONFIG.items() if cfg.scheduled_ingestion]


def get_social_enabled_leagues() -> list[str]:
    """Get leagues with social/X integration enabled."""
    return [code for code, cfg in LEAGUE_CONFIG.items() if cfg.social_enabled]


def get_timeline_enabled_leagues() -> list[str]:
    """Get leagues with timeline generation enabled."""
    return [code for code, cfg in LEAGUE_CONFIG.items() if cfg.timeline_enabled]


def validate_league_code(league_code: str) -> str:
    """
    Validate and return league code.

    Raises:
        ValueError: If league_code is not valid
    """
    if league_code not in LEAGUE_CONFIG:
        valid = ", ".join(LEAGUE_CONFIG.keys())
        raise ValueError(
            f"Invalid league_code '{league_code}'. Must be one of: {valid}"
        )
    return league_code


def is_social_enabled(league_code: str) -> bool:
    """Check if social integration is enabled for a league."""
    cfg = LEAGUE_CONFIG.get(league_code)
    return cfg.social_enabled if cfg else False


def is_timeline_enabled(league_code: str) -> bool:
    """Check if timeline generation is enabled for a league."""
    cfg = LEAGUE_CONFIG.get(league_code)
    return cfg.timeline_enabled if cfg else False
