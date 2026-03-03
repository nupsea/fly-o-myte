"""
Tests for the analytics layer (analytics.py / db/duckdb.py).

Phase 2 — tests are skipped if DuckDB is not installed.
"""

from __future__ import annotations

import pytest

duckdb = pytest.importorskip(
    "duckdb", reason="DuckDB not installed — skipping analytics tests"
)


class TestAnalytics:
    """Placeholder for Phase 2 analytics tests."""

    def test_placeholder(self):
        """Analytics tests are implemented in Phase 2."""
        pass
