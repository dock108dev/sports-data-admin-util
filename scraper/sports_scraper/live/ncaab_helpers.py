"""Helper functions for NCAAB live feed processing.

Utility functions for parsing API responses and building domain objects.
"""

from __future__ import annotations

from ..models import TeamIdentity
from ..utils.parsing import parse_int


def build_team_identity(name: str, team_id: int) -> TeamIdentity:
    """Build TeamIdentity for an NCAAB team.

    NCAAB has hundreds of teams, so we don't have a canonical mapping.
    We store the name as-is and use the API team ID as external_ref.
    """
    return TeamIdentity(
        league_code="NCAAB",
        name=name,
        short_name=name,  # Use full name since abbreviations vary
        abbreviation=None,  # NCAAB teams don't have standard abbreviations
        external_ref=str(team_id),
    )


def extract_points(value: int | dict | None) -> int:
    """Extract points from API response which may be int or dict.

    The CBB API sometimes returns points as an integer, and sometimes as a dict:
    {"total": 89, "byPeriod": [...], "offTurnovers": 17}

    This handles both formats.
    """
    if value is None:
        return 0
    if isinstance(value, dict):
        # New format: {"total": 89, ...}
        return parse_int(value.get("total")) or 0
    # Old format: just an integer
    return parse_int(value) or 0


def parse_minutes(value: str | int | float | None) -> float | None:
    """Parse minutes value which may be 'MM:SS' or numeric."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # Try parsing "MM:SS" format
        if ":" in value:
            try:
                parts = value.split(":")
                if len(parts) == 2:
                    mins = int(parts[0])
                    secs = int(parts[1])
                    return round(mins + secs / 60, 2)
            except (ValueError, IndexError):
                pass

        # Try parsing as plain number
        try:
            return float(value)
        except ValueError:
            pass

    return None
