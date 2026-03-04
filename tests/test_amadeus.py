"""
Unit tests for AmadeusPriceSource.get_price_level_signal().

All HTTP calls are mocked at the transport boundary via pytest-httpx.
No real API calls are made.
"""

from __future__ import annotations

from datetime import date

from fly_o_myte.price_sources.amadeus import AmadeusPriceSource

# ─── shared mock data ─────────────────────────────────────────────────────────

_TOKEN_RESPONSE = {"access_token": "test-token-123", "expires_in": 1799}

# priceMetrics bands in ascending price order, each with a quartileRanking
_PRICE_METRICS_RESPONSE = {
    "data": [
        {
            "type": "flight-price-analysis",
            "origin": {"iataCode": "BNE"},
            "destination": {"iataCode": "SYD"},
            "priceMetrics": [
                {"amount": "300.00", "quartileRanking": "LOW"},
                {"amount": "450.00", "quartileRanking": "MEDIUM_LOW"},
                {"amount": "600.00", "quartileRanking": "MEDIUM"},
                {"amount": "750.00", "quartileRanking": "MEDIUM_HIGH"},
                {"amount": "900.00", "quartileRanking": "HIGH"},
            ],
        }
    ]
}


# ─── helpers ──────────────────────────────────────────────────────────────────


def _src() -> AmadeusPriceSource:
    """Create a fresh AmadeusPriceSource with test credentials."""
    return AmadeusPriceSource(client_id="test-id", client_secret="test-secret")


def _signal(src: AmadeusPriceSource, price_aud: float = 400.0) -> str | None:
    return src.get_price_level_signal("BNE", "SYD", date(2026, 7, 20), price_aud)


# ─── signal mapping — LOW band ────────────────────────────────────────────────


def test_price_in_low_band_returns_low(httpx_mock):
    """price_aud below LOW threshold → 'LOW'."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    src = _src()
    assert _signal(src, price_aud=250.0) == "LOW"


def test_medium_low_quartile_maps_to_low(httpx_mock):
    """MEDIUM_LOW quartileRanking → 'LOW'."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    src = _src()
    # price 400 > LOW(300) → falls into MEDIUM_LOW(450) band → signal 'LOW'
    assert _signal(src, price_aud=400.0) == "LOW"


# ─── signal mapping — TYPICAL band ───────────────────────────────────────────


def test_price_in_medium_band_returns_typical(httpx_mock):
    """price_aud in MEDIUM band → 'TYPICAL'."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    src = _src()
    # price 500 > MEDIUM_LOW(450), ≤ MEDIUM(600) → 'TYPICAL'
    assert _signal(src, price_aud=500.0) == "TYPICAL"


def test_medium_high_quartile_maps_to_typical(httpx_mock):
    """MEDIUM_HIGH quartileRanking → 'TYPICAL'."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    src = _src()
    # price 700 > MEDIUM(600), ≤ MEDIUM_HIGH(750) → 'TYPICAL'
    assert _signal(src, price_aud=700.0) == "TYPICAL"


# ─── signal mapping — HIGH band ───────────────────────────────────────────────


def test_price_in_high_band_returns_high(httpx_mock):
    """price_aud in HIGH band → 'HIGH'."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    src = _src()
    # price 800 > MEDIUM_HIGH(750), ≤ HIGH(900) → 'HIGH'
    assert _signal(src, price_aud=800.0) == "HIGH"


def test_price_above_all_bands_returns_high(httpx_mock):
    """price_aud exceeding all priceMetrics bands → 'HIGH' fallback."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    src = _src()
    # price 1500 > all bands → 'HIGH'
    assert _signal(src, price_aud=1500.0) == "HIGH"


# ─── graceful degradation ─────────────────────────────────────────────────────


def test_returns_none_on_auth_failure(httpx_mock):
    """Auth failure (401) → PriceSourceError caught → None returned."""
    httpx_mock.add_response(status_code=401, text="Unauthorized")
    src = _src()
    assert _signal(src) is None


def test_returns_none_on_non_200_analysis(httpx_mock):
    """Auth succeeds but analysis endpoint returns non-200 → None."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(status_code=404, text="Not Found")
    src = _src()
    assert _signal(src) is None


def test_returns_none_on_empty_data(httpx_mock):
    """Analysis returns empty data list → None."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json={"data": []})
    src = _src()
    assert _signal(src) is None


def test_returns_none_on_empty_price_metrics(httpx_mock):
    """Analysis returns data item with empty priceMetrics → None."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json={"data": [{"priceMetrics": []}]})
    src = _src()
    assert _signal(src) is None


# ─── BNE → SIN international route ───────────────────────────────────────────


_PRICE_METRICS_BNE_SIN = {
    "data": [
        {
            "type": "flight-price-analysis",
            "origin": {"iataCode": "BNE"},
            "destination": {"iataCode": "SIN"},
            "priceMetrics": [
                {"amount": "850.00", "quartileRanking": "LOW"},
                {"amount": "1100.00", "quartileRanking": "MEDIUM_LOW"},
                {"amount": "1400.00", "quartileRanking": "MEDIUM"},
                {"amount": "1700.00", "quartileRanking": "MEDIUM_HIGH"},
                {"amount": "2100.00", "quartileRanking": "HIGH"},
            ],
        }
    ]
}


def test_bne_sin_price_analysis_returns_low(httpx_mock):
    """BNE→SIN: price below LOW threshold returns 'LOW' signal."""
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_BNE_SIN)
    src = _src()
    result = src.get_price_level_signal("BNE", "SIN", date(2026, 9, 18), 700.0)
    assert result == "LOW"


# ─── token caching ────────────────────────────────────────────────────────────


def test_token_not_refetched_when_cached(httpx_mock):
    """Token cached within TTL — only 1 auth POST for 2 signal calls."""
    # 1 token fetch + 2 analysis calls
    httpx_mock.add_response(json=_TOKEN_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)
    httpx_mock.add_response(json=_PRICE_METRICS_RESPONSE)

    src = _src()

    sig1 = _signal(src, price_aud=400.0)
    sig2 = _signal(src, price_aud=400.0)

    post_requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert len(post_requests) == 1, "Token was re-fetched unexpectedly"
    assert sig1 is not None
    assert sig2 is not None
