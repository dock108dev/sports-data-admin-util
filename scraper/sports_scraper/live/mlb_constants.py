"""Constants for MLB live feed processing.

Contains API endpoints and event type mappings for statsapi.mlb.com.
"""

from __future__ import annotations

# MLB Stats API endpoints (statsapi.mlb.com)
MLB_SCHEDULE_URL = (
    "https://statsapi.mlb.com/api/v1/schedule"
    "?sportId=1&date={date}&hydrate=team,venue,weather,linescore"
)
MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore"
MLB_PBP_URL = "https://statsapi.mlb.com/api/v1/game/{game_pk}/playByPlay"

# Play index multiplier to ensure unique ordering across innings
# Allows up to 10,000 at-bats per inning (more than sufficient)
MLB_INNING_MULTIPLIER = 10000

# Minimum expected plays for a completed MLB game
MLB_MIN_EXPECTED_PLAYS = 50

# Offset for bottom-of-inning plays within the multiplier range
MLB_HALF_INNING_BOTTOM_OFFSET = 5000

# Explicit mapping of MLB event types from result.eventType
# All recognized event types - unknown types are logged but still stored
MLB_EVENT_TYPE_MAP: dict[str, str] = {
    # Hit events
    "single": "SINGLE",
    "double": "DOUBLE",
    "triple": "TRIPLE",
    "home_run": "HOME_RUN",
    # Out events
    "strikeout": "STRIKEOUT",
    "field_out": "FIELD_OUT",
    "grounded_into_double_play": "DOUBLE_PLAY",
    "double_play": "DOUBLE_PLAY",
    "triple_play": "TRIPLE_PLAY",
    "force_out": "FORCE_OUT",
    "sac_fly": "SAC_FLY",
    "sac_bunt": "SAC_BUNT",
    "fielders_choice_out": "FIELDERS_CHOICE",
    "fielders_choice": "FIELDERS_CHOICE",
    "strikeout_double_play": "STRIKEOUT_DOUBLE_PLAY",
    # Walk / HBP
    "walk": "WALK",
    "intent_walk": "INTENT_WALK",
    "hit_by_pitch": "HIT_BY_PITCH",
    # Baserunning
    "stolen_base_2b": "STOLEN_BASE",
    "stolen_base_3b": "STOLEN_BASE",
    "stolen_base_home": "STOLEN_BASE",
    "caught_stealing_2b": "CAUGHT_STEALING",
    "caught_stealing_3b": "CAUGHT_STEALING",
    "caught_stealing_home": "CAUGHT_STEALING",
    "wild_pitch": "WILD_PITCH",
    "passed_ball": "PASSED_BALL",
    "balk": "BALK",
    "pickoff_1b": "PICKOFF",
    "pickoff_2b": "PICKOFF",
    "pickoff_3b": "PICKOFF",
    # Errors
    "field_error": "ERROR",
    "catcher_interf": "CATCHER_INTERFERENCE",
    # Game flow
    "game_advisory": "GAME_ADVISORY",
    "runner_placed": "RUNNER_PLACED",
}
