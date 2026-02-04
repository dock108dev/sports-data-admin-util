"""Constants for NBA live feed processing.

Contains API endpoints and minimum expected plays.
"""

from __future__ import annotations

# Minimum expected plays for a completed NBA game
# A typical NBA game has 200-300 plays. Use 100 as a conservative minimum.
NBA_MIN_EXPECTED_PLAYS = 100
