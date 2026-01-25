"""
Unit tests for Player Identity Resolution.

These tests validate:
- Canonical player key generation
- Truncated name detection
- Alias resolution via roster lookup
- Diacritics handling
- Unresolved name logging

ISSUE: Name Resolution (Chapters-First Architecture)
"""

import pytest

from app.services.chapters.player_identity import (
    # Data structures
    RosterPlayer,
    # Functions
    normalize_for_matching,
    extract_initial_and_lastname,
    is_truncated_name,
    build_roster_from_boxscore,
    # Resolver class
    PlayerIdentityResolver,
)


# ============================================================================
# TEST: NAME NORMALIZATION
# ============================================================================


class TestNormalizeForMatching:
    """Tests for normalize_for_matching function."""

    def test_lowercase(self):
        """Should convert to lowercase."""
        assert normalize_for_matching("LeBron James") == "lebron james"

    def test_strip_whitespace(self):
        """Should strip leading/trailing whitespace."""
        assert normalize_for_matching("  LeBron James  ") == "lebron james"

    def test_collapse_internal_spaces(self):
        """Should collapse multiple internal spaces."""
        assert normalize_for_matching("LeBron  James") == "lebron james"

    def test_remove_diacritics(self):
        """Should remove diacritics (e.g., accents)."""
        assert normalize_for_matching("Nikola Vučević") == "nikola vucevic"
        assert normalize_for_matching("José Calderón") == "jose calderon"
        # Note: Turkish 'ş' (s-cedilla) decomposes to 's' alone, not 'si'
        # The 'ı' (dotless i) also doesn't have ASCII equivalent
        assert normalize_for_matching("Ömer Aşık") == "omer ask"

    def test_remove_punctuation(self):
        """Should remove punctuation."""
        assert normalize_for_matching("N. Vucevic") == "n vucevic"
        assert normalize_for_matching("O'Neal") == "oneal"
        assert normalize_for_matching("Abdul-Jabbar") == "abduljabbar"

    def test_empty_string(self):
        """Should handle empty string."""
        assert normalize_for_matching("") == ""

    def test_none_handling(self):
        """Should handle None gracefully."""
        assert normalize_for_matching(None) == ""


# ============================================================================
# TEST: TRUNCATED NAME DETECTION
# ============================================================================


class TestIsTruncatedName:
    """Tests for is_truncated_name function."""

    def test_initial_first(self):
        """Should detect initial-first pattern."""
        assert is_truncated_name("N. Vucevic") is True
        assert is_truncated_name("N Vucevic") is True
        assert is_truncated_name("I. Joe") is True

    def test_full_name_not_truncated(self):
        """Should not flag full names as truncated."""
        assert is_truncated_name("Nikola Vucevic") is False
        assert is_truncated_name("LeBron James") is False
        assert is_truncated_name("Giannis Antetokounmpo") is False

    def test_single_name_not_truncated(self):
        """Should not flag single names as truncated."""
        assert is_truncated_name("LeBron") is False
        assert is_truncated_name("Nene") is False

    def test_empty_string(self):
        """Should handle empty string."""
        assert is_truncated_name("") is False


class TestExtractInitialAndLastname:
    """Tests for extract_initial_and_lastname function."""

    def test_initial_first_with_period(self):
        """Should extract from 'N. Lastname' pattern."""
        result = extract_initial_and_lastname("N. Vucevic")
        assert result == ("n", "vucevic")

    def test_initial_first_without_period(self):
        """Should extract from 'N Lastname' pattern."""
        result = extract_initial_and_lastname("N Vucevic")
        assert result == ("n", "vucevic")

    def test_multi_word_lastname(self):
        """Should handle multi-word last names."""
        result = extract_initial_and_lastname("G. Antetokounmpo")
        assert result == ("g", "antetokounmpo")

    def test_full_name_returns_none(self):
        """Should return None for full names."""
        result = extract_initial_and_lastname("Nikola Vucevic")
        assert result is None

    def test_empty_string(self):
        """Should handle empty string."""
        result = extract_initial_and_lastname("")
        assert result is None


# ============================================================================
# TEST: ROSTER PLAYER
# ============================================================================


