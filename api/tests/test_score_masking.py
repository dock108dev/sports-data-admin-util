"""Tests for score masking service and endpoint integration."""

from __future__ import annotations

from app.services.score_masking import UserScorePreferences, should_mask_score

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _prefs(
    mode: str = "onMarkRead",
    hide_leagues: list[str] | None = None,
    hide_teams: list[str] | None = None,
    revealed: set[int] | None = None,
    role: str = "user",
) -> UserScorePreferences:
    return UserScorePreferences(
        user_id=1,
        role=role,
        score_reveal_mode=mode,
        score_hide_leagues=hide_leagues or [],
        score_hide_teams=hide_teams or [],
        revealed_game_ids=revealed or set(),
    )


GAME_ID = 42
LEAGUE = "NBA"
HOME_ABBR = "LAL"
AWAY_ABBR = "BOS"


# ---------------------------------------------------------------------------
# No preferences (guest / unauthenticated)
# ---------------------------------------------------------------------------

class TestNoPreferences:
    def test_none_prefs_no_masking(self) -> None:
        assert not should_mask_score(None, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)


# ---------------------------------------------------------------------------
# Admin bypass
# ---------------------------------------------------------------------------

class TestAdminBypass:
    def test_admin_never_masked(self) -> None:
        prefs = _prefs(mode="onMarkRead", role="admin")
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_admin_with_blacklist_never_masked(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["NBA"], role="admin")
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)


# ---------------------------------------------------------------------------
# "always" reveal mode — no masking ever
# ---------------------------------------------------------------------------

class TestAlwaysMode:
    def test_always_mode_no_masking(self) -> None:
        prefs = _prefs(mode="always")
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_always_mode_ignores_hide_lists(self) -> None:
        prefs = _prefs(mode="always", hide_leagues=["NBA"], hide_teams=["LAL"])
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)


# ---------------------------------------------------------------------------
# "onMarkRead" reveal mode — masked until game is revealed
# ---------------------------------------------------------------------------

class TestOnMarkReadMode:
    def test_unrevealed_game_masked(self) -> None:
        prefs = _prefs(mode="onMarkRead")
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_revealed_game_not_masked(self) -> None:
        prefs = _prefs(mode="onMarkRead", revealed={GAME_ID})
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_other_game_revealed_still_masked(self) -> None:
        prefs = _prefs(mode="onMarkRead", revealed={999})
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)


# ---------------------------------------------------------------------------
# "blacklist" reveal mode — masked only for listed leagues/teams
# ---------------------------------------------------------------------------

class TestBlacklistMode:
    def test_no_blacklist_no_masking(self) -> None:
        prefs = _prefs(mode="blacklist")
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_league_blacklisted(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["NBA"])
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_league_blacklist_case_insensitive(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["nba"])
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_home_team_blacklisted(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["LAL"])
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_away_team_blacklisted(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["BOS"])
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_team_blacklist_case_insensitive(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["lal"])
        assert should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_unrelated_league_not_masked(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["NFL"])
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_unrelated_team_not_masked(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["NYK"])
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_blacklisted_but_revealed(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["NBA"], revealed={GAME_ID})
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_blacklisted_team_but_revealed(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["LAL"], revealed={GAME_ID})
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_abbreviations_no_crash(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["LAL"])
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, None, None)

    def test_empty_league_code(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["NBA"])
        assert not should_mask_score(prefs, GAME_ID, "", HOME_ABBR, AWAY_ABBR)

    def test_unknown_mode_no_masking(self) -> None:
        prefs = _prefs(mode="unknown_mode")
        assert not should_mask_score(prefs, GAME_ID, LEAGUE, HOME_ABBR, AWAY_ABBR)

    def test_multiple_leagues_blacklisted(self) -> None:
        prefs = _prefs(mode="blacklist", hide_leagues=["NFL", "NBA", "MLB"])
        assert should_mask_score(prefs, GAME_ID, "NBA", HOME_ABBR, AWAY_ABBR)
        assert should_mask_score(prefs, GAME_ID, "NFL", HOME_ABBR, AWAY_ABBR)
        assert not should_mask_score(prefs, GAME_ID, "NHL", HOME_ABBR, AWAY_ABBR)

    def test_multiple_teams_blacklisted(self) -> None:
        prefs = _prefs(mode="blacklist", hide_teams=["LAL", "BOS", "NYK"])
        assert should_mask_score(prefs, 1, LEAGUE, "LAL", "GSW")
        assert should_mask_score(prefs, 2, LEAGUE, "GSW", "BOS")
        assert not should_mask_score(prefs, 3, LEAGUE, "GSW", "MIA")
