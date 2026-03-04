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
                    base_fare_per_adult=295.0,
                    true_family_cost=620.0,
                    true_cost_breakdown='{"base_adults": 590.0, "base_children": 0.0, "bags": 30.0, "seats": 0.0, "infant": 0.0, "total": 620.0}',
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


class TestFlexCommand:
    """S33: fom flex command shows date alternatives ranked by true family cost."""

    @pytest.fixture(autouse=True)
    def fresh_db(self, tmp_path, monkeypatch):
        from fly_o_myte.config import get_settings
        from fly_o_myte.db.sqlite import create_db_engine, create_tables

        db_path = tmp_path / "flex_test.db"
        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        get_settings.cache_clear()
        engine = create_db_engine(db_path)
        create_tables(engine)
        self._engine = engine  # type: ignore[attr-defined]
        yield
        get_settings.cache_clear()

    def test_flex_nonexistent_trip(self):
        result = runner.invoke(app, ["flex", "999"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_flex_snapshot(self, snapshot: SnapshotAssertion):
        """fom flex with pre-seeded FlexCache shows table and prompt."""
        import json

        from fly_o_myte.db.sqlite import (
            FlexCache,
            PriceSnapshot,
            Trip,
            get_session,
            insert_snapshot,
            insert_trip,
        )

        with get_session(self._engine) as session:  # type: ignore[attr-defined]
            trip = insert_trip(
                session,
                Trip(
                    label="BNE-SYD Flex test",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-09-20",
                    return_date="2026-09-27",
                    adults=2,
                ),
            )
            assert trip.id is not None

            # Seed a tracked snapshot (high cost = alternatives look cheap)
            insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=trip.id,
                    fetched_at="2026-03-01T10:00:00",
                    source="stub",
                    airline_code="QF",
                    true_family_cost=800.0,
                    rank=1,
                ),
            )

            # Pre-populate FlexCache (key must match fom flex defaults: flex=3, symmetric)
            flex_key = "BNE_SYD_2026-09-20_2026-09-27_3_3"
            cache_data = [
                {
                    "depart_date": "2026-09-17",
                    "return_date": "2026-09-24",
                    "true_family_cost": 300.0,
                    "airline_code": "QF",
                    "stops": 0,
                    "departure_time": "10:30",
                    "school_holiday_label": None,
                },
                {
                    "depart_date": "2026-09-20",
                    "return_date": "2026-09-27",
                    "true_family_cost": 350.0,
                    "airline_code": "QF",
                    "stops": 0,
                    "departure_time": "10:30",
                    "school_holiday_label": None,
                },
                {
                    "depart_date": "2026-09-23",
                    "return_date": "2026-09-30",
                    "true_family_cost": 400.0,
                    "airline_code": "JQ",
                    "stops": 1,
                    "departure_time": "14:00",
                    "school_holiday_label": None,
                },
            ]
            session.add(
                FlexCache(
                    trip_id=trip.id,
                    flex_key=flex_key,
                    computed_at="2026-03-04T08:00:00+00:00",
                    results_json=json.dumps(cache_data),
                )
            )
            session.commit()

        # Pass "n" to skip the interactive watch prompt
        result = runner.invoke(app, ["flex", "1"], input="n\n")
        assert result.exit_code == 0
        assert result.output == snapshot

    def test_flex_month_snapshot(self, snapshot: SnapshotAssertion):
        """fom flex --month with pre-seeded FlexCache shows month-mode table."""
        import json

        from fly_o_myte.db.sqlite import (
            FlexCache,
            PriceSnapshot,
            Trip,
            get_session,
            insert_snapshot,
            insert_trip,
        )

        with get_session(self._engine) as session:  # type: ignore[attr-defined]
            trip = insert_trip(
                session,
                Trip(
                    label="BNE-SYD Month test",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-07-20",
                    return_date="2026-07-27",
                    adults=2,
                ),
            )
            assert trip.id is not None

            insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=trip.id,
                    fetched_at="2026-03-01T10:00:00",
                    source="stub",
                    airline_code="QF",
                    true_family_cost=800.0,
                    rank=1,
                ),
            )

            # Pre-populate FlexCache with month-mode key
            flex_key = "month_BNE_SYD_2026_7"
            cache_data = [
                {
                    "depart_date": "2026-07-01",
                    "return_date": "2026-07-08",
                    "true_family_cost": 280.0,
                    "airline_code": "QF",
                    "stops": 0,
                    "departure_time": "08:00",
                    "school_holiday_label": "QLD Mid-Year",
                },
                {
                    "depart_date": "2026-07-08",
                    "return_date": "2026-07-15",
                    "true_family_cost": 320.0,
                    "airline_code": "VA",
                    "stops": 0,
                    "departure_time": "10:30",
                    "school_holiday_label": None,
                },
                {
                    "depart_date": "2026-07-15",
                    "return_date": "2026-07-22",
                    "true_family_cost": 360.0,
                    "airline_code": "JQ",
                    "stops": 1,
                    "departure_time": "14:00",
                    "school_holiday_label": None,
                },
            ]
            session.add(
                FlexCache(
                    trip_id=trip.id,
                    flex_key=flex_key,
                    computed_at="2026-03-04T08:00:00+00:00",
                    results_json=json.dumps(cache_data),
                )
            )
            session.commit()

        result = runner.invoke(app, ["flex", "1", "--month"], input="n\n")
        assert result.exit_code == 0
        assert result.output == snapshot


