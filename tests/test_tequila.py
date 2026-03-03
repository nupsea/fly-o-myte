"""
Unit tests for TequilaPriceSource.

All HTTP calls are mocked at the transport boundary via pytest-httpx.
No real API calls are made.
"""

from __future__ import annotations

from datetime import date

import pytest

from fly_o_myte.price_sources.hookspecs import PriceSourceError
from fly_o_myte.price_sources.tequila import TequilaPriceSource
from tests.conftest import MOCK_TEQUILA_RESPONSE

# ─── helpers ────────────────────────────────────────────────────────────────


def _search(src: TequilaPriceSource, **kwargs):
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


# ─── happy path ──────────────────────────────────────────────────────────────


def test_happy_path_returns_flight_offer(httpx_mock):
    """MOCK_TEQUILA_RESPONSE parsed into a valid FlightOffer."""
    httpx_mock.add_response(json=MOCK_TEQUILA_RESPONSE)
    src = TequilaPriceSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 1
    offer = offers[0]
    assert offer.airline_code == "QF"
    assert offer.base_fare_per_adult == 149.0
    assert offer.stops == 0
    assert offer.departure_time == "10:30"
    assert offer.source == "tequila"


# ─── empty data ─────────────────────────────────────────────────────────────


def test_empty_data_array_returns_empty_list(httpx_mock):
    """data=[] should return [] without error."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    offers = _search(src)
    assert offers == []


# ─── HTTP error handling ──────────────────────────────────────────────────────


def test_http_500_retries_three_times_then_raises(httpx_mock, monkeypatch):
    """HTTP 500 triggers tenacity retry; httpx is called exactly 3 times."""
    # Suppress retry wait so the test is not slow
    monkeypatch.setattr("time.sleep", lambda _: None)

    for _ in range(3):
        httpx_mock.add_response(status_code=500, text="Internal Server Error")

    src = TequilaPriceSource(api_key="test-key")
    with pytest.raises(PriceSourceError):
        _search(src)

    assert len(httpx_mock.get_requests()) == 3


def test_http_404_raises_price_source_error(httpx_mock, monkeypatch):
    """HTTP 404 raises PriceSourceError (not a bare Exception)."""
    monkeypatch.setattr("time.sleep", lambda _: None)

    for _ in range(3):
        httpx_mock.add_response(status_code=404, text="Not Found")

    src = TequilaPriceSource(api_key="test-key")
    with pytest.raises(PriceSourceError):
        _search(src)


# ─── malformed itinerary ─────────────────────────────────────────────────────


def test_malformed_itinerary_skipped_valid_offer_returned(httpx_mock):
    """Itinerary missing 'price' key is skipped; remaining valid offers returned."""
    response_data = {
        "data": [
            # missing 'price' — should be silently skipped
            {
                "id": "bad",
                "route": [
                    {
                        "airline": "QF",
                        "flight_no": "QF500",
                        "local_departure": "2026-07-20T10:30:00",
                        "local_arrival": "2026-07-20T12:10:00",
                    }
                ],
                "duration": {"total": 6000},
            },
            # valid offer
            {
                "id": "good",
                "price": 200.0,
                "route": [
                    {
                        "airline": "VA",
                        "flight_no": "VA100",
                        "local_departure": "2026-07-20T14:00:00",
                        "local_arrival": "2026-07-20T16:00:00",
                    }
                ],
                "duration": {"total": 7200},
                "stopovers": 0,
            },
        ],
        "currency": "AUD",
    }
    httpx_mock.add_response(json=response_data)
    src = TequilaPriceSource(api_key="test-key")
    offers = _search(src)

    assert len(offers) == 1
    assert offers[0].airline_code == "VA"
    assert offers[0].base_fare_per_adult == 200.0


# ─── return trip ─────────────────────────────────────────────────────────────


def test_return_trip_params_include_return_keys(httpx_mock):
    """When return_date is set, request contains return_from and return_to."""
    httpx_mock.add_response(json=MOCK_TEQUILA_RESPONSE)
    src = TequilaPriceSource(api_key="test-key")
    _search(src, return_date=date(2026, 7, 27))

    request = httpx_mock.get_requests()[0]
    params = dict(request.url.params)
    assert "return_from" in params
    assert "return_to" in params
    assert params["return_from"] == "27/07/2026"
    assert params["return_to"] == "27/07/2026"
    # flight_type should NOT be present for return trips
    assert "flight_type" not in params


# ─── S13: children / infant params ───────────────────────────────────────────


def test_children_ages_split_into_seated_and_infants(httpx_mock):
    """ages >= 2 → 'children' count; ages < 2 → 'infants' count."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    # 3 children: ages 4, 7 are seated; age 0 is infant
    _search(src, children_ages=[4, 7, 0])

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["children"] == "2"
    assert params["infants"] == "1"


def test_no_children_omits_children_and_infants_params(httpx_mock):
    """When children_ages=[], 'children' and 'infants' keys must not appear."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    _search(src, children_ages=[])

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert "children" not in params
    assert "infants" not in params


# ─── S13: one-way trip params ─────────────────────────────────────────────────


def test_oneway_trip_params(httpx_mock):
    """One-way: flight_type=oneway present; return_from/return_to absent."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    _search(src, return_date=None)

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params.get("flight_type") == "oneway"
    assert "return_from" not in params
    assert "return_to" not in params


# ─── S13: currency forwarding ────────────────────────────────────────────────


def test_currency_forwarded_to_curr_param(httpx_mock):
    """currency='AUD' is passed as 'curr' in every request."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    _search(src, currency="AUD")

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["curr"] == "AUD"


# ─── S13: max_stops param ────────────────────────────────────────────────────


def test_max_stops_none_omits_max_stopovers(httpx_mock):
    """max_stops=None must not add max_stopovers to the request."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    _search(src, max_stops=None)

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert "max_stopovers" not in params


def test_max_stops_zero_sets_max_stopovers(httpx_mock):
    """max_stops=0 sets max_stopovers=0 (direct flights only)."""
    httpx_mock.add_response(json={"data": [], "currency": "AUD"})
    src = TequilaPriceSource(api_key="test-key")
    _search(src, max_stops=0)

    params = dict(httpx_mock.get_requests()[0].url.params)
    assert params["max_stopovers"] == "0"


# ─── S13: Pluggy registration ────────────────────────────────────────────────


def test_tequila_registers_correctly_via_pluggy():
    """TequilaPriceSource registers one search_flights hookimpl with Pluggy."""
    from fly_o_myte.price_sources.hookspecs import build_plugin_manager

    pm = build_plugin_manager()
    pm.register(TequilaPriceSource("k"))
    assert len(pm.hook.search_flights.get_hookimpls()) == 1