class TestRosterPlayer:
    """Tests for RosterPlayer dataclass."""

    def test_auto_extract_first_last_name(self):
        """Should auto-extract first/last name from full_name."""
        player = RosterPlayer(
            player_id="vuc1",
            full_name="Nikola Vucevic",
            team_id="CHI",
        )

        assert player.first_name == "Nikola"
        assert player.last_name == "Vucevic"

    def test_preserve_explicit_names(self):
        """Should preserve explicitly provided first/last names."""
        player = RosterPlayer(
            player_id="vuc1",
            full_name="Nikola Vucevic",
            team_id="CHI",
            first_name="Nikola",
            last_name="Vučević",  # Different spelling
        )

        assert player.first_name == "Nikola"
        assert player.last_name == "Vučević"

    def test_multi_word_lastname(self):
        """Should handle multi-word last names."""
        player = RosterPlayer(
            player_id="ga1",
            full_name="Giannis Antetokounmpo",
            team_id="MIL",
        )

        assert player.first_name == "Giannis"
        assert player.last_name == "Antetokounmpo"


# ============================================================================
# TEST: PLAYER IDENTITY RESOLVER
# ============================================================================


class TestPlayerIdentityResolver:
    """Tests for PlayerIdentityResolver class."""

    @pytest.fixture
    def sample_roster(self) -> list[RosterPlayer]:
        """Create sample roster for tests."""
        return [
            RosterPlayer(
                player_id="vuc1",
                full_name="Nikola Vucevic",
                team_id="CHI",
            ),
            RosterPlayer(
                player_id="joe1",
                full_name="Isaiah Joe",
                team_id="OKC",
            ),
            RosterPlayer(
                player_id="lbj1",
                full_name="LeBron James",
                team_id="LAL",
            ),
            RosterPlayer(
                player_id="ad1",
                full_name="Anthony Davis",
                team_id="LAL",
            ),
            RosterPlayer(
                player_id="jd1",
                full_name="James Davis",  # Same last name as Anthony
                team_id="MIA",
            ),
        ]

    def test_resolve_by_player_id(self, sample_roster):
        """Should resolve by player_id when available."""
        resolver = PlayerIdentityResolver(sample_roster)

        resolved = resolver.resolve("Some Name", player_id="vuc1")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vucevic"
        assert resolved.canonical_key == "nikola vucevic"
        assert resolved.player_id == "vuc1"
        assert resolved.is_alias is False

    def test_resolve_exact_match(self, sample_roster):
        """Should resolve exact name match."""
        resolver = PlayerIdentityResolver(sample_roster)

        resolved = resolver.resolve("Nikola Vucevic")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vucevic"
        assert resolved.is_alias is False

    def test_resolve_case_insensitive(self, sample_roster):
        """Should resolve case-insensitive match."""
        resolver = PlayerIdentityResolver(sample_roster)

        resolved = resolver.resolve("NIKOLA VUCEVIC")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vucevic"

    def test_resolve_truncated_name(self, sample_roster):
        """Should resolve truncated name via alias matching."""
        resolver = PlayerIdentityResolver(sample_roster)

        resolved = resolver.resolve("N. Vucevic", team_id="CHI")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vucevic"
        assert resolved.canonical_key == "nikola vucevic"
        assert resolved.is_alias is True
        assert resolved.raw_name == "N. Vucevic"

    def test_resolve_truncated_without_period(self, sample_roster):
        """Should resolve truncated name without period."""
        resolver = PlayerIdentityResolver(sample_roster)

        resolved = resolver.resolve("N Vucevic", team_id="CHI")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vucevic"
        assert resolved.is_alias is True

    def test_resolve_truncated_with_team_disambiguation(self, sample_roster):
        """Should use team_id to disambiguate truncated names."""
        resolver = PlayerIdentityResolver(sample_roster)

        # Both "A. Davis" and "J. Davis" exist with different teams
        resolved_ad = resolver.resolve("A. Davis", team_id="LAL")
        resolved_jd = resolver.resolve("J. Davis", team_id="MIA")

        assert resolved_ad is not None
        assert resolved_ad.canonical_name == "Anthony Davis"

        assert resolved_jd is not None
        assert resolved_jd.canonical_name == "James Davis"

    def test_resolve_unresolved_logs_warning(self, sample_roster, caplog):
        """Should log warning for unresolved names."""
        import logging

        resolver = PlayerIdentityResolver(sample_roster)

        with caplog.at_level(logging.WARNING):
            resolved = resolver.resolve("Unknown Player")

        # Should still return a result (with raw name as canonical)
        assert resolved is not None
        assert resolved.canonical_name == "Unknown Player"

        # Should have logged warning
        assert "Unresolved player name" in caplog.text

    def test_cache_alias_resolution(self, sample_roster):
        """Should cache alias resolutions."""
        resolver = PlayerIdentityResolver(sample_roster)

        # First resolution
        resolved1 = resolver.resolve("N. Vucevic", team_id="CHI")

        # Second resolution (should hit cache)
        resolved2 = resolver.resolve("N. Vucevic", team_id="CHI")

        assert resolved1 == resolved2

        # Check stats
        stats = resolver.get_stats()
        # Only one resolution should be counted (cache hit doesn't count)
        assert stats.alias_matches == 1

    def test_resolution_stats(self, sample_roster):
        """Should track resolution statistics."""
        resolver = PlayerIdentityResolver(sample_roster)

        # Various resolutions
        resolver.resolve("Nikola Vucevic")  # Direct match
        resolver.resolve("N. Vucevic", team_id="CHI")  # Alias match
        resolver.resolve("LeBron James", player_id="lbj1")  # Player ID match
        resolver.resolve("Unknown Player")  # Unresolved

        stats = resolver.get_stats()
        assert stats.total_resolutions == 4
        assert stats.direct_matches == 1
        assert stats.alias_matches == 1
        assert stats.player_id_matches == 1
        assert stats.unresolved == 1
        assert "Unknown Player" in stats.unresolved_names

    def test_get_canonical_key(self, sample_roster):
        """Should return canonical key via convenience method."""
        resolver = PlayerIdentityResolver(sample_roster)

        key = resolver.get_canonical_key("N. Vucevic", team_id="CHI")

        assert key == "nikola vucevic"

    def test_get_canonical_name(self, sample_roster):
        """Should return canonical name via convenience method."""
        resolver = PlayerIdentityResolver(sample_roster)

        name = resolver.get_canonical_name("N. Vucevic", team_id="CHI")

        assert name == "Nikola Vucevic"


