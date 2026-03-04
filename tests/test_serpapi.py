"""
Unit tests for SerpAPIFlightSource.

All HTTP calls are mocked at the transport boundary via pytest-httpx.
No real API calls are made.
"""

from __future__ import annotations

from datetime import date

import pytest

from fly_o_myte.price_sources.hookspecs import PriceSourceError
from fly_o_myte.price_sources.serpapi import SerpAPIFlightSource

# ─── mock SerpAPI response ────────────────────────────────────────────────────

MOCK_SERPAPI_RESPONSE = {
    "best_flights": [
        {
            "price": 149.0,
            "flights": [
                {
                    "airline": "Qantas",
                    "flight_number": "QF 500",
                    "departure_airport": {"time": "2026-07-20 10:30"},
                    "arrival_airport": {"time": "2026-07-20 12:10"},
                }
            ],
            "total_duration": 100,
            "layovers": [],
        }
    ],
    "other_flights": [],
    "price_insights": {"price_level": "typical"},
}


# ─── helpers ──────────────────────────────────────────────────────────────────


def _search(src: SerpAPIFlightSource, **kwargs):
    """Call search_flights with sensible defaults; override via kwargs."""
    defaults = {
        "origin": "BNE",
        "destination": "SYD",
        "depart_date": date(2026, 7, 20),
        "return_date": None,
        "adults": 2,
        "children_ages": [],
        "max_stops": None,
        "currency": "AUD",
    }
    defaults.update(kwargs)
    return src.search_flights(**defaults)


# ─── happy path ───────────────────────────────────────────────────────────────


def test_happy_path_returns_flight_offer(httpx_mock):
    """MOCK_SERPAPI_RESPONSE with best_flights returns a valid FlightOffer."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.airline_code == "QF"
    assert offer.base_fare_per_adult == 149.0
    assert offer.stops == 0
    assert offer.departure_time == "10:30"
    assert offer.source == "serpapi"


# ─── airline name mapping ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "airline_name,expected_code",
    [
        ("Qantas", "QF"),
        ("Virgin Australia", "VA"),
        ("Jetstar", "JQ"),
        ("Unknown Carrier", "UN"),  # first 2 chars uppercased
    ],
)
def test_airline_name_mapping(httpx_mock, airline_name, expected_code):
    """Airline full names map to correct IATA codes."""
    response = {
        "best_flights": [
            {
                "price": 200.0,
                "flights": [
                    {
                        "airline": airline_name,
                        "flight_number": "XX 100",
                        "departure_airport": {"time": "2026-07-20 10:30"},
                        "arrival_airport": {"time": "2026-07-20 12:10"},
                    }
                ],
                "total_duration": 100,
                "layovers": [],
            }
        ],
        "other_flights": [],
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 1
    assert offers[0].airline_code == expected_code


# ─── price level signal ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw_level,expected_signal",
    [
        ("low", "LOW"),
        ("typical", "TYPICAL"),
        ("high", "HIGH"),
    ],
)
def test_price_level_signal_mapping(httpx_mock, raw_level, expected_signal):
    """price_insights.price_level maps to the correct price_level_signal."""
    response = {
        "best_flights": [
            {
                "price": 199.0,
                "flights": [
                    {
                        "airline": "Qantas",
                        "flight_number": "QF 100",
                        "departure_airport": {"time": "2026-07-20 10:30"},
                        "arrival_airport": {"time": "2026-07-20 12:10"},
                    }
                ],
                "total_duration": 100,
                "layovers": [],
            }
        ],
        "other_flights": [],
        "price_insights": {"price_level": raw_level},
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 1
    assert offers[0].price_level_signal == expected_signal


def test_missing_price_insights_returns_none_signal(httpx_mock):
    """When price_insights is absent, price_level_signal is None."""
    response = {
        "best_flights": [
            {
                "price": 149.0,
                "flights": [
                    {
                        "airline": "Qantas",
                        "flight_number": "QF 500",
                        "departure_airport": {"time": "2026-07-20 10:30"},
                        "arrival_airport": {"time": "2026-07-20 12:10"},
                    }
                ],
                "total_duration": 100,
                "layovers": [],
            }
        ],
        "other_flights": [],
        # no price_insights key
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 1
    assert offers[0].price_level_signal is None


# ─── stops from layovers ──────────────────────────────────────────────────────


def test_stops_empty_layovers(httpx_mock):
    """Empty layovers array → stops=0."""
    response = {
        "best_flights": [
            {
                "price": 149.0,
                "flights": [
                    {
                        "airline": "Qantas",
                        "flight_number": "QF 500",
                        "departure_airport": {"time": "2026-07-20 10:30"},
                        "arrival_airport": {"time": "2026-07-20 12:10"},
                    }
                ],
                "total_duration": 100,
                "layovers": [],
            }
        ],
        "other_flights": [],
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert offers[0].stops == 0


def test_stops_one_layover(httpx_mock):
    """One layover entry → stops=1."""
    response = {
        "best_flights": [
            {
                "price": 250.0,
                "flights": [
                    {
                        "airline": "Jetstar",
                        "flight_number": "JQ 100",
                        "departure_airport": {"time": "2026-07-20 08:00"},
                        "arrival_airport": {"time": "2026-07-20 14:00"},
                    }
                ],
                "total_duration": 360,
                "layovers": [{"airport": "MEL", "duration": 120}],
            }
        ],
        "other_flights": [],
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert offers[0].stops == 1


# ─── return vs one-way request params ────────────────────────────────────────


def test_return_trip_params_include_type_1(httpx_mock):
    """Return trip → params contain type=1 and return_date."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, return_date=date(2026, 7, 27))

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["type"] == "1"
    assert "return_date" in params
    assert params["return_date"] == "2026-07-27"


