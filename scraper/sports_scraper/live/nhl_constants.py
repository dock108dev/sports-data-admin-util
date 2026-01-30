"""Constants for NHL live feed processing.

Contains API endpoints and event type mappings.
"""

from __future__ import annotations

# NHL API endpoints (api-web.nhle.com)
NHL_SCHEDULE_URL = "https://api-web.nhle.com/v1/schedule/{date}"
NHL_PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
NHL_BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"

# Play index multiplier to ensure unique ordering across periods
# Allows up to 10,000 plays per period (sufficient for multi-OT games)
NHL_PERIOD_MULTIPLIER = 10000

# Minimum expected plays for a completed NHL game
NHL_MIN_EXPECTED_PLAYS = 100

# Explicit mapping of NHL event types from typeDescKey
# All recognized event types - unknown types are logged but still stored
NHL_EVENT_TYPE_MAP: dict[str, str] = {
    # Scoring events
    "goal": "GOAL",
    # Shot events
    "shot-on-goal": "SHOT",
    "missed-shot": "MISS",
    "blocked-shot": "BLOCK",
    # Physical play
    "hit": "HIT",
    "giveaway": "GIVEAWAY",
    "takeaway": "TAKEAWAY",
    # Penalties
    "penalty": "PENALTY",
    # Face-offs
    "faceoff": "FACEOFF",
    # Game flow
    "stoppage": "STOPPAGE",
    "period-start": "PERIOD_START",
    "period-end": "PERIOD_END",
    "game-end": "GAME_END",
    "game-official": "GAME_OFFICIAL",
    "shootout-complete": "SHOOTOUT_COMPLETE",
    # Other
    "delayed-penalty": "DELAYED_PENALTY",
    "failed-shot-attempt": "FAILED_SHOT",
}
