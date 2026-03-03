"""
Tests for the poll cycle orchestration (tracker.py).

Uses the deterministic _StubTequilaSource from conftest (not MagicMock)
so that cost calculations are predictable and assertion values don't drift.
"""

from __future__ import annotations

import pytest

from fly_o_myte.config import DepartureWindow, FamilyProfile
from fly_o_myte.db.sqlite import (
    get_latest_recommendation,
    get_snapshots_for_trip,
    insert_trip,
    Trip,
)
from fly_o_myte.price_sources.hookspecs import build_plugin_manager
from fly_o_myte.tracker import poll_trip, poll_all_active
from tests.conftest import _StubTequilaSource


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


# ─── poll_trip ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPollTrip:
    def test_poll_saves_snapshot(self, db_session, sample_trip, stub_pm):
        snap = poll_trip(db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False)
        assert snap is not None
        assert snap.trip_id == sample_trip.id
        assert snap.true_family_cost > 0

    def test_poll_saves_recommendation(self, db_session, sample_trip, stub_pm):
        poll_trip(db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False)
        rec = get_latest_recommendation(db_session, sample_trip.id)
        assert rec is not None
        assert rec.decision in ("book_now", "wait", "monitor")

    def test_poll_no_offers_returns_none(self, db_session, sample_trip):
        """Empty price source returns None, nothing persisted."""
        from fly_o_myte.price_sources.hookspecs import hookimpl

        class _EmptySource:
            @hookimpl
            def source_name(self) -> str:
                return "empty"

            @hookimpl
            def supports_route(self, origin, destination) -> bool:
                return True

            @hookimpl
            def search_flights(self, **_kwargs):
                return []

        pm = build_plugin_manager()
        pm.register(_EmptySource())
        snap = poll_trip(db_session, sample_trip, _make_profile(), pm, send_alerts=False)
        assert snap is None
        assert len(get_snapshots_for_trip(db_session, sample_trip.id)) == 0

    def test_poll_true_cost_exceeds_base_fare(self, db_session, sample_trip, stub_pm):
        """
        Stub returns QF at $149/adult, 2 adults.
        Qantas has zero bag/seat/infant fees domestically, so true cost = 2 × $149 = $298.
        """
        snap = poll_trip(db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False)
        assert snap is not None
        assert snap.true_family_cost == pytest.approx(298.0)

    def test_poll_accumulates_snapshots(self, db_session, sample_trip, stub_pm):
        """Each poll adds a new snapshot row."""
        for _ in range(3):
            poll_trip(db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False)
        snaps = get_snapshots_for_trip(db_session, sample_trip.id)
        assert len(snaps) == 3

    @pytest.mark.parametrize("stub_pm", [{"price": 99.0, "airline": "JQ"}], indirect=True)
    def test_poll_jetstar_true_cost_includes_bags(self, db_session, sample_trip, stub_pm):
        """
        Jetstar at $99/adult, 2 adults, 1 bag/person, return (2 legs).
        Bags: 2 pax × $55 × 2 legs = $220
        Seats: 2 pax × $8 × 2 legs = $32
        Base: 2 × $99 = $198
        Expected total = $450
        """
        snap = poll_trip(db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False)
        assert snap is not None
        assert snap.true_family_cost == pytest.approx(450.0)


# ─── poll_all_active ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPollAllActive:
    def test_polls_all_active_trips(self, db_session, stub_pm):
        profile = _make_profile()
        trip1 = insert_trip(db_session, Trip(
            label="Trip A", origin="BNE", destination="SYD",
            depart_date="2026-07-20", return_date="2026-07-27",
        ))
        trip2 = insert_trip(db_session, Trip(
            label="Trip B", origin="BNE", destination="MEL",
            depart_date="2026-08-10", return_date="2026-08-17",
        ))
        results = poll_all_active(db_session, profile, stub_pm, send_alerts=False)
        assert results[trip1.id] == "ok"
        assert results[trip2.id] == "ok"

    def test_error_in_one_trip_continues_others(self, db_session, stub_pm):
        """If one trip's price source raises, poll continues to next trip."""
        from fly_o_myte.price_sources.hookspecs import hookimpl

        call_count = [0]

        class _FailFirstSource:
            @hookimpl
            def source_name(self):
                return "fail_first"

            @hookimpl
            def supports_route(self, origin, destination):
                return True

            @hookimpl
            def search_flights(self, **_kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("simulated API error")
                return [
                    __import__("fly_o_myte.price_sources.hookspecs", fromlist=["FlightOffer"])
                    .FlightOffer(
                        source="fail_first", airline_code="QF", flight_number=None,
                        base_fare_per_adult=149.0, currency="AUD", stops=0,
                        departure_time="10:30", arrival_time="12:10",
                        duration_minutes=100, price_level_signal=None, offer_raw={},
                    )
                ]

        pm = build_plugin_manager()
        pm.register(_FailFirstSource())

        profile = _make_profile()
        trip1 = insert_trip(db_session, Trip(
            label="Fail", origin="BNE", destination="SYD",
            depart_date="2026-07-20", return_date="2026-07-27",
        ))
        trip2 = insert_trip(db_session, Trip(
            label="OK", origin="BNE", destination="MEL",
            depart_date="2026-08-10", return_date="2026-08-17",
        ))
        results = poll_all_active(db_session, profile, pm, send_alerts=False)
        assert results[trip1.id] == "error"
        assert results[trip2.id] == "ok"

    def test_paused_trip_not_polled(self, db_session, stub_pm):
        """Paused trips (is_active=0) are excluded from poll_all_active."""
        from fly_o_myte.db.sqlite import set_trip_active
        profile = _make_profile()
        trip = insert_trip(db_session, Trip(
            label="Paused", origin="BNE", destination="SYD",
            depart_date="2026-07-20", return_date="2026-07-27",
        ))
        set_trip_active(db_session, trip.id, active=False)
        results = poll_all_active(db_session, profile, stub_pm, send_alerts=False)
        assert trip.id not in results
