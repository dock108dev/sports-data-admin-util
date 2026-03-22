"""Shared math utilities for safe arithmetic operations.

Used across advanced stats ingestion services to handle nullable/zero values
without raising exceptions.
"""

from __future__ import annotations


def safe_div(numerator: int | float | None, denominator: int | float | None) -> float | None:
    """Divide numerator by denominator, returning None if denominator is zero or either value is None."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def safe_pct(numerator: int | float | None, denominator: int | float | None) -> float | None:
    """Compute (numerator / denominator) * 100, returning None if not computable."""
    result = safe_div(numerator, denominator)
    return result * 100 if result is not None else None


def safe_float(val: object) -> float | None:
    """Coerce a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val: object) -> int | None:
    """Coerce a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def parse_minutes(val: object) -> float | None:
    """Parse minutes from various formats (ISO duration, MM:SS, raw float).

    Handles:
    - ISO 8601 duration: "PT36M12.00S" -> 36.2
    - Clock format: "36:12" -> 36.2
    - Raw numeric: 36.2 -> 36.2
    """
    if val is None:
        return None
    s = str(val)
    # Handle ISO duration: PT36M12.00S
    if s.startswith("PT"):
        import re

        m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", s)
        if m:
            mins = int(m.group(1) or 0)
            secs = float(m.group(2) or 0)
            return round(mins + secs / 60.0, 2)
    # Handle MM:SS format
    if ":" in s:
        parts = s.split(":")
        try:
            return round(int(parts[0]) + int(parts[1]) / 60.0, 2)
        except (ValueError, IndexError):
            pass
    return safe_float(val)
