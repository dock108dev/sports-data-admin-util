"""Constants for NBA live feed processing.

Contains API endpoints and minimum expected plays.
"""

from __future__ import annotations

# Minimum expected plays for a completed NBA game
# A typical NBA game has 200-300 plays. Use 100 as a conservative minimum.
NBA_MIN_EXPECTED_PLAYS = 100

# NBA CDN boxscore endpoint — data available immediately after game ends
NBA_BOXSCORE_URL = "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
