"""Tests for game_metadata nuggets module."""

from datetime import datetime


class TestNormalizeTags:
    """Tests for _normalize_tags function."""

    def test_normalizes_to_lowercase(self):
        """Tags are lowercased."""
        from app.game_metadata.nuggets import _normalize_tags

        result = _normalize_tags(["RIVALRY", "Top25"])
        assert "rivalry" in result
        assert "top25" in result

    def test_replaces_spaces_with_underscores(self):
        """Spaces become underscores."""
        from app.game_metadata.nuggets import _normalize_tags

        result = _normalize_tags(["playoff implications"])
        assert "playoff_implications" in result

    def test_strips_whitespace(self):
        """Leading/trailing whitespace stripped."""
        from app.game_metadata.nuggets import _normalize_tags

        result = _normalize_tags(["  rivalry  ", "  playoff  "])
        assert "rivalry" in result
        assert "playoff" in result

    def test_filters_empty_strings(self):
        """Empty strings are filtered out."""
        from app.game_metadata.nuggets import _normalize_tags

        result = _normalize_tags(["rivalry", "", "  ", "playoff"])
        assert len(result) == 2
        assert "" not in result

    def test_filters_non_strings(self):
        """Non-string values are filtered out."""
        from app.game_metadata.nuggets import _normalize_tags

        result = _normalize_tags(["rivalry", None, 123, "playoff"])
        assert len(result) == 2

    def test_empty_input(self):
        """Empty input returns empty set."""
        from app.game_metadata.nuggets import _normalize_tags

        result = _normalize_tags([])
        assert result == set()


class TestContextTags:
    """Tests for _context_tags function."""

    def _make_context(self, **kwargs):
        """Create a mock GameContext."""
        from app.game_metadata.models import GameContext

        defaults = {
            "game_id": "123",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "league": "NBA",
            "start_time": datetime(2025, 1, 15, 19, 0, 0),
            "rivalry": False,
            "playoff_implications": False,
            "national_broadcast": False,
            "has_big_name_players": False,
            "coach_vs_former_team": False,
            "projected_spread": None,
            "projected_total": None,
        }
        defaults.update(kwargs)
        return GameContext(**defaults)

    def test_rivalry_tag(self):
        """Rivalry adds rivalry tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(rivalry=True)
        result = _context_tags(context)
        assert "rivalry" in result

    def test_playoff_implications_tag(self):
        """Playoff implications adds tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(playoff_implications=True)
        result = _context_tags(context)
        assert "playoff_implications" in result

    def test_national_broadcast_tag(self):
        """National broadcast adds tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(national_broadcast=True)
        result = _context_tags(context)
        assert "national_broadcast" in result

    def test_star_power_tag(self):
        """Big name players adds star_power tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(has_big_name_players=True)
        result = _context_tags(context)
        assert "star_power" in result

    def test_coach_revenge_tag(self):
        """Coach vs former team adds coach_revenge tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(coach_vs_former_team=True)
        result = _context_tags(context)
        assert "coach_revenge" in result

    def test_tight_spread_tag(self):
        """Spread <= 4 adds tight_spread tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(projected_spread=3.5)
        result = _context_tags(context)
        assert "tight_spread" in result

    def test_no_tight_spread_for_large_spread(self):
        """Spread > 4 doesn't add tight_spread."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(projected_spread=7.5)
        result = _context_tags(context)
        assert "tight_spread" not in result

    def test_high_total_tag(self):
        """Total >= 150 adds high_total tag."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(projected_total=155)
        result = _context_tags(context)
        assert "high_total" in result

    def test_no_high_total_for_low_total(self):
        """Total < 150 doesn't add high_total."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(projected_total=140)
        result = _context_tags(context)
        assert "high_total" not in result

    def test_no_tags_when_all_false(self):
        """No tags when everything is False/None."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context()
        result = _context_tags(context)
        assert result == set()

    def test_multiple_tags(self):
        """Multiple conditions add multiple tags."""
        from app.game_metadata.nuggets import _context_tags

        context = self._make_context(
            rivalry=True,
            playoff_implications=True,
            projected_spread=2.0,
        )
        result = _context_tags(context)
        assert "rivalry" in result
        assert "playoff_implications" in result
        assert "tight_spread" in result


class TestGenerateNugget:
    """Tests for generate_nugget function."""

    def _make_context(self, **kwargs):
        """Create a mock GameContext."""
        from app.game_metadata.models import GameContext

        defaults = {
            "game_id": "123",
            "home_team": "Lakers",
            "away_team": "Celtics",
            "league": "NBA",
            "start_time": datetime(2025, 1, 15, 19, 0, 0),
            "rivalry": False,
            "playoff_implications": False,
            "national_broadcast": False,
            "has_big_name_players": False,
            "coach_vs_former_team": False,
            "projected_spread": None,
            "projected_total": None,
        }
        defaults.update(kwargs)
        return GameContext(**defaults)

    def test_default_nugget_when_no_match(self):
        """Returns default when no template matches."""
        from app.game_metadata.nuggets import generate_nugget, DEFAULT_NUGGET

        context = self._make_context()
        result = generate_nugget(context, [])
        assert result == DEFAULT_NUGGET

    def test_playoff_implications_template(self):
        """Playoff implications template matched."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context(playoff_implications=True)
        result = generate_nugget(context, [])
        assert "postseason" in result.lower()

    def test_tight_spread_template(self):
        """Tight spread template matched."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context(projected_spread=2.5)
        result = generate_nugget(context, [])
        assert "final stretch" in result.lower() or "oddsmakers" in result.lower()

    def test_high_total_template(self):
        """High total template matched."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context(projected_total=160)
        result = generate_nugget(context, [])
        assert "tempo" in result.lower() or "points" in result.lower()

    def test_national_broadcast_with_stars(self):
        """National broadcast + star power template."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context(
            national_broadcast=True,
            has_big_name_players=True,
        )
        result = generate_nugget(context, [])
        assert "national" in result.lower() or "star" in result.lower()

    def test_tags_from_input_combined_with_context(self):
        """Input tags combined with context tags."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context(rivalry=True)
        # Add playoff_implications via tags
        result = generate_nugget(context, ["playoff_implications"])
        assert "rivalry" in result.lower() or "postseason" in result.lower()

    def test_conference_lead_template(self):
        """Conference lead templates require input tags."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context()
        result = generate_nugget(context, ["conference_lead", "top25_matchup"])
        assert "conference" in result.lower() or "championship" in result.lower()

    def test_tournament_preview_template(self):
        """Tournament preview template."""
        from app.game_metadata.nuggets import generate_nugget

        context = self._make_context()
        result = generate_nugget(context, ["tournament_preview", "top_rated"])
        assert "tournament" in result.lower() or "top-rated" in result.lower()
