"""
SerpAPI Google Flights price source plugin.

Primary flight data source — scrapes Google Flights via SerpAPI.
Covers all Australian domestic carriers: Qantas (QF), Virgin Australia (VA),
Jetstar (JQ), Rex (ZL), and all other carriers on Google Flights.

Free tier: 100 searches/month.
Sign up: https://serpapi.com

API reference: https://serpapi.com/google-flights-results

Notes:
- Always searches for 1 adult to get a clean per-adult base fare.
  The true cost calculator in true_cost.py handles all ancillary fees.
- Uses gl=au so Google returns Australian pricing in AUD.
- price_insights.price_level (low/typical/high) is mapped to our
  price_level_signal (LOW/TYPICAL/HIGH) when available.
"""

from __future__ import annotations

import logging
from datetime import date

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fly_o_myte.price_sources.hookspecs import FlightOffer, PriceSourceError, hookimpl

logger = logging.getLogger(__name__)

_BASE_URL = "https://serpapi.com/search"

# Google Flights returns full airline names; map to IATA codes.
# Lowercase keys — compare with airline.lower().
_AIRLINE_IATA: dict[str, str] = {
    # AU domestic
    "qantas": "QF",
    "virgin australia": "VA",
    "jetstar": "JQ",
    "rex airlines": "ZL",
    "rex": "ZL",
    "tigerair australia": "TT",
    "bonza": "AB",
    # International — Asia Pacific
    "air new zealand": "NZ",
    "singapore airlines": "SQ",
    "scoot": "TR",
    "cathay pacific": "CX",
    "hong kong express": "UO",
    "malaysia airlines": "MH",
    "airasia": "AK",
    "air asia": "AK",
    "airasia x": "D7",
    "garuda indonesia": "GA",
    "korean air": "KE",
    "asiana airlines": "OZ",
    "china southern airlines": "CZ",
    "china eastern airlines": "MU",
    "air china": "CA",
    "jetstar asia": "3K",
    "all nippon airways": "NH",
    "ana": "NH",
    "japan airlines": "JL",
    "jal": "JL",
    "philippine airlines": "PR",
    "cebu pacific": "5J",
    "vietnam airlines": "VN",
    "thai airways international": "TG",
    "thai airways": "TG",
    "air india": "AI",
    # Middle East
    "emirates": "EK",
    "etihad airways": "EY",
    "qatar airways": "QR",
    # Europe
    "british airways": "BA",
    "lufthansa": "LH",
    "klm": "KL",
    "klm royal dutch airlines": "KL",
    "air france": "AF",
    "turkish airlines": "TK",
    "swiss": "LX",
    "swiss international air lines": "LX",
    # North America
    "united airlines": "UA",
    "american airlines": "AA",
    "delta air lines": "DL",
    "air canada": "AC",
}

# Destination country code → SerpAPI gl (Google country) value.
# Using the destination country's Google instance gives better local pricing.
_COUNTRY_GL_MAP: dict[str, str] = {
    "AU": "au",
    "SG": "sg",
    "GB": "gb",
    "JP": "jp",
    "TH": "th",
    "US": "us",
    "NZ": "nz",
    "AE": "ae",
    "HK": "hk",
    "IN": "in",
    "FR": "fr",
    "DE": "de",
    "MY": "my",
    "ID": "id",
    "KR": "kr",
    "CN": "cn",
    "QA": "qa",
    "PH": "ph",
    "IT": "it",
    "ES": "es",
    "CA": "ca",
    "TR": "tr",
    "ZA": "za",
    "VN": "vn",
}

# Australian domestic airports — destination in this set → gl='au'
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

