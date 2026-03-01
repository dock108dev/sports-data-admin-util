"""Helper functions for MLB live feed processing.

Utility functions for parsing API responses and building domain objects.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..models import TeamIdentity
from ..normalization import normalize_team_name
from ..utils.datetime_utils import now_utc


def build_team_identity_from_api(team_data: dict) -> TeamIdentity:
    """Build TeamIdentity from the MLB Stats API team data.

    The MLB API provides team info in the format:
    {"team": {"id": 147, "name": "New York Yankees", "abbreviation": "NYY", ...}}
    """
    team = team_data.get("team", team_data)
    abbr = team.get("abbreviation", "")
    full_name = team.get("name", "")
    short_name = team.get("shortName", "") or team.get("teamName", "")

    # Normalize through our team name system
    canonical_name, normalized_abbr = normalize_team_name("MLB", full_name)

    return TeamIdentity(
        league_code="MLB",
        name=canonical_name or full_name,
        short_name=short_name or canonical_name,
        abbreviation=normalized_abbr or abbr,
        external_ref=abbr,
    )


def map_mlb_game_state(status_code: str) -> str:
    """Map MLB abstractGameState / statusCode to normalized status.

    Common status codes from the MLB API:
    - "F", "Final" -> final
    - "I", "IP", "In Progress", "Live" -> live
    - "S", "P", "Scheduled", "Pre-Game", "Preview" -> scheduled
    """
    code = status_code.upper().strip()
    if code in ("F", "FINAL", "O", "GAME OVER", "DR"):
        return "final"
    if code in ("I", "IP", "IN PROGRESS", "LIVE", "MA", "MF", "MI"):
        return "live"
    if code in ("S", "P", "SCHEDULED", "PRE-GAME", "PREVIEW", "PW", "FUT"):
        return "scheduled"
    return "scheduled"


def parse_datetime(value: str | None) -> datetime:
    """Parse ISO datetime string to UTC datetime."""
    if not value:
        return now_utc()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return now_utc()


def one_day() -> timedelta:
    """Return timedelta of one day."""
    return timedelta(days=1)
