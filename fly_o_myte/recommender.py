"""
Booking recommendation engine — pure functions, no I/O.

All inputs are passed explicitly. No DB reads, no network calls, no side effects.
This makes the engine fully testable without any mocking.

Decision output: book_now | wait | monitor
Supporting outputs: confidence (0–1), regret_risk (low|medium|high), rationale
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fly_o_myte.calendar import HolidayContext

Decision = Literal["book_now", "wait", "monitor"]
RegretRisk = Literal["low", "medium", "high"]
PriceSignal = Literal["LOW", "TYPICAL", "HIGH"]


class RouteType(enum.Enum):
    DOMESTIC = "domestic"
    TRANS_TASMAN = "trans_tasman"
    ASIA_PACIFIC = "asia_pacific"
    LONG_HAUL = "long_haul"


# (min_days, optimal_days, max_days) per route type
BOOKING_WINDOWS: dict[RouteType, tuple[int, int, int]] = {
    RouteType.DOMESTIC: (14, 60, 180),
    RouteType.TRANS_TASMAN: (30, 90, 270),
    RouteType.ASIA_PACIFIC: (45, 120, 300),
    RouteType.LONG_HAUL: (60, 180, 365),
}

_AU_AIRPORTS: frozenset[str] = frozenset(
    {
        "SYD",
        "MEL",
        "BNE",
        "PER",
        "ADL",
        "CBR",
        "HBA",
        "DRW",
        "CNS",
        "OOL",
        "MCY",
        "AVV",
        "TSV",
        "MKY",
        "ROK",
        "HTI",
        "BHQ",
        "NTL",
        "LST",
        "PPP",
        "KGI",
        "DBO",
        "WGA",
        "MQL",
        "BME",
        "KTA",
        "ASP",
        "ARM",
        "MEB",
        "ABX",
        "EMD",
        "MIM",
        "CFS",
        "GLT",
    }
)

_NZ_AIRPORTS: frozenset[str] = frozenset({"AKL", "CHC", "WLG", "ZQN", "DUD"})

_ASIA_PACIFIC_AIRPORTS: frozenset[str] = frozenset(
    {
        # Japan
        "NRT",
        "HND",
        "KIX",
        "NGO",
        "FUK",
        # Thailand
        "BKK",
        "DMK",
        "HKT",
        "CNX",
        # Singapore
        "SIN",
        # Malaysia
        "KUL",
        "PEN",
        # Indonesia
        "CGK",
        "DPS",
        # Hong Kong
        "HKG",
        # South Korea
        "ICN",
        "GMP",
        # China
        "PEK",
        "PKX",
        "PVG",
        "CAN",
        "SHA",
        # Philippines
        "MNL",
        "CEB",
        # Vietnam
        "SGN",
        "HAN",
        # India
        "DEL",
        "BOM",
        "MAA",
        "BLR",
        "CCU",
    }
)


def classify_route(origin: str, destination: str) -> RouteType:
    """
    Classify a route by type based on airport IATA codes.

    Assumes origin is typically an AU airport for inter-regional routes.
    Falls through to LONG_HAUL for any unrecognised destination.
    """
    dest = destination.upper()
    if dest in _AU_AIRPORTS:
        return RouteType.DOMESTIC
    if dest in _NZ_AIRPORTS:
        return RouteType.TRANS_TASMAN
    if dest in _ASIA_PACIFIC_AIRPORTS:
        return RouteType.ASIA_PACIFIC
    return RouteType.LONG_HAUL


@dataclass(frozen=True)
class SnapshotPoint:
    """Minimal snapshot data needed by the recommender."""

    fetched_at: datetime
    true_family_cost: float


@dataclass(frozen=True)
class RecommendationResult:
    decision: Decision
    confidence: float  # 0.0–1.0 after data richness adjustment
    regret_risk: RegretRisk
    regret_book_aud: float  # expected family regret (AUD) if book now
    regret_wait_aud: float  # expected family regret (AUD) if wait
    rolling_avg_cost: float
    trend_slope: float  # AUD/day — negative = prices falling
    rationale: str


# ─── Campaign-aware snapshot aggregation ──────────────────────────────────────


def build_campaign_snapshots(
    all_snapshots: list,  # list[PriceSnapshot] from all campaign variants
    current_variant_id: int | None,
    decay_factor: float = 0.7,
) -> list[SnapshotPoint]:
    """Build a recency-weighted snapshot list from all variants in a campaign.

    Snapshots from the current active variant get full weight (1.0).
    Snapshots from archived variants get exponentially decaying weight,
    modelling their costs as less representative of current market conditions
    but still informative for trend analysis.

    The output is a unified list suitable for the standard compute() function.
    Cost values from older variants are soft-blended toward the campaign average
    to reduce noise from potentially different date-windows.

    Args:
        all_snapshots: PriceSnapshot objects from all variants in the campaign.
        current_variant_id: Trip ID of the current active variant.
        decay_factor: Weight decay per variant generation (0.7 = 30% discount per gen).
    """
    if not all_snapshots:
        return []

    # Group snapshots by variant (trip_id), keeping only rank-1
    from collections import defaultdict

    by_variant: dict[int, list] = defaultdict(list)
    for s in all_snapshots:
        if s.rank == 1:
            by_variant[s.trip_id].append(s)

    if not by_variant:
        return []

    # Sort variants by their newest snapshot (most recent variant first)
    def _newest_ts(snaps: list) -> str:
        return max(s.fetched_at for s in snaps)

    sorted_variants = sorted(by_variant.items(), key=lambda x: _newest_ts(x[1]), reverse=True)

    # Compute campaign-wide average cost for blending
    all_costs = [s.true_family_cost for snaps in by_variant.values() for s in snaps]
    campaign_avg = sum(all_costs) / len(all_costs) if all_costs else 0.0

    result: list[SnapshotPoint] = []
    for gen_index, (variant_id, snaps) in enumerate(sorted_variants):
        is_current = variant_id == current_variant_id
        weight = 1.0 if is_current else decay_factor ** (gen_index)

        for s in snaps:
            # Blend older variant costs toward campaign average
            blended_cost = (
                s.true_family_cost
                if is_current
                else s.true_family_cost * weight + campaign_avg * (1.0 - weight)
            )
            result.append(
                SnapshotPoint(
                    fetched_at=datetime.fromisoformat(s.fetched_at),
                    true_family_cost=blended_cost,
                )
            )

    # Sort by time for correct trend calculation
    result.sort(key=lambda sp: sp.fetched_at)
    return result


# ─── Core computation ─────────────────────────────────────────────────────────


def compute(
    snapshots: list[SnapshotPoint],
    current_true_cost: float,
    days_to_departure: int,
    price_level_signal: str | None,
    school_holiday_context: HolidayContext | None = None,
    lookback_days: int = 30,
    route_type: RouteType | None = None,
) -> RecommendationResult:
    """
    Compute booking recommendation from price history and context signals.

    Args:
        snapshots: Price history, ordered oldest → newest.
        current_true_cost: True family cost from the most recent snapshot.
        days_to_departure: Calendar days from today to departure.
        price_level_signal: "LOW" | "TYPICAL" | "HIGH" from Tequila/Amadeus.
        school_holiday_context: If the trip dates overlap a school holiday.
        lookback_days: History window for rolling average.
        route_type: Route classification for booking-window-aware decisions.

    Returns:
        RecommendationResult with decision, confidence, regret risk, rationale.
    """
    grouped_snaps = _group_by_day(snapshots)
    n = len(grouped_snaps)

    if n < 3:
        return RecommendationResult(
            decision="monitor",
            confidence=_adjust_confidence(0.35, n),
            regret_risk="medium",
            regret_book_aud=0.0,
            regret_wait_aud=0.0,
            rolling_avg_cost=current_true_cost,
            trend_slope=0.0,
            rationale=(
                f"Only {n} price point{'s' if n != 1 else ''} collected. "
                f"Building history — check back in {max(1, 3 - n)} more day{'s' if 3 - n != 1 else ''}."
            ),
        )

    costs = [s.true_family_cost for s in grouped_snaps]
    avg = rolling_average(costs)
    slope = trend_slope(grouped_snaps)
    deviation_pct = price_deviation_pct(current_true_cost, avg)
    signal = (price_level_signal or "TYPICAL").upper()
    is_holiday = school_holiday_context is not None
    has_flexibility = not (
        school_holiday_context and school_holiday_context.is_fully_within
    )

    # ─ Decision matrix (evaluated top to bottom, first match wins) ─────────
    decision: Decision
    base_confidence: float

    if days_to_departure <= 7:
        decision, base_confidence = "book_now", 0.92

    elif signal == "LOW" and slope > 0:
        decision, base_confidence = "book_now", 0.90

    elif (
        route_type is not None
        and signal == "LOW"
        and days_to_departure <= BOOKING_WINDOWS[route_type][1]
    ):
        # Route-type-aware: LOW signal within the optimal booking window → book now
        decision, base_confidence = "book_now", 0.85

    elif signal == "LOW" and days_to_departure <= 45:
        decision, base_confidence = "book_now", 0.85

    elif deviation_pct <= -15 and slope > 0:
        decision, base_confidence = "book_now", 0.83

    elif signal == "LOW" and days_to_departure > 45:
        # Prices are low but there's time — may still improve
        decision, base_confidence = "monitor", 0.65

    elif signal == "HIGH" and slope < 0 and days_to_departure > 21:
        decision, base_confidence = "wait", 0.75

    elif slope < 0 and days_to_departure > 30 and not is_holiday:
        decision, base_confidence = "wait", 0.68

    elif is_holiday and signal != "LOW" and days_to_departure > 60 and has_flexibility:
        # In a holiday window, prices above average, plenty of time — consider waiting
        decision, base_confidence = "wait", 0.62

    elif days_to_departure > 90:
        decision, base_confidence = "monitor", 0.55

    else:
        decision, base_confidence = "monitor", 0.50

    confidence = _adjust_confidence(base_confidence, n)
    price_volatility = _std_dev(costs)
    regret_book, regret_wait = _compute_regret(confidence, slope, price_volatility)
    risk = _classify_regret_risk(regret_book, regret_wait)
    rationale = _build_rationale(
        decision,
        current_true_cost,
        avg,
        deviation_pct,
        slope,
        days_to_departure,
        signal,
        school_holiday_context,
        n,
    )

    return RecommendationResult(
        decision=decision,
        confidence=confidence,
        regret_risk=risk,
        regret_book_aud=round(regret_book, 2),
        regret_wait_aud=round(regret_wait, 2),
        rolling_avg_cost=round(avg, 2),
        trend_slope=round(slope, 2),
        rationale=rationale,
    )


# ─── Supporting calculations ──────────────────────────────────────────────────


def _group_by_day(snapshots: list[SnapshotPoint]) -> list[SnapshotPoint]:
    """Group snapshots by day, keeping the latest price per day to avoid intra-day skew."""
    daily: dict[str, SnapshotPoint] = {}
    for s in snapshots:
        day_key = s.fetched_at.strftime("%Y-%m-%d")
        daily[day_key] = s
    return list(daily.values())


def rolling_average(costs: list[float]) -> float:
    return sum(costs) / len(costs) if costs else 0.0


def trend_slope(snapshots: list[SnapshotPoint]) -> float:
    """
    Linear regression slope: AUD/day.
    Negative = prices falling. Positive = prices rising.
    Uses pure Python stdlib — no numpy required.
    """
    if len(snapshots) < 2:
        return 0.0

    t0 = snapshots[0].fetched_at.timestamp()
    days = [(s.fetched_at.timestamp() - t0) / 86400 for s in snapshots]
    prices = [s.true_family_cost for s in snapshots]
    n = len(days)

    sum_x = sum(days)
    sum_y = sum(prices)
    sum_xx = sum(x * x for x in days)
    sum_xy = sum(x * y for x, y in zip(days, prices, strict=True))

    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-9:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def price_deviation_pct(current: float, average: float) -> float:
    """Percentage deviation from average. Negative = below average (good)."""
    if average == 0:
        return 0.0
    return (current - average) / average * 100


def _std_dev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = sum(values) / len(values)
    variance = sum((v - avg) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _adjust_confidence(base: float, n_snapshots: int) -> float:
    """Scale confidence by data richness. Saturates at 10+ snapshots."""
    data_factor = min(n_snapshots / 10, 1.0)
    return round(base * (0.5 + 0.5 * data_factor), 3)


def _compute_regret(
    confidence: float, slope: float, price_volatility: float
) -> tuple[float, float]:
    """
    Estimate expected regret (AUD) for each decision.
    Based on Random Regret Minimisation model.
    """
    if slope > 0:
        p_rise = confidence
        p_drop = 1.0 - confidence
    else:
        p_drop = confidence
        p_rise = 1.0 - confidence

    regret_book = p_drop * price_volatility * 1.5
    regret_wait = p_rise * price_volatility * 1.5

    return regret_book, regret_wait


def _classify_regret_risk(regret_book: float, regret_wait: float) -> RegretRisk:
    if regret_book < regret_wait * 0.5:
        return "low"
    if regret_wait < regret_book * 0.5:
        return "high"
    return "medium"


def _build_rationale(
    decision: Decision,
    current: float,
    avg: float,
    deviation_pct: float,
    slope: float,
    days: int,
    signal: str,
    holiday: HolidayContext | None,
    n_snapshots: int,
) -> str:
    parts: list[str] = []

    dev_sign = "below" if deviation_pct < 0 else "above"
    dev_abs = abs(round(deviation_pct, 1))
    parts.append(
        f"Price ${current:,.0f} is {dev_abs}% {dev_sign} the {n_snapshots}-snapshot average of ${avg:,.0f}."
    )

    if slope != 0:
        direction = "rising" if slope > 0 else "falling"
        parts.append(f"Trend: {direction} at ${abs(slope):.1f}/day.")

    if signal in ("LOW", "HIGH"):
        signal_desc = (
            "below market average" if signal == "LOW" else "above market average"
        )
        parts.append(f"Market signal: {signal} ({signal_desc}).")

    if holiday:
        parts.append(
            f"School holiday overlap: {holiday.label} ({holiday.overlap_days} days). "
            + (
                "Dates are fixed — holiday pricing rarely improves."
                if holiday.is_fully_within
                else "Consider shifting dates by 1–2 days to avoid peak pricing."
            )
        )

    if days <= 14:
        parts.append(f"Only {days} days to departure — time pressure is high.")
    elif days > 90:
        parts.append(f"{days} days to departure — still early in the booking window.")

    action_map = {
        "book_now": "Book this week.",
        "wait": f"Wait {min(14, days // 3)} more days and check again.",
        "monitor": "Continue monitoring — no strong signal yet.",
    }
    parts.append(action_map[decision])

    return " ".join(parts)
