"""
Shared pytest fixtures for the fly-o-myte test suite.

Key pattern (adopted from learning-mate):
  session-scoped isolation fixture resets all module-level singletons
  (get_settings cache, airline DB, school calendar) before each test session,
  pointing them at a temp directory so tests never touch ~/.fly-o-myte.

Test pyramid:
  unit        — pure function tests (recommender, true_cost, calendar)
                no I/O, no mocking required
  integration — real in-memory SQLite, deterministic mock price source
                marked with @pytest.mark.integration
  slow        — real Tequila API calls (excluded from `make ci`)
  e2e         — full CLI invocation (excluded from `make ci`)
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlmodel import create_engine

from fly_o_myte.db.sqlite import (
    Trip,
    create_tables,
    get_session,
    insert_trip,
)
from fly_o_myte.fees import AirlineFees
from fly_o_myte.price_sources.hookspecs import FlightOffer, hookimpl
from fly_o_myte.recommender import SnapshotPoint

# ─── Session-scoped isolation ──────────────────────────────────────────────────
#
# Resets all module-level singletons before the test session so tests run
# in an isolated temp dir, never touching ~/.fly-o-myte.
# Pattern taken from learning-mate/backend/tests/conftest.py.


@pytest.fixture(scope="session", autouse=True)
def isolated_travo_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[str, None, None]:
    """
    Point all singletons at a session-scoped temp directory.
    Runs once per pytest session; tears down on exit.
    """
    tmp = str(tmp_path_factory.mktemp("travo_test"))

    # Override env before any module loads Settings
    os.environ["FLY_O_MYTE_DB_PATH"] = str(Path(tmp) / "fly-o-myte.db")
    os.environ["FLY_O_MYTE_ANALYTICS_DIR"] = str(Path(tmp) / "analytics")
    os.environ["FLY_O_MYTE_CONFIG_PATH"] = str(Path(tmp) / "config.yaml")
    os.environ["FLY_O_MYTE_LOG_PATH"] = str(Path(tmp) / "fly-o-myte.log")
    os.environ["SERPAPI_API_KEY"] = ""
    os.environ["TEQUILA_API_KEY"] = ""
    os.environ["ANTHROPIC_API_KEY"] = ""

    # Clear lru_cache on get_settings so it re-reads the env vars
    from fly_o_myte.config import get_settings

    get_settings.cache_clear()

    # Reset module-level singletons
    import fly_o_myte.calendar as calendar_module
    import fly_o_myte.currency as currency_module
    import fly_o_myte.fees as fees_module

    fees_module._db = None
    calendar_module._calendar = None
    currency_module._converter = None

    yield tmp

    # Teardown — restore env and caches
    for key in (
        "FLY_O_MYTE_DB_PATH",
        "FLY_O_MYTE_ANALYTICS_DIR",
        "FLY_O_MYTE_CONFIG_PATH",
        "FLY_O_MYTE_LOG_PATH",
        "SERPAPI_API_KEY",
        "TEQUILA_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        os.environ.pop(key, None)

    from fly_o_myte.config import get_settings as _gs

    _gs.cache_clear()
    fees_module._db = None
    calendar_module._calendar = None
    currency_module._converter = None


# ─── Database fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def in_memory_engine():
    """Ephemeral in-memory SQLite engine — isolated per test, no disk state."""
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


@pytest.fixture
def db_session(in_memory_engine):
    with get_session(in_memory_engine) as session:
        yield session


@pytest.fixture
def sample_trip(db_session) -> Trip:
    """A minimal active trip used across tracker and CLI tests."""
    return insert_trip(
        db_session,
        Trip(
            label="Test BNE-SYD",
            origin="BNE",
            destination="SYD",
            depart_date="2026-07-20",
            return_date="2026-07-27",
            adults=2,
            children_json='[{"name": "Mia", "dob": "2018-06-15"}]',
            bags_per_person=1,
            max_stops=1,
        ),
    )


# ─── Recommender snapshot helpers ─────────────────────────────────────────────


def make_snapshots(
    costs: list[float], start: datetime | None = None
) -> list[SnapshotPoint]:
    """
    Build a list of SnapshotPoints with evenly-spaced daily timestamps.
    Used directly by test functions (not a fixture) for conciseness.
    """
    base = start or datetime(2026, 6, 1, 9, 0)
    return [
        SnapshotPoint(
            fetched_at=base + timedelta(days=i),
            true_family_cost=cost,
        )
        for i, cost in enumerate(costs)
    ]


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


# ─── Deterministic mock price source ──────────────────────────────────────────
#
# Use this instead of MagicMock() in tracker/integration tests.
# Returns a fixed FlightOffer so cost calculations are predictable.


class _StubTequilaSource:
    """
    Deterministic Pluggy plugin for tests.
    Always returns one QF offer at a fixed price, regardless of search params.
    Replace `price` in the constructor to test different cost scenarios.
    """

    def __init__(self, price: float = 149.0, airline: str = "QF") -> None:
        self._price = price
        self._airline = airline

    @hookimpl
    def source_name(self) -> str:
        return "stub"

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
                source="stub",
                airline_code=self._airline,
                flight_number=f"{self._airline}500",
                base_fare_per_adult=self._price,
                currency=currency,
                stops=0,
                departure_time="10:30",
                arrival_time="12:10",
                duration_minutes=100,
                price_level_signal=None,
                offer_raw={},
            )
        ]


@pytest.fixture
def stub_pm(request: pytest.FixtureRequest):
    """
    Build a plugin manager pre-loaded with _StubTequilaSource.
    Accepts an optional indirect parameter dict: {"price": 200.0, "airline": "VA"}
    Usage in tests:
        def test_foo(stub_pm): ...
        @pytest.mark.parametrize("stub_pm", [{"price": 200}], indirect=True)
    """
    from fly_o_myte.price_sources.hookspecs import build_plugin_manager

    kwargs = getattr(request, "param", {})
    pm = build_plugin_manager()
    pm.register(_StubTequilaSource(**kwargs))
    return pm


# ─── Shared raw Tequila API response ──────────────────────────────────────────

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
