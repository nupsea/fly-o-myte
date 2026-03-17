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
from concurrent.futures import ThreadPoolExecutor
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
    arrival_time: str
    return_departure_time: str | None
    return_arrival_time: str | None
    duration_minutes: int
    school_holiday: HolidayContext | None
    breakdown: TrueCostBreakdown
    fly_o_myte_legs: dict | None = None
    offer_raw: dict | None = None


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

    tasks = []
    while current <= end_of_month:
        ret = current + timedelta(days=trip_length_days)
        tasks.append((current, ret))
        current += timedelta(days=sample_every_n_days)

    def _scout_task(pair: tuple[date, date]) -> ScoutResult | None:
        return _scout_single(
            pm=pm,
            profile=profile,
            airline_db=airline_db,
            calendar=calendar,
            origin=origin,
            destination=destination,
            depart_date=pair[0],
            return_date=pair[1],
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(_scout_task, tasks):
            if res:
                results.append(res)

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
    Raises PriceSourceError if every attempted date fails with an API error
    (e.g. quota exhausted), so callers can distinguish that from genuine no-results.
    """
    effective_depart_flex = depart_flex if depart_flex is not None else flex_days
    effective_return_flex = return_flex if return_flex is not None else flex_days

    trip_length = (return_date - depart_date).days
    results: list[ScoutResult] = []
    last_error: Exception | None = None

    tasks: list[tuple[date, date]] = []

    if effective_return_flex == 0:
        for d_offset in range(-effective_depart_flex, effective_depart_flex + 1):
            candidate_depart = depart_date + timedelta(days=d_offset)
            if candidate_depart < date.today():
                continue
            if candidate_depart >= return_date:
                continue
            tasks.append((candidate_depart, return_date))
    elif effective_depart_flex == 0:
        for r_offset in range(-effective_return_flex, effective_return_flex + 1):
            candidate_return = return_date + timedelta(days=r_offset)
            if candidate_return <= depart_date:
                continue
            tasks.append((depart_date, candidate_return))
    else:
        for d_offset in range(-effective_depart_flex, effective_depart_flex + 1):
            candidate_depart = depart_date + timedelta(days=d_offset)
            if candidate_depart < date.today():
                continue
            tasks.append(
                (candidate_depart, candidate_depart + timedelta(days=trip_length))
            )

    def _scout_task(pair: tuple[date, date]) -> ScoutResult | None:
        nonlocal last_error
        try:
            return _scout_single(
                pm=pm,
                profile=profile,
                airline_db=airline_db,
                calendar=calendar,
                origin=origin,
                destination=destination,
                depart_date=pair[0],
                return_date=pair[1],
            )
        except PriceSourceError as exc:
            last_error = exc
            logger.warning("Scout fetch failed for %s: %s", pair[0], exc)
            return None

    attempted = len(tasks)
    with ThreadPoolExecutor(max_workers=5) as executor:
        for res in executor.map(_scout_task, tasks):
            if res:
                results.append(res)

    # If every attempted call raised an API error and we have nothing to show,
    # re-raise so the caller can surface the real reason (e.g. quota exhausted).
    if not results and attempted > 0 and last_error is not None:
        raise last_error

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

    # PriceSourceError intentionally not caught here — propagates to scout_flex
    # so it can distinguish quota/network errors from genuine no-results.
    offers: list[list[FlightOffer]] = pm.hook.search_flights(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        return_date=return_date,
        adults=profile.adults,
        children_ages=child_ages,
        max_stops=profile.max_stops,
        currency="AUD",
    )

    all_offers = [o for offer_list in offers for o in offer_list]
    if not all_offers:
        return None

    # Sort all offers by base fare to find the absolute cheapest
    all_offers.sort(key=lambda o: o.base_fare_per_adult)
    cheapest = all_offers[0]

    # Preference Logic: If we have multiple providers, prefer the one that
    # provides return journey details (e.g. Tequila) if its price is within 5%
    # of the absolute cheapest (e.g. SerpAPI which might only have outbound).
    best = cheapest
    if return_date:
        for offer in all_offers:
            # Check if this offer has return details
            if offer.return_departure_time and offer.return_arrival_time:
                # Is it within 5% of the absolute cheapest?
                if offer.base_fare_per_adult <= cheapest.base_fare_per_adult * 1.05:
                    best = offer
                    break

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
        arrival_time=best.arrival_time,
        return_departure_time=best.return_departure_time,
        return_arrival_time=best.return_arrival_time,
        duration_minutes=best.duration_minutes,
        school_holiday=holiday_ctx,
        breakdown=breakdown,
        fly_o_myte_legs=best.fly_o_myte_legs,
        offer_raw=best.offer_raw,
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
