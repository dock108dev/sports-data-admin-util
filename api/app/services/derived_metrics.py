"""Compute derived metrics for sports games."""

from __future__ import annotations

from typing import Any, Sequence

from ..db.sports import SportsGame
from ..db.odds import SportsGameOdds


def _select_closing_lines(
    odds: Sequence[SportsGameOdds], market: str
) -> list[SportsGameOdds]:
    candidates = [odd for odd in odds if odd.market_type == market]
    closing = [odd for odd in candidates if odd.is_closing_line]
    return closing or candidates


def _implied_probability(price: float | None) -> float | None:
    if price is None or price == 0:
        return None
    if price > 0:
        return 100 / (price + 100)
    return -price / (-price + 100)


def compute_derived_metrics(
    game: SportsGame, odds: Sequence[SportsGameOdds]
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if game.home_score is not None and game.away_score is not None:
        home = game.home_score
        away = game.away_score
        metrics["home_score"] = home
        metrics["away_score"] = away
        metrics["margin_of_victory"] = home - away
        metrics["combined_score"] = home + away
        metrics["winner"] = (
            "home" if home > away else ("away" if away > home else "tie")
        )

    spread_lines = _select_closing_lines(odds, "spread")
    if spread_lines and game.home_score is not None and game.away_score is not None:
        home_keys = {
            (game.home_team.name or "").lower() if game.home_team else "",
            (game.home_team.short_name or "").lower() if game.home_team else "",
            (game.home_team.abbreviation or "").lower() if game.home_team else "",
        }
        away_keys = {
            (game.away_team.name or "").lower() if game.away_team else "",
            (game.away_team.short_name or "").lower() if game.away_team else "",
            (game.away_team.abbreviation or "").lower() if game.away_team else "",
        }

        def _matches_side(side_val: str | None, keys: set[str]) -> bool:
            if not side_val:
                return False
            s = side_val.lower()
            for k in keys:
                if not k:
                    continue
                if k.startswith(s) or s.startswith(k):
                    return True
            return s in {"home", "away"}

        for line in spread_lines:
            side = (line.side or "").lower()
            if _matches_side(side, home_keys):
                metrics["closing_spread_home"] = line.line
                metrics["closing_spread_home_price"] = line.price
            elif _matches_side(side, away_keys):
                metrics["closing_spread_away"] = line.line
                metrics["closing_spread_away_price"] = line.price

        if "closing_spread_home" not in metrics and "closing_spread_away" in metrics:
            away_line = metrics["closing_spread_away"]
            if away_line is not None:
                metrics["closing_spread_home"] = -(away_line)
        if "closing_spread_away" not in metrics and "closing_spread_home" in metrics:
            home_line = metrics["closing_spread_home"]
            if home_line is not None:
                metrics["closing_spread_away"] = -(home_line)

        if "closing_spread_home" in metrics:
            cover = metrics["margin_of_victory"] - (metrics["closing_spread_home"] or 0)
            metrics["did_home_cover"] = cover > 0
            metrics["did_away_cover"] = cover < 0

    total_lines = _select_closing_lines(odds, "total")
    if total_lines and "combined_score" in metrics:
        total_line = total_lines[0]
        total_value = total_line.line or 0
        combined = metrics["combined_score"]
        metrics["closing_total"] = total_value
        metrics["closing_total_price"] = total_line.price
        metrics["total_result"] = (
            "over"
            if combined > total_value
            else "under"
            if combined < total_value
            else "push"
        )

    moneyline = _select_closing_lines(odds, "moneyline")
    if moneyline:
        for line in moneyline:
            if line.side is None:
                continue
            side = line.side.lower()
            prob = _implied_probability(line.price)
            if side in {"home", game.home_team.name.lower() if game.home_team else ""}:
                metrics["closing_ml_home"] = line.price
                metrics["closing_ml_home_implied"] = prob
            if side in {"away", game.away_team.name.lower() if game.away_team else ""}:
                metrics["closing_ml_away"] = line.price
                metrics["closing_ml_away_implied"] = prob
        if "winner" in metrics:
            if (
                metrics["winner"] == "home"
                and "closing_ml_home" in metrics
                and "closing_ml_away" in metrics
            ):
                metrics["moneyline_upset"] = (metrics["closing_ml_home"] or 0) > (
                    metrics["closing_ml_away"] or 0
                )
            elif (
                metrics["winner"] == "away"
                and "closing_ml_home" in metrics
                and "closing_ml_away" in metrics
            ):
                metrics["moneyline_upset"] = (metrics["closing_ml_away"] or 0) > (
                    metrics["closing_ml_home"] or 0
                )

    return metrics