class TestResolverWithDiacritics:
    """Tests for resolver handling of diacritics."""

    def test_resolve_with_diacritics_in_roster(self):
        """Should resolve names with diacritics in roster."""
        roster = [
            RosterPlayer(
                player_id="vuc1",
                full_name="Nikola Vučević",  # With diacritics
                team_id="CHI",
            ),
        ]
        resolver = PlayerIdentityResolver(roster)

        # Query without diacritics should still match
        resolved = resolver.resolve("Nikola Vucevic")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vučević"

    def test_resolve_truncated_with_diacritics(self):
        """Should resolve truncated names to names with diacritics."""
        roster = [
            RosterPlayer(
                player_id="vuc1",
                full_name="Nikola Vučević",
                team_id="CHI",
            ),
        ]
        resolver = PlayerIdentityResolver(roster)

        resolved = resolver.resolve("N. Vucevic", team_id="CHI")

        assert resolved is not None
        assert resolved.canonical_name == "Nikola Vučević"
        assert resolved.is_alias is True


class TestResolverEmptyRoster:
    """Tests for resolver with empty roster."""

    def test_empty_roster(self):
        """Should handle empty roster gracefully."""
        resolver = PlayerIdentityResolver([])

        resolved = resolver.resolve("LeBron James")

        # Should return unresolved result
        assert resolved is not None
        assert resolved.canonical_name == "LeBron James"
        assert resolved.is_alias is False

    def test_none_roster(self):
        """Should handle None roster."""
        resolver = PlayerIdentityResolver(None)

        resolved = resolver.resolve("LeBron James")

        assert resolved is not None


# ============================================================================
# TEST: BUILD ROSTER FROM BOXSCORE
# ============================================================================


