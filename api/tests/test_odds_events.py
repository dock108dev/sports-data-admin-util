"""Tests for app.services.odds_events."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from app.services.odds_events import (
    build_odds_events,
    detect_significant_movements,
    select_preferred_book,
)


def _odds_row(
    *,
    book: str = "fanduel",
    market_type: str = "spread",
    side: str | None = "home",
    line: float | None = -3.5,
    price: float | None = -110.0,
    is_closing_line: bool = False,
    observed_at: datetime | None = None,
) -> Any:
    """Create a fake SportsGameOdds-like object using SimpleNamespace."""
    return SimpleNamespace(
        book=book,
        market_type=market_type,
        side=side,
        line=line,
        price=price,
        is_closing_line=is_closing_line,
        observed_at=observed_at,
    )


# ---------------------------------------------------------------------------
# select_preferred_book
# ---------------------------------------------------------------------------


class TestSelectPreferredBook:
    def test_empty_returns_none(self):
        assert select_preferred_book([]) is None

    def test_fanduel_preferred(self):
        odds = [_odds_row(book="draftkings"), _odds_row(book="fanduel")]
        assert select_preferred_book(odds) == "fanduel"

    def test_draftkings_second(self):
        odds = [_odds_row(book="draftkings"), _odds_row(book="betmgm")]
        assert select_preferred_book(odds) == "draftkings"

    def test_fallback_most_rows(self):
        odds = [
            _odds_row(book="pinnacle"),
            _odds_row(book="pinnacle"),
            _odds_row(book="bovada"),
        ]
        assert select_preferred_book(odds) == "pinnacle"

    def test_priority_order(self):
        for i, book in enumerate(["fanduel", "draftkings", "betmgm", "caesars"]):
            # Only this book and lower-priority ones present
            present = [_odds_row(book=b) for b in ["fanduel", "draftkings", "betmgm", "caesars"][i:]]
            assert select_preferred_book(present) == book


# ---------------------------------------------------------------------------
# detect_significant_movements
# ---------------------------------------------------------------------------


class TestDetectSignificantMovements:
    def test_no_rows_empty(self):
        assert detect_significant_movements([]) == []

    def test_no_movement_below_threshold(self):
        odds = [
            _odds_row(line=-3.0, is_closing_line=False, side="home"),
            _odds_row(line=-3.5, is_closing_line=True, side="home"),
        ]
        # Delta 0.5 < SPREAD_MOVEMENT_THRESHOLD (1.0)
        assert detect_significant_movements(odds) == []

    def test_spread_movement_detected(self):
        odds = [
            _odds_row(line=-3.0, is_closing_line=False, side="home"),
            _odds_row(line=-5.0, is_closing_line=True, side="home"),
        ]
        movements = detect_significant_movements(odds)
        assert len(movements) == 1
        assert movements[0]["market_type"] == "spread"
        assert movements[0]["movement"] == -2.0

    def test_total_movement_detected(self):
        odds = [
            _odds_row(market_type="total", line=220.0, is_closing_line=False, side="over"),
            _odds_row(market_type="total", line=222.0, is_closing_line=True, side="over"),
        ]
        movements = detect_significant_movements(odds)
        assert len(movements) == 1
        assert movements[0]["market_type"] == "total"
        assert movements[0]["movement"] == 2.0

    def test_moneyline_uses_price_not_line(self):
        odds = [
            _odds_row(
                market_type="moneyline", line=None, price=-150.0,
                is_closing_line=False, side="home",
            ),
            _odds_row(
                market_type="moneyline", line=None, price=-180.0,
                is_closing_line=True, side="home",
            ),
        ]
        movements = detect_significant_movements(odds)
        assert len(movements) == 1
        assert movements[0]["market_type"] == "moneyline"
        assert movements[0]["opening_line"] == -150.0
        assert movements[0]["closing_line"] == -180.0

    def test_moneyline_no_movement_below_threshold(self):
        odds = [
            _odds_row(
                market_type="moneyline", line=None, price=-150.0,
                is_closing_line=False, side="home",
            ),
            _odds_row(
                market_type="moneyline", line=None, price=-155.0,
                is_closing_line=True, side="home",
            ),
        ]
        # Delta 5 < MONEYLINE_MOVEMENT_THRESHOLD (20)
        assert detect_significant_movements(odds) == []

    def test_missing_opening_or_closing_skipped(self):
        # Only opening, no closing
        odds = [_odds_row(is_closing_line=False, side="home")]
        assert detect_significant_movements(odds) == []

    def test_none_line_skipped_for_spread(self):
        odds = [
            _odds_row(line=None, is_closing_line=False, side="home"),
            _odds_row(line=-5.0, is_closing_line=True, side="home"),
        ]
        assert detect_significant_movements(odds) == []

    def test_multiple_sides_independent(self):
        odds = [
            _odds_row(line=-3.0, is_closing_line=False, side="home"),
            _odds_row(line=-5.0, is_closing_line=True, side="home"),
            _odds_row(line=3.0, is_closing_line=False, side="away"),
            _odds_row(line=3.5, is_closing_line=True, side="away"),  # delta 0.5, no movement
        ]
        movements = detect_significant_movements(odds)
        assert len(movements) == 1
        assert movements[0]["side"] == "home"

    def test_moneyline_none_price_skipped(self):
        odds = [
            _odds_row(
                market_type="moneyline", line=None, price=None,
                is_closing_line=False, side="home",
            ),
            _odds_row(
                market_type="moneyline", line=None, price=-180.0,
                is_closing_line=True, side="home",
            ),
        ]
        assert detect_significant_movements(odds) == []

    def test_unknown_market_type_skipped(self):
        odds = [
            _odds_row(market_type="prop", line=1.5, is_closing_line=False, side="over"),
            _odds_row(market_type="prop", line=3.0, is_closing_line=True, side="over"),
        ]
        assert detect_significant_movements(odds) == []


# ---------------------------------------------------------------------------
# build_odds_events
# ---------------------------------------------------------------------------


class TestBuildOddsEvents:
    _game_start = datetime(2026, 1, 15, 19, 0, tzinfo=UTC)
    _phase_boundaries = {
        "pregame": (
            datetime(2026, 1, 15, 17, 0, tzinfo=UTC),
            datetime(2026, 1, 15, 19, 0, tzinfo=UTC),
        ),
    }

    def test_empty_odds(self):
        assert build_odds_events([], self._game_start, self._phase_boundaries) == []

    def test_opening_and_closing_events(self):
        t1 = self._game_start - timedelta(hours=1)
        t2 = self._game_start - timedelta(minutes=10)
        odds = [
            _odds_row(is_closing_line=False, observed_at=t1, side="home"),
            _odds_row(is_closing_line=True, observed_at=t2, side="home"),
        ]
        events = build_odds_events(odds, self._game_start, self._phase_boundaries)
        types = [e[1]["odds_type"] for e in events]
        assert "opening_line" in types
        assert "closing_line" in types
        for _, payload in events:
            assert payload["phase"] == "pregame"
            assert payload["event_type"] == "odds"
            assert payload["book"] == "fanduel"

    def test_no_movement_event_below_threshold(self):
        t1 = self._game_start - timedelta(hours=1)
        t2 = self._game_start - timedelta(minutes=10)
        odds = [
            _odds_row(line=-3.0, is_closing_line=False, observed_at=t1, side="home"),
            _odds_row(line=-3.5, is_closing_line=True, observed_at=t2, side="home"),
        ]
        events = build_odds_events(odds, self._game_start, self._phase_boundaries)
        types = [e[1]["odds_type"] for e in events]
        assert "line_movement" not in types

    def test_movement_event_when_significant(self):
        t1 = self._game_start - timedelta(hours=1)
        t2 = self._game_start - timedelta(minutes=10)
        odds = [
            _odds_row(line=-3.0, is_closing_line=False, observed_at=t1, side="home"),
            _odds_row(line=-6.0, is_closing_line=True, observed_at=t2, side="home"),
        ]
        events = build_odds_events(odds, self._game_start, self._phase_boundaries)
        types = [e[1]["odds_type"] for e in events]
        assert "line_movement" in types

    def test_markets_dict_keys_by_side(self):
        t1 = self._game_start - timedelta(hours=1)
        odds = [
            _odds_row(is_closing_line=False, observed_at=t1, side="home", line=-3.5),
            _odds_row(is_closing_line=False, observed_at=t1, side="away", line=3.5),
        ]
        events = build_odds_events(odds, self._game_start, self._phase_boundaries)
        opening = [e for e in events if e[1]["odds_type"] == "opening_line"]
        assert len(opening) == 1
        markets = opening[0][1]["markets"]
        assert "home" in markets["spread"]
        assert "away" in markets["spread"]

    def test_fallback_timestamps_when_observed_at_none(self):
        odds = [
            _odds_row(is_closing_line=False, observed_at=None, side="home"),
            _odds_row(is_closing_line=True, observed_at=None, side="home"),
        ]
        events = build_odds_events(odds, self._game_start, self._phase_boundaries)
        assert len(events) >= 2
        # Opening fallback: game_start - 2h
        open_ts = events[0][0]
        assert open_ts == self._game_start - timedelta(hours=2)

    def test_only_opening_rows(self):
        t1 = self._game_start - timedelta(hours=1)
        odds = [_odds_row(is_closing_line=False, observed_at=t1, side="home")]
        events = build_odds_events(odds, self._game_start, self._phase_boundaries)
        types = [e[1]["odds_type"] for e in events]
        assert "opening_line" in types
        assert "closing_line" not in types
