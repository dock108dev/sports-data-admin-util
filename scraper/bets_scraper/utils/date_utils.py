"""
Domain-level date and season calculation utilities.

This module handles sports-specific calendar logic, such as season boundaries
and year inference. It operates on 'date' objects and should NOT contain
time-of-day or timezone-specific logic (which belongs in datetime_utils.py).
"""

from __future__ import annotations

from datetime import date


def season_from_date(day: date, league_code: str) -> int:
    """Calculate season year from a date based on league.
    
    Season calculation rules:
    - NBA: Season starts in October (month >= 10), ends in June
      - If month >= 10: season = year
      - If month < 10: season = year - 1
    - NFL: Season starts in September (month >= 9), ends in February
      - If month >= 9: season = year
      - If month < 9: season = year - 1
    - MLB: Season starts in March/April, ends in October
      - If month >= 3: season = year
      - If month < 3: season = year - 1
    - NHL: Season starts in October (month >= 10), ends in June
      - If month >= 10: season = year
      - If month < 10: season = year - 1
    - NCAAB/NCAAF: Season starts in November (month >= 11), ends in April
      - If month >= 11: season = year
      - If month < 11: season = year - 1
    
    Args:
        day: Date to calculate season for
        league_code: League code (NBA, NFL, MLB, NHL, NCAAB, NCAAF)
        
    Returns:
        Season year (e.g., 2023 for 2023-24 season)
    """
    month = day.month
    year = day.year
    
    if league_code == "NBA":
        # NBA season: October (10) to June (6)
        return year if month >= 10 else year - 1
    elif league_code == "NFL":
        # NFL season: September (9) to February (2)
        return year if month >= 9 else year - 1
    elif league_code == "MLB":
        # MLB season: March (3) to October (10)
        return year if month >= 3 else year - 1
    elif league_code == "NHL":
        # NHL season: October (10) to June (6)
        return year if month >= 10 else year - 1
    elif league_code in ("NCAAB", "NCAAF"):
        # College season: November (11) to April (4)
        return year if month >= 11 else year - 1
    else:
        # Default: assume season starts in July (like NBA/NHL)
        return year if month >= 7 else year - 1