class TestAirportsCommand:
    """S32: fom airports command resolves IATA codes by city/country name."""

    def test_airports_sri_lanka(self):
        result = runner.invoke(app, ["airports", "sri lanka"])
        assert result.exit_code == 0
        assert "CMB" in result.output

    def test_airports_japan(self):
        result = runner.invoke(app, ["airports", "japan"])
        assert result.exit_code == 0
        assert "NRT" in result.output
        assert "HND" in result.output
        assert "KIX" in result.output

    def test_airports_no_match(self):
        result = runner.invoke(app, ["airports", "zzz"])
        assert result.exit_code == 0
        assert "No matches found" in result.output

    def test_airports_snapshot(self, snapshot: SnapshotAssertion):
        result = runner.invoke(app, ["airports", "sri lanka"])
        assert result.exit_code == 0
        assert result.output == snapshot


class TestInternationalRouteCheck:
    """S30: fom check on an international trip shows 'International route' context."""

    @pytest.fixture(autouse=True)
    def fresh_db(self, tmp_path, monkeypatch):
        from fly_o_myte.config import get_settings
        from fly_o_myte.db.sqlite import create_db_engine, create_tables

        db_path = tmp_path / "intl_test.db"
        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        get_settings.cache_clear()
        engine = create_db_engine(db_path)
        create_tables(engine)
        self._engine = engine  # type: ignore[attr-defined]
        yield
        get_settings.cache_clear()

    def test_check_shows_international_route_context(self):
        """fom check on BNE→SIN trip shows 'International route' in output."""
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
                    label="BNE-SIN Intl",
                    origin="BNE",
                    destination="SIN",
                    depart_date="2026-09-18",
                    return_date="2026-09-25",
                    adults=2,
                ),
            )
            assert trip.id is not None
            insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=trip.id,
                    fetched_at="2026-03-01T10:00:00",
                    source="stub",
                    airline_code="SQ",
                    base_fare_per_adult=800.0,
                    true_family_cost=1600.0,
                    true_cost_breakdown='{"base_adults": 1600.0, "base_children": 0.0, "bags": 0.0, "seats": 0.0, "infant": 0.0, "total": 1600.0}',
                    price_level_signal="LOW",
                    stops=0,
                    departure_time="09:00",
                    family_score=85.0,
                ),
            )
            insert_recommendation(
                session,
                Recommendation(
                    trip_id=trip.id,
                    generated_at="2026-03-01T10:00:00",
                    decision="monitor",
                    confidence=0.50,
                    regret_risk="medium",
                    true_family_cost=1600.0,
                    rolling_avg_cost=1600.0,
                    trend_slope=0.0,
                    days_to_departure=200,
                    price_level_signal="LOW",
                    rationale="Building history for BNE-SIN route.",
                ),
            )

        result = runner.invoke(app, ["check", "1"])
        assert result.exit_code == 0
        assert "International route" in result.output
        assert "1,600" in result.output  # AUD total visible


class TestPlanCommand:
    """S35: fom plan command — structured fallback when ANTHROPIC_API_KEY unset."""

    @pytest.fixture(autouse=True)
    def fresh_db(self, tmp_path, monkeypatch):
        from fly_o_myte.config import get_settings
        from fly_o_myte.db.sqlite import create_db_engine, create_tables

        db_path = tmp_path / "plan_test.db"
        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        get_settings.cache_clear()
        engine = create_db_engine(db_path)
        create_tables(engine)
        self._engine = engine  # type: ignore[attr-defined]
        yield
        get_settings.cache_clear()

    def test_plan_no_api_key_no_results(self):
        """fom plan with no API key and empty PM → shows note + no results message."""
        # Input: destination=Sri Lanka, month=dec-2026, nights=7, flex=3
        result = runner.invoke(app, ["plan"], input="Sri Lanka\ndec-2026\n7\n3\n")
        assert result.exit_code == 0
        # Should show the API key note
        assert "ANTHROPIC_API_KEY not set" in result.output
        # Should show no results (empty PM in test env)
        assert "No results" in result.output or "CMB" in result.output

    def test_plan_snapshot(self, snapshot: SnapshotAssertion):
        """Syrupy snapshot for fom plan structured fallback (no LLM, no results)."""
        result = runner.invoke(app, ["plan"], input="Sri Lanka\ndec-2026\n7\n3\n")
        assert result.exit_code == 0
        assert result.output == snapshot


