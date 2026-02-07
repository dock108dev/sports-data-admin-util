"""
Generic, format-agnostic parsing utilities.

This module must NOT depend on format-specific libraries (like BeautifulSoup)
to ensure it can be used for parsing data from any source (API, JSON, CLI).
"""

from __future__ import annotations


def parse_int(value: str | int | float | None) -> int | None:
    """Parse a value to an integer, handling common edge cases.

    Accepts strings, ints, floats, or None. Returns None for empty strings or "-".
    """
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


