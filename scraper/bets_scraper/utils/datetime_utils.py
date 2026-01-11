"""
Low-level timezone and timestamp utilities.

This module provides helpers for timezone-aware UTC datetime operations,
conversion, and window generation. It is domain-agnostic and should NOT
contain sports-specific logic (e.g., season boundaries), which belongs in
date_utils.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def now_utc() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def date_to_utc_datetime(day: date) -> datetime:
    """Convert a date to a timezone-aware UTC datetime at midnight."""
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)


def date_to_datetime_range(day: date) -> tuple[datetime, datetime]:
    """Convert a date to a datetime range (start and end of day in UTC).
    
    Args:
        day: Date object
        
    Returns:
        Tuple of (start_datetime, end_datetime) in UTC
    """
    start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(day, datetime.max.time()).replace(tzinfo=timezone.utc)
    return start, end


def date_window_for_matching(day: date, days_before: int = 1, days_after: int = 1) -> tuple[datetime, datetime]:
    """Get a datetime window for matching games by date.
    
    Useful when games are stored at midnight but odds use actual tipoff times.
    
    Args:
        day: Target date
        days_before: Days before to include in window
        days_after: Days after to include in window
        
    Returns:
        Tuple of (window_start, window_end) in UTC
    """
    start_date = day - timedelta(days=days_before)
    end_date = day + timedelta(days=days_after)
    start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    return start, end