# Top international airports → ISO country code (covers most AU international routes)
_AIRPORT_COUNTRY: dict[str, str] = {
    # Singapore
    "SIN": "SG",
    # United Kingdom
    "LHR": "GB",
    "LGW": "GB",
    "STN": "GB",
    "MAN": "GB",
    "EDI": "GB",
    "BHX": "GB",
    # Japan
    "NRT": "JP",
    "HND": "JP",
    "KIX": "JP",
    "NGO": "JP",
    "FUK": "JP",
    # Thailand
    "BKK": "TH",
    "DMK": "TH",
    "HKT": "TH",
    "CNX": "TH",
    # USA
    "LAX": "US",
    "SFO": "US",
    "JFK": "US",
    "ORD": "US",
    "DFW": "US",
    "IAH": "US",
    "SEA": "US",
    "HNL": "US",
    "EWR": "US",
    "LAS": "US",
    # New Zealand
    "AKL": "NZ",
    "CHC": "NZ",
    "WLG": "NZ",
    "ZQN": "NZ",
    "DUD": "NZ",
    # UAE
    "DXB": "AE",
    "AUH": "AE",
    "SHJ": "AE",
    # Hong Kong
    "HKG": "HK",
    # India
    "DEL": "IN",
    "BOM": "IN",
    "MAA": "IN",
    "BLR": "IN",
    "CCU": "IN",
    # France
    "CDG": "FR",
    "ORY": "FR",
    # Germany
    "FRA": "DE",
    "MUC": "DE",
    "DUS": "DE",
    # Malaysia
    "KUL": "MY",
    "PEN": "MY",
    # Indonesia
    "CGK": "ID",
    "DPS": "ID",
    # South Korea
    "ICN": "KR",
    "GMP": "KR",
    # China
    "PEK": "CN",
    "PKX": "CN",
    "PVG": "CN",
    "CAN": "CN",
    "SHA": "CN",
    # Qatar
    "DOH": "QA",
    # Philippines
    "MNL": "PH",
    "CEB": "PH",
    # Italy
    "FCO": "IT",
    "MXP": "IT",
    # Spain
    "MAD": "ES",
    "BCN": "ES",
    # Canada
    "YYZ": "CA",
    "YVR": "CA",
    # Turkey
    "IST": "TR",
    "SAW": "TR",
    # South Africa
    "JNB": "ZA",
    "CPT": "ZA",
    # Vietnam
    "SGN": "VN",
    "HAN": "VN",
}

# SerpAPI stops parameter values:
#   1 = nonstop only, 2 = 1 stop or fewer, 3 = 2 stops or fewer, 0 = any
_STOPS_PARAM: dict[int, int] = {0: 1, 1: 2, 2: 3}

_PRICE_LEVEL: dict[str, str] = {
    "low": "LOW",
    "typical": "TYPICAL",
    "high": "HIGH",
}


def detect_destination_country(airport_iata: str) -> str | None:
    """
    Return the ISO country code for a destination airport.

    Returns 'AU' for Australian domestic airports.
    Returns None when the airport is not in the known list.
    """
    code = airport_iata.upper()
    if code in _AU_AIRPORTS:
        return "AU"
    return _AIRPORT_COUNTRY.get(code)