def test_oneway_trip_params_include_type_2(httpx_mock):
    """One-way trip → params contain type=2, no return_date key."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, return_date=None)

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["type"] == "2"
    assert "return_date" not in params


# ─── fixed request params ─────────────────────────────────────────────────────


def test_always_uses_adults_1(httpx_mock):
    """adults param is always 1 regardless of actual pax count passed in."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, adults=4)  # pass 4 — should still send 1

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["adults"] == "1"


def test_gl_au_always_present(httpx_mock):
    """gl='au' is always present in request params."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src)

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["gl"] == "au"


# ─── HTTP error handling ──────────────────────────────────────────────────────


def test_http_500_retries_three_times_then_raises(httpx_mock, monkeypatch):
    """HTTP 500 triggers tenacity retry — httpx called exactly 3 times before PriceSourceError."""
    monkeypatch.setattr("time.sleep", lambda _: None)

    for _ in range(3):
        httpx_mock.add_response(status_code=500, text="Internal Server Error")

    src = SerpAPIFlightSource(api_key="test-key")
    with pytest.raises(PriceSourceError):
        _search(src)

    assert len(httpx_mock.get_requests()) == 3


def test_json_error_key_raises_price_source_error(httpx_mock, monkeypatch):
    """JSON response with 'error' key raises PriceSourceError."""
    monkeypatch.setattr("time.sleep", lambda _: None)

    for _ in range(3):
        httpx_mock.add_response(
            json={"error": "Invalid API key. Please use a valid key."}
        )

    src = SerpAPIFlightSource(api_key="bad-key")
    with pytest.raises(PriceSourceError):
        _search(src)


# ─── best_flights + other_flights combined ────────────────────────────────────


def test_best_and_other_flights_combined(httpx_mock):
    """Offers from best_flights and other_flights are both parsed and combined."""
    response = {
        "best_flights": [
            {
                "price": 149.0,
                "flights": [
                    {
                        "airline": "Qantas",
                        "flight_number": "QF 500",
                        "departure_airport": {"time": "2026-07-20 10:30"},
                        "arrival_airport": {"time": "2026-07-20 12:10"},
                    }
                ],
                "total_duration": 100,
                "layovers": [],
            }
        ],
        "other_flights": [
            {
                "price": 199.0,
                "flights": [
                    {
                        "airline": "Jetstar",
                        "flight_number": "JQ 100",
                        "departure_airport": {"time": "2026-07-20 14:00"},
                        "arrival_airport": {"time": "2026-07-20 16:00"},
                    }
                ],
                "total_duration": 120,
                "layovers": [],
            }
        ],
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 2
    airline_codes = {o.airline_code for o in offers}
    assert "QF" in airline_codes
    assert "JQ" in airline_codes


# ─── Pluggy registration ──────────────────────────────────────────────────────


def test_serpapi_registers_correctly_via_pluggy():
    """SerpAPIFlightSource registers one search_flights hookimpl with Pluggy."""
    from fly_o_myte.price_sources.hookspecs import build_plugin_manager

    pm = build_plugin_manager()
    pm.register(SerpAPIFlightSource("test-key"))
    assert len(pm.hook.search_flights.get_hookimpls()) == 1


# ─── origin-based gl routing ──────────────────────────────────────────────────


def test_bne_to_sin_uses_gl_au(httpx_mock):
    """BNE -> SIN departs AU — gl must be 'au' (user POS)."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, origin="BNE", destination="SIN")

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["gl"] == "au"


