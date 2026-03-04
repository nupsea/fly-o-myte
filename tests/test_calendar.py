"""
Tests for the school holiday calendar (calendar.py).

Uses the embedded school_holidays.yaml — no mocking needed.
"""

from __future__ import annotations

from datetime import date

from fly_o_myte.calendar import get_calendar


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

    def test_all_eight_states_supported(self):
        """All 8 AU states/territories must be present after Phase 2 data entry."""
        cal = get_calendar()
        states = cal.supported_states()
        for code in ("QLD", "NSW", "VIC", "WA", "SA", "TAS", "NT", "ACT"):
            assert code in states, f"Expected {code} in supported_states()"

    def test_unknown_state_not_in_supported(self):
        cal = get_calendar()
        assert "XX" not in cal.supported_states()


class TestMultiStateCalendar:
    """Holiday overlap tests for the 7 new AU states/territories added in S19."""

    def test_nsw_winter_break_detected(self):
        """NSW winter break 2026 (Jul 4-19) — trip Jul 7-14 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("NSW", date(2026, 7, 7), date(2026, 7, 14))
        assert ctx is not None
        assert "winter" in ctx.label.lower() or "holiday" in ctx.label.lower()

    def test_vic_winter_break_detected(self):
        """VIC winter break 2026 (Jun 27 - Jul 12) — trip Jul 1-8 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("VIC", date(2026, 7, 1), date(2026, 7, 8))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_wa_mid_year_break_detected(self):
        """WA mid-year break 2026 (Jun 27 - Jul 12) — trip Jul 1-8 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("WA", date(2026, 7, 1), date(2026, 7, 8))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_sa_mid_year_break_detected(self):
        """SA mid-year break 2026 (Jul 4-19) — trip Jul 7-14 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("SA", date(2026, 7, 7), date(2026, 7, 14))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_tas_winter_break_detected(self):
        """TAS winter break 2026 (Jul 4-19) — trip Jul 7-14 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("TAS", date(2026, 7, 7), date(2026, 7, 14))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_nt_mid_year_break_detected(self):
        """NT mid-year break 2026 (Jun 27 - Jul 12) — trip Jul 1-8 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("NT", date(2026, 7, 1), date(2026, 7, 8))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_act_winter_break_detected(self):
        """ACT winter break 2026 (Jul 4-19) — trip Jul 7-14 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("ACT", date(2026, 7, 7), date(2026, 7, 14))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_unknown_state_returns_none(self):
        """State code not in YAML always returns None."""
        cal = get_calendar()
        ctx = cal.check_overlap("ZZ", date(2026, 7, 7), date(2026, 7, 14))
        assert ctx is None

    def test_each_state_has_four_breaks_2026(self):
        """Each of the 8 AU states has exactly 4 break periods in 2026."""
        cal = get_calendar()
        for state in ("QLD", "NSW", "VIC", "WA", "SA", "TAS", "NT", "ACT"):
            periods = cal.list_periods(state, 2026)
            assert len(periods) == 4, (
                f"{state} 2026 has {len(periods)} breaks, expected 4"
            )


class TestInternationalCalendar:
    """Holiday overlap tests for the 6 international countries added in S27."""

    def test_nz_summer_holidays_detected(self):
        """NZ summer break 2026 (Dec 18 - Jan 29 2027) — trip Dec 21-28 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("NZ", date(2026, 12, 21), date(2026, 12, 28))
        assert ctx is not None
        assert "summer" in ctx.label.lower()

    def test_gb_christmas_break_detected(self):
        """GB Christmas break 2026 (Dec 19 - Jan 4 2027) — trip Dec 22-28 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("GB", date(2026, 12, 22), date(2026, 12, 28))
        assert ctx is not None
        assert "christmas" in ctx.label.lower() or "holiday" in ctx.label.lower()

    def test_sg_june_break_detected(self):
        """SG June school holidays 2026 (May 30 - Jun 28) — trip Jun 10-17 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("SG", date(2026, 6, 10), date(2026, 6, 17))
        assert ctx is not None
        assert ctx.overlap_days >= 1

    def test_jp_summer_holidays_detected(self):
        """JP summer holidays 2026 (Jul 20 - Aug 31) — trip Jul 25 - Aug 5 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("JP", date(2026, 7, 25), date(2026, 8, 5))
        assert ctx is not None
        assert "summer" in ctx.label.lower()

    def test_th_summer_holidays_detected(self):
        """TH summer school holidays 2026 (Mar 21 - May 3) — trip Apr 1-8 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("TH", date(2026, 4, 1), date(2026, 4, 8))
        assert ctx is not None
        assert "summer" in ctx.label.lower()

    def test_us_summer_holidays_detected(self):
        """US summer holidays 2026 (Jun 5 - Aug 21) — trip Jul 1-8 overlaps."""
        cal = get_calendar()
        ctx = cal.check_overlap("US", date(2026, 7, 1), date(2026, 7, 8))
        assert ctx is not None
        assert "summer" in ctx.label.lower()

    def test_all_14_codes_in_supported_states(self):
        """All 8 AU + 6 international codes must be in supported_states()."""
        cal = get_calendar()
        states = cal.supported_states()
        expected = (
            "QLD",
            "NSW",
            "VIC",
            "WA",
            "SA",
            "TAS",
            "NT",
            "ACT",
            "NZ",
            "GB",
            "SG",
            "JP",
            "TH",
            "US",
        )
        for code in expected:
            assert code in states, f"{code} not in supported_states()"

    def test_nz_outside_holidays_returns_none(self):
        """NZ in a non-holiday period (e.g. mid-August) returns None."""
        cal = get_calendar()
        ctx = cal.check_overlap("NZ", date(2026, 8, 10), date(2026, 8, 17))
        assert ctx is None
