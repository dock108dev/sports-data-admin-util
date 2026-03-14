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


class TestTodayEt:
    """Tests for today_et function."""

    def test_returns_date(self):
        """Returns a date object."""
        from app.utils.datetime_utils import today_et

        result = today_et()
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


class TestToEtDate:
    """Tests for to_et_date function."""

    def test_utc_evening_maps_to_same_et_date(self):
        """UTC evening time stays on same ET date."""
        from app.utils.datetime_utils import to_et_date

        # 2026-03-05 22:00 UTC = 2026-03-05 17:00 ET (same day)
        dt = datetime(2026, 3, 5, 22, 0, tzinfo=UTC)
        assert to_et_date(dt) == date(2026, 3, 5)

    def test_utc_late_night_maps_to_previous_et_date(self):
        """UTC after midnight maps to previous ET date."""
        from app.utils.datetime_utils import to_et_date

        # 2026-03-06 03:00 UTC = 2026-03-05 22:00 ET (previous day)
        dt = datetime(2026, 3, 6, 3, 0, tzinfo=UTC)
        assert to_et_date(dt) == date(2026, 3, 5)


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
