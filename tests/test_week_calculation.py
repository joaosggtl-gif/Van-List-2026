from datetime import date

from app.services.week_service import get_week_number, get_week_dates, get_week_days


class TestWeekCalculation:
    """Test the fixed-base week numbering system.

    Base date: 2025-12-28 (Sunday)
    Week 1: 2025-12-28 to 2026-01-03
    """

    def test_week1_start(self):
        """Dec 28, 2025 should be Week 1."""
        assert get_week_number(date(2025, 12, 28)) == 1

    def test_week1_end(self):
        """Jan 3, 2026 should be Week 1."""
        assert get_week_number(date(2026, 1, 3)) == 1

    def test_week1_middle(self):
        """Dec 31, 2025 should be Week 1."""
        assert get_week_number(date(2025, 12, 31)) == 1

    def test_week2_start(self):
        """Jan 4, 2026 should be Week 2."""
        assert get_week_number(date(2026, 1, 4)) == 2

    def test_week2_end(self):
        """Jan 10, 2026 should be Week 2."""
        assert get_week_number(date(2026, 1, 10)) == 2

    def test_week5(self):
        """Jan 25, 2026 should be Week 5."""
        assert get_week_number(date(2026, 1, 25)) == 5

    def test_week6_start(self):
        """Feb 1, 2026 should be Week 6."""
        assert get_week_number(date(2026, 2, 1)) == 6

    def test_week10(self):
        """March 1, 2026 = day 63 from base, Week = 63//7 + 1 = 10."""
        assert get_week_number(date(2026, 3, 1)) == 10

    def test_before_base_returns_zero(self):
        """Dates before Dec 28, 2025 should return 0."""
        assert get_week_number(date(2025, 12, 27)) == 0

    def test_get_week_dates_week1(self):
        """Week 1 dates should be Dec 28 to Jan 3."""
        start, end = get_week_dates(1)
        assert start == date(2025, 12, 28)
        assert end == date(2026, 1, 3)

    def test_get_week_dates_week2(self):
        """Week 2 dates should be Jan 4 to Jan 10."""
        start, end = get_week_dates(2)
        assert start == date(2026, 1, 4)
        assert end == date(2026, 1, 10)

    def test_get_week_days_returns_7_days(self):
        """get_week_days should return exactly 7 dates."""
        days = get_week_days(1)
        assert len(days) == 7
        assert days[0] == date(2025, 12, 28)
        assert days[6] == date(2026, 1, 3)

    def test_week_number_roundtrip(self):
        """Converting date to week and back should give the same week range."""
        d = date(2026, 2, 15)
        wn = get_week_number(d)
        start, end = get_week_dates(wn)
        assert start <= d <= end

    def test_consecutive_weeks(self):
        """Weeks should be consecutive with no gaps or overlaps."""
        for wn in range(1, 20):
            _, end_this = get_week_dates(wn)
            start_next, _ = get_week_dates(wn + 1)
            assert (start_next - end_this).days == 1
