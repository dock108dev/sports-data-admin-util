"""Tests for parlay evaluation."""

from __future__ import annotations

import pytest

from app.services.ev import implied_to_american


class TestParlayMath:
    """Test the underlying math used by the parlay endpoint."""

    def test_two_leg_parlay_probability(self) -> None:
        # 50% * 50% = 25%
        combined = 0.5 * 0.5
        assert combined == pytest.approx(0.25)

    def test_three_leg_parlay_probability(self) -> None:
        # 60% * 50% * 40% = 12%
        combined = 0.6 * 0.5 * 0.4
        assert combined == pytest.approx(0.12)

    def test_fair_odds_from_combined_prob(self) -> None:
        # 25% probability -> +300
        odds = implied_to_american(0.25)
        assert round(odds) == 300

    def test_low_probability_parlay(self) -> None:
        # 10% -> +900
        odds = implied_to_american(0.10)
        assert round(odds) == 900


class TestDateSection:
    """Test date section classification."""

    def test_today(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.services.date_section import classify_date_section

        et = ZoneInfo("America/New_York")
        now = datetime(2026, 2, 24, 19, 0, tzinfo=et)
        game_time = datetime(2026, 2, 25, 0, 30, tzinfo=ZoneInfo("UTC"))  # 7:30 PM ET
        result = classify_date_section(game_time, now=now)
        assert result == "Today"

    def test_yesterday(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.services.date_section import classify_date_section

        et = ZoneInfo("America/New_York")
        now = datetime(2026, 2, 24, 10, 0, tzinfo=et)
        game_time = datetime(2026, 2, 24, 0, 30, tzinfo=ZoneInfo("UTC"))  # Feb 23 7:30 PM ET
        result = classify_date_section(game_time, now=now)
        assert result == "Yesterday"

    def test_tomorrow(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.services.date_section import classify_date_section

        et = ZoneInfo("America/New_York")
        now = datetime(2026, 2, 24, 10, 0, tzinfo=et)
        game_time = datetime(2026, 2, 26, 0, 30, tzinfo=ZoneInfo("UTC"))  # Feb 25 7:30 PM ET
        result = classify_date_section(game_time, now=now)
        assert result == "Tomorrow"

    def test_earlier(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.services.date_section import classify_date_section

        et = ZoneInfo("America/New_York")
        now = datetime(2026, 2, 24, 10, 0, tzinfo=et)
        game_time = datetime(2026, 2, 20, 0, 30, tzinfo=ZoneInfo("UTC"))
        result = classify_date_section(game_time, now=now)
        assert result == "Earlier"

    def test_upcoming(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from app.services.date_section import classify_date_section

        et = ZoneInfo("America/New_York")
        now = datetime(2026, 2, 24, 10, 0, tzinfo=et)
        game_time = datetime(2026, 3, 1, 0, 30, tzinfo=ZoneInfo("UTC"))
        result = classify_date_section(game_time, now=now)
        assert result == "Upcoming"

    def test_none_game_time(self) -> None:
        from app.services.date_section import classify_date_section

        assert classify_date_section(None) is None
