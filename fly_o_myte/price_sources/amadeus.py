"""
Amadeus flight price source plugin — Phase 2/3.

Used for:
  - International routes (better coverage than Tequila for long-haul)
  - Flight Price Analysis signal (LOW / WITHIN_AVERAGE / HIGH)
    This historical pricing intelligence is the main value of Amadeus —
    it provides a market benchmark the recommender uses directly.

Authentication: OAuth2 client credentials flow.
Free test tier available at https://developers.amadeus.com

Note: Amadeus coverage of Australian domestic carriers (VA, JQ) is limited
as of 2026. Use Tequila as the domestic primary source.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fly_o_myte.price_sources.hookspecs import FlightOffer, PriceSourceError, hookimpl

logger = logging.getLogger(__name__)

_AUTH_URL = "https://{host}.api.amadeus.com/v1/security/oauth2/token"
_SEARCH_URL = "https://{host}.api.amadeus.com/v2/shopping/flight-offers"
_ANALYSIS_URL = "https://{host}.api.amadeus.com/v1/analytics/itinerary-price-metrics"

# Domestic Australian routes — let Tequila handle these
_AUSTRALIAN_AIRPORTS = {
    "ADL",
    "BNE",
    "CBR",
    "CNS",
    "DRW",
    "HBA",
    "MEL",
    "MKY",
    "OOL",
    "PER",
    "SYD",
    "TSV",
    "WOL",
}


class AmadeusPriceSource:
    """
    Pluggy plugin implementing the Amadeus API adapter.

    Register after TequilaPriceSource so Tequila handles domestic routes:
        pm.register(TequilaPriceSource(...))
        pm.register(AmadeusPriceSource(...))
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        hostname: str = "test",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._hostname = hostname  # "test" or "api" (production)
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._http = httpx.Client(timeout=30.0)

    # ─── hookspec implementations ──────────────────────────────────────────

    @hookimpl
    def source_name(self) -> str:
        return "amadeus"

    @hookimpl
    def supports_route(self, origin: str, destination: str) -> bool:
        """
        Amadeus is used for international routes only.
        Domestic Australian routes are handled by Tequila.
        """
        both_domestic = (
            origin.upper() in _AUSTRALIAN_AIRPORTS
            and destination.upper() in _AUSTRALIAN_AIRPORTS
        )
        return not both_domestic

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
        Search Amadeus for international flight offers.
        Raises PriceSourceError on API failure.
        """
        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        params: dict = {
            "originLocationCode": origin.upper(),
            "destinationLocationCode": destination.upper(),
            "departureDate": depart_date.isoformat(),
            "adults": adults,
            "currencyCode": currency,
            "max": 10,
        }

        if return_date:
            params["returnDate"] = return_date.isoformat()

        children = [age for age in children_ages if 2 <= age < 12]
        infants = [age for age in children_ages if age < 2]
        if children:
            params["children"] = len(children)
        if infants:
            params["infants"] = len(infants)

        if max_stops is not None:
            params["nonStop"] = "true" if max_stops == 0 else "false"

        url = _SEARCH_URL.format(host=self._hostname)
        try:
            response = self._http.get(url, headers=headers, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PriceSourceError(
                source="amadeus",
                message=f"HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise PriceSourceError(source="amadeus", message=str(exc)) from exc

        data = response.json()
        offers = []
        for raw_offer in data.get("data", []):
            offer = self._parse_offer(raw_offer, currency)
            if offer:
                offers.append(offer)

        # Attempt to enrich with price level signal
        if offers:
            signal = self._fetch_price_signal(
                origin, destination, depart_date, currency
            )
            if signal:
                offers = [
                    FlightOffer(**{**vars(o), "price_level_signal": signal})
                    for o in offers
                ]

        logger.debug(
            "Amadeus: %s → %s on %s — %d offer(s)",
            origin,
            destination,
            depart_date,
            len(offers),
        )
        return offers

    # ─── Private helpers ───────────────────────────────────────────────────

    def _get_token(self) -> str:
        """Return a cached OAuth2 token, refreshing if expired."""
        if self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token

        url = _AUTH_URL.format(host=self._hostname)
        try:
            response = self._http.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PriceSourceError(
                source="amadeus",
                message=f"Auth failed: HTTP {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

        token_data = response.json()
        self._access_token = str(token_data["access_token"])
        self._token_expires_at = time.time() + token_data.get("expires_in", 1799)
        return self._access_token

    def _parse_offer(self, raw: dict, currency: str) -> FlightOffer | None:
        try:
            price_str = raw.get("price", {}).get("grandTotal") or raw.get(
                "price", {}
            ).get("total")
            if not price_str:
                return None
            price = float(price_str)

            itineraries = raw.get("itineraries", [])
            if not itineraries:
                return None

            first_itin = itineraries[0]
            segments = first_itin.get("segments", [])
            if not segments:
                return None

            first_seg = segments[0]
            last_seg = segments[-1]

            airline_code = first_seg.get("carrierCode", "")
            flight_number = first_seg.get("number")

            dep_str = first_seg.get("departure", {}).get("at", "")
            arr_str = last_seg.get("arrival", {}).get("at", "")
            departure_time = dep_str[11:16] if len(dep_str) >= 16 else ""
            arrival_time = arr_str[11:16] if len(arr_str) >= 16 else ""

            duration_str = first_itin.get("duration", "")
            duration_minutes = _parse_iso_duration(duration_str)

            stops = len(segments) - 1

            return FlightOffer(
                source="amadeus",
                airline_code=airline_code.upper(),
                flight_number=str(flight_number) if flight_number else None,
                base_fare_per_adult=price,
                currency=currency,
                stops=stops,
                departure_time=departure_time,
                arrival_time=arrival_time,
                duration_minutes=duration_minutes,
                price_level_signal=None,
                offer_raw=raw,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse Amadeus offer: %s", exc)
            return None

    def _fetch_price_signal(
        self, origin: str, destination: str, depart_date: date, currency: str
    ) -> str | None:
        """
        Call Amadeus Flight Price Analysis to get LOW/WITHIN_AVERAGE/HIGH signal.
        Returns None on any failure — callers must handle gracefully.
        """
        try:
            token = self._get_token()
            url = _ANALYSIS_URL.format(host=self._hostname)
            response = self._http.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "originIataCode": origin.upper(),
                    "destinationIataCode": destination.upper(),
                    "departureDate": depart_date.isoformat(),
                    "currencyCode": currency,
                    "oneWay": "false",
                },
                timeout=10.0,
            )
            if response.status_code != 200:
                return None
            data = response.json()
            price_metrics = data.get("data", [{}])[0]
            return price_metrics.get("priceMetrics", [{}])[0].get("amount")
        except Exception as exc:
            logger.debug("Price signal fetch failed (non-critical): %s", exc)
            return None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AmadeusPriceSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _parse_iso_duration(duration: str) -> int:
    """Parse ISO 8601 duration string 'PT2H30M' → minutes."""
    if not duration:
        return 0
    total = 0
    duration = duration.replace("PT", "")
    if "H" in duration:
        parts = duration.split("H")
        total += int(parts[0]) * 60
        duration = parts[1]
    if "M" in duration:
        total += int(duration.replace("M", ""))
    return total
