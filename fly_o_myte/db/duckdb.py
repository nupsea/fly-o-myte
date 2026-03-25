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
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RouteContext:
    """Price percentile context for an origin/destination route."""

    p25: float
    p50: float
    p75: float
    min_price: float
    max_price: float
    sample_count: int
    school_holiday_premium_pct: float | None
    weekly_trends: list[dict]  # [{week, avg_cost, min_cost}]
    airline_breakdown: list[dict]  # [{airline, avg_cost, sample_count}]


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
                    FROM sqlite_scan('{sqlite_db_path}', 'pricesnapshot') ps
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


def query_route_context(
    analytics_dir: Path,
    origin: str,
    destination: str,
) -> RouteContext | None:
    """
    Return price percentile context for an origin/destination route.

    Queries snapshot Parquet files for percentiles and route_stats for
    school holiday premium. Returns None when insufficient data exists.
    """
    route_stats_dir = analytics_dir / "route_stats"
    stat_file = route_stats_dir / f"route_{origin}_{destination}.parquet"

    if not stat_file.exists():
        return None

    snapshots_dir = analytics_dir / "snapshots"
    parquet_files = list(snapshots_dir.glob("*.parquet"))
    if not parquet_files:
        return None

    try:
        import duckdb
    except ImportError:
        return None

    parquet_glob = str(snapshots_dir / "*.parquet")

    try:
        with duckdb.connect() as conn:
            row = conn.execute(f"""
                SELECT
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY true_family_cost) AS p25,
                    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY true_family_cost) AS p50,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY true_family_cost) AS p75,
                    MIN(true_family_cost) AS min_price,
                    MAX(true_family_cost) AS max_price,
                    COUNT(*) AS sample_count
                FROM read_parquet('{parquet_glob}')
                WHERE origin = '{origin}' AND destination = '{destination}'
            """).fetchone()

            if not row or row[5] < 5:
                return None

            holiday_row = conn.execute(f"""
                SELECT
                    AVG(CASE WHEN school_holiday_week THEN avg_cost END) AS holiday_avg,
                    AVG(CASE WHEN NOT school_holiday_week THEN avg_cost END) AS non_holiday_avg
                FROM read_parquet('{stat_file}')
            """).fetchone()

            premium_pct = None
            if (
                holiday_row
                and holiday_row[0] is not None
                and holiday_row[1] is not None
                and holiday_row[1] > 0
            ):
                premium_pct = round(
                    (holiday_row[0] - holiday_row[1]) / holiday_row[1] * 100, 1
                )

            # Weekly Trends
            weekly_rows = conn.execute(f"""
                SELECT
                    week_start::VARCHAR AS week,
                    AVG(avg_cost) AS avg_cost,
                    MIN(min_cost) AS min_cost
                FROM read_parquet('{stat_file}')
                GROUP BY week_start
                ORDER BY week_start ASC
            """).fetchall()
            weekly_trends = [
                {"week": r[0], "avg": round(r[1], 2), "min": round(r[2], 2)}
                for r in weekly_rows
            ]

            # Airline Breakdown
            airline_rows = conn.execute(f"""
                SELECT
                    airline_code,
                    AVG(avg_cost) AS avg_cost,
                    COUNT(*) AS sample_count
                FROM read_parquet('{stat_file}')
                GROUP BY airline_code
                ORDER BY avg_cost ASC
            """).fetchall()
            airline_breakdown = [
                {"airline": r[0], "avg": round(r[1], 2), "count": r[2]}
                for r in airline_rows
            ]

            return RouteContext(
                p25=round(row[0], 2),
                p50=round(row[1], 2),
                p75=round(row[2], 2),
                min_price=round(row[3], 2),
                max_price=round(row[4], 2),
                sample_count=row[5],
                school_holiday_premium_pct=premium_pct,
                weekly_trends=weekly_trends,
                airline_breakdown=airline_breakdown,
            )
    except Exception as exc:
        logger.warning("query_route_context failed: %s", exc)
        return None
