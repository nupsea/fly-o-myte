"""
Shared pytest fixtures for the Travo test suite.

All external I/O (API calls, file reads beyond package data) is
handled via fixtures and mocks. Tests must never make real network calls.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from sqlmodel import create_engine

from travo.db.sqlite import Trip, PriceSnapshot, Recommendation, create_tables, get_session
from travo.fees import AirlineFees
from travo.recommender import SnapshotPoint


# ─── Database fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def in_memory_engine():
    """Ephemeral SQLite engine for each test — no disk state."""
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine):
    with get_session(in_memory_engine) as session:
        yield session


@pytest.fixture
def sample_trip(db_session) -> Trip:
    """A minimal active trip for testing."""
    from travo.db.sqlite import insert_trip
    trip = Trip(
        label="Test BNE-SYD",
        origin="BNE",
        destination="SYD",
        depart_date="2026-07-20",
        return_date="2026-07-27",
        adults=2,
        children_json='[{"name": "Mia", "dob": "2018-06-15"}]',
        bags_per_person=1,
        max_stops=1,
    )
    return insert_trip(db_session, trip)


# ─── Recommender fixtures ──────────────────────────────────────────────────────


def make_snapshots(costs: list[float], start: datetime | None = None) -> list[SnapshotPoint]:
    """Create SnapshotPoint list with evenly-spaced timestamps."""
    base = start or datetime(2026, 6, 1, 9, 0)
    from datetime import timedelta
    return [
        SnapshotPoint(
            fetched_at=base + timedelta(days=i),
            true_family_cost=cost,
        )
        for i, cost in enumerate(costs)
    ]


@pytest.fixture
def snapshots_rising():
    """Prices rising steadily — supports book_now signal."""
    return make_snapshots([1200, 1250, 1310, 1380, 1450])


@pytest.fixture
def snapshots_falling():
    """Prices falling steadily — supports wait signal."""
    return make_snapshots([1600, 1520, 1440, 1380, 1310])


@pytest.fixture
def snapshots_flat():
    """Stable prices — typical monitor situation."""
    return make_snapshots([1400, 1410, 1395, 1405, 1400])


# ─── Airline fee fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def qantas_fees() -> AirlineFees:
    return AirlineFees(
        iata="QF",
        name="Qantas",
        family_score=88,
        bag1_fee=0.0,
        bag1_fee_lite=45.0,
        bag1_weight_kg=23,
        bag2_fee=60.0,
        seat_selection_fee=0.0,
        seat_selection_fee_lite=15.0,
        family_seating_guaranteed=True,
        infant_lap_fee_domestic=0.0,
        infant_lap_fee_intl=0.0,
        on_time_pct=82,
    )


@pytest.fixture
def jetstar_fees() -> AirlineFees:
    return AirlineFees(
        iata="JQ",
        name="Jetstar",
        family_score=42,
        bag1_fee=55.0,
        bag1_fee_lite=55.0,
        bag1_weight_kg=15,
        bag2_fee=85.0,
        seat_selection_fee=8.0,
        seat_selection_fee_lite=8.0,
        family_seating_guaranteed=False,
        infant_lap_fee_domestic=35.0,
        infant_lap_fee_intl=0.0,
        on_time_pct=74,
    )


# ─── Mock Tequila response ─────────────────────────────────────────────────────


MOCK_TEQUILA_RESPONSE = {
    "data": [
        {
            "id": "mock_itinerary_1",
            "price": 149.0,
            "route": [
                {
                    "airline": "QF",
                    "flight_no": "QF500",
                    "local_departure": "2026-07-20T10:30:00",
                    "local_arrival": "2026-07-20T12:10:00",
                }
            ],
            "duration": {"total": 6000},
            "stopovers": 0,
        },
    ],
    "currency": "AUD",
}
