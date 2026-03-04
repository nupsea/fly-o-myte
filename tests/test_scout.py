"""
Integration tests for the scout command (scout.py).

Tests cover month scouting, flex scouting, school holiday detection,
empty price source handling, and CLI behaviour with no API key set.
"""

from __future__ import annotations

from datetime import date

import pytest

from fly_o_myte.calendar import get_calendar
from fly_o_myte.config import DepartureWindow, FamilyProfile
from fly_o_myte.fees import get_airline_db
from fly_o_myte.scout import ScoutResult, scout_flex, scout_month


def _make_profile() -> FamilyProfile:
    return FamilyProfile(
        adults=2,
        children=[],
        state="QLD",
        bags_per_person=1,
        max_stops=1,
        preferred_departure_window=DepartureWindow(earliest_hour=8, latest_hour=18),
    )


@pytest.mark.integration
class TestScoutMonth:
    """Tests for scout_month() using the deterministic stub price source."""

    def test_returns_non_empty_list(self, stub_pm) -> None:
        """scout_month() for BNE→SYD Jul 2026 returns at least one ScoutResult."""
        results = scout_month(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            year=2026,
            month=7,
        )
        assert len(results) >= 1
        assert all(isinstance(r, ScoutResult) for r in results)

    def test_holiday_dates_have_school_holiday_set(self, stub_pm) -> None:
        """ScoutResult for 2026-07-01 to 2026-07-08 has school_holiday set (QLD mid-year)."""
        results = scout_month(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            year=2026,
            month=7,
            sample_every_n_days=7,
        )
        # Find the window starting 2026-07-01
        july_1 = next((r for r in results if r.depart_date == date(2026, 7, 1)), None)
        assert july_1 is not None, "Expected a ScoutResult for 2026-07-01"
        assert july_1.school_holiday is not None, (
            "2026-07-01 to 2026-07-08 should overlap QLD mid-year holidays"
        )

    def test_non_holiday_dates_have_no_school_holiday(self, stub_pm) -> None:
        """ScoutResult for 2026-05-01 to 2026-05-08 has school_holiday=None."""
        results = scout_month(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            year=2026,
            month=5,
            sample_every_n_days=7,
        )
        may_1 = next((r for r in results if r.depart_date == date(2026, 5, 1)), None)
        assert may_1 is not None, "Expected a ScoutResult for 2026-05-01"
        assert may_1.school_holiday is None, (
            "2026-05-01 to 2026-05-08 should not overlap any school holiday"
        )

    def test_results_ordered_by_true_family_cost(self, stub_pm) -> None:
        """Results are sorted by true_family_cost ascending."""
        results = scout_month(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            year=2026,
            month=7,
        )
        costs = [r.true_family_cost for r in results]
        assert costs == sorted(costs), "Results must be ordered by true_family_cost"

    def test_scout_results_have_positive_costs(self, stub_pm) -> None:
        """All ScoutResults have positive true_family_cost."""
        results = scout_month(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            year=2026,
            month=7,
        )
        for r in results:
            assert r.true_family_cost > 0


@pytest.mark.integration
class TestScoutFlex:
    """Tests for scout_flex() flex-date scouting."""

    def test_flex_3_covers_7_windows(self, stub_pm) -> None:
        """scout_flex() with flex=3 returns results covering ±3 day range."""
        anchor_depart = date(2026, 7, 20)
        anchor_return = date(2026, 7, 27)

        results = scout_flex(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=anchor_depart,
            return_date=anchor_return,
            flex_days=3,
        )
        # 7 windows: -3, -2, -1, 0, +1, +2, +3 (all in future)
        assert len(results) == 7

    def test_flex_0_returns_single_window(self, stub_pm) -> None:
        """scout_flex() with flex=0 returns exactly one result."""
        results = scout_flex(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
            flex_days=0,
        )
        assert len(results) == 1
        assert results[0].depart_date == date(2026, 7, 20)

    def test_flex_results_ordered_by_cost(self, stub_pm) -> None:
        """scout_flex() results are sorted by true_family_cost ascending."""
        results = scout_flex(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
            flex_days=3,
        )
        costs = [r.true_family_cost for r in results]
        assert costs == sorted(costs)


@pytest.mark.integration
class TestScoutEmptySource:
    """Tests that an empty price source returns [] without crashing."""

    def test_empty_source_returns_empty_list(self) -> None:
        """scout_month() with a plugin manager with no implementations returns []."""
        from fly_o_myte.price_sources.hookspecs import build_plugin_manager

        empty_pm = build_plugin_manager()  # no plugins registered

        results = scout_month(
            pm=empty_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            year=2026,
            month=7,
        )
        assert results == []

    def test_flex_empty_source_returns_empty_list(self) -> None:
        """scout_flex() with empty plugin manager returns []."""
        from fly_o_myte.price_sources.hookspecs import build_plugin_manager

        empty_pm = build_plugin_manager()

        results = scout_flex(
            pm=empty_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
            flex_days=3,
        )
        assert results == []


@pytest.mark.integration
class TestScoutFlexModes:
    """Tests for the new depart_flex/return_flex mode parameters."""

    def test_fix_return_all_results_have_same_return_date(self, stub_pm) -> None:
        """scout_flex with depart_flex=3, return_flex=0 produces results with fixed return_date."""
        anchor_depart = date(2026, 7, 20)
        anchor_return = date(2026, 7, 27)

        results = scout_flex(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=anchor_depart,
            return_date=anchor_return,
            depart_flex=3,
            return_flex=0,
        )
        assert len(results) > 0
        # All results must have the same return_date (fixed)
        return_dates = {r.return_date for r in results}
        assert len(return_dates) == 1, "All results should have the same return_date"
        assert list(return_dates)[0] == anchor_return

        # Depart dates should vary
        depart_dates = {r.depart_date for r in results}
        assert len(depart_dates) > 1, "Depart dates should vary"

    def test_fix_depart_all_results_have_same_depart_date(self, stub_pm) -> None:
        """scout_flex with depart_flex=0, return_flex=3 produces results with fixed depart_date."""
        anchor_depart = date(2026, 7, 20)
        anchor_return = date(2026, 7, 27)

        results = scout_flex(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=anchor_depart,
            return_date=anchor_return,
            depart_flex=0,
            return_flex=3,
        )
        assert len(results) > 0
        # All results must have the same depart_date (fixed)
        depart_dates = {r.depart_date for r in results}
        assert len(depart_dates) == 1, "All results should have the same depart_date"
        assert list(depart_dates)[0] == anchor_depart

    def test_backward_compat_flex_days_still_works(self, stub_pm) -> None:
        """Existing flex_days param still works unchanged (backward compat)."""
        results = scout_flex(
            pm=stub_pm,
            profile=_make_profile(),
            airline_db=get_airline_db(),
            calendar=get_calendar(),
            origin="BNE",
            destination="SYD",
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
            flex_days=3,
        )
        assert len(results) == 7


class TestScoutCLI:
    """Tests for the fom scout CLI command."""

    def test_scout_no_api_key_exits_0_no_results(self) -> None:
        """fom scout BNE SYD --month jul-2026 with no API key exits 0 with 'No results'."""
        from typer.testing import CliRunner

        from fly_o_myte.cli import app

        runner = CliRunner()
        # isolated_travo_dir already sets SERPAPI_API_KEY='' and TEQUILA_API_KEY=''
        result = runner.invoke(app, ["scout", "BNE", "SYD", "--month", "jul-2026"])
        assert result.exit_code == 0
        assert "No results" in result.output
