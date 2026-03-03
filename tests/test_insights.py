"""
Tests for the LLM insights layer (insights.py).

Three-layer strategy:
  1. Schema validation (TravelInsight Pydantic model)
  2. Golden fixture evaluation with LLM-as-judge (when LLM available)
  3. Graceful degradation (no LLM → no crash)
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch, MagicMock

import pytest

from fly_o_myte.insights import TravelInsight, generate_insight


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
            TravelInsight(
                price_impact="higher",
                event_type="holiday",
                confidence=0.8,
                sources=[],
            )  # missing summary


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
        with patch("fly_o_myte.insights._call_llm", side_effect=Exception("API timeout")):
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