def test_sin_to_bne_uses_gl_sg(httpx_mock):
    """SIN -> BNE departs SG — gl must be 'sg'."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, origin="SIN", destination="BNE")

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["gl"] == "sg"


def test_lhr_to_jfk_uses_gl_gb(httpx_mock):
    """LHR -> JFK departs GB — gl must be 'gb'."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, origin="LHR", destination="JFK")

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["gl"] == "gb"


def test_domestic_bne_syd_uses_gl_au(httpx_mock):
    """BNE -> SYD is domestic AU — gl must be 'au'."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, origin="BNE", destination="SYD")

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["gl"] == "au"


def test_unknown_origin_falls_back_to_gl_au(httpx_mock):
    """Unknown origin airport codes fall back to gl='au'."""
    httpx_mock.add_response(json=MOCK_SERPAPI_RESPONSE)
    src = SerpAPIFlightSource(api_key="test-key")
    _search(src, origin="ZZZ", destination="BNE")

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["gl"] == "au"


# ─── international airline IATA codes ────────────────────────────────────────


@pytest.mark.parametrize(
    "airline_name,expected_code",
    [
        ("Singapore Airlines", "SQ"),
        ("Emirates", "EK"),
        ("Cathay Pacific", "CX"),
        ("Qatar Airways", "QR"),
        ("Malaysia Airlines", "MH"),
        ("Garuda Indonesia", "GA"),
        ("Japan Airlines", "JL"),
        ("All Nippon Airways", "NH"),
    ],
)
def test_international_airline_name_mapping(httpx_mock, airline_name, expected_code):
    """International airline full names map to correct IATA codes."""
    response = {
        "best_flights": [
            {
                "price": 500.0,
                "flights": [
                    {
                        "airline": airline_name,
                        "flight_number": "XX 100",
                        "departure_airport": {"time": "2026-09-18 10:30"},
                        "arrival_airport": {"time": "2026-09-18 18:30"},
                    }
                ],
                "total_duration": 480,
                "layovers": [],
            }
        ],
        "other_flights": [],
    }
    httpx_mock.add_response(json=response)
    src = SerpAPIFlightSource(api_key="test-key")
    offers = _search(src, destination="SIN")

    assert len(offers) == 1
    assert offers[0].airline_code == expected_code


# ─── detect_airport_country helper ───────────────────────────────────────────


def test_detect_airport_country_au_airport():
    """Australian airports return 'AU'."""
    from fly_o_myte.price_sources.serpapi import detect_airport_country

    assert detect_airport_country("SYD") == "AU"
    assert detect_airport_country("MEL") == "AU"
    assert detect_airport_country("BNE") == "AU"


def test_detect_airport_country_international():
    """Known international airports return their country code."""
    from fly_o_myte.price_sources.serpapi import detect_airport_country

    assert detect_airport_country("SIN") == "SG"
    assert detect_airport_country("LHR") == "GB"
    assert detect_airport_country("NRT") == "JP"
    assert detect_airport_country("DXB") == "AE"
    assert detect_airport_country("HKG") == "HK"


def test_detect_airport_country_unknown():
    """Unknown airport codes return None."""
    from fly_o_myte.price_sources.serpapi import detect_airport_country

    assert detect_airport_country("ZZZ") is None
