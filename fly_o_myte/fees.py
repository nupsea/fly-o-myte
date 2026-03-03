"""
Airline fee database loader.

Reads travo/data/airlines.json and provides helpers for computing
bag fees, seat selection fees, and infant fees per airline.

This is static data — updated 2-3x per year when airlines change policies.
Run `travo data-version` to see when the database was last updated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path


@dataclass(frozen=True)
class AirlineFees:
    iata: str
    name: str
    family_score: int            # 0–100

    # Domestic bag fees (AUD)
    bag1_fee: float              # first checked bag — standard fare
    bag1_fee_lite: float         # first bag on budget/lite fares (if different)
    bag1_weight_kg: int
    bag2_fee: float

    # Seat selection
    seat_selection_fee: float    # per seat, 0 = free
    seat_selection_fee_lite: float  # on lite fares, if different

    # Family seating
    family_seating_guaranteed: bool

    # Infant fees
    infant_lap_fee_domestic: float     # AUD per sector (0 if free)
    infant_lap_fee_intl: float         # AUD per sector international

    # On-time performance (0–100)
    on_time_pct: int

    notes: str = ""

    def bag_fee(self, n_bags: int, fare_type: str = "standard") -> float:
        """
        Compute bag fees for n_bags checked bags.
        fare_type: "standard" | "lite" | "starter_plus"
        """
        if n_bags == 0:
            return 0.0
        first = self.bag1_fee_lite if fare_type == "lite" else self.bag1_fee
        if n_bags == 1:
            return first
        return first + (n_bags - 1) * self.bag2_fee

    def seat_fee(self, n_seats: int, fare_type: str = "standard") -> float:
        """Compute seat selection fees."""
        fee = self.seat_selection_fee_lite if fare_type == "lite" else self.seat_selection_fee
        return fee * n_seats

    def infant_domestic_fee(self, n_infants: int, n_sectors: int = 2) -> float:
        """
        Total infant lap fee for n_infants on n_sectors.
        Jetstar charges per sector; Qantas charges 0.
        n_sectors=2 for a return trip (outbound + inbound).
        """
        return self.infant_lap_fee_domestic * n_infants * n_sectors


def _load_raw() -> dict:
    """Load airlines.json from the package data directory."""
    data_path = files("fly_o_myte") / "data" / "airlines.json"
    with data_path.open() as f:
        return json.load(f)


def _parse_airline(raw: dict, iata: str) -> AirlineFees:
    dom = raw.get("domestic", {})
    return AirlineFees(
        iata=iata,
        name=raw["name"],
        family_score=raw.get("family_score", 50),
        bag1_fee=dom.get("bag1_fee", dom.get("bag1_fee_economy_choice", 45)),
        bag1_fee_lite=dom.get(
            "bag1_fee_lite",
            dom.get("bag1_fee_starter", dom.get("bag1_fee_economy_lite", dom.get("bag1_fee", 45))),
        ),
        bag1_weight_kg=dom.get("bag1_weight_kg", 23),
        bag2_fee=dom.get("bag2_fee", 60),
        seat_selection_fee=dom.get(
            "seat_selection_fee",
            dom.get("seat_selection_fee_choice", 0),
        ),
        seat_selection_fee_lite=dom.get(
            "seat_selection_fee",
            dom.get("seat_selection_fee_lite", dom.get("seat_selection_fee", 0)),
        ),
        family_seating_guaranteed=dom.get("family_seating_guaranteed", False),
        infant_lap_fee_domestic=dom.get(
            "infant_lap_fee_domestic_aud",
            dom.get("infant_lap_fee_per_sector_aud", 0),
        ),
        infant_lap_fee_intl=dom.get("infant_lap_fee_intl_shorthaul_aud", 0),
        on_time_pct=raw.get("on_time_pct", 70),
        notes=dom.get("notes", ""),
    )


class AirlineDatabase:
    def __init__(self) -> None:
        raw = _load_raw()
        self._db: dict[str, AirlineFees] = {}
        self._version: str = raw.get("_version", "unknown")
        self._last_updated: str = raw.get("_last_updated", "unknown")

        for key, value in raw.items():
            if key.startswith("_") or not isinstance(value, dict):
                continue
            if "name" in value:
                self._db[key] = _parse_airline(value, key)

    def get(self, iata: str) -> AirlineFees | None:
        return self._db.get(iata.upper())

    def get_or_default(self, iata: str) -> AirlineFees:
        """
        Return airline fees or a conservative default for unknown carriers.
        Conservative default: charges for everything (safe to overestimate).
        """
        return self._db.get(iata.upper()) or AirlineFees(
            iata=iata,
            name=f"Unknown ({iata})",
            family_score=50,
            bag1_fee=40,
            bag1_fee_lite=40,
            bag1_weight_kg=23,
            bag2_fee=60,
            seat_selection_fee=20,
            seat_selection_fee_lite=20,
            family_seating_guaranteed=False,
            infant_lap_fee_domestic=0,
            infant_lap_fee_intl=0,
            on_time_pct=70,
            notes="Unknown airline — using conservative default fees.",
        )

    @property
    def version(self) -> str:
        return self._version

    @property
    def last_updated(self) -> str:
        return self._last_updated

    def all_codes(self) -> list[str]:
        return list(self._db.keys())


# Module-level singleton — loaded once
_db: AirlineDatabase | None = None


def get_airline_db() -> AirlineDatabase:
    global _db
    if _db is None:
        _db = AirlineDatabase()
    return _db
