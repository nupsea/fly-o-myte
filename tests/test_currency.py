"""
Tests for the CurrencyConverter (currency.py).

HTTP calls are mocked at the transport boundary via pytest-httpx.
Each test creates a fresh CurrencyConverter() instance to avoid
cross-test cache contamination.
"""

from __future__ import annotations

import time

import pytest

from fly_o_myte.currency import CurrencyConverter

# Shared mock Frankfurter response for USD -> AUD
MOCK_RATE_USD_AUD = {
    "amount": 1.0,
    "base": "USD",
    "date": "2026-03-04",
    "rates": {"AUD": 1.567},
}

MOCK_RATE_SGD_AUD = {
    "amount": 1.0,
    "base": "SGD",
    "date": "2026-03-04",
    "rates": {"AUD": 1.12},
}


class TestGetRate:
    def test_same_currency_returns_one_no_http(self):
        """AUD -> AUD (or any same-currency pair) must return 1.0 without HTTP."""
        converter = CurrencyConverter()
        assert converter.get_rate("AUD", "AUD") == 1.0
        assert converter.get_rate("USD", "USD") == 1.0

    def test_fetches_rate_from_frankfurter(self, httpx_mock):
        """Happy path: rate fetched and returned correctly."""
        httpx_mock.add_response(json=MOCK_RATE_USD_AUD)
        converter = CurrencyConverter()
        rate = converter.get_rate("USD", "AUD")
        assert rate == pytest.approx(1.567)

    def test_request_passes_correct_params(self, httpx_mock):
        """Verify the correct from/to query params are sent."""
        httpx_mock.add_response(json=MOCK_RATE_SGD_AUD)
        converter = CurrencyConverter()
        converter.get_rate("SGD", "AUD")
        req = httpx_mock.get_request()
        assert req is not None
        assert req.url.params["from"] == "SGD"
        assert req.url.params["to"] == "AUD"

    def test_second_call_within_ttl_skips_http(self, httpx_mock):
        """Second call within 24h must use the cache — only one HTTP request queued."""
        httpx_mock.add_response(json=MOCK_RATE_USD_AUD)
        converter = CurrencyConverter()
        # First call: goes to API
        rate1 = converter.get_rate("USD", "AUD")
        # Second call: served from cache — if HTTP were called, pytest-httpx
        # would raise because no second response is queued
        rate2 = converter.get_rate("USD", "AUD")
        assert rate1 == rate2 == pytest.approx(1.567)

    def test_cache_expires_after_ttl(self, httpx_mock, monkeypatch):
        """After TTL expires a second HTTP request is made."""
        httpx_mock.add_response(json=MOCK_RATE_USD_AUD)
        httpx_mock.add_response(json={**MOCK_RATE_USD_AUD, "rates": {"AUD": 1.600}})

        now = time.time()
        call_count = 0

        def _fake_time() -> float:
            nonlocal call_count
            call_count += 1
            # First 2 calls (cache check + store): return now
            # Subsequent calls: return now + 25h (past TTL)
            return now if call_count <= 2 else now + 90001  # 25h

        monkeypatch.setattr("fly_o_myte.currency.time.time", _fake_time)

        converter = CurrencyConverter()
        rate1 = converter.get_rate("USD", "AUD")  # first fetch
        rate2 = converter.get_rate("USD", "AUD")  # past TTL — re-fetch
        assert rate1 == pytest.approx(1.567)
        assert rate2 == pytest.approx(1.600)

    def test_fallback_on_http_500(self, httpx_mock):
        """HTTP 500 must return 1.0 without raising."""
        httpx_mock.add_response(status_code=500)
        converter = CurrencyConverter()
        rate = converter.get_rate("USD", "AUD")
        assert rate == 1.0

    def test_fallback_on_connection_error(self, httpx_mock):
        """Network error must return 1.0 without raising."""
        import httpx as _httpx

        httpx_mock.add_exception(_httpx.ConnectError("connection refused"))
        converter = CurrencyConverter()
        rate = converter.get_rate("USD", "AUD")
        assert rate == 1.0

    def test_case_insensitive(self, httpx_mock):
        """Currency codes are normalised to uppercase before lookup/fetch."""
        httpx_mock.add_response(json=MOCK_RATE_USD_AUD)
        converter = CurrencyConverter()
        rate = converter.get_rate("usd", "aud")
        assert rate == pytest.approx(1.567)


class TestConvertToAud:
    def test_converts_correctly(self, httpx_mock):
        """convert_to_aud multiplies amount by the fetched rate."""
        httpx_mock.add_response(json=MOCK_RATE_USD_AUD)
        converter = CurrencyConverter()
        result = converter.convert_to_aud(100.0, "USD")
        assert result == pytest.approx(100.0 * 1.567)

    def test_aud_to_aud_no_http(self):
        """AUD amount needs no conversion — no HTTP call made."""
        converter = CurrencyConverter()
        result = converter.convert_to_aud(150.0, "AUD")
        assert result == pytest.approx(150.0)

    def test_fallback_returns_original_amount(self, httpx_mock):
        """When API unavailable, fallback rate=1.0 so amount is returned unchanged."""
        httpx_mock.add_response(status_code=503)
        converter = CurrencyConverter()
        result = converter.convert_to_aud(680.0, "SGD")
        assert result == pytest.approx(680.0)
