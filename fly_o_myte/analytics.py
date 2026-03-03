"""
Incremental analytics — SQLite snapshots → DuckDB + Parquet.

Called after each successful poll to keep analytics current without
a separate batch job. DuckDB processes the update in milliseconds.

Phase 2 feature — this module is a stub in Phase 1 (poll works without it).
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def update_after_snapshot(
    analytics_dir: Path,
    trip_id: int,
    origin: str,
    destination: str,
    sqlite_db_path: Path,
) -> None:
    """
    Append the latest snapshot to Parquet and recompute route stats.

    Called by tracker.py after a successful snapshot insert.
    Failures are logged but do not abort the poll cycle.

    Phase 2 implementation: connect to DuckDB, use sqlite_scan extension
    to read the new snapshot row from SQLite, append to quarterly Parquet,
    and recompute route_stats for the affected route.
    """
    try:
        import duckdb  # noqa: F401 — imported lazily so Phase 1 works without

        _run_incremental_update(
            analytics_dir, trip_id, origin, destination, sqlite_db_path
        )
    except ImportError:
        logger.debug("DuckDB not available — skipping analytics update")
    except Exception as exc:
        logger.warning("Analytics update failed (non-critical): %s", exc)


def rebuild_all(analytics_dir: Path, sqlite_db_path: Path) -> None:
    """
    Full rebuild of all Parquet files from SQLite source of truth.

    Run `fom analytics --rebuild` to recover from corrupted Parquet files.
    Reads all price_snapshots from SQLite and recomputes everything.
    """
    try:
        import duckdb  # noqa: F401

        _run_full_rebuild(analytics_dir, sqlite_db_path)
    except ImportError:
        logger.error("DuckDB not available — install duckdb to use analytics")
    except Exception as exc:
        logger.error("Analytics rebuild failed: %s", exc, exc_info=True)
        raise


def _run_incremental_update(
    analytics_dir: Path,
    trip_id: int,
    origin: str,
    destination: str,
    sqlite_db_path: Path,
) -> None:
    """Phase 2 implementation goes here."""
    import duckdb

    analytics_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = analytics_dir / "snapshots"
    route_stats_dir = analytics_dir / "route_stats"
    snapshots_dir.mkdir(exist_ok=True)
    route_stats_dir.mkdir(exist_ok=True)

    with duckdb.connect(str(analytics_dir / "fly_o_myte_analytics.duckdb")) as conn:
        conn.execute("INSTALL sqlite; LOAD sqlite;")

        # Determine quarter for partition
        conn.execute(f"""
            COPY (
                SELECT
                    ps.trip_id,
                    ps.fetched_at::TIMESTAMP AS fetched_at,
                    t.origin,
                    t.destination,
                    ps.airline_code,
                    ps.base_fare_per_adult,
                    ps.true_family_cost,
                    ps.price_level_signal,
                    ps.stops,
                    (date_part('day', t.depart_date::DATE) -
                     date_part('day', ps.fetched_at::DATE)) AS days_to_departure,
                    date_part('month', t.depart_date::DATE) AS departure_month,
                    ps.price_level_signal IS NOT NULL AS school_holiday,
                    ps.family_score
                FROM sqlite_scan('{sqlite_db_path}', 'price_snapshot') ps
                JOIN sqlite_scan('{sqlite_db_path}', 'trip') t ON t.id = ps.trip_id
                WHERE ps.trip_id = {trip_id}
                  AND ps.fetched_at = (
                      SELECT MAX(fetched_at) FROM sqlite_scan('{sqlite_db_path}', 'price_snapshot')
                      WHERE trip_id = {trip_id}
                  )
            )
            TO '{snapshots_dir}/latest_{trip_id}.parquet'
            (FORMAT PARQUET)
        """)

        # Recompute route stats for this origin/destination pair
        _recompute_route_stats(
            conn, snapshots_dir, route_stats_dir, origin, destination
        )

    logger.debug(
        "Analytics updated for trip %s (%s → %s)", trip_id, origin, destination
    )


def _recompute_route_stats(
    conn: object,
    snapshots_dir: Path,
    route_stats_dir: Path,
    origin: str,
    destination: str,
) -> None:
    """Recompute aggregated route stats for one origin/destination pair."""
    import duckdb

    assert isinstance(conn, duckdb.DuckDBPyConnection)
    parquet_glob = str(snapshots_dir / "*.parquet")
    out_path = route_stats_dir / f"route_{origin}_{destination}.parquet"

    conn.execute(f"""
        COPY (
            SELECT
                origin,
                destination,
                airline_code,
                DATE_TRUNC('week', fetched_at) AS week_start,
                school_holiday AS school_holiday_week,
                AVG(true_family_cost) AS avg_cost,
                MIN(true_family_cost) AS min_cost,
                MAX(true_family_cost) AS max_cost,
                PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY true_family_cost) AS p25_cost,
                PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY true_family_cost) AS p75_cost,
                COUNT(*) AS sample_count
            FROM read_parquet('{parquet_glob}')
            WHERE origin = '{origin}' AND destination = '{destination}'
            GROUP BY origin, destination, airline_code, week_start, school_holiday_week
        )
        TO '{out_path}' (FORMAT PARQUET)
    """)


def _run_full_rebuild(analytics_dir: Path, sqlite_db_path: Path) -> None:
    """Full analytics rebuild from SQLite — Phase 2 implementation."""
    import duckdb

    analytics_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = analytics_dir / "snapshots"
    route_stats_dir = analytics_dir / "route_stats"
    snapshots_dir.mkdir(exist_ok=True)
    route_stats_dir.mkdir(exist_ok=True)

    with duckdb.connect(str(analytics_dir / "fly_o_myte_analytics.duckdb")) as conn:
        conn.execute("INSTALL sqlite; LOAD sqlite;")

        conn.execute(f"""
            COPY (
                SELECT
                    ps.trip_id,
                    ps.fetched_at::TIMESTAMP AS fetched_at,
                    t.origin,
                    t.destination,
                    ps.airline_code,
                    ps.base_fare_per_adult,
                    ps.true_family_cost,
                    ps.price_level_signal,
                    ps.stops,
                    ps.family_score,
                    date_part('month', t.depart_date::DATE) AS departure_month
                FROM sqlite_scan('{sqlite_db_path}', 'price_snapshot') ps
                JOIN sqlite_scan('{sqlite_db_path}', 'trip') t ON t.id = ps.trip_id
            )
            TO '{snapshots_dir}/all_snapshots.parquet'
            (FORMAT PARQUET)
        """)

        # Get all unique routes
        routes = conn.execute(f"""
            SELECT DISTINCT origin, destination
            FROM read_parquet('{snapshots_dir}/all_snapshots.parquet')
        """).fetchall()

        for origin, destination in routes:
            _recompute_route_stats(
                conn, snapshots_dir, route_stats_dir, origin, destination
            )

    logger.info("Full analytics rebuild complete")
