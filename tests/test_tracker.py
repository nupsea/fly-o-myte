"""
Tests for the poll cycle orchestration (tracker.py).

External API calls are mocked via pytest-httpx.
Database operations use in-memory SQLite.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from travo.config import FamilyProfile, DepartureWindow
from travo.db.sqlite import (
    get_latest_recommendation,
    get_latest_snapshot,
    get_snapshots_for_trip,
    insert_trip,
    Trip,
)
from travo.fees import AirlineFees
from travo.price_sources.hookspecs import FlightOffer, build_plugin_manager
from travo.tracker import poll_trip, poll_all_active


def _make_profile() -> FamilyProfile:
    return FamilyProfile(
        adults=2,
        children=[],
        origin_airport="BNE",
        state="QLD",
        bags_per_person=1,
        max_stops=1,
        preferred_departure_window=DepartureWindow(earliest_hour=8, latest_hour=18),
    )


def _make_offer(price: float = 149.0) -> FlightOffer:
    return FlightOffer(
        source="tequila",
        airline_code="QF",
        flight_number="QF500",
        base_fare_per_adult=price,
        currency="AUD",
        stops=0,
        departure_time="10:30",
        arrival_time="12:10",
        duration_minutes=100,
        price_level_signal=None,
        offer_raw={},
    )


def _mock_pm(offer: FlightOffer | None = None):
    """Create a mock plugin manager that returns a preset offer."""
    pm = MagicMock()
    pm.hook.search_flights.return_value = [[offer]] if offer else [[]]
    return pm


class TestPollTrip:
    def test_poll_saves_snapshot(self, db_session, sample_trip):
        """Successful poll saves one snapshot to the database."""
        pm = _mock_pm(_make_offer())
        snap = poll_trip(db_session, sample_trip, _make_profile(), pm, send_alerts=False)
        assert snap is not None
        assert snap.trip_id == sample_trip.id
        assert snap.true_family_cost > 0

    def test_poll_saves_recommendation(self, db_session, sample_trip):
        """Successful poll saves a recommendation."""
        pm = _mock_pm(_make_offer())
        poll_trip(db_session, sample_trip, _make_profile(), pm, send_alerts=False)
        rec = get_latest_recommendation(db_session, sample_trip.id)
        assert rec is not None
        assert rec.decision in ("book_now", "wait", "monitor")

    def test_poll_no_offers_returns_none(self, db_session, sample_trip):
        """When no offers are returned, poll returns None and saves nothing."""
        pm = _mock_pm(None)
        snap = poll_trip(db_session, sample_trip, _make_profile(), pm, send_alerts=False)
        assert snap is None
        snaps = get_snapshots_for_trip(db_session, sample_trip.id)
        assert len(snaps) == 0

    def test_poll_computes_true_cost(self, db_session, sample_trip):
        """True cost must exceed base fare (bags/seats/infant fees added)."""
        pm = _mock_pm(_make_offer(price=99.0))
        snap = poll_trip(db_session, sample_trip, _make_profile(), pm, send_alerts=False)
        # 2 adults × $99 = $198 base; true cost may include bags for unknown fare type
        assert snap.true_family_cost >= 99.0 * 2

    def test_poll_accumulates_snapshots(self, db_session, sample_trip):
        """Each poll adds a new snapshot row."""
        pm = _mock_pm(_make_offer())
        for _ in range(3):
            poll_trip(db_session, sample_trip, _make_profile(), pm, send_alerts=False)
        snaps = get_snapshots_for_trip(db_session, sample_trip.id)
        assert len(snaps) == 3


class TestPollAllActive:
    def test_polls_all_active_trips(self, db_session, in_memory_engine):
        """poll_all_active runs against every active trip."""
        from travo.db.sqlite import get_session
        profile = _make_profile()
        pm = _mock_pm(_make_offer())

        trip1 = insert_trip(db_session, Trip(
            label="Trip A", origin="BNE", destination="SYD",
            depart_date="2026-07-20", return_date="2026-07-27",
        ))
        trip2 = insert_trip(db_session, Trip(
            label="Trip B", origin="BNE", destination="MEL",
            depart_date="2026-08-10", return_date="2026-08-17",
        ))

        results = poll_all_active(db_session, profile, pm, send_alerts=False)
        assert trip1.id in results
        assert trip2.id in results

    def test_error_in_one_trip_continues_others(self, db_session, in_memory_engine):
        """If one trip fails, poll continues to next trip."""
        profile = _make_profile()

        # Plugin manager raises for first call, succeeds for second
        pm = MagicMock()
        call_count = [0]
        def side_effect(**_kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("API error")
            return [[_make_offer()]]
        pm.hook.search_flights.side_effect = side_effect

        trip1 = insert_trip(db_session, Trip(
            label="Trip fail", origin="BNE", destination="SYD",
            depart_date="2026-07-20", return_date="2026-07-27",
        ))
        trip2 = insert_trip(db_session, Trip(
            label="Trip ok", origin="BNE", destination="MEL",
            depart_date="2026-08-10", return_date="2026-08-17",
        ))

        results = poll_all_active(db_session, profile, pm, send_alerts=False)
        assert results[trip1.id] == "error"
        assert results[trip2.id] == "ok"
