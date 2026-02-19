"""Tests for app.services.period_labels."""

from app.services.period_labels import period_label, time_label

# ---------------------------------------------------------------------------
# period_label
# ---------------------------------------------------------------------------


class TestPeriodLabelNBA:
    def test_quarters(self):
        assert period_label(1, "NBA") == "Q1"
        assert period_label(2, "NBA") == "Q2"
        assert period_label(3, "NBA") == "Q3"
        assert period_label(4, "NBA") == "Q4"

    def test_overtime(self):
        assert period_label(5, "NBA") == "OT"
        assert period_label(6, "NBA") == "2OT"
        assert period_label(7, "NBA") == "3OT"

    def test_case_insensitive(self):
        assert period_label(1, "nba") == "Q1"


class TestPeriodLabelNHL:
    def test_periods(self):
        assert period_label(1, "NHL") == "P1"
        assert period_label(2, "NHL") == "P2"
        assert period_label(3, "NHL") == "P3"

    def test_overtime_and_shootout(self):
        assert period_label(4, "NHL") == "OT"
        assert period_label(5, "NHL") == "SO"


class TestPeriodLabelNCAAB:
    def test_halves(self):
        assert period_label(1, "NCAAB") == "H1"
        assert period_label(2, "NCAAB") == "H2"

    def test_overtime(self):
        assert period_label(3, "NCAAB") == "OT"
        assert period_label(4, "NCAAB") == "2OT"
        assert period_label(5, "NCAAB") == "3OT"


class TestPeriodLabelUnknownLeague:
    def test_defaults_to_nba_style(self):
        assert period_label(1, "WNBA") == "Q1"
        assert period_label(5, "WNBA") == "OT"


# ---------------------------------------------------------------------------
# time_label
# ---------------------------------------------------------------------------


class TestTimeLabel:
    def test_with_clock(self):
        assert time_label(4, "2:35", "NBA") == "Q4 2:35"
        assert time_label(3, "12:00", "NHL") == "P3 12:00"
        assert time_label(2, "5:15", "NCAAB") == "H2 5:15"

    def test_without_clock(self):
        assert time_label(1, None, "NBA") == "Q1"
        assert time_label(4, "", "NHL") == "OT"