class TestBuildRosterFromBoxscore:
    """Tests for build_roster_from_boxscore function."""

    def test_home_away_players(self):
        """Should extract players from home_players and away_players."""
        boxscore = {
            "home_players": [
                {"player_id": "p1", "player_name": "Player One", "team_id": "HOM"},
            ],
            "away_players": [
                {"player_id": "p2", "player_name": "Player Two", "team_id": "AWY"},
            ],
        }

        roster = build_roster_from_boxscore(boxscore)

        assert len(roster) == 2
        assert any(p.full_name == "Player One" for p in roster)
        assert any(p.full_name == "Player Two" for p in roster)

    def test_players_key(self):
        """Should extract from generic 'players' key."""
        boxscore = {
            "players": [
                {"player_id": "p1", "player_name": "Player One", "team_id": "TM1"},
            ],
        }

        roster = build_roster_from_boxscore(boxscore)

        assert len(roster) == 1
        assert roster[0].full_name == "Player One"

    def test_infer_team_from_source_key(self):
        """Should infer team from source key (home/away)."""
        boxscore = {
            "home_team_id": "HOM",
            "away_team_id": "AWY",
            "home_players": [
                {"player_id": "p1", "player_name": "Player One"},  # No team_id
            ],
            "away_players": [
                {"player_id": "p2", "player_name": "Player Two"},  # No team_id
            ],
        }

        roster = build_roster_from_boxscore(boxscore)

        home_player = next(p for p in roster if p.full_name == "Player One")
        away_player = next(p for p in roster if p.full_name == "Player Two")

        assert home_player.team_id == "HOM"
        assert away_player.team_id == "AWY"

    def test_skip_players_without_id(self):
        """Should skip players without player_id."""
        boxscore = {
            "players": [
                {"player_name": "Player Without ID"},  # No player_id
                {"player_id": "p1", "player_name": "Player With ID"},
            ],
        }

        roster = build_roster_from_boxscore(boxscore)

        assert len(roster) == 1
        assert roster[0].full_name == "Player With ID"


# ============================================================================
# TEST: INTEGRATION WITH RUNNING STATS
# ============================================================================


class TestResolverIntegration:
    """Integration tests for resolver with running_stats module."""

    def test_build_snapshots_with_resolver(self):
        """Should use resolver when building snapshots."""
        from app.services.chapters.types import Chapter, Play
        from app.services.chapters.running_stats import build_running_snapshots

        # Create roster with full name
        roster = [
            RosterPlayer(
                player_id="lbj1",
                full_name="LeBron James",
                team_id="LAL",
            ),
        ]
        resolver = PlayerIdentityResolver(roster)

        # Create chapter with truncated name
        plays = [
            Play(
                index=0,
                event_type="pbp",
                raw_data={
                    "description": "L. James makes layup",
                    "player_name": "L. James",  # Truncated
                    "team_abbreviation": "LAL",
                    "home_score": 2,
                    "away_score": 0,
                },
            ),
        ]
        chapter = Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=0,
            plays=plays,
            reason_codes=["TEST"],
        )

        # Build snapshots with resolver
        snapshots = build_running_snapshots([chapter], resolver=resolver)

        assert len(snapshots) == 1
        snapshot = snapshots[0]

        # Player should be stored under canonical key
        assert "lebron james" in snapshot.players
        player = snapshot.players["lebron james"]
        assert player.player_name == "LeBron James"  # Canonical display name
        assert player.points_scored_total == 2

    def test_stats_not_split_across_name_variants(self):
        """Stats should aggregate under single canonical key."""
        from app.services.chapters.types import Chapter, Play
        from app.services.chapters.running_stats import build_running_snapshots

        roster = [
            RosterPlayer(
                player_id="lbj1",
                full_name="LeBron James",
                team_id="LAL",
            ),
        ]
        resolver = PlayerIdentityResolver(roster)

        # Multiple plays with different name variants
        plays = [
            Play(
                index=0,
                event_type="pbp",
                raw_data={
                    "description": "L. James makes layup",
                    "player_name": "L. James",  # Truncated
                    "team_abbreviation": "LAL",
                    "home_score": 2,
                    "away_score": 0,
                },
            ),
            Play(
                index=1,
                event_type="pbp",
                raw_data={
                    "description": "LeBron James makes 3-pt",
                    "player_name": "LeBron James",  # Full name
                    "team_abbreviation": "LAL",
                    "home_score": 5,
                    "away_score": 0,
                },
            ),
        ]
        chapter = Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=1,
            plays=plays,
            reason_codes=["TEST"],
        )

        snapshots = build_running_snapshots([chapter], resolver=resolver)

        snapshot = snapshots[0]

        # Should only have one player entry
        assert len(snapshot.players) == 1
        assert "lebron james" in snapshot.players

        # Stats should be combined
        player = snapshot.players["lebron james"]
        assert player.points_scored_total == 5  # 2 + 3
        assert player.fg_made_total == 2
