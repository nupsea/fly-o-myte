"""
Pluggy hook specifications for the price source plugin system.

Any module can register a price source by implementing these hooks
and registering with the plugin manager:

    pm = build_plugin_manager()
    pm.register(MyPriceSource())

The tracker calls pm.hook.search_flights(...) which returns a list of
results from all registered providers. The tracker selects the best
result based on family score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pluggy
from pydantic import Field

APP_NAME = "fly_o_myte"
hookspec = pluggy.HookspecMarker(APP_NAME)
hookimpl = pluggy.HookimplMarker(APP_NAME)


@dataclass
class FlightOffer:
    """Normalised flight offer returned by any price source."""

    source: str  # "tequila" | "amadeus" | ...
    airline_code: str  # IATA carrier code
    flight_number: str | None  # e.g. "QF500"
    base_fare_per_adult: float  # AUD (base fare only, no ancillary fees)
    currency: str  # "AUD"
    stops: int
    departure_time: str  # "HH:MM" (local)
    arrival_time: str  # "HH:MM" (local)
    return_departure_time: str | None = None  # "HH:MM" (local)
    return_arrival_time: str | None = None  # "HH:MM" (local)
    duration_minutes: int = 0
    price_level_signal: str | None = (
        None  # "LOW" | "TYPICAL" | "HIGH" if API provides it
    )
    offer_raw: dict = Field(default_factory=dict)  # full API response for debugging


class PriceSourceSpec:
    """
    Hook specifications for fly-o-myte price source plugins.

    Implement these methods and register your class with the plugin manager
    to add a new flight data source.
    """

    @hookspec
    def source_name(self) -> str:
        """Unique identifier for this price source, e.g. 'tequila'."""
        return ""  # hookspec — pluggy invokes implementations, never the spec

    @hookspec
    def supports_route(self, origin: str, destination: str) -> bool:
        """
        Return True if this source can search flights for this route.
        Enables graceful fallback when a source doesn't cover a route.
        """
        return False  # hookspec — pluggy invokes implementations

    @hookspec
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
        Search for available flights matching the given parameters.

        Returns a list of FlightOffer objects (cheapest first preferred).
        Return empty list if no results found.
        Raise PriceSourceError on connection/auth failures.
        """
        return []  # hookspec — pluggy invokes implementations


class PriceSourceError(Exception):
    """Raised when a price source call fails."""

    def __init__(
        self, source: str, message: str, status_code: int | None = None
    ) -> None:
        self.source = source
        self.status_code = status_code
        super().__init__(f"[{source}] {message}")


def build_plugin_manager() -> pluggy.PluginManager:
    """
    Create and configure the plugin manager.
    Providers are registered in tracker.py at startup.
    """
    pm = pluggy.PluginManager(APP_NAME)
    pm.add_hookspecs(PriceSourceSpec)
    return pm
