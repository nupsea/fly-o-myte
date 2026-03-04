"""
Date scouting — find the cheapest travel windows across a month.

`fom scout BNE SYD --month jul-2026`

Samples date windows across the requested month and returns true family
costs for each, so the user can pick the best window before committing
to a specific trip.

No data is saved to the database — scouting is read-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pluggy

from fly_o_myte.calendar import HolidayContext, SchoolCalendar
from fly_o_myte.config import FamilyProfile
from fly_o_myte.fees import AirlineDatabase
from fly_o_myte.price_sources.hookspecs import FlightOffer, PriceSourceError
from fly_o_myte.recommender import classify_route
from fly_o_myte.true_cost import TrueCostBreakdown, compute_true_cost

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoutResult:
    """One sampled date window from a scouting run."""

    depart_date: date
    return_date: date
    trip_length_days: int
    true_family_cost: float
    base_fare_per_adult: float
    airline_code: str
    stops: int
    departure_time: str
    duration_minutes: int
    school_holiday: HolidayContext | None
    breakdown: TrueCostBreakdown


def scout_month(
    pm: pluggy.PluginManager,
    profile: FamilyProfile,
    airline_db: AirlineDatabase,
    calendar: SchoolCalendar,
    origin: str,
    destination: str,
    year: int,
    month: int,
    trip_length_days: int = 7,
    sample_every_n_days: int = 7,
) -> list[ScoutResult]:
    """
    Sample date windows across a month and return true family costs.

    Samples departure dates every `sample_every_n_days` days through the month.
    For each departure, the return date is `trip_length_days` later.

    Returns results sorted by true_family_cost ascending.
    """
    results: list[ScoutResult] = []
    current = date(year, month, 1)
    # End of month
    if month == 12:
        end_of_month = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_of_month = date(year, month + 1, 1) - timedelta(days=1)

    while current <= end_of_month:
        ret = current + timedelta(days=trip_length_days)
        result = _scout_single(
            pm=pm,
            profile=profile,
            airline_db=airline_db,
            calendar=calendar,
            origin=origin,
            destination=destination,
            depart_date=current,
            return_date=ret,
        )
        if result:
            results.append(result)
        current += timedelta(days=sample_every_n_days)

    return sorted(results, key=lambda r: r.true_family_cost)


def scout_flex(
    pm: pluggy.PluginManager,
    profile: FamilyProfile,
    airline_db: AirlineDatabase,
    calendar: SchoolCalendar,
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
    flex_days: int = 3,
    depart_flex: int | None = None,
    return_flex: int | None = None,
) -> list[ScoutResult]:
    """
    Scout around a specific date pair.

    Parameters
    ----------
    flex_days:    Symmetric flex for both ends (backward-compat default).
    depart_flex:  Override flex for departure end only.
    return_flex:  Override flex for return end only.

    Modes (depart_flex/return_flex take precedence over flex_days):
      - return_flex == 0: return_date is fixed; depart varies ±depart_flex.
      - depart_flex == 0: depart_date is fixed; return varies ±return_flex.
      - Otherwise: symmetric; return = depart + original trip length.

    Returns all results sorted by true_family_cost.
    """
    effective_depart_flex = depart_flex if depart_flex is not None else flex_days
    effective_return_flex = return_flex if return_flex is not None else flex_days

    trip_length = (return_date - depart_date).days
    results: list[ScoutResult] = []

    if effective_return_flex == 0:
        # Fix return_date; vary depart only
        for d_offset in range(-effective_depart_flex, effective_depart_flex + 1):
            candidate_depart = depart_date + timedelta(days=d_offset)
            if candidate_depart < date.today():
                continue
            if candidate_depart >= return_date:
                continue
            result = _scout_single(
                pm=pm,
                profile=profile,
                airline_db=airline_db,
                calendar=calendar,
                origin=origin,
                destination=destination,
                depart_date=candidate_depart,
                return_date=return_date,
            )
            if result:
                results.append(result)
    elif effective_depart_flex == 0:
        # Fix depart_date; vary return only
        for r_offset in range(-effective_return_flex, effective_return_flex + 1):
            candidate_return = return_date + timedelta(days=r_offset)
            if candidate_return <= depart_date:
                continue
            result = _scout_single(
                pm=pm,
                profile=profile,
                airline_db=airline_db,
                calendar=calendar,
                origin=origin,
                destination=destination,
                depart_date=depart_date,
                return_date=candidate_return,
            )
            if result:
                results.append(result)
    else:
        # Symmetric: shift depart; return = depart + trip_length
        for d_offset in range(-effective_depart_flex, effective_depart_flex + 1):
            candidate_depart = depart_date + timedelta(days=d_offset)
            if candidate_depart < date.today():
                continue
            candidate_return = candidate_depart + timedelta(days=trip_length)
            result = _scout_single(
                pm=pm,
                profile=profile,
                airline_db=airline_db,
                calendar=calendar,
                origin=origin,
                destination=destination,
                depart_date=candidate_depart,
                return_date=candidate_return,
            )
            if result:
                results.append(result)

    return sorted(results, key=lambda r: r.true_family_cost)


def _scout_single(
    pm: pluggy.PluginManager,
    profile: FamilyProfile,
    airline_db: AirlineDatabase,
    calendar: SchoolCalendar,
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
) -> ScoutResult | None:
    """Fetch and price a single date window. Returns None on failure."""
    child_ages = profile.child_ages_at(depart_date)

    offers: list[list[FlightOffer]] = []
    try:
        offers = pm.hook.search_flights(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            return_date=return_date,
            adults=profile.adults,
            children_ages=child_ages,
            max_stops=profile.max_stops,
            currency="AUD",
        )
    except PriceSourceError as exc:
        logger.warning("Scout fetch failed for %s: %s", depart_date, exc)
        return None

    all_offers = [o for offer_list in offers for o in offer_list]
    if not all_offers:
        return None

    best = min(all_offers, key=lambda o: o.base_fare_per_adult)
    bundle = airline_db.get_or_default(best.airline_code)
    route_type = classify_route(origin, destination)

    breakdown = compute_true_cost(
        airline_bundle=bundle,
        base_fare_per_adult=best.base_fare_per_adult,
        adults=profile.adults,
        child_ages=child_ages,
        bags_per_person=profile.bags_per_person,
        depart_date=depart_date,
        return_date=return_date,
        stops=best.stops,
        route_type=route_type,
    )

    holiday_ctx = calendar.check_overlap(profile.state, depart_date, return_date)

    return ScoutResult(
        depart_date=depart_date,
        return_date=return_date,
        trip_length_days=(return_date - depart_date).days,
        true_family_cost=breakdown.total,
        base_fare_per_adult=best.base_fare_per_adult,
        airline_code=best.airline_code,
        stops=best.stops,
        departure_time=best.departure_time,
        duration_minutes=best.duration_minutes,
        school_holiday=holiday_ctx,
        breakdown=breakdown,
    )


def compute_price_variance_ratio(costs: list[float]) -> float:
    """Return std_dev / mean for a list of costs.

    Used to detect high price variance across a flex window and suggest a wider
    flex range to the user. Returns 0.0 if fewer than 2 values or mean is 0.
    """
    if len(costs) < 2:
        return 0.0
    mean = sum(costs) / len(costs)
    if mean <= 0.0:
        return 0.0
    variance = sum((c - mean) ** 2 for c in costs) / (len(costs) - 1)
    return variance**0.5 / mean
