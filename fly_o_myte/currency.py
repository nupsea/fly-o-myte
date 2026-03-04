"""
Multi-currency support wrapping the free Frankfurter API (api.frankfurter.app).

Layer 2 — static data/utility. Exchange rates cached in memory for 24 hours.
Falls back to 1.0 (no conversion) if the API is unavailable.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"
_CACHE_TTL_SECONDS = 86400  # 24 hours


class CurrencyConverter:
    """
    Thin wrapper around the Frankfurter API for currency conversion.

    Rates are cached in memory for 24 hours. Returns 1.0 (no conversion) when:
      - from_currency == to_currency
      - from_currency == 'AUD' (already in target currency)
      - The API is unavailable for any reason
    """

    def __init__(self) -> None:
        self._rates: dict[str, float] = {}
        self._timestamps: dict[str, float] = {}

    def get_rate(self, from_currency: str, to_currency: str = "AUD") -> float:
        """
        Return the exchange rate from from_currency to to_currency.

        Returns 1.0 if the currencies are the same or the API is unavailable.
        Rate is cached in memory for 24 hours.
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return 1.0

        cache_key = f"{from_currency}_{to_currency}"
        now = time.time()
        if (
            cache_key in self._rates
            and now - self._timestamps[cache_key] < _CACHE_TTL_SECONDS
        ):
            return self._rates[cache_key]

        try:
            response = httpx.get(
                _FRANKFURTER_URL,
                params={"from": from_currency, "to": to_currency},
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            rate = float(data["rates"][to_currency])
            self._rates[cache_key] = rate
            self._timestamps[cache_key] = now
            return rate
        except Exception:
            logger.warning(
                "Failed to fetch exchange rate %s -> %s, using 1.0 fallback",
                from_currency,
                to_currency,
            )
            return 1.0

    def convert_to_aud(self, amount: float, currency: str) -> float:
        """Convert amount from currency to AUD using the cached exchange rate."""
        return amount * self.get_rate(currency, "AUD")


# Module-level singleton — created once per process
_converter: CurrencyConverter | None = None


def get_converter() -> CurrencyConverter:
    global _converter
    if _converter is None:
        _converter = CurrencyConverter()
    return _converter
