"""Score masking service for enforcing score-hide preferences at the API layer.

Determines whether scores should be visible for a given game based on
the user's score reveal mode, hidden leagues/teams, and revealed games.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserScorePreferences:
    """Resolved score preferences for a single request."""

    user_id: int
    role: str
    score_reveal_mode: str
    score_hide_leagues: list[str]
    score_hide_teams: list[str]
    revealed_game_ids: set[int]


def should_mask_score(
    prefs: UserScorePreferences | None,
    game_id: int,
    league_code: str,
    home_team_abbr: str | None,
    away_team_abbr: str | None,
) -> bool:
    """Return True if scores should be replaced with null for this game.

    Masking rules:
    - No preferences (guest/unauthenticated) → no masking
    - Admin/analyst role → no masking
    - ``always`` reveal mode → no masking
    - ``onMarkRead`` mode → mask unless game is in revealed set
    - ``blacklist`` mode → mask only if the game's league or either team
      is in the user's hide lists (and game not revealed)
    """
    if prefs is None:
        return False

    if prefs.role == "admin":
        return False

    if prefs.score_reveal_mode == "always":
        return False

    if game_id in prefs.revealed_game_ids:
        return False

    if prefs.score_reveal_mode == "onMarkRead":
        return True

    if prefs.score_reveal_mode == "blacklist":
        if league_code.upper() in {lg.upper() for lg in prefs.score_hide_leagues}:
            return True
        hide_teams_lower = {t.lower() for t in prefs.score_hide_teams}
        if home_team_abbr and home_team_abbr.lower() in hide_teams_lower:
            return True
        return bool(away_team_abbr and away_team_abbr.lower() in hide_teams_lower)

    return False
