"""Helper functions for NFL live feed processing.

Utility functions for parsing ESPN API responses and building domain objects.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import TeamIdentity
from ..normalization import normalize_team_name
from ..utils.datetime_utils import now_utc
from .nfl_constants import NFL_SEASON_TYPE_MAP, NFL_STATUS_MAP


def build_team_identity_from_espn(team_data: dict) -> TeamIdentity:
    """Build TeamIdentity from ESPN team JSON.

    ESPN team objects have structure like:
    {"id": "1", "abbreviation": "ATL", "displayName": "Atlanta Falcons",
     "shortDisplayName": "Falcons", ...}
    """
    abbr = team_data.get("abbreviation", "")
    display_name = team_data.get("displayName", "")
    short_name = team_data.get("shortDisplayName", "")

    # Normalize through our team name system
    canonical_name, normalized_abbr = normalize_team_name("NFL", display_name)

    return TeamIdentity(
        league_code="NFL",
        name=canonical_name or display_name,
        short_name=short_name or canonical_name,
        abbreviation=normalized_abbr or abbr,
        external_ref=team_data.get("id", ""),
    )


def map_espn_game_status(status_type_name: str) -> str:
    """Map ESPN status type name to internal status string."""
    return NFL_STATUS_MAP.get(status_type_name, "scheduled")


def map_espn_season_type(season_type_id: int) -> str:
    """Map ESPN season type ID to internal season_type string."""
    return NFL_SEASON_TYPE_MAP.get(season_type_id, "regular")


def parse_espn_datetime(date_str: str | None) -> datetime:
    """Parse ESPN ISO datetime string to UTC datetime."""
    if not date_str:
        return now_utc()
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return now_utc()
