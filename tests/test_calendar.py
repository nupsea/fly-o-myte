"""
Tests for the school holiday calendar (calendar.py).

Uses the embedded school_holidays.yaml — no mocking needed.
"""

from __future__ import annotations

from datetime import date

import pytest

from fly_o_myte.calendar import get_calendar, SchoolCalendar


class TestHolidayOverlap:
    def test_trip_fully_within_qld_mid_year(self):
        """Trip 30 Jun – 10 Jul 2026 is fully within QLD mid-year holidays."""
        cal = get_calendar()
        ctx = cal.check_overlap("QLD", date(2026, 6, 30), date(2026, 7, 10))
        assert ctx is not None
        assert "Mid-year" in ctx.label or "mid" in ctx.label.lower()
        assert ctx.is_fully_within is True
        assert ctx.overlap_days == 11  # 30 Jun – 10 Jul inclusive

    def test_trip_outside_any_holiday(self):
        """Trip in a non-holiday period → no overlap."""
        cal = get_calendar()
        # March is typically a school term month in QLD
        ctx = cal.check_overlap("QLD", date(2026, 3, 10), date(2026, 3, 17))
        assert ctx is None

    def test_trip_partially_overlapping(self):
        """Trip starts before holiday but ends inside it → partial overlap."""
        cal = get_calendar()
        # QLD mid-year 2026: 27 Jun – 12 Jul
        # Trip: 23 Jun – 30 Jun → starts before, ends 3 days into holiday
        ctx = cal.check_overlap("QLD", date(2026, 6, 23), date(2026, 6, 30))
        assert ctx is not None
        assert ctx.is_fully_within is False
        assert ctx.overlap_days >= 1

    def test_trip_crosses_holiday_start_only(self):
        """Trip starts outside holiday and return is first day of holiday."""
        cal = get_calendar()
        # QLD mid-year starts 27 Jun 2026 — trip 25-27 Jun overlaps by 1 day
        ctx = cal.check_overlap("QLD", date(2026, 6, 25), date(2026, 6, 27))
        assert ctx is not None
        assert ctx.overlap_days == 1

    def test_one_way_trip_on_holiday(self):
        """One-way trip (no return): departure date on holiday → overlap."""
        cal = get_calendar()
        ctx = cal.check_overlap("QLD", date(2026, 7, 5), return_date=None)
        assert ctx is not None

    def test_one_way_trip_outside_holiday(self):
        cal = get_calendar()
        ctx = cal.check_overlap("QLD", date(2026, 3, 15), return_date=None)
        assert ctx is None

    def test_case_insensitive_state_code(self):
        """State code matching is case-insensitive."""
        cal = get_calendar()
        ctx_upper = cal.check_overlap("QLD", date(2026, 7, 1), date(2026, 7, 5))
        ctx_lower = cal.check_overlap("qld", date(2026, 7, 1), date(2026, 7, 5))
        assert (ctx_upper is None) == (ctx_lower is None)

    def test_unknown_state_returns_none(self):
        """State with no data in YAML returns None (graceful)."""
        cal = get_calendar()
        ctx = cal.check_overlap("XX", date(2026, 7, 1), date(2026, 7, 5))
        assert ctx is None


class TestListPeriods:
    def test_qld_2026_has_four_breaks(self):
        """QLD 2026 should have 4 holiday periods (autumn, mid-year, spring, summer)."""
        cal = get_calendar()
        periods = cal.list_periods("QLD", 2026)
        assert len(periods) == 4

    def test_periods_ordered_by_start_date(self):
        cal = get_calendar()
        periods = cal.list_periods("QLD", 2026)
        starts = [p.start for p in periods]
        assert starts == sorted(starts)

    def test_qld_2025_has_four_breaks(self):
        cal = get_calendar()
        periods = cal.list_periods("QLD", 2025)
        assert len(periods) == 4


class TestSupportedStates:
    def test_qld_is_supported(self):
        cal = get_calendar()
        assert "QLD" in cal.supported_states()
