"""Sport-aware period labels for play-by-play data."""

from __future__ import annotations


def period_label(period: int, league_code: str) -> str:
    """Return a display-ready period label.

    NBA:   Q1-Q4, OT, 2OT, 3OT …
    NHL:   P1-P3, OT, SO
    NCAAB: H1, H2, OT, 2OT, 3OT …
    """
    code = league_code.upper()

    if code == "NHL":
        if period <= 3:
            return f"P{period}"
        if period == 4:
            return "OT"
        return "SO"

    if code == "NCAAB":
        if period <= 2:
            return f"H{period}"
        ot_num = period - 2
        return "OT" if ot_num == 1 else f"{ot_num}OT"

    # NBA (default)
    if period <= 4:
        return f"Q{period}"
    ot_num = period - 4
    return "OT" if ot_num == 1 else f"{ot_num}OT"


def time_label(period: int, game_clock: str | None, league_code: str) -> str:
    """Combine period label + game clock: "Q4 2:35", "P3 12:00", "H2 5:15"."""
    plabel = period_label(period, league_code)
    if game_clock:
        return f"{plabel} {game_clock}"
    return plabel
