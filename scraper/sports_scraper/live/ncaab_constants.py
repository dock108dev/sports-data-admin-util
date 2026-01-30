"""Constants for NCAAB live feed processing.

Extracted from ncaab.py to improve readability and maintainability.
Contains event type mappings for normalizing CBB API play types.
"""

from __future__ import annotations

# College Basketball Data API endpoints
CBB_API_BASE = "https://api.collegebasketballdata.com"
CBB_GAMES_URL = f"{CBB_API_BASE}/games"
CBB_GAMES_TEAMS_URL = f"{CBB_API_BASE}/games/teams"
CBB_GAMES_PLAYERS_URL = f"{CBB_API_BASE}/games/players"
CBB_PLAYS_GAME_URL = f"{CBB_API_BASE}/plays/game/{{game_id}}"

# Play index multiplier to ensure unique ordering across periods
# Allows up to 10,000 plays per period (sufficient for overtime games)
NCAAB_PERIOD_MULTIPLIER = 10000

# Minimum expected plays for a completed NCAAB game
NCAAB_MIN_EXPECTED_PLAYS = 100

# Mapping of play types from the CBB API to normalized event types.
# Based on actual API responses observed in logs.
# Note: API uses inconsistent naming (camelCase, spaces, etc.) so we map all variants.
NCAAB_EVENT_TYPE_MAP: dict[str, str] = {
    # Scoring events - shots (various naming conventions)
    "JumpShot": "MADE_SHOT",
    "Layup": "MADE_SHOT",
    "LayUpShot": "MADE_SHOT",
    "Dunk": "MADE_SHOT",
    "DunkShot": "MADE_SHOT",
    "Tip Shot": "MADE_SHOT",
    "TipShot": "MADE_SHOT",
    "Hook Shot": "MADE_SHOT",
    "HookShot": "MADE_SHOT",
    "Three Point Jumper": "MADE_SHOT",
    "ThreePointJumper": "MADE_SHOT",
    "Two Point Jumper": "MADE_SHOT",
    "TwoPointJumper": "MADE_SHOT",
    # Missed shots
    "Missed JumpShot": "MISSED_SHOT",
    "MissedJumpShot": "MISSED_SHOT",
    "Missed Layup": "MISSED_SHOT",
    "MissedLayup": "MISSED_SHOT",
    "MissedLayUpShot": "MISSED_SHOT",
    "Missed Dunk": "MISSED_SHOT",
    "MissedDunk": "MISSED_SHOT",
    "MissedDunkShot": "MISSED_SHOT",
    "Missed Three Point Jumper": "MISSED_SHOT",
    "MissedThreePointJumper": "MISSED_SHOT",
    "Missed Two Point Jumper": "MISSED_SHOT",
    "MissedTwoPointJumper": "MISSED_SHOT",
    "Missed Tip Shot": "MISSED_SHOT",
    "MissedTipShot": "MISSED_SHOT",
    "Missed Hook Shot": "MISSED_SHOT",
    "MissedHookShot": "MISSED_SHOT",
    # Free throws
    "Free Throw Made": "MADE_FREE_THROW",
    "Free Throw Missed": "MISSED_FREE_THROW",
    "MadeFreeThrow": "MADE_FREE_THROW",
    "MissedFreeThrow": "MISSED_FREE_THROW",
    # Rebounds
    "Offensive Rebound": "OFFENSIVE_REBOUND",
    "OffensiveRebound": "OFFENSIVE_REBOUND",
    "Defensive Rebound": "DEFENSIVE_REBOUND",
    "DefensiveRebound": "DEFENSIVE_REBOUND",
    "Rebound": "REBOUND",
    "Team Rebound": "REBOUND",
    "TeamRebound": "REBOUND",
    "Dead Ball Rebound": "REBOUND",
    "DeadBallRebound": "REBOUND",
    # Ball movement - turnovers
    "Turnover": "TURNOVER",
    "Lost Ball Turnover": "TURNOVER",
    "LostBallTurnover": "TURNOVER",
    "Bad Pass Turnover": "TURNOVER",
    "BadPassTurnover": "TURNOVER",
    "Traveling": "TURNOVER",
    "TravelingTurnover": "TURNOVER",
    "Out of Bounds Turnover": "TURNOVER",
    "OutOfBoundsTurnover": "TURNOVER",
    "Shot Clock Violation": "TURNOVER",
    "ShotClockViolation": "TURNOVER",
    "DoublePersonalFoul": "TURNOVER",
    # Other ball movement
    "Steal": "STEAL",
    "Assist": "ASSIST",
    # Fouls (various naming conventions)
    "Foul": "FOUL",
    "Personal Foul": "PERSONAL_FOUL",
    "PersonalFoul": "PERSONAL_FOUL",
    "Shooting Foul": "SHOOTING_FOUL",
    "ShootingFoul": "SHOOTING_FOUL",
    "Offensive Foul": "OFFENSIVE_FOUL",
    "OffensiveFoul": "OFFENSIVE_FOUL",
    "Technical Foul": "TECHNICAL_FOUL",
    "TechnicalFoul": "TECHNICAL_FOUL",
    "Flagrant Foul": "FLAGRANT_FOUL",
    "FlagrantFoul": "FLAGRANT_FOUL",
    "Charging Foul": "OFFENSIVE_FOUL",
    "ChargingFoul": "OFFENSIVE_FOUL",
    # Game flow - timeouts
    "Timeout": "TIMEOUT",
    "TV Timeout": "TIMEOUT",
    "TVTimeout": "TIMEOUT",
    "Team Timeout": "TIMEOUT",
    "TeamTimeout": "TIMEOUT",
    "Official Timeout": "TIMEOUT",
    "OfficialTimeout": "TIMEOUT",
    "OfficialTVTimeOut": "TIMEOUT",
    "ShortTimeOut": "TIMEOUT",
    "FullTimeOut": "TIMEOUT",
    "RegularTimeOut": "TIMEOUT",
    "Media Timeout": "TIMEOUT",
    "MediaTimeout": "TIMEOUT",
    # Other game flow
    "Substitution": "SUBSTITUTION",
    "JumpBall": "JUMP_BALL",
    "Jumpball": "JUMP_BALL",
    "Jump Ball": "JUMP_BALL",
    # Coach's challenge
    "Coach's Challenge (Stands)": "CHALLENGE",
    "Coach's Challenge (Overturned)": "CHALLENGE",
    "CoachsChallenge": "CHALLENGE",
    # Blocks
    "Block": "BLOCK",
    "Block Shot": "BLOCK",
    "BlockShot": "BLOCK",
    "Blocked Shot": "BLOCK",
    "BlockedShot": "BLOCK",
    # Period markers
    "End Period": "END_PERIOD",
    "EndPeriod": "END_PERIOD",
    "End Game": "END_GAME",
    "EndGame": "END_GAME",
    "End of Period": "END_PERIOD",
    "EndOfPeriod": "END_PERIOD",
    "Start Period": "START_PERIOD",
    "StartPeriod": "START_PERIOD",
    "Game Start": "GAME_START",
    "GameStart": "GAME_START",
    "End of Half": "END_PERIOD",
    "EndOfHalf": "END_PERIOD",
    "Start of Half": "START_PERIOD",
    "StartOfHalf": "START_PERIOD",
}
