from datetime import date, timedelta

from app.config import WEEK_BASE_DATE_ISO

# Base date: Sunday, December 28, 2025
WEEK_BASE = date.fromisoformat(WEEK_BASE_DATE_ISO)


def get_week_number(d: date) -> int:
    """Calculate week number from the fixed base date.

    Week 1 = 2025-12-28 to 2026-01-03
    Week N = floor((d - base) / 7) + 1
    Negative weeks are allowed for historical data before WEEK_BASE.
    """
    delta = (d - WEEK_BASE).days
    return delta // 7 + 1


def get_week_dates(week_number: int) -> tuple[date, date]:
    """Return (start_date, end_date) for a given week number."""
    start = WEEK_BASE + timedelta(days=(week_number - 1) * 7)
    end = start + timedelta(days=6)
    return start, end


def get_current_week_number() -> int:
    """Get the week number for today."""
    return get_week_number(date.today())


def get_week_days(week_number: int) -> list[date]:
    """Return all 7 dates in a given week."""
    start, _ = get_week_dates(week_number)
    return [start + timedelta(days=i) for i in range(7)]
