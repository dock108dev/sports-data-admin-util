"""Team color utilities: hex conversion and clash detection.

Ported from GameTheme.swift (lines 617-658). This is a pure utility module
with no database access — it can be called from game endpoints to resolve
matchup colors when two teams have visually similar colors.
"""

from __future__ import annotations

import math

CLASH_THRESHOLD = 0.12
NEUTRAL_LIGHT = "#000000"  # black for light mode
NEUTRAL_DARK = "#FFFFFF"   # white for dark mode


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    """Convert '#RRGGBB' to normalized (0.0-1.0) RGB tuple."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r / 255.0, g / 255.0, b / 255.0


def color_distance(c1: str, c2: str) -> float:
    """Normalized Euclidean distance in RGB space (0.0-1.0).

    Max possible RGB distance is sqrt(3) ≈ 1.732, so we normalize by that.
    Matches the Swift implementation in GameTheme.swift.
    """
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    dr = r1 - r2
    dg = g1 - g2
    db = b1 - b2
    return math.sqrt(dr * dr + dg * dg + db * db) / math.sqrt(3)


def get_matchup_colors(
    home_color_light: str | None,
    home_color_dark: str | None,
    away_color_light: str | None,
    away_color_dark: str | None,
) -> dict[str, str]:
    """Return matchup-aware colors. Home team yields to neutral on clash.

    When the home and away light-mode colors are too similar (distance < threshold),
    the home team's colors are replaced with neutral black/white to ensure visual
    distinction. This matches the Swift app behavior where the home team yields.

    Returns dict with keys: homeLightHex, homeDarkHex, awayLightHex, awayDarkHex.
    """
    h_light = home_color_light or NEUTRAL_LIGHT
    h_dark = home_color_dark or NEUTRAL_DARK
    a_light = away_color_light or NEUTRAL_LIGHT
    a_dark = away_color_dark or NEUTRAL_DARK

    # Check clash on light-mode colors (primary comparison)
    if color_distance(h_light, a_light) < CLASH_THRESHOLD:
        h_light = NEUTRAL_LIGHT
        h_dark = NEUTRAL_DARK

    return {
        "homeLightHex": h_light,
        "homeDarkHex": h_dark,
        "awayLightHex": a_light,
        "awayDarkHex": a_dark,
    }