class TestGroupTagCommand:
    """S36: fom watch --group stores tag; fom status --group filters; fom check shows tag."""

    @pytest.fixture(autouse=True)
    def fresh_db(self, tmp_path, monkeypatch):
        from fly_o_myte.config import get_settings
        from fly_o_myte.db.sqlite import create_db_engine, create_tables

        db_path = tmp_path / "group_test.db"
        monkeypatch.setenv("FLY_O_MYTE_DB_PATH", str(db_path))
        get_settings.cache_clear()
        engine = create_db_engine(db_path)
        create_tables(engine)
        self._engine = engine  # type: ignore[attr-defined]
        yield
        get_settings.cache_clear()

    def test_status_group_filter(self):
        """fom status --group shows only trips matching the group tag."""
        from fly_o_myte.db.sqlite import (
            Recommendation,
            Trip,
            get_session,
            insert_recommendation,
            insert_trip,
        )

        with get_session(self._engine) as session:  # type: ignore[attr-defined]
            t1 = insert_trip(
                session,
                Trip(
                    label="Easter BNE-SYD",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-04-03",
                    return_date="2026-04-10",
                    adults=2,
                    group_tag="easter",
                ),
            )
            assert t1.id is not None
            insert_recommendation(
                session,
                Recommendation(
                    trip_id=t1.id,
                    decision="wait",
                    confidence=0.60,
                    regret_risk="medium",
                    true_family_cost=500.0,
                    rolling_avg_cost=510.0,
                    trend_slope=-1.0,
                    days_to_departure=30,
                    rationale="Monitor.",
                ),
            )
            t2 = insert_trip(
                session,
                Trip(
                    label="Winter BNE-MEL",
                    origin="BNE",
                    destination="MEL",
                    depart_date="2026-07-10",
                    return_date="2026-07-17",
                    adults=2,
                    group_tag="winter",
                ),
            )
            assert t2.id is not None
            insert_recommendation(
                session,
                Recommendation(
                    trip_id=t2.id,
                    decision="monitor",
                    confidence=0.50,
                    regret_risk="low",
                    true_family_cost=400.0,
                    rolling_avg_cost=400.0,
                    trend_slope=0.0,
                    days_to_departure=128,
                    rationale="Monitor.",
                ),
            )

        result = runner.invoke(app, ["status", "--all", "--group", "easter"])
        assert result.exit_code == 0
        assert "Easter BNE-SYD" in result.output
        assert "Winter BNE-MEL" not in result.output

    def test_check_shows_group_tag(self):
        """fom check shows 'Group: <tag>' in the info line when group_tag is set."""
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
                    label="Easter BNE-SYD",
                    origin="BNE",
                    destination="SYD",
                    depart_date="2026-04-03",
                    return_date="2026-04-10",
                    adults=2,
                    group_tag="easter",
                ),
            )
            assert trip.id is not None
            insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=trip.id,
                    fetched_at="2026-03-01T10:00:00",
                    source="stub",
                    airline_code="QF",
                    base_fare_per_adult=250.0,
                    true_family_cost=500.0,
                    true_cost_breakdown='{"base_adults": 500.0, "bags": 0.0, "seats": 0.0, "infant": 0.0, "total": 500.0}',
                    stops=0,
                    departure_time="09:00",
                    family_score=85.0,
                ),
            )
            insert_recommendation(
                session,
                Recommendation(
                    trip_id=trip.id,
                    generated_at="2026-03-01T10:00:00",
                    decision="monitor",
                    confidence=0.50,
                    regret_risk="low",
                    true_family_cost=500.0,
                    rolling_avg_cost=500.0,
                    trend_slope=0.0,
                    days_to_departure=33,
                    rationale="Not enough data yet.",
                ),
            )

        result = runner.invoke(app, ["check", "1"])
        assert result.exit_code == 0
        assert "Group: easter" in result.output
