"""Constants for NCAA API live feed processing.

The NCAA API (ncaa-api.henrygd.me) provides real-time scoreboard data with
accurate game states, plus per-game PBP and boxscore endpoints. It serves
as the primary live data source for NCAAB polling.

Key properties:
- Free, no authentication required
- 5 requests/second rate limit
- All numeric values returned as strings
"""

from __future__ import annotations

import re

# NCAA API base URL and endpoint templates
NCAA_API_BASE = "https://ncaa-api.henrygd.me"
NCAA_SCOREBOARD_URL = f"{NCAA_API_BASE}/scoreboard/basketball-men/d1"
NCAA_PBP_URL = f"{NCAA_API_BASE}/game/{{game_id}}/play-by-play"
NCAA_BOXSCORE_URL = f"{NCAA_API_BASE}/game/{{game_id}}/boxscore"
NCAA_TEAM_STATS_URL = f"{NCAA_API_BASE}/game/{{game_id}}/team-stats"

# Map NCAA API gameState values to our normalized status strings
NCAA_GAME_STATE_MAP: dict[str, str] = {
    "live": "live",
    "final": "final",
    "pre": "scheduled",
}

# Minimum interval between NCAA API requests (seconds) to respect 5 req/s limit
NCAA_MIN_REQUEST_INTERVAL = 0.25

# Regex-based play type classification for NCAA eventDescription text.
# Patterns are checked in order; first match wins.
# Each tuple is (compiled_regex, canonical_play_type).
NCAA_EVENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Free throws (check before general shot patterns)
    (re.compile(r"free throw.*made", re.IGNORECASE), "MADE_FREE_THROW"),
    (re.compile(r"free throw.*missed", re.IGNORECASE), "MISSED_FREE_THROW"),
    (re.compile(r"made free throw", re.IGNORECASE), "MADE_FREE_THROW"),
    (re.compile(r"missed free throw", re.IGNORECASE), "MISSED_FREE_THROW"),
    # Three-point shots (check before general shot patterns)
    (re.compile(r"three point.*made|made three point|made 3-?pt", re.IGNORECASE), "MADE_THREE"),
    (re.compile(r"three point.*missed|missed three point|missed 3-?pt", re.IGNORECASE), "MISSED_THREE"),
    # General made/missed shots
    (re.compile(r"(layup|dunk|jumper|jump shot|hook shot|tip shot).*made|made.*(layup|dunk|jumper|jump shot|hook shot|tip shot)", re.IGNORECASE), "MADE_SHOT"),
    (re.compile(r"(layup|dunk|jumper|jump shot|hook shot|tip shot).*missed|missed.*(layup|dunk|jumper|jump shot|hook shot|tip shot)", re.IGNORECASE), "MISSED_SHOT"),
    (re.compile(r"\bmade\b.*\bshot\b|\bshot\b.*\bmade\b", re.IGNORECASE), "MADE_SHOT"),
    (re.compile(r"\bmissed\b.*\bshot\b|\bshot\b.*\bmissed\b", re.IGNORECASE), "MISSED_SHOT"),
    # Rebounds
    (re.compile(r"offensive rebound|off\.? rebound", re.IGNORECASE), "OFFENSIVE_REBOUND"),
    (re.compile(r"defensive rebound|def\.? rebound", re.IGNORECASE), "DEFENSIVE_REBOUND"),
    (re.compile(r"deadball rebound|dead ball rebound|team rebound", re.IGNORECASE), "REBOUND"),
    (re.compile(r"\brebound\b", re.IGNORECASE), "REBOUND"),
    # Turnovers
    (re.compile(r"turnover|traveling|shot clock|out of bounds.*turn|bad pass|lost ball", re.IGNORECASE), "TURNOVER"),
    # Steals
    (re.compile(r"\bsteal\b|\bstolen\b", re.IGNORECASE), "STEAL"),
    # Blocks
    (re.compile(r"\bblock(ed)?\b", re.IGNORECASE), "BLOCK"),
    # Assists
    (re.compile(r"\bassist\b", re.IGNORECASE), "ASSIST"),
    # Fouls
    (re.compile(r"technical foul", re.IGNORECASE), "TECHNICAL_FOUL"),
    (re.compile(r"flagrant foul", re.IGNORECASE), "FLAGRANT_FOUL"),
    (re.compile(r"offensive foul|charging", re.IGNORECASE), "OFFENSIVE_FOUL"),
    (re.compile(r"shooting foul", re.IGNORECASE), "SHOOTING_FOUL"),
    (re.compile(r"personal foul|\bfoul\b", re.IGNORECASE), "PERSONAL_FOUL"),
    # Timeouts
    (re.compile(r"timeout|time out|time-out|media timeout", re.IGNORECASE), "TIMEOUT"),
    # Substitutions
    (re.compile(r"\bsubstitution\b|\bsub\b.*\bin\b|\bsub\b.*\bout\b", re.IGNORECASE), "SUBSTITUTION"),
    # Jump balls
    (re.compile(r"jump ball", re.IGNORECASE), "JUMP_BALL"),
    # Period markers
    (re.compile(r"end\s+(of\s+)?(period|half|game|overtime)", re.IGNORECASE), "END_PERIOD"),
    (re.compile(r"start\s+(of\s+)?(period|half|game|overtime)", re.IGNORECASE), "START_PERIOD"),
]
