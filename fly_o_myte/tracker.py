"""
Poll cycle orchestration — the core of `fom poll` and `fom refresh`.

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
from datetime import UTC, date, datetime

import pluggy

from fly_o_myte.analytics import update_after_snapshot
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
from fly_o_myte.price_sources.serpapi import (
    SerpAPIFlightSource,
    detect_airport_country,
)
from fly_o_myte.price_sources.tequila import TequilaPriceSource
from fly_o_myte.recommender import RouteType, SnapshotPoint, classify_route, compute
from fly_o_myte.true_cost import (
    TrueCostBreakdown,
    compute_family_score,
    compute_true_cost,
)

logger = logging.getLogger(__name__)


def build_plugin_manager_from_settings() -> pluggy.PluginManager:
    """Instantiate and register price source plugins based on available credentials."""
    settings = get_settings()
    pm = build_plugin_manager()

    if settings.serpapi_api_key:
        pm.register(
            SerpAPIFlightSource(
                api_key=settings.serpapi_api_key,
                cache_ttl_hours=settings.serpapi_cache_ttl_hours,
            )
        )
        logger.debug(
            "Registered SerpAPI (Google Flights) price source (cache TTL: %dh)",
            settings.serpapi_cache_ttl_hours,
        )
    elif settings.tequila_api_key:
        pm.register(TequilaPriceSource(api_key=settings.tequila_api_key))
        logger.debug("Registered Tequila price source")
    else:
        logger.warning("No price source API key set — set SERPAPI_API_KEY in .env")

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
    Fetch the latest price for a trip, save snapshots for top-3 offers, and compute
    a recommendation based on the rank-1 (lowest true family cost) offer.

    Returns the rank-1 snapshot on success, or None if the fetch failed.
    """
    depart = date.fromisoformat(trip.depart_date)
    ret = date.fromisoformat(trip.return_date) if trip.return_date else None
    child_ages = profile.child_ages_at(depart)

    # ─── 1. Fetch top offers ───────────────────────────────────────────────
    offers = _fetch_top_offers(
        pm=pm,
        origin=trip.origin,
        destination=trip.destination,
        depart_date=depart,
        return_date=ret,
        adults=trip.adults,
        children_ages=child_ages,
        max_stops=trip.max_stops,
    )
    if not offers:
        logger.warning("No offers found for trip %s (%s)", trip.id, trip.label)
        return None

    # ─── 1b. Route classification ───────────────────────────────────────────
    route_type = classify_route(trip.origin, trip.destination)

    # ─── 1c. Amadeus signal enrichment (applied to base-fare-cheapest offer) ─
    # ASIA_PACIFIC / LONG_HAUL: always call Amadeus for a reliable market signal.
    # DOMESTIC / TRANS_TASMAN: Amadeus only as fallback when SerpAPI returned None.
    _needs_amadeus = (
        route_type in (RouteType.ASIA_PACIFIC, RouteType.LONG_HAUL)
        or offers[0].price_level_signal is None
    )
    if _needs_amadeus:
        for plugin in pm.get_plugins():
            if isinstance(plugin, AmadeusPriceSource):
                signal = plugin.get_price_level_signal(
                    trip.origin, trip.destination, depart, offers[0].base_fare_per_adult
                )
                if signal:
                    offers[0] = FlightOffer(
                        **{**vars(offers[0]), "price_level_signal": signal}
                    )
                break

    # ─── 2. Compute true family cost for all offers ────────────────────────
    airline_db = get_airline_db()
    offers_with_data: list[tuple[FlightOffer, TrueCostBreakdown, float]] = []
    for offer in offers:
        bundle = airline_db.get_or_default(offer.airline_code)
        bd = compute_true_cost(
            airline_bundle=bundle,
            base_fare_per_adult=offer.base_fare_per_adult,
            adults=trip.adults,
            child_ages=child_ages,
            bags_per_person=trip.bags_per_person,
            depart_date=depart,
            return_date=ret,
            stops=offer.stops,
            route_type=route_type,
            currency=offer.currency,
        )
        dep_hour = _parse_hour(offer.departure_time)
        fs = compute_family_score(
            airline_bundle=bundle,
            true_cost=bd.total,
            avg_cost_on_route=bd.total,
            stops=offer.stops,
            departure_hour=dep_hour,
            preferred_earliest=profile.preferred_departure_window.earliest_hour,
            preferred_latest=profile.preferred_departure_window.latest_hour,
        )
        offers_with_data.append((offer, bd, fs))

    # Sort by true family cost ascending → assign ranks 1, 2, 3
    offers_with_data.sort(key=lambda x: x[1].total)

    # ─── 3. Save snapshots (shared fetched_at, one per offer) ─────────────
    assert trip.id is not None  # guaranteed for persisted trips
    shared_fetched_at = datetime.now(UTC).isoformat()
    primary_snapshot: PriceSnapshot | None = None

    for rank, (offer, bd, fs) in enumerate(offers_with_data, 1):
        snap = insert_snapshot(
            session,
            PriceSnapshot(
                trip_id=trip.id,
                fetched_at=shared_fetched_at,
                source=offer.source,
                airline_code=offer.airline_code,
                flight_number=offer.flight_number,
                base_fare_per_adult=offer.base_fare_per_adult,
                true_family_cost=bd.total,
                true_cost_breakdown=json.dumps(bd.as_dict()),
                price_level_signal=offer.price_level_signal,
                stops=offer.stops,
                departure_time=offer.departure_time,
                duration_minutes=offer.duration_minutes,
                family_score=fs,
                offer_raw=json.dumps(offer.offer_raw),
                rank=rank,
            ),
        )
        if rank == 1:
            primary_snapshot = snap

    assert primary_snapshot is not None

    # ─── 3a. Analytics update (Phase 2) ───────────────────────────────────
    _settings = get_settings()
    update_after_snapshot(
        analytics_dir=_settings.analytics_dir,
        trip_id=trip.id,
        origin=trip.origin,
        destination=trip.destination,
        sqlite_db_path=_settings.db_path,
    )

    # ─── 4. Build recommendation (rank-1 offer only) ──────────────────────
    primary_offer, primary_breakdown, _ = offers_with_data[0]

    snapshots = get_snapshots_for_trip(session, trip.id)
    # Use only rank-1 snapshots for recommendation history
    # (rank-2/3 are alternatives at the same timestamp and should not skew history)
    snap_points = [
        SnapshotPoint(
            fetched_at=datetime.fromisoformat(s.fetched_at),
            true_family_cost=s.true_family_cost,
        )
        for s in snapshots
        if s.rank == 1
    ]

    days_to_departure = (depart - date.today()).days

    # School holiday context — check family's AU state first
    cal = get_calendar()
    holiday_ctx = cal.check_overlap(profile.state, depart, ret)

    # For international routes also check the destination country's school calendar
    if holiday_ctx is None and route_type != RouteType.DOMESTIC:
        dest_country = detect_airport_country(trip.destination)
        if (
            dest_country
            and dest_country != "AU"
            and dest_country in cal.supported_states()
        ):
            holiday_ctx = cal.check_overlap(dest_country, depart, ret)

    result = compute(
        snapshots=snap_points,
        current_true_cost=primary_breakdown.total,
        days_to_departure=max(0, days_to_departure),
        price_level_signal=primary_offer.price_level_signal,
        school_holiday_context=holiday_ctx,
        route_type=route_type,
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
            true_family_cost=primary_breakdown.total,
            rolling_avg_cost=result.rolling_avg_cost,
            trend_slope=result.trend_slope,
            days_to_departure=days_to_departure,
            price_level_signal=primary_offer.price_level_signal,
            school_holiday_flag=holiday_ctx.label if holiday_ctx else None,
            rationale=result.rationale,
        ),
    )

    logger.info(
        "Trip %s — %s: $%.0f — %s (%.0f%% confident)",
        trip.id,
        trip.label,
        primary_breakdown.total,
        result.decision.upper(),
        result.confidence * 100,
    )

    # ─── 5. Send alerts ────────────────────────────────────────────────────
    # Identify if this is the first primary snapshot for this trip
    is_initial_poll = len([s for s in snapshots if s.rank == 1]) <= 1

    # Trigger if it's a "book_now", below user's threshold, OR if it's the first poll
    is_book_now = result.decision == "book_now"

    # Check threshold: trip-specific first, then fallback to family profile
    threshold = (
        trip.alert_threshold_aud
        if trip.alert_threshold_aud is not None
        else profile.budget_threshold_aud
    )
    is_below_threshold = threshold is not None and primary_breakdown.total <= threshold

    should_alert = send_alerts and (
        is_book_now or is_below_threshold or is_initial_poll
    )

    if should_alert:
        sent = send_book_now_alert(trip, rec, is_initial=is_initial_poll)
        if sent:
            assert rec.id is not None  # guaranteed after insert
            mark_email_sent(session, rec.id)

    return primary_snapshot


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


def _fetch_top_offers(
    pm: pluggy.PluginManager,
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date | None,
    adults: int,
    children_ages: list[int],
    max_stops: int,
    n: int = 10,
) -> list[FlightOffer]:
    """
    Call all registered price sources and return up to n cheapest offers by base fare.

    Results are sorted by base_fare_per_adult ascending. True cost ranking
    (which determines the final rank 1/2/3 saved to the DB) happens in poll_trip()
    after fee calculation.
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
        return []

    # Sort by base fare and return top n candidates for true cost ranking
    all_offers.sort(key=lambda o: o.base_fare_per_adult)
    return all_offers[:n]


def _parse_hour(departure_time: str) -> int:
    """Parse 'HH:MM' → hour integer. Returns 12 on parse failure."""
    try:
        return int(departure_time.split(":")[0])
    except (ValueError, IndexError):
        return 12
