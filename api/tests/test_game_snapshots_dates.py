"""Tests for Eastern date to UTC range conversion."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


class TestEasternDateToUtcRange:
    """Tests for eastern_date_to_utc_range function."""

    def test_est_date_conversion(self):
        """EST date (January) converts correctly to UTC range."""
        from app.utils.datetime_utils import eastern_date_to_utc_range

        # January 22, 2026 (EST = UTC-5)
        d = date(2026, 1, 22)
        start_utc, end_utc = eastern_date_to_utc_range(d)

        # Midnight Jan 22 ET = 5:00 AM Jan 22 UTC
        assert start_utc.year == 2026
        assert start_utc.month == 1
        assert start_utc.day == 22
        assert start_utc.hour == 5
        assert start_utc.minute == 0
        assert start_utc.tzinfo == timezone.utc

        # Midnight Jan 23 ET = 5:00 AM Jan 23 UTC
        assert end_utc.day == 23
        assert end_utc.hour == 5

    def test_edt_date_conversion(self):
        """EDT date (July) converts correctly to UTC range."""
        from app.utils.datetime_utils import eastern_date_to_utc_range

        # July 15, 2026 (EDT = UTC-4)
        d = date(2026, 7, 15)
        start_utc, end_utc = eastern_date_to_utc_range(d)

        # Midnight Jul 15 ET = 4:00 AM Jul 15 UTC (EDT)
        assert start_utc.day == 15
        assert start_utc.hour == 4

        # Midnight Jul 16 ET = 4:00 AM Jul 16 UTC
        assert end_utc.day == 16
        assert end_utc.hour == 4

    def test_late_night_game_included(self):
        """A 10pm ET game on Jan 22 is within Jan 22's UTC range."""
        from app.utils.datetime_utils import eastern_date_to_utc_range

        d = date(2026, 1, 22)
        start_utc, end_utc = eastern_date_to_utc_range(d)

        # 10pm ET on Jan 22 = 3:00 AM Jan 23 UTC
        eastern = ZoneInfo("America/New_York")
        game_time_et = datetime(2026, 1, 22, 22, 0, tzinfo=eastern)
        game_time_utc = game_time_et.astimezone(timezone.utc)

        assert start_utc <= game_time_utc < end_utc


class TestTodayEastern:
    """Tests for today_eastern function."""

    def test_returns_date(self):
        """Returns a date object."""
        from app.utils.datetime_utils import today_eastern

        result = today_eastern()
        assert isinstance(result, date)
