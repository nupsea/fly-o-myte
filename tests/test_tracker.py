"""
Tests for the poll cycle orchestration (tracker.py).

Uses the deterministic _StubTequilaSource from conftest (not MagicMock)
so that cost calculations are predictable and assertion values don't drift.
"""

from __future__ import annotations

import pytest

from fly_o_myte.config import DepartureWindow, FamilyProfile
from fly_o_myte.db.sqlite import (
    Trip,
    get_latest_recommendation,
    get_snapshots_for_trip,
    insert_trip,
)
from fly_o_myte.price_sources.amadeus import AmadeusPriceSource
from fly_o_myte.price_sources.hookspecs import (
    FlightOffer,
    build_plugin_manager,
    hookimpl,
)
from fly_o_myte.tracker import poll_all_active, poll_trip


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
        snap = poll_trip(
            db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False
        )
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
        snap = poll_trip(
            db_session, sample_trip, _make_profile(), pm, send_alerts=False
        )
        assert snap is None
        assert len(get_snapshots_for_trip(db_session, sample_trip.id)) == 0

    def test_poll_true_cost_exceeds_base_fare(self, db_session, sample_trip, stub_pm):
        """
        Stub returns QF at $149/adult, 2 adults.
        Qantas has zero bag/seat/infant fees domestically, so true cost = 2 × $149 = $298.
        """
        snap = poll_trip(
            db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False
        )
        assert snap is not None
        assert snap.true_family_cost == pytest.approx(298.0)

    def test_poll_accumulates_snapshots(self, db_session, sample_trip, stub_pm):
        """Each poll adds a new snapshot row."""
        for _ in range(3):
            poll_trip(
                db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False
            )
        snaps = get_snapshots_for_trip(db_session, sample_trip.id)
        assert len(snaps) == 3

    @pytest.mark.parametrize(
        "stub_pm", [{"price": 99.0, "airline": "JQ"}], indirect=True
    )
    def test_poll_jetstar_true_cost_includes_bags(
        self, db_session, sample_trip, stub_pm
    ):
        """
        Jetstar at $99/adult, 2 adults, 1 bag/person, return (2 legs).
        Bags: 2 pax × $55 × 2 legs = $220
        Seats: 2 pax × $8 × 2 legs = $32
        Base: 2 × $99 = $198
        Expected total = $450
        """
        snap = poll_trip(
            db_session, sample_trip, _make_profile(), stub_pm, send_alerts=False
        )
        assert snap is not None
        assert snap.true_family_cost == pytest.approx(450.0)


# ─── poll_all_active ──────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPollAllActive:
    def test_polls_all_active_trips(self, db_session, stub_pm):
        profile = _make_profile()
        trip1 = insert_trip(
            db_session,
            Trip(
                label="Trip A",
                origin="BNE",
                destination="SYD",
                depart_date="2026-07-20",
                return_date="2026-07-27",
            ),
        )
        trip2 = insert_trip(
            db_session,
            Trip(
                label="Trip B",
                origin="BNE",
                destination="MEL",
                depart_date="2026-08-10",
                return_date="2026-08-17",
            ),
        )
        results = poll_all_active(db_session, profile, stub_pm, send_alerts=False)
        assert trip1.id is not None
        assert trip2.id is not None
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
                    __import__(
                        "fly_o_myte.price_sources.hookspecs", fromlist=["FlightOffer"]
                    ).FlightOffer(
                        source="fail_first",
                        airline_code="QF",
                        flight_number=None,
                        base_fare_per_adult=149.0,
                        currency="AUD",
                        stops=0,
                        departure_time="10:30",
                        arrival_time="12:10",
                        duration_minutes=100,
                        price_level_signal=None,
                        offer_raw={},
                    )
                ]

        pm = build_plugin_manager()
        pm.register(_FailFirstSource())

        profile = _make_profile()
        trip1 = insert_trip(
            db_session,
            Trip(
                label="Fail",
                origin="BNE",
                destination="SYD",
                depart_date="2026-07-20",
                return_date="2026-07-27",
            ),
        )
        trip2 = insert_trip(
            db_session,
            Trip(
                label="OK",
                origin="BNE",
                destination="MEL",
                depart_date="2026-08-10",
                return_date="2026-08-17",
            ),
        )
        results = poll_all_active(db_session, profile, pm, send_alerts=False)
        assert trip1.id is not None
        assert trip2.id is not None
        assert results[trip1.id] == "error"
        assert results[trip2.id] == "ok"

    def test_paused_trip_not_polled(self, db_session, stub_pm):
        """Paused trips (is_active=0) are excluded from poll_all_active."""
        from fly_o_myte.db.sqlite import set_trip_active

        profile = _make_profile()
        trip = insert_trip(
            db_session,
            Trip(
                label="Paused",
                origin="BNE",
                destination="SYD",
                depart_date="2026-07-20",
                return_date="2026-07-27",
            ),
        )
        assert trip.id is not None
        set_trip_active(db_session, trip.id, active=False)
        results = poll_all_active(db_session, profile, stub_pm, send_alerts=False)
        assert trip.id not in results


