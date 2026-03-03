"""
DuckDB connection helpers — OLAP analytics layer (Phase 2).

Separate from SQLite: DuckDB is read-heavy (analytics queries over Parquet);
SQLite is write-heavy (transactional snapshots and recommendations).

Key constraint: DuckDB allows only ONE writer across all processes.
Never write to DuckDB from concurrent CLI processes (cron + manual).
All writes go through SQLite first; DuckDB reads via sqlite_scan extension.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


@contextmanager
def get_analytics_connection(analytics_dir: Path) -> Generator:
    """
    Open a DuckDB connection to the analytics database.
    Yields the connection; closes it on exit.

    Usage:
        with get_analytics_connection(settings.analytics_dir) as conn:
            rows = conn.execute("SELECT ...").fetchall()
    """
    try:
        import duckdb
    except ImportError:
        raise ImportError(
            "duckdb is required for analytics. Install with: uv add duckdb"
        ) from None

    db_path = analytics_dir / "fly_o_myte_analytics.duckdb"
    analytics_dir.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(db_path))
    try:
        # Load sqlite extension for hybrid SQLite+Parquet queries
        conn.execute("INSTALL sqlite; LOAD sqlite;")
        yield conn
    finally:
        conn.close()


def query_route_stats(
    analytics_dir: Path,
    origin: str,
    destination: str,
) -> list[dict]:
    """
    Return aggregated route stats for an origin/destination pair.
    Returns empty list if no Parquet data exists yet.
    """
    route_stats_dir = analytics_dir / "route_stats"
    stat_file = route_stats_dir / f"route_{origin}_{destination}.parquet"

    if not stat_file.exists():
        return []

    with get_analytics_connection(analytics_dir) as conn:
        rows = conn.execute(f"""
            SELECT *
            FROM read_parquet('{stat_file}')
            ORDER BY week_start DESC
        """).fetchall()

        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, row, strict=True)) for row in rows]


def query_price_percentiles(
    analytics_dir: Path,
    origin: str,
    destination: str,
    sqlite_db_path: Path,
) -> dict | None:
    """
    Compute price percentiles for a route using both SQLite and Parquet data.
    Returns dict with p25, median, p75, avg, min, max, sample_count.
    Returns None if insufficient data.
    """
    with get_analytics_connection(analytics_dir) as conn:
        snapshots_dir = analytics_dir / "snapshots"
        if not snapshots_dir.exists() or not list(snapshots_dir.glob("*.parquet")):
            # Fall back to SQLite only
            try:
                row = conn.execute(f"""
                    SELECT
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY ps.true_family_cost) AS p25,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY ps.true_family_cost) AS median,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY ps.true_family_cost) AS p75,
                        AVG(ps.true_family_cost) AS avg_cost,
                        MIN(ps.true_family_cost) AS min_cost,
                        MAX(ps.true_family_cost) AS max_cost,
                        COUNT(*) AS sample_count
                    FROM sqlite_scan('{sqlite_db_path}', 'price_snapshot') ps
                    JOIN sqlite_scan('{sqlite_db_path}', 'trip') t ON t.id = ps.trip_id
                    WHERE t.origin = '{origin}' AND t.destination = '{destination}'
                """).fetchone()
            except Exception as exc:
                logger.warning("Percentile query failed: %s", exc)
                return None
        else:
            parquet_glob = str(snapshots_dir / "*.parquet")
            try:
                row = conn.execute(f"""
                    SELECT
                        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY true_family_cost) AS p25,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY true_family_cost) AS median,
                        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY true_family_cost) AS p75,
                        AVG(true_family_cost) AS avg_cost,
                        MIN(true_family_cost) AS min_cost,
                        MAX(true_family_cost) AS max_cost,
                        COUNT(*) AS sample_count
                    FROM read_parquet('{parquet_glob}')
                    WHERE origin = '{origin}' AND destination = '{destination}'
                """).fetchone()
            except Exception as exc:
                logger.warning("Parquet percentile query failed: %s", exc)
                return None

        if not row or row[-1] == 0:
            return None

        return {
            "p25": round(row[0], 2),
            "median": round(row[1], 2),
            "p75": round(row[2], 2),
            "avg": round(row[3], 2),
            "min": round(row[4], 2),
            "max": round(row[5], 2),
            "sample_count": row[6],
        }
