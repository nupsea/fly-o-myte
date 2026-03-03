"""
CLI integration tests (test_cli.py).

Uses Typer's CliRunner for command execution.
Snapshot tests for Rich output use Syrupy (run with --snapshot-update to regenerate).

All commands use the session-scoped isolated temp DB set up in conftest.py
(isolated_travo_dir fixture, autouse=True).  Do NOT monkeypatch env vars here —
get_settings() is lru_cache'd so per-test env patches are silently ignored.
No real API calls — Tequila plugin is not registered in these tests.

Snapshot tests (TestSnapshotOutput) are the exception: each uses a fresh
function-scoped DB via monkeypatch so trip IDs are deterministic (always 1).
"""

from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion
from typer.testing import CliRunner

from fly_o_myte.cli import app

runner = CliRunner()


class TestCLIBasics:
    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "fly-o-myte" in result.output

    def test_no_args_shows_help(self):
        result = runner.invoke(app, [])
        assert result.exit_code in (0, 2)  # Typer help exit code varies by version
        assert "Family travel advisor" in result.output or "Usage" in result.output

    def test_data_version(self):
        result = runner.invoke(app, ["data-version"])
        assert result.exit_code == 0
        assert "QF" in result.output or "Qantas" in result.output

    def test_profile_shows_defaults(self):
        """profile command shows family profile without crashing."""
        result = runner.invoke(app, ["profile"])
        assert result.exit_code == 0
        assert "Adults" in result.output or "adults" in result.output.lower()


class TestStatusCommand:
    def test_status_no_trips(self):
        """status with no trips exits 0 — uses session-isolated DB from conftest."""
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    def test_status_all_flag(self):
        result = runner.invoke(app, ["status", "--all"])
        assert result.exit_code == 0


class TestRemoveCommand:
    def test_remove_nonexistent_trip(self):
        result = runner.invoke(app, ["remove", "999", "--yes"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestPollCommand:
    def test_poll_dry_run(self):
        result = runner.invoke(app, ["poll", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output

    def test_poll_no_trips(self):
        result = runner.invoke(app, ["poll"])
        assert result.exit_code == 0
        assert "0 ok" in result.output or "Poll complete" in result.output


class TestPauseResumeCommands:
    def test_pause_nonexistent_trip(self):
        # pause/resume on non-existent trip should not crash — just no-op
        result = runner.invoke(app, ["pause", "999"])
        # Acceptable: either graceful no-op or error message
        assert result.exit_code in (0, 1)


class TestSnapshotOutput:
    """Syrupy snapshot tests for Rich terminal output.

    Each test gets a fresh isolated DB via monkeypatch so trip IDs always
    start at 1 and output is fully deterministic.

    Regenerate baselines:
        uv run pytest tests/test_cli.py -k snapshot --snapshot-update -v
    """

    @pytest.fixture(autouse=True)
    def fresh_db(self, tmp_path, monkeypatch):
        from fly_o_myte.config import get_settings
        from fly_o_myte.db.sqlite import create_db_engine, create_tables

        db_path = tmp_path / "snap_test.db"
        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        get_settings.cache_clear()

        engine = create_db_engine(db_path)
        create_tables(engine)
        self._engine = engine  # type: ignore[attr-defined]

        yield

        get_settings.cache_clear()

    def test_status_snapshot(self, snapshot: SnapshotAssertion):
        from fly_o_myte.db.sqlite import (
            Recommendation,
            Trip,
            get_session,
            insert_recommendation,
            insert_trip,
        )

        with get_session(self._engine) as session:  # type: ignore[attr-defined]
            trip = insert_trip(
                session,
                Trip(
                    label="BNE-SYD July",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-07-20",
                    return_date="2026-07-27",
                    adults=2,
                ),
            )
            assert trip.id is not None
            insert_recommendation(
                session,
                Recommendation(
                    trip_id=trip.id,
                    generated_at="2026-03-03T10:00:00",
                    decision="wait",
                    confidence=0.70,
                    regret_risk="medium",
                    true_family_cost=620.0,
                    rolling_avg_cost=640.0,
                    trend_slope=-2.5,
                    days_to_departure=138,
                    rationale="Prices are falling. Wait for a better deal.",
                ),
            )

        result = runner.invoke(app, ["status", "--all"])
        assert result.exit_code == 0
        assert result.output == snapshot

    def test_check_snapshot(self, snapshot: SnapshotAssertion):
        from fly_o_myte.db.sqlite import (
            PriceSnapshot,
            Recommendation,
            Trip,
            get_session,
            insert_recommendation,
            insert_snapshot,
            insert_trip,
        )

        with get_session(self._engine) as session:  # type: ignore[attr-defined]
            trip = insert_trip(
                session,
                Trip(
                    label="BNE-SYD July",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-07-20",
                    return_date="2026-07-27",
                    adults=2,
                ),
            )
            assert trip.id is not None
            trip_id = trip.id

            for i in range(10):
                insert_snapshot(
                    session,
                    PriceSnapshot(
                        trip_id=trip_id,
                        fetched_at=f"2026-02-{i + 1:02d}T10:00:00",
                        source="stub",
                        airline_code="QF",
                        true_family_cost=620.0 - i * 5.0,
                        true_cost_breakdown='{"base_adults": 298.0, "base_children": 0.0, "bags": 0.0, "seats": 0.0, "infant": 0.0, "total": 298.0}',
                        price_level_signal="TYPICAL",
                        stops=0,
                        departure_time="10:30",
                        family_score=88.0,
                    ),
                )

            insert_recommendation(
                session,
                Recommendation(
                    trip_id=trip_id,
                    generated_at="2026-03-03T10:00:00",
                    decision="wait",
                    confidence=0.70,
                    regret_risk="medium",
                    true_family_cost=575.0,
                    rolling_avg_cost=597.5,
                    trend_slope=-5.0,
                    days_to_departure=138,
                    price_level_signal="TYPICAL",
                    rationale="Prices are falling steadily. Wait for a better deal before booking.",
                ),
            )

        result = runner.invoke(app, ["check", "1"])
        assert result.exit_code == 0
        assert result.output == snapshot

    def test_compare_snapshot(self, snapshot: SnapshotAssertion):
        from fly_o_myte.db.sqlite import (
            PriceSnapshot,
            Recommendation,
            Trip,
            get_session,
            insert_recommendation,
            insert_snapshot,
            insert_trip,
        )

        with get_session(self._engine) as session:  # type: ignore[attr-defined]
            trip = insert_trip(
                session,
                Trip(
                    label="BNE-SYD July",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-07-20",
                    return_date="2026-07-27",
                    adults=2,
                ),
            )
            assert trip.id is not None
            trip_id = trip.id

            insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=trip_id,
                    fetched_at="2026-03-03T10:00:00",
                    source="stub",
                    airline_code="QF",
                    true_family_cost=620.0,
                    stops=0,
                    departure_time="10:30",
                    family_score=88.0,
                ),
            )

            insert_recommendation(
                session,
                Recommendation(
                    trip_id=trip_id,
                    generated_at="2026-03-03T10:00:00",
                    decision="wait",
                    confidence=0.70,
                    regret_risk="medium",
                    true_family_cost=620.0,
                    rolling_avg_cost=620.0,
                    trend_slope=0.0,
                    days_to_departure=138,
                    rationale="Insufficient history for a strong recommendation. Keep monitoring.",
                ),
            )

        result = runner.invoke(app, ["compare", "1", "1"])
        assert result.exit_code == 0
        assert result.output == snapshot
