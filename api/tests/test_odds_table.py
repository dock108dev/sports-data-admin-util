"""Tests for odds_table.build_odds_table."""

from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import MagicMock

import pytest

from app.services.odds_table import build_odds_table


def _mock_odds_entry(
    book: str = "DraftKings",
    market_type: str = "spread",
    market_category: str = "mainline",
    side: str | None = "home",
    line: float | None = -3.5,
    price: float | None = -110,
    is_closing_line: bool = True,
) -> MagicMock:
    entry = MagicMock()
    entry.book = book
    entry.market_type = market_type
    entry.market_category = market_category
    entry.side = side
    entry.line = line
    entry.price = price
    entry.is_closing_line = is_closing_line
    return entry


class TestBuildOddsTable:
    def test_empty_odds(self) -> None:
        assert build_odds_table([]) == []

    def test_market_ordering(self) -> None:
        odds = [
            _mock_odds_entry(market_type="moneyline", side="home", line=0, price=-150),
            _mock_odds_entry(market_type="spread", side="home", line=-3.5, price=-110),
            _mock_odds_entry(market_type="total", side="over", line=215.5, price=-110),
        ]
        result = build_odds_table(odds)
        assert len(result) == 3
        assert result[0]["marketType"] == "spread"
        assert result[1]["marketType"] == "total"
        assert result[2]["marketType"] == "moneyline"

    def test_market_display_names(self) -> None:
        odds = [_mock_odds_entry(market_type="spread")]
        result = build_odds_table(odds)
        assert result[0]["marketDisplay"] == "Spread"

    def test_opening_closing_separation(self) -> None:
        odds = [
            _mock_odds_entry(side="home", price=-110, is_closing_line=False),
            _mock_odds_entry(side="home", price=-115, is_closing_line=True),
        ]
        result = build_odds_table(odds)
        assert len(result) == 1
        assert len(result[0]["openingLines"]) == 1
        assert len(result[0]["closingLines"]) == 1

    def test_is_best_per_side(self) -> None:
        odds = [
            _mock_odds_entry(book="DraftKings", side="home", price=-108, is_closing_line=True),
            _mock_odds_entry(book="FanDuel", side="home", price=-112, is_closing_line=True),
            _mock_odds_entry(book="DraftKings", side="away", price=100, is_closing_line=True),
            _mock_odds_entry(book="FanDuel", side="away", price=-102, is_closing_line=True),
        ]
        result = build_odds_table(odds)
        closing = result[0]["closingLines"]

        home_lines = [l for l in closing if l["side"] == "home"]
        away_lines = [l for l in closing if l["side"] == "away"]

        # DraftKings -108 is better than FanDuel -112
        best_home = next(l for l in home_lines if l["isBest"])
        assert best_home["book"] == "DraftKings"

        # DraftKings +100 is better than FanDuel -102
        best_away = next(l for l in away_lines if l["isBest"])
        assert best_away["book"] == "DraftKings"

    def test_price_display(self) -> None:
        odds = [_mock_odds_entry(price=-110)]
        result = build_odds_table(odds)
        assert result[0]["closingLines"][0]["priceDisplay"] == "-110"

    def test_positive_price_display(self) -> None:
        odds = [_mock_odds_entry(price=150)]
        result = build_odds_table(odds)
        assert result[0]["closingLines"][0]["priceDisplay"] == "+150"

    def test_non_mainline_excluded(self) -> None:
        odds = [
            _mock_odds_entry(market_category="player_prop"),
        ]
        result = build_odds_table(odds)
        assert result == []
