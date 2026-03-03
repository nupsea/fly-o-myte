"""
Kiwi.com Tequila API price source plugin.

Primary flight data source for Phase 1 (domestic Australian routes).
Covers Qantas, Virgin Australia, Jetstar, Rex and all other carriers
globally — no partner agreement required.

Free tier: no per-call charges for personal use.
Rate limits: not publicly documented; poll at most once per hour per trip.

API reference: https://tequila.kiwi.com/portal/docs/tequila-api/search_api
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fly_o_myte.price_sources.hookspecs import FlightOffer, PriceSourceError, hookimpl

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.tequila.kiwi.com/v2/search"

# Tequila expects dates as dd/mm/yyyy
_DATE_FMT = "%d/%m/%Y"


class TequilaPriceSource:
    """
    Pluggy plugin implementing the Tequila API adapter.

    Register with the plugin manager in tracker.py:
        pm.register(TequilaPriceSource(api_key=settings.tequila_api_key))
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.Client(
            headers={"apikey": api_key},
            timeout=30.0,
        )

    # ─── hookspec implementations ──────────────────────────────────────────

    @hookimpl
    def source_name(self) -> str:
        return "tequila"

    @hookimpl
    def supports_route(self, origin: str, destination: str) -> bool:
        # Tequila covers all routes globally
        return True

    @hookimpl
    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def search_flights(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date | None,
        adults: int,
        children_ages: list[int],
        max_stops: int | None,
        currency: str,
    ) -> list[FlightOffer]:
        """
        Search Tequila for available flights.

        Returns a list of FlightOffer objects ordered cheapest first.
        Raises PriceSourceError on HTTP or API errors.
        """
        params = self._build_params(
            origin,
            destination,
            depart_date,
            return_date,
            adults,
            children_ages,
            max_stops,
            currency,
        )

        try:
            response = self._client.get(_BASE_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PriceSourceError(
                source="tequila",
                message=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise PriceSourceError(
                source="tequila",
                message=f"Connection error: {exc}",
            ) from exc

        data = response.json()
        offers = []
        for itinerary in data.get("data", []):
            offer = self._parse_itinerary(itinerary, currency)
            if offer:
                offers.append(offer)

        logger.debug(
            "Tequila: %s → %s on %s — %d offer(s) found",
            origin,
            destination,
            depart_date,
            len(offers),
        )
        return offers

    # ─── Private helpers ───────────────────────────────────────────────────

    def _build_params(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date | None,
        adults: int,
        children_ages: list[int],
        max_stops: int | None,
        currency: str,
    ) -> dict:
        fly_from = depart_date.strftime(_DATE_FMT)
        fly_to = fly_from  # single departure date

        params: dict = {
            "fly_from": origin,
            "fly_to": destination,
            "date_from": fly_from,
            "date_to": fly_to,
            "adults": adults,
            "curr": currency,
            "limit": 10,
            "sort": "price",
            "asc": 1,
            "vehicle_type": "aircraft",
            "one_for_city": 0,
        }

        if return_date:
            params["return_from"] = return_date.strftime(_DATE_FMT)
            params["return_to"] = return_date.strftime(_DATE_FMT)
        else:
            params["flight_type"] = "oneway"

        # Children: Tequila accepts children by age
        seated = [age for age in children_ages if age >= 2]
        infants = [age for age in children_ages if age < 2]
        if seated:
            params["children"] = len(seated)
        if infants:
            params["infants"] = len(infants)

        if max_stops is not None:
            params["max_stopovers"] = max_stops

        return params

    def _parse_itinerary(self, raw: dict, currency: str) -> FlightOffer | None:
        """Parse a single Tequila itinerary into a FlightOffer."""
        try:
            price = float(raw["price"])
            routes = raw.get("route", [])
            if not routes:
                return None

            first_leg = routes[0]
            airline_code = first_leg.get("airline", "")
            flight_number = first_leg.get("flight_no")

            # Departure / arrival times
            dep_utc = first_leg.get("local_departure", "")
            arr_utc = first_leg.get("local_arrival", "")
            departure_time = dep_utc[11:16] if len(dep_utc) >= 16 else None
            arrival_time = arr_utc[11:16] if len(arr_utc) >= 16 else None

            duration_sec = raw.get("duration", {}).get("total", 0)
            duration_minutes = int(duration_sec / 60) if duration_sec else 0

            # Stops = number of route segments minus 1 per direction
            # For return trips, count only outbound stops
            stops = max(0, len(routes) - 1)
            if raw.get("return_duration"):
                # It's a return trip; route list includes inbound legs
                # Tequila interleaves or appends — use stopovers field if present
                stops = raw.get("stopovers", stops)

            # Tequila doesn't provide LOW/TYPICAL/HIGH signals
            # (that's Amadeus Flight Price Analysis)

            return FlightOffer(
                source="tequila",
                airline_code=airline_code.upper() if airline_code else "",
                flight_number=str(flight_number) if flight_number else None,
                base_fare_per_adult=price,
                currency=currency,
                stops=stops,
                departure_time=departure_time or "",
                arrival_time=arrival_time or "",
                duration_minutes=duration_minutes,
                price_level_signal=None,
                offer_raw=raw,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning(
                "Failed to parse Tequila itinerary: %s — %s", exc, raw.get("id")
            )
            return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TequilaPriceSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
