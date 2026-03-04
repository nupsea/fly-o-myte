"""
Unit tests for fly_o_myte/airports.py -- resolve_destination() function.
"""

from __future__ import annotations

import pytest

from fly_o_myte.airports import resolve_destination


class TestResolveDestination:
    def test_sri_lanka_returns_exactly_cmb(self):
        """'sri lanka' should return exactly one result: CMB."""
        results = resolve_destination("sri lanka")
        assert len(results) == 1
        assert results[0][0] == "CMB"
        assert "Sri Lanka" in results[0][1]

    def test_japan_returns_four_airports(self):
        """'japan' should match NRT, HND, KIX, FUK (and possibly more)."""
        results = resolve_destination("japan")
        codes = [r[0] for r in results]
        assert "NRT" in codes
        assert "HND" in codes
        assert "KIX" in codes
        assert "FUK" in codes
        assert len(results) >= 4

    def test_unknown_query_returns_empty(self):
        """Gibberish query returns empty list."""
        results = resolve_destination("zzzzzz")
        assert results == []

    def test_empty_query_returns_empty(self):
        results = resolve_destination("")
        assert results == []

    def test_case_insensitive_match(self):
        """Matching is case-insensitive."""
        lower = resolve_destination("singapore")
        upper = resolve_destination("SINGAPORE")
        mixed = resolve_destination("Singapore")
        assert lower == upper == mixed
        assert len(lower) >= 1
        assert lower[0][0] == "SIN"

    def test_partial_match(self):
        """Partial city name matches the airport."""
        results = resolve_destination("dubai")
        codes = [r[0] for r in results]
        assert "DXB" in codes

    def test_iata_code_direct_lookup(self):
        """Direct IATA code lookup works."""
        results = resolve_destination("CMB")
        assert len(results) >= 1
        assert results[0][0] == "CMB"

    def test_results_sorted_alphabetically_by_iata(self):
        """Results should be sorted alphabetically by IATA code."""
        japan_results = resolve_destination("japan")
        codes = [r[0] for r in japan_results]
        assert codes == sorted(codes)

    def test_no_au_domestic_airports(self):
        """AU domestic airports are NOT in this resolver."""
        # BNE, SYD, MEL, ADL, PER, CBR are domestic and excluded
        for code in ("BNE", "SYD", "MEL", "ADL", "PER", "CBR"):
            results = resolve_destination(code)
            assert all(r[0] != code for r in results), f"{code} should not appear"

    def test_new_zealand_returns_multiple_airports(self):
        """'new zealand' returns AKL, WLG, CHC, ZQN."""
        results = resolve_destination("new zealand")
        codes = [r[0] for r in results]
        assert "AKL" in codes
        assert "WLG" in codes
        assert "CHC" in codes

    def test_bali_matches_dps(self):
        """'bali' resolves to DPS."""
        results = resolve_destination("bali")
        codes = [r[0] for r in results]
        assert "DPS" in codes

    def test_london_returns_multiple_airports(self):
        """'london' matches both LHR and LGW."""
        results = resolve_destination("london")
        codes = [r[0] for r in results]
        assert "LHR" in codes
        assert "LGW" in codes

    @pytest.mark.parametrize(
        "query,expected_iata",
        [
            ("bangkok", "BKK"),
            ("phuket", "HKT"),
            ("singapore", "SIN"),
            ("hong kong", "HKG"),
            ("doha", "DOH"),
            ("paris", "CDG"),
            ("rome", "FCO"),
            ("barcelona", "BCN"),
            ("kuala lumpur", "KUL"),
            ("manila", "MNL"),
            ("ho chi minh", "SGN"),
            ("hanoi", "HAN"),
        ],
    )
    def test_key_destinations(self, query: str, expected_iata: str):
        """Key international destinations resolve to expected IATA codes."""
        results = resolve_destination(query)
        codes = [r[0] for r in results]
        assert expected_iata in codes, f"Expected {expected_iata} for query '{query}'"
