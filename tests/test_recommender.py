"""
Tests for the recommendation engine (recommender.py).

All pure functions — no I/O, no mocking required.
This is the most critical test file in the suite.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fly_o_myte.calendar import HolidayContext
from fly_o_myte.recommender import (
    SnapshotPoint,
    compute,
    price_deviation_pct,
    rolling_average,
    trend_slope,
)
from tests.conftest import make_snapshots

# ─── Helper ───────────────────────────────────────────────────────────────────


def snap(cost: float, days_ago: int = 0) -> SnapshotPoint:
    return SnapshotPoint(
        fetched_at=datetime(2026, 6, 20) - timedelta(days=days_ago),
        true_family_cost=cost,
    )


# ─── Decision matrix tests ────────────────────────────────────────────────────


class TestDecisionMatrix:
    def test_book_now_on_urgency(self):
        """days_to_departure <= 7 always → BOOK NOW."""
        snaps = make_snapshots([1400, 1410, 1395, 1405, 1400])
        result = compute(
            snaps,
            current_true_cost=1400,
            days_to_departure=5,
            price_level_signal="TYPICAL",
        )
        assert result.decision == "book_now"
        assert result.confidence >= 0.45  # 0.92 * data_factor for 5 snaps

    def test_book_now_low_signal_rising_trend(self):
        """LOW signal + rising prices → BOOK NOW (priority 2)."""
        snaps = make_snapshots([1200, 1250, 1310, 1380, 1450])
        result = compute(
            snaps,
            current_true_cost=1450,
            days_to_departure=60,
            price_level_signal="LOW",
        )
        assert result.decision == "book_now"
        assert result.trend_slope > 0

    def test_book_now_low_signal_short_lead(self):
        """LOW signal + days <= 45 → BOOK NOW (priority 3)."""
        snaps = make_snapshots([1300, 1320, 1290, 1280, 1260])
        result = compute(
            snaps,
            current_true_cost=1260,
            days_to_departure=30,
            price_level_signal="LOW",
        )
        assert result.decision == "book_now"

    def test_book_now_below_average_rising(self):
        """Price >= 15% below average + rising → BOOK NOW (priority 4)."""
        # Historical prices around 1600, trending up. Current price is a dip at 18% below avg.
        # Snapshots are purely historical (do not include current) so the rolling avg stays ~1600.
        current = 1312.0  # 18% below 1600
        historical_snaps = make_snapshots(
            [1520, 1560, 1600, 1640, 1680]
        )  # avg=1600, slope=+40/day
        result = compute(
            historical_snaps,
            current_true_cost=current,
            days_to_departure=50,
            price_level_signal="TYPICAL",
        )
        assert result.decision == "book_now"

    def test_monitor_low_signal_long_lead(self):
        """LOW signal + days > 45 → MONITOR (priority 5) — may improve further."""
        snaps = make_snapshots([1350, 1340, 1330, 1320, 1310])
        result = compute(
            snaps,
            current_true_cost=1310,
            days_to_departure=90,
            price_level_signal="LOW",
        )
        assert result.decision == "monitor"

    def test_wait_high_signal_falling(self):
        """HIGH signal + falling + days > 21 → WAIT (priority 6)."""
        snaps = make_snapshots([1700, 1650, 1600, 1560, 1510])
        result = compute(
            snaps,
            current_true_cost=1510,
            days_to_departure=45,
            price_level_signal="HIGH",
        )
        assert result.decision == "wait"

    def test_wait_falling_no_holiday(self):
        """Falling trend + days > 30 + no school holiday → WAIT (priority 7)."""
        snaps = make_snapshots([1600, 1550, 1500, 1450, 1400])
        result = compute(
            snaps,
            current_true_cost=1400,
            days_to_departure=45,
            price_level_signal="TYPICAL",
            school_holiday_context=None,
        )
        assert result.decision == "wait"

    def test_wait_holiday_high_price_flexible(self):
        """School holiday + high price + days > 60 + flexible dates → WAIT (priority 8)."""
        holiday = HolidayContext(
            label="Mid-year holidays", overlap_days=5, is_fully_within=False
        )
        snaps = make_snapshots([1500, 1510, 1520, 1530, 1540])
        result = compute(
            snaps,
            current_true_cost=1540,
            days_to_departure=90,
            price_level_signal="HIGH",
            school_holiday_context=holiday,
        )
        assert result.decision == "wait"

    def test_monitor_long_lead_no_signal(self):
        """days > 90 + no directional trend + no strong signal → MONITOR (priority 9)."""
        # Symmetric values give slope = 0, so rule 7 (slope < 0) does not fire.
        snaps = make_snapshots([1400, 1410, 1420, 1410, 1400])
        result = compute(
            snaps,
            current_true_cost=1400,
            days_to_departure=120,
            price_level_signal="TYPICAL",
        )
        assert result.decision == "monitor"

    def test_monitor_insufficient_data(self):
        """Less than 3 snapshots → always MONITOR with data-richness note."""
        snaps = make_snapshots([1400, 1450])
        result = compute(
            snaps,
            current_true_cost=1450,
            days_to_departure=60,
            price_level_signal="LOW",
        )
        assert result.decision == "monitor"
        assert "2 price point" in result.rationale or "Building" in result.rationale

    def test_monitor_zero_snapshots(self):
        snaps = make_snapshots([])
        result = compute(
            snaps, current_true_cost=1400, days_to_departure=60, price_level_signal=None
        )
        assert result.decision == "monitor"
        assert "0 price point" in result.rationale


# ─── Confidence scaling ───────────────────────────────────────────────────────


class TestConfidenceScaling:
    def test_confidence_scales_with_data(self):
        """More snapshots → higher confidence (up to saturation at 10)."""
        base_costs = [1400.0] * 10
        prev_confidence = 0.0
        for n in [3, 5, 7, 10]:
            snaps = make_snapshots(base_costs[:n])
            result = compute(
                snaps,
                current_true_cost=1400,
                days_to_departure=5,
                price_level_signal="TYPICAL",
            )
            assert result.confidence >= prev_confidence - 0.001  # non-decreasing
            prev_confidence = result.confidence

    def test_confidence_caps_at_base(self):
        """Confidence never exceeds the base_confidence for the decision."""
        snaps = make_snapshots([1400.0] * 20)  # well above 10 snaps
        result = compute(
            snaps,
            current_true_cost=1400,
            days_to_departure=5,
            price_level_signal="TYPICAL",
        )
        assert result.confidence <= 0.92 + 0.001  # book_now base is 0.92


# ─── Regret risk ──────────────────────────────────────────────────────────────


class TestRegretRisk:
    def test_low_regret_on_strong_book_signal(self):
        """Strong book_now signal → low regret risk (booking is clearly right)."""
        snaps = make_snapshots([1200, 1250, 1310, 1380, 1450])
        result = compute(
            snaps, current_true_cost=1450, days_to_departure=6, price_level_signal="LOW"
        )
        assert result.regret_risk in ("low", "medium")

    def test_regret_fields_are_non_negative(self):
        snaps = make_snapshots([1500, 1510, 1490, 1505, 1498])
        result = compute(
            snaps,
            current_true_cost=1498,
            days_to_departure=30,
            price_level_signal="TYPICAL",
        )
        assert result.regret_book_aud >= 0
        assert result.regret_wait_aud >= 0


# ─── Supporting math ──────────────────────────────────────────────────────────


class TestSupportingMath:
    def test_rolling_average_empty(self):
        assert rolling_average([]) == 0.0

    def test_rolling_average_single(self):
        assert rolling_average([1500.0]) == 1500.0

    def test_rolling_average_correct(self):
        assert rolling_average([1000, 2000, 3000]) == pytest.approx(2000.0)

    def test_trend_slope_rising(self):
        """Linear rising prices → positive slope."""
        snaps = make_snapshots([100, 200, 300, 400, 500])
        slope = trend_slope(snaps)
        assert slope > 0

    def test_trend_slope_falling(self):
        snaps = make_snapshots([500, 400, 300, 200, 100])
        slope = trend_slope(snaps)
        assert slope < 0

    def test_trend_slope_flat(self):
        snaps = make_snapshots([1000, 1000, 1000, 1000, 1000])
        assert trend_slope(snaps) == pytest.approx(0.0, abs=0.01)

    def test_trend_slope_single_snapshot(self):
        assert trend_slope(make_snapshots([1400])) == 0.0

    def test_price_deviation_pct_below(self):
        pct = price_deviation_pct(current=850, average=1000)
        assert pct == pytest.approx(-15.0)

    def test_price_deviation_pct_above(self):
        pct = price_deviation_pct(current=1150, average=1000)
        assert pct == pytest.approx(15.0)

    def test_price_deviation_zero_average(self):
        assert price_deviation_pct(current=1000, average=0) == 0.0


# ─── Rationale content ────────────────────────────────────────────────────────


class TestRationale:
    def test_rationale_mentions_price_vs_average(self):
        snaps = make_snapshots([1400, 1410, 1395, 1405, 1400])
        result = compute(
            snaps,
            current_true_cost=1400,
            days_to_departure=30,
            price_level_signal="TYPICAL",
        )
        assert "$" in result.rationale
        assert "average" in result.rationale.lower()

    def test_rationale_mentions_holiday(self):
        holiday = HolidayContext(
            label="Autumn holidays", overlap_days=3, is_fully_within=True
        )
        snaps = make_snapshots([1500, 1510, 1520, 1530, 1540])
        result = compute(
            snaps,
            current_true_cost=1540,
            days_to_departure=30,
            price_level_signal="HIGH",
            school_holiday_context=holiday,
        )
        assert "Autumn" in result.rationale or "holiday" in result.rationale.lower()

    def test_rationale_mentions_trend_direction(self):
        snaps = make_snapshots([1200, 1300, 1400, 1500, 1600])
        result = compute(
            snaps,
            current_true_cost=1600,
            days_to_departure=60,
            price_level_signal="HIGH",
        )
        assert (
            "rising" in result.rationale.lower()
            or "falling" in result.rationale.lower()
        )
