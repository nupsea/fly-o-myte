"""
School holiday calendar — Australian state term dates.

Holiday data is embedded in travo/data/school_holidays.yaml and loaded once
at import time. No network calls, no external API.

Phase 1: QLD only.
Phase 2: All Australian states.
Phase 3: International (NZ, SG, UK, etc.)

Usage:
    cal = get_calendar()
    ctx = cal.check_overlap("QLD", depart_date, return_date)
    if ctx:
        print(ctx.label, ctx.overlap_days)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib.resources import files

import yaml


@dataclass(frozen=True)
class HolidayContext:
    label: str  # e.g. "Mid-year holidays"
    overlap_days: int  # days of trip that fall within the holiday
    is_fully_within: bool


@dataclass(frozen=True)
class HolidayPeriod:
    label: str
    start: date
    end: date
    state: str
    year: int


class SchoolCalendar:
    """
    In-memory index of school holiday periods by state and year.
    Built from the embedded school_holidays.yaml on first access.
    """

    def __init__(self, raw: dict) -> None:
        self._periods: list[HolidayPeriod] = []
        for state_code, state_data in raw.items():
            if state_code.startswith("_") or not isinstance(state_data, dict):
                continue
            for key, value in state_data.items():
                if not isinstance(key, int):
                    continue
                year = key
                for _break_name, break_data in value.items():
                    if not isinstance(break_data, dict):
                        continue
                    if "label" not in break_data:
                        continue  # skip term periods (no label key)
                    self._periods.append(
                        HolidayPeriod(
                            label=break_data["label"],
                            start=date.fromisoformat(break_data["start"]),
                            end=date.fromisoformat(break_data["end"]),
                            state=state_code,
                            year=year,
                        )
                    )

    def check_overlap(
        self,
        state: str,
        depart_date: date,
        return_date: date | None,
    ) -> HolidayContext | None:
        """
        Return the first holiday period that overlaps with the trip.
        Returns None if the trip does not overlap any school holiday.

        If return_date is None (one-way), only the departure date is checked.
        """
        trip_start = depart_date
        trip_end = return_date if return_date else depart_date

        for period in self._periods:
            if period.state != state.upper():
                continue
            # Overlap when trip does not end before holiday starts, and
            # holiday does not end before trip starts
            if trip_end < period.start or trip_start > period.end:
                continue

            overlap_start = max(trip_start, period.start)
            overlap_end = min(trip_end, period.end)
            overlap_days = (overlap_end - overlap_start).days + 1

            is_fully_within = trip_start >= period.start and trip_end <= period.end

            return HolidayContext(
                label=period.label,
                overlap_days=overlap_days,
                is_fully_within=is_fully_within,
            )

        return None

    def list_periods(self, state: str, year: int) -> list[HolidayPeriod]:
        """Return all holiday periods for a state and year, ordered by start date."""
        return sorted(
            [p for p in self._periods if p.state == state.upper() and p.year == year],
            key=lambda p: p.start,
        )

    def supported_states(self) -> list[str]:
        """Return all states with data loaded."""
        return sorted({p.state for p in self._periods})


def _load_raw() -> dict:
    data_path = files("fly_o_myte") / "data" / "school_holidays.yaml"
    with data_path.open() as f:
        return yaml.safe_load(f)


_calendar: SchoolCalendar | None = None


def get_calendar() -> SchoolCalendar:
    global _calendar
    if _calendar is None:
        _calendar = SchoolCalendar(_load_raw())
    return _calendar
