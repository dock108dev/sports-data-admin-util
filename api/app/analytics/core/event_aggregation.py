"""Sport-aware event summary aggregation.

Converts raw per-iteration event counts into projected box score
statistics appropriate for each sport. Used by both
``SimulationRunner`` (per-game aggregation) and batch sim summary
(across-game aggregation).
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def aggregate_events(
    sim_results: list[dict[str, Any]],
    sport: str | None = None,
) -> dict[str, Any]:
    """Build a sport-appropriate event summary from simulation results.

    Auto-detects the sport from event keys if ``sport`` is not provided.

    Returns:
        Dict with ``home``, ``away``, and ``game`` sections containing
        sport-specific projected box score stats.
    """
    if not sim_results or "home_events" not in sim_results[0]:
        return {}

    if sport is None:
        sport = _detect_sport(sim_results[0].get("home_events", {}))

    n = len(sim_results)

    builders = {
        "mlb": _mlb_team_summary,
        "nba": _basketball_team_summary,
        "ncaab": _basketball_team_summary,
        "nhl": _nhl_team_summary,
        "nfl": _nfl_team_summary,
    }
    builder = builders.get(sport, _generic_team_summary)

    home = builder(sim_results, "home_events", n, sport)
    away = builder(sim_results, "away_events", n, sport)
    game = _game_summary(sim_results, n, sport)

    return {"home": home, "away": away, "game": game, "sport": sport}


def _detect_sport(events: dict[str, Any]) -> str:
    """Infer sport from event key names."""
    if "pa_total" in events:
        return "mlb"
    if "drives_total" in events:
        return "nfl"
    if "shots_total" in events:
        return "nhl"
    if "offensive_rebounds" in events:
        return "ncaab"
    if "possessions_total" in events:
        return "nba"
    return "unknown"


# ---------------------------------------------------------------------------
# MLB: Plate appearance rates
# ---------------------------------------------------------------------------

def _mlb_team_summary(
    results: list[dict], key: str, n: int, sport: str,
) -> dict[str, Any]:
    totals = _sum_events(results, key)
    pa = totals.get("pa_total", 1) or 1
    hits = (
        totals.get("single", 0) + totals.get("double", 0)
        + totals.get("triple", 0) + totals.get("home_run", 0)
    )
    bb = totals.get("walk_or_hbp", 0) + totals.get("walk", 0)
    outs = totals.get("ball_in_play_out", 0) + totals.get("out", 0)
    score_key = "home_score" if key == "home_events" else "away_score"

    return {
        "avg_pa": round(totals.get("pa_total", 0) / n, 1),
        "avg_runs": round(sum(r.get(score_key, 0) for r in results) / n, 1),
        "avg_hits": round(hits / n, 1),
        "avg_hr": round(totals.get("home_run", 0) / n, 1),
        "avg_bb": round(bb / n, 1),
        "avg_k": round(totals.get("strikeout", 0) / n, 1),
        "rates": {
            "k_pct": round(totals.get("strikeout", 0) / pa, 3),
            "bb_pct": round(bb / pa, 3),
            "single_pct": round(totals.get("single", 0) / pa, 3),
            "double_pct": round(totals.get("double", 0) / pa, 3),
            "triple_pct": round(totals.get("triple", 0) / pa, 3),
            "hr_pct": round(totals.get("home_run", 0) / pa, 3),
            "out_pct": round(outs / pa, 3),
        },
        # Backward compat: also emit pa_rates for existing consumers
        "pa_rates": {
            "k_pct": round(totals.get("strikeout", 0) / pa, 3),
            "bb_pct": round(bb / pa, 3),
            "single_pct": round(totals.get("single", 0) / pa, 3),
            "double_pct": round(totals.get("double", 0) / pa, 3),
            "triple_pct": round(totals.get("triple", 0) / pa, 3),
            "hr_pct": round(totals.get("home_run", 0) / pa, 3),
            "out_pct": round(outs / pa, 3),
        },
    }


# ---------------------------------------------------------------------------
# NBA / NCAAB: Possession rates + shooting efficiency
# ---------------------------------------------------------------------------

def _basketball_team_summary(
    results: list[dict], key: str, n: int, sport: str,
) -> dict[str, Any]:
    totals = _sum_events(results, key)
    poss = totals.get("possessions_total", 1) or 1
    score_key = "home_score" if key == "home_events" else "away_score"

    two_make = totals.get("two_pt_make", 0)
    two_miss = totals.get("two_pt_miss", 0)
    three_make = totals.get("three_pt_make", 0)
    three_miss = totals.get("three_pt_miss", 0)
    ft_trips = totals.get("free_throw_trip", 0)
    turnovers = totals.get("turnover", 0)
    orbs = totals.get("offensive_rebounds", 0)

    fga_2 = two_make + two_miss
    fga_3 = three_make + three_miss
    fga_total = fga_2 + fga_3
    fgm_total = two_make + three_make

    fg_pct = round(fgm_total / fga_total, 3) if fga_total > 0 else 0.0
    fg3_pct = round(three_make / fga_3, 3) if fga_3 > 0 else 0.0
    efg_pct = round((fgm_total + 0.5 * three_make) / fga_total, 3) if fga_total > 0 else 0.0

    summary: dict[str, Any] = {
        "avg_possessions": round(poss / n, 1),
        "avg_points": round(sum(r.get(score_key, 0) for r in results) / n, 1),
        "fg_pct": fg_pct,
        "fg3_pct": fg3_pct,
        "efg_pct": efg_pct,
        "rates": {
            "two_pt_make_pct": round(two_make / poss, 3),
            "two_pt_miss_pct": round(two_miss / poss, 3),
            "three_pt_make_pct": round(three_make / poss, 3),
            "three_pt_miss_pct": round(three_miss / poss, 3),
            "ft_trip_pct": round(ft_trips / poss, 3),
            "turnover_pct": round(turnovers / poss, 3),
        },
    }

    if sport == "ncaab" and orbs > 0:
        miss_total = two_miss + three_miss
        summary["avg_orb"] = round(orbs / n, 1)
        summary["rates"]["orb_pct"] = round(orbs / miss_total, 3) if miss_total > 0 else 0.0

    return summary


# ---------------------------------------------------------------------------
# NHL: Shot attempt rates + shooting efficiency
# ---------------------------------------------------------------------------

def _nhl_team_summary(
    results: list[dict], key: str, n: int, sport: str,
) -> dict[str, Any]:
    totals = _sum_events(results, key)
    shots = totals.get("shots_total", 1) or 1
    score_key = "home_score" if key == "home_events" else "away_score"

    goals = totals.get("goal", 0)
    saves = totals.get("save", 0)
    blocked = totals.get("blocked_shot", 0)
    missed = totals.get("missed_shot", 0)

    return {
        "avg_shots": round(shots / n, 1),
        "avg_goals": round(goals / n, 1),
        "avg_points": round(sum(r.get(score_key, 0) for r in results) / n, 1),
        "shooting_pct": round(goals / shots, 3),
        "rates": {
            "goal_pct": round(goals / shots, 3),
            "save_pct": round(saves / shots, 3),
            "blocked_pct": round(blocked / shots, 3),
            "missed_pct": round(missed / shots, 3),
        },
    }


# ---------------------------------------------------------------------------
# NFL: Drive outcome rates
# ---------------------------------------------------------------------------

def _nfl_team_summary(
    results: list[dict], key: str, n: int, sport: str,
) -> dict[str, Any]:
    totals = _sum_events(results, key)
    drives = totals.get("drives_total", 1) or 1
    score_key = "home_score" if key == "home_events" else "away_score"

    tds = totals.get("touchdown", 0)
    fgs = totals.get("field_goal", 0)
    punts = totals.get("punt", 0)
    turnovers = totals.get("turnover", 0)
    downs = totals.get("turnover_on_downs", 0)

    scoring_drives = tds + fgs

    return {
        "avg_drives": round(drives / n, 1),
        "avg_points": round(sum(r.get(score_key, 0) for r in results) / n, 1),
        "avg_tds": round(tds / n, 1),
        "avg_fgs": round(fgs / n, 1),
        "scoring_drive_pct": round(scoring_drives / drives, 3),
        "rates": {
            "td_pct": round(tds / drives, 3),
            "fg_pct": round(fgs / drives, 3),
            "punt_pct": round(punts / drives, 3),
            "turnover_pct": round(turnovers / drives, 3),
            "downs_pct": round(downs / drives, 3),
        },
    }


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------

def _generic_team_summary(
    results: list[dict], key: str, n: int, sport: str,
) -> dict[str, Any]:
    totals = _sum_events(results, key)
    score_key = "home_score" if key == "home_events" else "away_score"
    return {
        "avg_points": round(sum(r.get(score_key, 0) for r in results) / n, 1),
        "event_totals": {k: round(v / n, 1) for k, v in totals.items()},
    }


# ---------------------------------------------------------------------------
# Game-level summary (sport-aware)
# ---------------------------------------------------------------------------

def _game_summary(
    results: list[dict], n: int, sport: str,
) -> dict[str, Any]:
    from .simulation_analysis import _median

    total_scores = [
        r.get("home_score", 0) + r.get("away_score", 0) for r in results
    ]
    one_run = sum(
        1 for r in results
        if abs(r.get("home_score", 0) - r.get("away_score", 0)) == 1
    )

    avg_total = round(sum(total_scores) / n, 1)
    one_score_pct = round(one_run / n, 3)

    summary: dict[str, Any] = {
        "avg_total": avg_total,
        "median_total": _median(total_scores),
        "one_score_game_pct": one_score_pct,
    }

    # Sport-specific game shape
    if sport == "mlb":
        extra = sum(1 for r in results if r.get("innings_played", 9) > 9)
        shutout = sum(
            1 for r in results
            if r.get("home_score", 0) == 0 or r.get("away_score", 0) == 0
        )
        summary["extra_innings_pct"] = round(extra / n, 3)
        summary["shutout_pct"] = round(shutout / n, 3)
        # Backward-compat aliases for existing consumers
        summary["avg_total_runs"] = avg_total
        summary["median_total_runs"] = summary["median_total"]
        summary["one_run_game_pct"] = one_score_pct

    elif sport in ("nba", "ncaab"):
        reg_periods = 4 if sport == "nba" else 2
        ot = sum(1 for r in results if r.get("periods_played", reg_periods) > reg_periods)
        summary["overtime_pct"] = round(ot / n, 3)

    elif sport == "nhl":
        ot = sum(1 for r in results if r.get("periods_played", 3) > 3)
        shootout = sum(1 for r in results if r.get("went_to_shootout", False))
        summary["overtime_pct"] = round(ot / n, 3)
        summary["shootout_pct"] = round(shootout / n, 3)

    elif sport == "nfl":
        ot = sum(1 for r in results if r.get("went_to_overtime", False))
        summary["overtime_pct"] = round(ot / n, 3)

    return summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sum_events(results: list[dict], key: str) -> Counter:
    """Sum event dicts across all simulation results."""
    totals: Counter[str] = Counter()
    for r in results:
        for k, v in r.get(key, {}).items():
            totals[k] += v
    return totals
