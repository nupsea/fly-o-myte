"""
Tests for the analytics layer (analytics.py / db/duckdb.py).

Phase 2 — tests are skipped if DuckDB is not installed.
All analytics tests use file-based SQLite because DuckDB's sqlite_scan
extension requires a real file path (in-memory SQLite is not supported).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fly_o_myte.config import DepartureWindow, FamilyProfile
from fly_o_myte.db.duckdb import query_price_percentiles
from fly_o_myte.db.sqlite import (
    Trip,
    create_db_engine,
    create_tables,
    get_session,
    insert_trip,
)
from fly_o_myte.price_sources.hookspecs import FlightOffer, hookimpl
from fly_o_myte.tracker import poll_trip

# Skip entire module if DuckDB is not installed.
duckdb = pytest.importorskip(
    "duckdb", reason="DuckDB not installed — skipping analytics tests"
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_profile() -> FamilyProfile:
    return FamilyProfile(
        adults=2,
        children=[],
        state="QLD",
        preferred_departure_window=DepartureWindow(earliest_hour=8, latest_hour=18),
    )


class _StubSource:
    """Deterministic Pluggy plugin for analytics tests."""

    def __init__(self, price: float = 200.0) -> None:
        self._price = price

    @hookimpl
    def source_name(self) -> str:
        return "stub_analytics"

    @hookimpl
    def supports_route(self, origin: str, destination: str) -> bool:
        return True

    @hookimpl
    def search_flights(self, **kwargs) -> list[FlightOffer]:  # type: ignore[override]
        return [
            FlightOffer(
                source="stub_analytics",
                airline_code="QF",
                flight_number="QF500",
                base_fare_per_adult=self._price,
                currency=kwargs.get("currency", "AUD"),
                stops=0,
                departure_time="10:30",
                arrival_time="12:10",
                duration_minutes=100,
                price_level_signal=None,
                offer_raw={},
            )
        ]


def _make_stub_pm(price: float = 200.0):
    from fly_o_myte.price_sources.hookspecs import build_plugin_manager

    pm = build_plugin_manager()
    pm.register(_StubSource(price=price))
    return pm


def _make_file_engine(db_path: Path):
    engine = create_db_engine(db_path)
    create_tables(engine)
    return engine


# ─── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestUpdateAfterSnapshot:
    """Tests that update_after_snapshot correctly writes Parquet data."""

    def test_parquet_created_after_poll_trip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After 3 poll_trip() calls, a Parquet file exists in analytics_dir/snapshots/."""
        db_path = tmp_path / "test.db"
        analytics_dir = tmp_path / "analytics"

        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        monkeypatch.setenv("FLY_O_MYTE_ANALYTICS_DIR", str(analytics_dir))
        from fly_o_myte.config import get_settings

        get_settings.cache_clear()
        try:
            engine = _make_file_engine(db_path)
            pm = _make_stub_pm()
            profile = _make_profile()

            with get_session(engine) as session:
                trip = insert_trip(
                    session,
                    Trip(
                        label="Analytics Test",
                        origin="BNE",
                        destination="SYD",
                        depart_date="2026-07-20",
                        return_date="2026-07-27",
                        adults=2,
                        children_json="[]",
                        bags_per_person=1,
                        max_stops=1,
                    ),
                )
                for _ in range(3):
                    poll_trip(session, trip, profile, pm, send_alerts=False)

            snap_files = list((analytics_dir / "snapshots").glob("*.parquet"))
            assert len(snap_files) >= 1
        finally:
            get_settings.cache_clear()

    def test_row_count_equals_poll_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """update_after_snapshot appends cumulatively — row count equals poll count."""
        db_path = tmp_path / "test.db"
        analytics_dir = tmp_path / "analytics"

        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        monkeypatch.setenv("FLY_O_MYTE_ANALYTICS_DIR", str(analytics_dir))
        from fly_o_myte.config import get_settings

        get_settings.cache_clear()
        try:
            engine = _make_file_engine(db_path)
            pm = _make_stub_pm()
            profile = _make_profile()

            with get_session(engine) as session:
                trip = insert_trip(
                    session,
                    Trip(
                        label="Row Count Test",
                        origin="BNE",
                        destination="SYD",
                        depart_date="2026-07-20",
                        return_date="2026-07-27",
                        adults=2,
                        children_json="[]",
                        bags_per_person=1,
                        max_stops=1,
                    ),
                )
                for _ in range(3):
                    poll_trip(session, trip, profile, pm, send_alerts=False)

            assert trip.id is not None
            parquet_path = analytics_dir / "snapshots" / f"trip_{trip.id}.parquet"
            assert parquet_path.exists()

            import duckdb as _duckdb

            with _duckdb.connect() as conn:
                row_count = conn.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')"
                ).fetchone()
            assert row_count is not None
            assert row_count[0] == 3
        finally:
            get_settings.cache_clear()

    def test_route_stats_created_for_bne_syd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After 3 snapshots, route_stats Parquet has at least one aggregated row."""
        db_path = tmp_path / "test.db"
        analytics_dir = tmp_path / "analytics"

        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        monkeypatch.setenv("FLY_O_MYTE_ANALYTICS_DIR", str(analytics_dir))
        from fly_o_myte.config import get_settings

        get_settings.cache_clear()
        try:
            engine = _make_file_engine(db_path)
            pm = _make_stub_pm()
            profile = _make_profile()

            with get_session(engine) as session:
                trip = insert_trip(
                    session,
                    Trip(
                        label="Route Stats Test",
                        origin="BNE",
                        destination="SYD",
                        depart_date="2026-07-20",
                        return_date="2026-07-27",
                        adults=2,
                        children_json="[]",
                        bags_per_person=1,
                        max_stops=1,
                    ),
                )
                for _ in range(3):
                    poll_trip(session, trip, profile, pm, send_alerts=False)

            route_stats_file = analytics_dir / "route_stats" / "route_BNE_SYD.parquet"
            assert route_stats_file.exists()

            import duckdb as _duckdb

            with _duckdb.connect() as conn:
                rows = conn.execute(
                    f"SELECT COUNT(*) FROM read_parquet('{route_stats_file}')"
                ).fetchone()
            assert rows is not None
            assert rows[0] >= 1
        finally:
            get_settings.cache_clear()


@pytest.mark.integration
class TestQueryPricePercentiles:
    """Tests for the DuckDB query_price_percentiles helper."""

    def test_percentiles_correctly_ordered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """query_price_percentiles returns dict with p25 <= median <= p75."""
        db_path = tmp_path / "test.db"
        analytics_dir = tmp_path / "analytics"

        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        monkeypatch.setenv("FLY_O_MYTE_ANALYTICS_DIR", str(analytics_dir))
        from fly_o_myte.config import get_settings

        get_settings.cache_clear()
        try:
            engine = _make_file_engine(db_path)
            profile = _make_profile()

            # Seed with 3 different prices so percentiles are meaningful
            for price in (150.0, 200.0, 300.0):
                pm = _make_stub_pm(price=price)
                with get_session(engine) as session:
                    trip = insert_trip(
                        session,
                        Trip(
                            label=f"Price {price}",
                            origin="BNE",
                            destination="SYD",
                            depart_date="2026-07-20",
                            return_date="2026-07-27",
                            adults=2,
                            children_json="[]",
                            bags_per_person=1,
                            max_stops=1,
                        ),
                    )
                    poll_trip(session, trip, profile, pm, send_alerts=False)

            result = query_price_percentiles(analytics_dir, "BNE", "SYD", db_path)
            assert result is not None
            assert result["p25"] <= result["median"] <= result["p75"]
            assert result["sample_count"] >= 3
        finally:
            get_settings.cache_clear()

    def test_returns_none_with_no_data(self, tmp_path: Path) -> None:
        """Returns None when no snapshots exist for the route."""
        db_path = tmp_path / "empty.db"
        analytics_dir = tmp_path / "analytics"
        _make_file_engine(db_path)

        result = query_price_percentiles(analytics_dir, "BNE", "SYD", db_path)
        assert result is None


@pytest.mark.integration
class TestRebuildAll:
    """Tests for the full analytics rebuild command."""

    def test_rebuild_via_cli_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """fom analytics --rebuild exits 0 and prints 'Rebuild complete'."""
        from typer.testing import CliRunner

        from fly_o_myte.cli import app

        db_path = tmp_path / "rebuild_test.db"
        analytics_dir = tmp_path / "analytics"

        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        monkeypatch.setenv("FLY_O_MYTE_ANALYTICS_DIR", str(analytics_dir))
        from fly_o_myte.config import get_settings

        get_settings.cache_clear()
        try:
            # Create an empty DB so sqlite_scan has a valid file to read
            _make_file_engine(db_path)

            runner = CliRunner()
            result = runner.invoke(app, ["analytics", "--rebuild"])
            assert result.exit_code == 0
            assert "Rebuild complete" in result.output
        finally:
            get_settings.cache_clear()
