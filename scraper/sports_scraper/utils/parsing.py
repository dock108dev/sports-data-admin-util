"""
Generic, format-agnostic parsing utilities.

This module must NOT depend on format-specific libraries (like BeautifulSoup)
to ensure it can be used for parsing data from any source (API, JSON, CLI).
"""

from __future__ import annotations


def parse_int(value: str | None) -> int | None:
    """Parse a string value to an integer, handling common edge cases."""
    if value in (None, "", "-"):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def parse_float(value: str | None) -> float | None:
    """Parse a string value to a float, handling common edge cases."""
    if value in (None, "", "-"):
        return None
    try:
        # Handle time format like "32:45" (minutes:seconds)
        if ":" in str(value):
            parts = str(value).split(":")
            if len(parts) == 2:
                return float(parts[0]) + float(parts[1]) / 60
        return float(value)
    except (ValueError, TypeError):
        return None


def parse_time_to_minutes(value: str | None) -> float | None:
    """Parse time string (MM:SS or HH:MM:SS) to decimal minutes."""
    if value in (None, "", "-"):
        return None
    try:
        parts = str(value).split(":")
        if len(parts) == 2:
            # MM:SS format
            return float(parts[0]) + float(parts[1]) / 60
        elif len(parts) == 3:
            # HH:MM:SS format
            return float(parts[0]) * 60 + float(parts[1]) + float(parts[2]) / 60
        return float(value)
    except (ValueError, TypeError):
        return None
