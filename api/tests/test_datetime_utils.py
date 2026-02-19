"""Tests for datetime_utils module."""

from datetime import UTC, date, datetime


class TestNowUtc:
    """Tests for now_utc function."""

    def test_returns_datetime(self):
        """Returns a datetime object."""
        from app.utils.datetime_utils import now_utc

        result = now_utc()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self):
        """Returned datetime is timezone-aware."""
        from app.utils.datetime_utils import now_utc

        result = now_utc()
        assert result.tzinfo is not None
        assert result.tzinfo == UTC


class TestTodayUtc:
    """Tests for today_utc function."""

    def test_returns_date(self):
        """Returns a date object."""
        from app.utils.datetime_utils import today_utc

        result = today_utc()
        assert isinstance(result, date)


class TestTodayEastern:
    """Tests for today_eastern function."""

    def test_returns_date(self):
        """Returns a date object."""
        from app.utils.datetime_utils import today_eastern

        result = today_eastern()
        assert isinstance(result, date)


class TestDateToUtcDatetime:
    """Tests for date_to_utc_datetime function."""

    def test_converts_date(self):
        """Converts date to UTC datetime."""
        from app.utils.datetime_utils import date_to_utc_datetime

        result = date_to_utc_datetime(date(2026, 1, 22))
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 22

    def test_is_timezone_aware(self):
        """Result is timezone-aware in UTC."""
        from app.utils.datetime_utils import date_to_utc_datetime

        result = date_to_utc_datetime(date(2026, 1, 22))
        assert result.tzinfo == UTC

    def test_midnight(self):
        """Result is at midnight."""
        from app.utils.datetime_utils import date_to_utc_datetime

        result = date_to_utc_datetime(date(2026, 1, 22))
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0


class TestEasternDateToUtcRange:
    """Tests for eastern_date_to_utc_range function."""

    def test_winter_date(self):
        """Winter date converts correctly (EST = UTC-5)."""
        from app.utils.datetime_utils import eastern_date_to_utc_range

        start, end = eastern_date_to_utc_range(date(2026, 1, 22))

        # EST is UTC-5, so midnight ET = 5:00 UTC
        assert start.tzinfo == UTC
        assert start.hour == 5
        assert start.day == 22
        assert end.hour == 5
        assert end.day == 23

    def test_summer_date(self):
        """Summer date converts correctly (EDT = UTC-4)."""
        from app.utils.datetime_utils import eastern_date_to_utc_range

        start, end = eastern_date_to_utc_range(date(2026, 7, 15))

        # EDT is UTC-4, so midnight ET = 4:00 UTC
        assert start.tzinfo == UTC
        assert start.hour == 4
        assert end.hour == 4

    def test_returns_tuple(self):
        """Returns tuple of two datetimes."""
        from app.utils.datetime_utils import eastern_date_to_utc_range

        result = eastern_date_to_utc_range(date(2026, 1, 22))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], datetime)
        assert isinstance(result[1], datetime)

    def test_24_hour_span(self):
        """Range spans exactly 24 hours."""
        from datetime import timedelta

        from app.utils.datetime_utils import eastern_date_to_utc_range

        start, end = eastern_date_to_utc_range(date(2026, 1, 22))
        assert (end - start) == timedelta(days=1)


class TestParseClockToSeconds:
    """Tests for parse_clock_to_seconds function."""

    def test_none_input(self):
        """None input returns None."""
        from app.utils.datetime_utils import parse_clock_to_seconds

        assert parse_clock_to_seconds(None) is None

    def test_empty_string(self):
        """Empty string returns None."""
        from app.utils.datetime_utils import parse_clock_to_seconds

        assert parse_clock_to_seconds("") is None

    def test_mm_ss_format(self):
        """MM:SS format parses correctly."""
        from app.utils.datetime_utils import parse_clock_to_seconds

        assert parse_clock_to_seconds("11:45") == 11 * 60 + 45
        assert parse_clock_to_seconds("5:30") == 5 * 60 + 30
        assert parse_clock_to_seconds("0:30") == 30
        assert parse_clock_to_seconds("12:00") == 12 * 60

    def test_mm_ss_decimal_format(self):
        """MM:SS.x format parses correctly."""
        from app.utils.datetime_utils import parse_clock_to_seconds

        assert parse_clock_to_seconds("5:30.0") == 5 * 60 + 30
        assert parse_clock_to_seconds("0:10.5") == 10

    def test_invalid_format(self):
        """Invalid format returns None."""
        from app.utils.datetime_utils import parse_clock_to_seconds

        assert parse_clock_to_seconds("invalid") is None
        assert parse_clock_to_seconds("abc:def") is None

    def test_single_number(self):
        """Single number is treated as seconds."""
        from app.utils.datetime_utils import parse_clock_to_seconds

        assert parse_clock_to_seconds("30") == 30
        # Note: "45.5" is parsed as "45:5" due to decimal replacement
        assert parse_clock_to_seconds("45.5") == 45 * 60 + 5
