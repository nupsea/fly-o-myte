"""
Poll cycle orchestration — the core of `travo poll` and `travo refresh`.

Coordinates:
  1. Fetching prices from the active plugin (Tequila / Amadeus)
  2. Computing true family cost
  3. Saving the snapshot to SQLite
  4. Running the recommendation engine
  5. Sending email alerts for book_now decisions
  6. (Phase 2) Triggering incremental analytics update

No business logic lives here — this module wires together the other modules.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

import pluggy

from fly_o_myte.calendar import get_calendar
from fly_o_myte.config import FamilyProfile, get_settings
from fly_o_myte.db.sqlite import (
    PriceSnapshot,
    Recommendation,
    Session,
    Trip,
    get_snapshots_for_trip,
    insert_recommendation,
    insert_snapshot,
    list_active_trips,
    mark_email_sent,
)
from fly_o_myte.fees import get_airline_db
from fly_o_myte.notifier import send_book_now_alert
from fly_o_myte.price_sources.amadeus import AmadeusPriceSource
from fly_o_myte.price_sources.hookspecs import (
    FlightOffer,
    build_plugin_manager,
)
from fly_o_myte.price_sources.tequila import TequilaPriceSource
from fly_o_myte.recommender import SnapshotPoint, compute
from fly_o_myte.true_cost import compute_family_score, compute_true_cost

logger = logging.getLogger(__name__)


def build_plugin_manager_from_settings() -> pluggy.PluginManager:
    """Instantiate and register price source plugins based on available credentials."""
    settings = get_settings()
    pm = build_plugin_manager()

    if settings.tequila_api_key:
        pm.register(TequilaPriceSource(api_key=settings.tequila_api_key))
        logger.debug("Registered Tequila price source")
    else:
        logger.warning("TEQUILA_API_KEY not set — no price source available")

    if settings.amadeus_client_id and settings.amadeus_client_secret:
        pm.register(
            AmadeusPriceSource(
                client_id=settings.amadeus_client_id,
                client_secret=settings.amadeus_client_secret,
                hostname=settings.amadeus_hostname,
            )
        )
        logger.debug("Registered Amadeus price source")

    return pm


def poll_trip(
    session: Session,
    trip: Trip,
    profile: FamilyProfile,
    pm: pluggy.PluginManager,
    send_alerts: bool = True,
) -> PriceSnapshot | None:
    """
    Fetch the latest price for a trip, save a snapshot, and compute a recommendation.

    Returns the saved snapshot on success, or None if the fetch failed.
    """
    depart = date.fromisoformat(trip.depart_date)
    ret = date.fromisoformat(trip.return_date) if trip.return_date else None
    child_ages = profile.child_ages_at(depart)

    # ─── 1. Fetch price ────────────────────────────────────────────────────
    offer = _fetch_best_offer(
        pm=pm,
        origin=trip.origin,
        destination=trip.destination,
        depart_date=depart,
        return_date=ret,
        adults=trip.adults,
        children_ages=child_ages,
        max_stops=trip.max_stops,
    )
    if offer is None:
        logger.warning("No offers found for trip %s (%s)", trip.id, trip.label)
        return None

    # ─── 2. Compute true family cost ───────────────────────────────────────
    airline_db = get_airline_db()
    airline = airline_db.get_or_default(offer.airline_code)
    breakdown = compute_true_cost(
        airline=airline,
        base_fare_per_adult=offer.base_fare_per_adult,
        adults=trip.adults,
        child_ages=child_ages,
        bags_per_person=trip.bags_per_person,
        depart_date=depart,
        return_date=ret,
    )

    # ─── 3. Compute family score ───────────────────────────────────────────
    dep_hour = _parse_hour(offer.departure_time)
    avg_cost = breakdown.total  # first snapshot — no history yet for avg
    family_score = compute_family_score(
        airline=airline,
        true_cost=breakdown.total,
        avg_cost_on_route=avg_cost,
        stops=offer.stops,
        departure_hour=dep_hour,
        preferred_earliest=profile.preferred_departure_window.earliest_hour,
        preferred_latest=profile.preferred_departure_window.latest_hour,
    )

    # ─── 4. Save snapshot ──────────────────────────────────────────────────
    assert trip.id is not None  # guaranteed for persisted trips
    snapshot = insert_snapshot(
        session,
        PriceSnapshot(
            trip_id=trip.id,
            source=offer.source,
            airline_code=offer.airline_code,
            flight_number=offer.flight_number,
            base_fare_per_adult=offer.base_fare_per_adult,
            true_family_cost=breakdown.total,
            true_cost_breakdown=json.dumps(breakdown.as_dict()),
            price_level_signal=offer.price_level_signal,
            stops=offer.stops,
            departure_time=offer.departure_time,
            duration_minutes=offer.duration_minutes,
            family_score=family_score,
            offer_raw=json.dumps(offer.offer_raw),
        ),
    )

    # ─── 5. Build recommendation ───────────────────────────────────────────
    snapshots = get_snapshots_for_trip(session, trip.id)
    snap_points = [
        SnapshotPoint(
            fetched_at=datetime.fromisoformat(s.fetched_at),
            true_family_cost=s.true_family_cost,
        )
        for s in snapshots
    ]

    days_to_departure = (depart - date.today()).days

    # School holiday context
    cal = get_calendar()
    holiday_ctx = cal.check_overlap(profile.state, depart, ret)

    result = compute(
        snapshots=snap_points,
        current_true_cost=breakdown.total,
        days_to_departure=max(0, days_to_departure),
        price_level_signal=offer.price_level_signal,
        school_holiday_context=holiday_ctx,
    )

    rec = insert_recommendation(
        session,
        Recommendation(
            trip_id=trip.id,
            decision=result.decision,
            confidence=result.confidence,
            regret_risk=result.regret_risk,
            regret_book_aud=result.regret_book_aud,
            regret_wait_aud=result.regret_wait_aud,
            true_family_cost=breakdown.total,
            rolling_avg_cost=result.rolling_avg_cost,
            trend_slope=result.trend_slope,
            days_to_departure=days_to_departure,
            price_level_signal=offer.price_level_signal,
            school_holiday_flag=holiday_ctx.label if holiday_ctx else None,
            rationale=result.rationale,
        ),
    )

    logger.info(
        "Trip %s — %s: $%,.0f — %s (%.0f%% confident)",
        trip.id,
        trip.label,
        breakdown.total,
        result.decision.upper(),
        result.confidence * 100,
    )

    # ─── 6. Send alerts ────────────────────────────────────────────────────
    if send_alerts and result.decision == "book_now":
        sent = send_book_now_alert(trip, rec)
        if sent:
            assert rec.id is not None  # guaranteed after insert
            mark_email_sent(session, rec.id)

    return snapshot


def poll_all_active(
    session: Session,
    profile: FamilyProfile,
    pm: pluggy.PluginManager,
    send_alerts: bool = True,
) -> dict[int, str]:
    """
    Poll all active trips.

    Returns dict of {trip_id: "ok" | "no_offers" | "error"}.
    Never raises — errors are caught and returned as status strings.
    """
    trips = list_active_trips(session)
    results: dict[int, str] = {}

    for trip in trips:
        assert trip.id is not None  # guaranteed for persisted trips
        try:
            snap = poll_trip(session, trip, profile, pm, send_alerts=send_alerts)
            results[trip.id] = "ok" if snap else "no_offers"
        except Exception as exc:
            logger.error("Error polling trip %s: %s", trip.id, exc, exc_info=True)
            results[trip.id] = "error"

    return results


# ─── Private helpers ───────────────────────────────────────────────────────────


def _fetch_best_offer(
    pm: pluggy.PluginManager,
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date | None,
    adults: int,
    children_ages: list[int],
    max_stops: int,
) -> FlightOffer | None:
    """
    Call all registered price sources in order and return the cheapest offer found.
    """
    all_offers: list[FlightOffer] = []

    results: list[list[FlightOffer]] = pm.hook.search_flights(
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        return_date=return_date,
        adults=adults,
        children_ages=children_ages,
        max_stops=max_stops,
        currency="AUD",
    )

    for offer_list in results:
        all_offers.extend(offer_list)

    if not all_offers:
        return None

    # Return the offer with the lowest base fare per adult
    # (True cost ranking happens after fee calculation in the caller)
    return min(all_offers, key=lambda o: o.base_fare_per_adult)


def _parse_hour(departure_time: str) -> int:
    """Parse 'HH:MM' → hour integer. Returns 12 on parse failure."""
    try:
        return int(departure_time.split(":")[0])
    except (ValueError, IndexError):
        return 12