class SerpAPIFlightSource:
    """
    Pluggy plugin implementing the SerpAPI Google Flights adapter.

    Register with the plugin manager in tracker.py:
        pm.register(SerpAPIFlightSource(api_key=settings.serpapi_api_key))

    Searches for 1 adult to get a clean per-adult base fare.
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.Client(timeout=30.0)

    # ─── hookspec implementations ──────────────────────────────────────────

    @hookimpl
    def source_name(self) -> str:
        return "serpapi"

    @hookimpl
    def supports_route(self, origin: str, destination: str) -> bool:
        # Google Flights covers all routes globally
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
        Search Google Flights via SerpAPI for available flights.

        Always searches for 1 adult to get a clean per-adult base fare.
        Returns a list of FlightOffer objects ordered cheapest first.
        Raises PriceSourceError on HTTP or API errors.
        """
        params = self._build_params(
            origin, destination, depart_date, return_date, max_stops, currency
        )

        try:
            response = self._client.get(_BASE_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PriceSourceError(
                source="serpapi",
                message=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.RequestError as exc:
            raise PriceSourceError(
                source="serpapi",
                message=f"Connection error: {exc}",
            ) from exc

        data = response.json()

        # SerpAPI returns errors as JSON even on HTTP 200
        if "error" in data:
            raise PriceSourceError(
                source="serpapi",
                message=data["error"],
            )

        # Extract price level signal from price_insights if present
        insights = data.get("price_insights", {})
        raw_level = insights.get("price_level", "")
        price_level_signal = _PRICE_LEVEL.get(raw_level.lower()) if raw_level else None

        offers: list[FlightOffer] = []
        for container in data.get("best_flights", []) + data.get("other_flights", []):
            offer = self._parse_container(container, price_level_signal)
            if offer is not None:
                offers.append(offer)

        logger.debug(
            "SerpAPI: %s → %s on %s — %d offer(s) found",
            origin,
            destination,
            depart_date,
            len(offers),
        )
        return sorted(offers, key=lambda o: o.base_fare_per_adult)

    # ─── Private helpers ───────────────────────────────────────────────────

    def _build_params(
        self,
        origin: str,
        destination: str,
        depart_date: date,
        return_date: date | None,
        max_stops: int | None,
        currency: str,
    ) -> dict:
        # Use destination-country gl for better local pricing on international routes
        dest_country = detect_destination_country(destination)
        gl = _COUNTRY_GL_MAP.get(dest_country or "AU", "au")

        params: dict = {
            "engine": "google_flights",
            "departure_id": origin,
            "arrival_id": destination,
            "outbound_date": depart_date.isoformat(),
            "adults": 1,  # always 1 — get clean per-adult fare
            "currency": currency,
            "hl": "en",
            "gl": gl,
            "api_key": self._api_key,
        }

        if return_date:
            params["return_date"] = return_date.isoformat()
            params["type"] = 1  # round trip
        else:
            params["type"] = 2  # one way

        if max_stops is not None and max_stops in _STOPS_PARAM:
            params["stops"] = _STOPS_PARAM[max_stops]

        return params

    def _parse_container(
        self,
        container: dict,
        price_level_signal: str | None,
    ) -> FlightOffer | None:
        """Parse a single Google Flights result container into a FlightOffer."""
        try:
            price = float(container["price"])
            flights = container.get("flights", [])
            if not flights:
                return None

            first_leg = flights[0]

            # Airline name → IATA code
            airline_name = first_leg.get("airline", "")
            airline_code: str = (
                _AIRLINE_IATA.get(airline_name.lower())
                or airline_name[:2].upper()
                or "XX"
            )

            # Flight number — Google returns "QF 500", normalise to "QF500"
            raw_fn = first_leg.get("flight_number", "")
            flight_number = raw_fn.replace(" ", "") if raw_fn else None

            # Departure time from "YYYY-MM-DD HH:MM"
            dep_raw = first_leg.get("departure_airport", {}).get("time", "")
            departure_time = dep_raw[11:16] if len(dep_raw) >= 16 else ""

            arr_raw = first_leg.get("arrival_airport", {}).get("time", "")
            arrival_time = arr_raw[11:16] if len(arr_raw) >= 16 else ""

            # Total duration in minutes across all legs
            duration_minutes = int(container.get("total_duration", 0))

            # Stops = number of layovers
            stops = len(container.get("layovers", []))

            return FlightOffer(
                source="serpapi",
                airline_code=airline_code,
                flight_number=flight_number,
                base_fare_per_adult=price,
                currency=container.get("currency") or "AUD",
                stops=stops,
                departure_time=departure_time,
                arrival_time=arrival_time,
                duration_minutes=duration_minutes,
                price_level_signal=price_level_signal,
                offer_raw=container,
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Failed to parse SerpAPI flight container: %s", exc)
            return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SerpAPIFlightSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
