"""Tests for app.services.team_colors."""

import math

from app.services.team_colors import (
    CLASH_THRESHOLD,
    NEUTRAL_DARK,
    NEUTRAL_LIGHT,
    color_distance,
    get_matchup_colors,
    hex_to_rgb,
)


# ---------------------------------------------------------------------------
# hex_to_rgb
# ---------------------------------------------------------------------------


class TestHexToRgb:
    def test_black(self):
        assert hex_to_rgb("#000000") == (0.0, 0.0, 0.0)

    def test_white(self):
        assert hex_to_rgb("#FFFFFF") == (1.0, 1.0, 1.0)

    def test_pure_red(self):
        assert hex_to_rgb("#FF0000") == (1.0, 0.0, 0.0)

    def test_arbitrary_color(self):
        r, g, b = hex_to_rgb("#1A2B3C")
        assert abs(r - 26 / 255) < 1e-6
        assert abs(g - 43 / 255) < 1e-6
        assert abs(b - 60 / 255) < 1e-6

    def test_lowercase_hex(self):
        assert hex_to_rgb("#aabbcc") == hex_to_rgb("#AABBCC")


# ---------------------------------------------------------------------------
# color_distance
# ---------------------------------------------------------------------------


class TestColorDistance:
    def test_identical_colors_zero(self):
        assert color_distance("#FF0000", "#FF0000") == 0.0

    def test_black_white_is_one(self):
        d = color_distance("#000000", "#FFFFFF")
        assert abs(d - 1.0) < 1e-6

    def test_symmetric(self):
        d1 = color_distance("#112233", "#AABBCC")
        d2 = color_distance("#AABBCC", "#112233")
        assert abs(d1 - d2) < 1e-9

    def test_range_is_0_to_1(self):
        d = color_distance("#FF0000", "#00FF00")
        assert 0.0 <= d <= 1.0


# ---------------------------------------------------------------------------
# get_matchup_colors
# ---------------------------------------------------------------------------


class TestGetMatchupColors:
    def test_distinct_colors_pass_through(self):
        result = get_matchup_colors("#FF0000", "#CC0000", "#0000FF", "#0000CC")
        assert result["homeLightHex"] == "#FF0000"
        assert result["homeDarkHex"] == "#CC0000"
        assert result["awayLightHex"] == "#0000FF"
        assert result["awayDarkHex"] == "#0000CC"

    def test_clashing_colors_home_yields(self):
        # Same color for both teams — home should be replaced with neutral
        result = get_matchup_colors("#FF0000", "#CC0000", "#FF0000", "#CC0000")
        assert result["homeLightHex"] == NEUTRAL_LIGHT
        assert result["homeDarkHex"] == NEUTRAL_DARK
        assert result["awayLightHex"] == "#FF0000"
        assert result["awayDarkHex"] == "#CC0000"

    def test_very_similar_colors_clash(self):
        # Colors differ by 1 unit in red — distance is tiny, should clash
        result = get_matchup_colors("#FF0000", "#000000", "#FE0000", "#000000")
        assert result["homeLightHex"] == NEUTRAL_LIGHT

    def test_none_colors_default_to_neutral(self):
        result = get_matchup_colors(None, None, None, None)
        # Both default to neutral, which clash (distance = 0), so home yields
        assert result["homeLightHex"] == NEUTRAL_LIGHT
        assert result["homeDarkHex"] == NEUTRAL_DARK
        assert result["awayLightHex"] == NEUTRAL_LIGHT
        assert result["awayDarkHex"] == NEUTRAL_DARK

    def test_one_side_none(self):
        result = get_matchup_colors(None, None, "#0000FF", "#0000CC")
        # Home defaults to #000000, away is #0000FF — likely distinct
        assert result["awayLightHex"] == "#0000FF"
