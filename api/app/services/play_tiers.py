"""Server-side play tier classification.

Classifies every PBP play into Tier 1 (key scoring), Tier 2 (notable non-scoring),
or Tier 3 (routine) so consumers don't duplicate this logic on-device.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TIER_2_TYPES: dict[str, frozenset[str]] = {
    "NBA": frozenset(
        ["foul", "turnover", "steal", "block", "offensive foul"]
    ),
    "NCAAB": frozenset(
        [
            "personal_foul",
            "shooting_foul",
            "offensive_foul",
            "technical_foul",
            "flagrant_foul",
            "foul",
            "turnover",
            "steal",
            "block",
        ]
    ),
    "NHL": frozenset(
        ["penalty", "delayed_penalty", "takeaway", "giveaway", "hit"]
    ),
}

_FINAL_PERIOD_THRESHOLD: dict[str, int] = {"NBA": 4, "NCAAB": 2, "NHL": 3}
_CLUTCH_MINUTES = 2.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_lead_change(
    prev_home: int, prev_away: int, curr_home: int, curr_away: int
) -> bool:
    """Detect if the leading team switched between two score states.

    Mirrors ``score_detection.is_lead_change`` but inlined here to avoid the
    heavy pipeline import chain.
    """
    if prev_home > prev_away:
        prev_lead = "HOME"
    elif prev_away > prev_home:
        prev_lead = "AWAY"
    else:
        return False  # was tied — no lead to change

    if curr_home > curr_away:
        curr_lead = "HOME"
    elif curr_away > curr_home:
        curr_lead = "AWAY"
    else:
        return False  # now tied — not a lead *change*

    return prev_lead != curr_lead


def _parse_clock_minutes(game_clock: str | None) -> float | None:
    """Parse ``"MM:SS"`` into fractional minutes. Returns *None* if unparseable."""
    if not game_clock:
        return None
    parts = game_clock.split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]) + int(parts[1]) / 60.0
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Import here so the module can be used without circular-import issues at
# module level; the actual schema type is only needed for the return value.
from ..routers.sports.schemas import PlayEntry, TieredPlayGroup  # noqa: E402


def classify_all_tiers(
    plays: list[PlayEntry],
    league_code: str,
) -> list[int]:
    """Classify each play in *plays* as Tier 1, 2, or 3.

    Returns a list of ints (1/2/3) parallel to *plays*.
    """
    if not plays:
        return []

    tier_2_types = _TIER_2_TYPES.get(league_code.upper(), frozenset())
    threshold = _FINAL_PERIOD_THRESHOLD.get(league_code.upper(), 4)

    # --- backfill scores (carry forward last known) ---
    score_pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    last_home, last_away = 0, 0
    for p in plays:
        before = (last_home, last_away)
        h = p.home_score if p.home_score is not None else last_home
        a = p.away_score if p.away_score is not None else last_away
        after = (h, a)
        score_pairs.append((before, after))
        last_home, last_away = h, a

    # --- find final period ---
    final_period = max(
        (p.quarter for p in plays if p.quarter is not None), default=1
    )

    # --- classify ---
    tiers: list[int] = []
    for i, p in enumerate(plays):
        before, after = score_pairs[i]
        home_before, away_before = before
        home_after, away_after = after

        is_scoring = (home_after != home_before) or (away_after != away_before)

        quarter = p.quarter or 0
        is_final_period = quarter >= threshold
        lead_changed = _is_lead_change(
            home_before, away_before, home_after, away_after
        )
        is_new_tie = is_scoring and (home_after == away_after)

        minutes_left = _parse_clock_minutes(p.game_clock)
        is_clutch = (
            quarter == final_period
            and is_final_period
            and minutes_left is not None
            and minutes_left < _CLUTCH_MINUTES
        )

        if is_scoring and (
            lead_changed or is_new_tie or is_clutch or is_final_period
        ):
            tiers.append(1)
        elif p.play_type and p.play_type.lower() in tier_2_types:
            tiers.append(2)
        else:
            tiers.append(3)

    return tiers


def group_tier3_plays(
    plays: list[PlayEntry],
    tiers: list[int],
) -> list[TieredPlayGroup]:
    """Group consecutive Tier-3 plays into collapsed summaries."""
    groups: list[TieredPlayGroup] = []
    run_start: int | None = None
    run_indices: list[int] = []

    def _flush() -> None:
        if run_start is None or not run_indices:
            return
        types = []
        seen: set[str] = set()
        for idx in run_indices:
            pt = (plays[idx].play_type or "unknown").lower()
            if pt not in seen:
                seen.add(pt)
                types.append(pt)
        label = f"{len(run_indices)} plays: {', '.join(types)}"
        groups.append(
            TieredPlayGroup(
                start_index=run_indices[0],
                end_index=run_indices[-1],
                play_indices=list(run_indices),
                summary_label=label,
            )
        )

    for i, tier in enumerate(tiers):
        if tier == 3:
            if run_start is None:
                run_start = i
                run_indices = [i]
            else:
                run_indices.append(i)
        else:
            _flush()
            run_start = None
            run_indices = []

    _flush()
    return groups
