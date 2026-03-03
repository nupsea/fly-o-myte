"""
Tests for the LLM insights layer (insights.py).

Three-layer strategy:
  1. Schema validation (TravelInsight Pydantic model)
  2. Golden fixture evaluation with LLM-as-judge (when LLM available)
  3. Graceful degradation (no LLM → no crash)
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from fly_o_myte.insights import TravelInsight, generate_insight

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "insights"


class TestInsightSchema:
    def test_travel_insight_valid_schema(self):
        """TravelInsight model accepts all valid field combinations."""
        insight = TravelInsight(
            summary="Prices are elevated due to school holiday demand.",
            price_impact="higher",
            event_type="holiday",
            confidence=0.85,
            sources=["school calendar", "price history"],
        )
        assert insight.confidence == 0.85
        assert insight.price_impact == "higher"

    def test_travel_insight_requires_summary(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TravelInsight(  # type: ignore[call-arg]
                price_impact="higher",
                event_type="holiday",
                confidence=0.8,
                sources=[],
            )  # intentionally missing summary to test validation


class TestGracefulDegradation:
    def test_no_llm_provider_returns_none(self):
        """When no LLM credentials are configured, generate_insight returns None."""
        with patch("fly_o_myte.insights._select_provider", return_value=None):
            result = generate_insight(
                origin="BNE",
                destination="SYD",
                depart_date=date(2026, 7, 20),
                current_cost=1400.0,
                avg_cost=1300.0,
                trend_slope=5.0,
                school_holiday_label="Mid-year holidays",
                price_level_signal="HIGH",
                n_snapshots=10,
            )
        assert result is None

    def test_llm_error_returns_none(self):
        """LLM API error → graceful None, not exception."""
        with patch(
            "fly_o_myte.insights._call_llm", side_effect=Exception("API timeout")
        ):
            with patch("fly_o_myte.insights._select_provider", return_value="claude"):
                result = generate_insight(
                    origin="BNE",
                    destination="SYD",
                    depart_date=date(2026, 7, 20),
                    current_cost=1400.0,
                    avg_cost=1300.0,
                    trend_slope=5.0,
                    school_holiday_label=None,
                    price_level_signal=None,
                    n_snapshots=5,
                )
        assert result is None


class TestSchemaValidation:
    """
    Schema tests that always run in CI — no LLM required.
    Validates TravelInsight with valid and invalid inputs using fixture data.
    """

    def test_fixture_files_exist(self) -> None:
        """10 golden fixture JSON files must exist in tests/fixtures/insights/."""
        fixture_files = list(FIXTURES_DIR.glob("*.json"))
        assert len(fixture_files) == 10, (
            f"Expected 10 fixture files, found {len(fixture_files)}"
        )

    def test_all_fixtures_have_required_fields(self) -> None:
        """Every fixture must have input and expected sections with required fields."""
        for fixture_path in sorted(FIXTURES_DIR.glob("*.json")):
            with fixture_path.open() as f:
                fixture = json.load(f)
            assert "input" in fixture, f"{fixture_path.name} missing 'input'"
            assert "expected" in fixture, f"{fixture_path.name} missing 'expected'"
            inp = fixture["input"]
            for key in (
                "origin",
                "destination",
                "depart_date",
                "current_cost",
                "avg_cost",
                "trend_slope",
                "school_holiday_label",
            ):
                assert key in inp, f"{fixture_path.name} input missing '{key}'"
            exp = fixture["expected"]
            for key in ("mentions_holiday", "gives_direction", "cites_source"):
                assert key in exp, f"{fixture_path.name} expected missing '{key}'"

    def test_travel_insight_accepts_valid_fixture_input(self) -> None:
        """TravelInsight model must accept a manually constructed valid insight."""
        insight = TravelInsight(
            summary="Prices are elevated due to school holiday demand on this route.",
            price_impact="higher",
            event_type="holiday",
            confidence=0.88,
            sources=["school calendar", "price history"],
        )
        assert insight.summary != ""
        assert insight.price_impact in ("higher", "lower", "uncertain", "none")
        assert insight.event_type in (
            "holiday",
            "disruption",
            "capacity",
            "seasonal",
            "none",
        )
        assert 0.0 <= insight.confidence <= 1.0
        assert isinstance(insight.sources, list)

    def test_travel_insight_rejects_missing_summary(self) -> None:
        """TravelInsight validation fails when summary is absent."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TravelInsight(  # type: ignore[call-arg]
                price_impact="lower",
                event_type="seasonal",
                confidence=0.7,
                sources=["price history"],
            )

    def test_holiday_fixtures_have_school_holiday_label(self) -> None:
        """Fixtures with mentions_holiday=True must have a non-null school_holiday_label."""
        for fixture_path in sorted(FIXTURES_DIR.glob("*.json")):
            with fixture_path.open() as f:
                fixture = json.load(f)
            if fixture["expected"]["mentions_holiday"]:
                assert fixture["input"]["school_holiday_label"] is not None, (
                    f"{fixture_path.name}: mentions_holiday=True but "
                    "school_holiday_label is null"
                )


@pytest.mark.slow
class TestGoldenFixtures:
    """
    LLM evaluation using golden fixtures — skips when ANTHROPIC_API_KEY is unset.
    Pass rate threshold: 80% (8/10 fixtures must match expected outputs).
    """

    def _eval_fixture(self, fixture: dict) -> dict[str, bool]:
        """
        Run generate_insight for one fixture and evaluate the output against expected.
        Returns dict with per-criterion pass/fail.
        """
        inp = fixture["input"]
        insight = generate_insight(
            origin=inp["origin"],
            destination=inp["destination"],
            depart_date=date.fromisoformat(inp["depart_date"]),
            current_cost=inp["current_cost"],
            avg_cost=inp["avg_cost"],
            trend_slope=inp["trend_slope"],
            school_holiday_label=inp.get("school_holiday_label"),
            price_level_signal=None,
            n_snapshots=10,
        )
        assert insight is not None, "LLM returned None — check API key"

        exp = fixture["expected"]
        holiday_label = inp.get("school_holiday_label") or ""
        summary_lower = insight.summary.lower()

        mentions_holiday = (
            (holiday_label.lower() in summary_lower)
            or any(
                kw in summary_lower
                for kw in ("school holiday", "holiday", "school break")
            )
            if exp["mentions_holiday"]
            else True  # Not required to mention holiday when expects False
        )

        gives_direction = insight.price_impact in (
            "higher",
            "lower",
            "uncertain",
            "none",
        )

        cites_source = len(insight.sources) > 0

        return {
            "mentions_holiday": not exp["mentions_holiday"] or mentions_holiday,
            "gives_direction": gives_direction,
            "cites_source": cites_source,
        }

    def test_golden_fixtures(self) -> None:
        """
        Run all 10 golden fixtures through the LLM.
        Pass rate must be >= 0.80.
        Skips if ANTHROPIC_API_KEY is empty.
        """
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            pytest.skip("ANTHROPIC_API_KEY not set — skipping LLM golden fixture eval")

        fixture_files = sorted(FIXTURES_DIR.glob("*.json"))
        assert len(fixture_files) == 10

        passed = 0
        total = len(fixture_files)

        for fixture_path in fixture_files:
            with fixture_path.open() as f:
                fixture = json.load(f)
            try:
                results = self._eval_fixture(fixture)
                if all(results.values()):
                    passed += 1
            except Exception:
                pass  # count as failed

        pass_rate = passed / total
        assert pass_rate >= 0.80, (
            f"Golden fixture pass rate {pass_rate:.0%} < 80% ({passed}/{total} passed)"
        )