# ─── Amadeus signal enrichment routing (S29) ──────────────────────────────────


class _StubAmadeus(AmadeusPriceSource):
    """Lightweight Amadeus stub — records calls to get_price_level_signal."""

    def __init__(self, return_signal: str | None = "LOW") -> None:
        # Skip real __init__ — no HTTP client needed
        self._return_signal = return_signal
        self.call_count = 0

    @hookimpl
    def source_name(self) -> str:
        return "stub_amadeus"

    @hookimpl
    def supports_route(self, origin: str, destination: str) -> bool:
        return True

    @hookimpl
    def search_flights(
        self,
        origin: str,
        destination: str,
        depart_date: object,
        return_date: object,
        adults: int,
        children_ages: list,
        max_stops: object,
        currency: str,
    ) -> list[FlightOffer]:
        return []  # yield to other price sources

    def get_price_level_signal(
        self,
        origin: str,
        destination: str,
        depart_date: object,
        price_aud: float,
    ) -> str | None:
        self.call_count += 1
        return self._return_signal


class _StubSourceWithSignal:
    """Price source that returns a FlightOffer with price_level_signal already set."""

    def __init__(self, signal: str = "HIGH") -> None:
        self._signal = signal

    @hookimpl
    def source_name(self) -> str:
        return "stub_with_signal"

    @hookimpl
    def supports_route(self, origin: str, destination: str) -> bool:
        return True

    @hookimpl
    def search_flights(
        self,
        origin: str,
        destination: str,
        depart_date: object,
        return_date: object,
        adults: int,
        children_ages: list,
        max_stops: object,
        currency: str,
    ) -> list[FlightOffer]:
        return [
            FlightOffer(
                source="stub_with_signal",
                airline_code="SQ",
                flight_number="SQ223",
                base_fare_per_adult=800.0,
                currency="AUD",
                stops=0,
                departure_time="09:00",
                arrival_time="13:30",
                duration_minutes=270,
                price_level_signal=self._signal,
                offer_raw={},
            )
        ]


@pytest.mark.integration
class TestAmadeusSignalEnrichment:
    """S29: Route-type-aware Amadeus signal enrichment."""

    def test_asia_pacific_always_calls_amadeus(self, db_session):
        """BNE→SIN (ASIA_PACIFIC): Amadeus called even when SerpAPI returned a signal."""
        stub_amadeus = _StubAmadeus(return_signal="LOW")
        pm = build_plugin_manager()
        pm.register(_StubSourceWithSignal(signal="HIGH"))  # SerpAPI returned HIGH
        pm.register(stub_amadeus)

        trip = insert_trip(
            db_session,
            Trip(
                label="BNE-SIN intl",
                origin="BNE",
                destination="SIN",
                depart_date="2026-09-18",
                return_date="2026-09-25",
                adults=2,
            ),
        )
        snap = poll_trip(db_session, trip, _make_profile(), pm, send_alerts=False)
        assert snap is not None
        assert stub_amadeus.call_count == 1, "Amadeus must be called for ASIA_PACIFIC"
        # Amadeus signal ("LOW") should override SerpAPI signal ("HIGH")
        assert snap.price_level_signal == "LOW"

    def test_domestic_with_signal_skips_amadeus(self, db_session):
        """BNE→SYD (DOMESTIC) + SerpAPI signal set: Amadeus NOT called."""
        stub_amadeus = _StubAmadeus(return_signal="LOW")
        pm = build_plugin_manager()
        pm.register(_StubSourceWithSignal(signal="HIGH"))
        pm.register(stub_amadeus)

        trip = insert_trip(
            db_session,
            Trip(
                label="BNE-SYD domestic",
                origin="BNE",
                destination="SYD",
                depart_date="2026-09-18",
                return_date="2026-09-25",
                adults=2,
            ),
        )
        snap = poll_trip(db_session, trip, _make_profile(), pm, send_alerts=False)
        assert snap is not None
        assert stub_amadeus.call_count == 0, (
            "Amadeus must NOT be called for DOMESTIC with signal"
        )
        assert snap.price_level_signal == "HIGH"
