"""
Airline fee database loader.

Reads fly_o_myte/data/airlines.json and provides helpers for computing
bag fees, seat selection fees, and infant fees per airline.

This is static data — updated 2-3x per year when airlines change policies.
Run `fom data-version` to see when the database was last updated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class AirlineFees:
    iata: str
    name: str
    family_score: int  # 0–100

    # Bag fees (AUD)
    bag1_fee: float  # first checked bag — standard fare
    bag1_fee_lite: float  # first bag on budget/lite fares (if different)
    bag1_weight_kg: int
    bag2_fee: float

    # Seat selection
    seat_selection_fee: float  # per seat, 0 = free
    seat_selection_fee_lite: float  # on lite fares, if different

    # Family seating
    family_seating_guaranteed: bool

    # Infant fees (per sector)
    infant_lap_fee: float

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
        fee = (
            self.seat_selection_fee_lite
            if fare_type == "lite"
            else self.seat_selection_fee
        )
        return fee * n_seats

    def infant_fee(self, n_infants: int, n_sectors: int = 2) -> float:
        """
        Total infant lap fee for n_infants on n_sectors.
        n_sectors=2 for a return trip (outbound + inbound).
        """
        return self.infant_lap_fee * n_infants * n_sectors


@dataclass(frozen=True)
class AirlineFeeBundle:
    iata: str
    name: str
    family_score: int
    on_time_pct: int
    domestic: AirlineFees
    international: AirlineFees


def _load_raw() -> dict:
    """Load airlines.json from the package data directory."""
    data_path = files("fly_o_myte") / "data" / "airlines.json"
    with data_path.open() as f:
        return json.load(f)


def _parse_fees(
    section: dict, iata: str, name: str, is_intl: bool = False
) -> AirlineFees:
    """Parse a domestic or international section into AirlineFees."""
    return AirlineFees(
        iata=iata,
        name=name,
        family_score=50,  # placeholder, unused in sub-object
        bag1_fee=section.get("bag1_fee", section.get("bag1_fee_economy_choice", 45)),
        bag1_fee_lite=section.get(
            "bag1_fee_lite",
            section.get(
                "bag1_fee_starter",
                section.get("bag1_fee_economy_lite", section.get("bag1_fee", 45)),
            ),
        ),
        bag1_weight_kg=section.get("bag1_weight_kg", 23),
        bag2_fee=section.get("bag2_fee", 60),
        seat_selection_fee=section.get(
            "seat_selection_fee",
            section.get("seat_selection_fee_choice", 0),
        ),
        seat_selection_fee_lite=section.get(
            "seat_selection_fee",
            section.get(
                "seat_selection_fee_lite", section.get("seat_selection_fee", 0)
            ),
        ),
        family_seating_guaranteed=section.get("family_seating_guaranteed", False),
        infant_lap_fee=section.get(
            "infant_lap_fee_intl_shorthaul_aud"
            if is_intl
            else "infant_lap_fee_domestic_aud",
            section.get("infant_lap_fee_per_sector_aud", 0),
        ),
        on_time_pct=70,  # placeholder
        notes=section.get("notes", ""),
    )


def _parse_airline(raw: dict, iata: str) -> AirlineFeeBundle:
    name = raw["name"]
    family_score = raw.get("family_score", 50)
    on_time_pct = raw.get("on_time_pct", 70)

    dom_raw = raw.get("domestic", raw.get("international", {}))
    intl_raw = raw.get("international", raw.get("domestic", {}))

    return AirlineFeeBundle(
        iata=iata,
        name=name,
        family_score=family_score,
        on_time_pct=on_time_pct,
        domestic=_parse_fees(dom_raw, iata, name, is_intl=False),
        international=_parse_fees(intl_raw, iata, name, is_intl=True),
    )


class AirlineDatabase:
    def __init__(self) -> None:
        raw = _load_raw()
        self._db: dict[str, AirlineFeeBundle] = {}
        self._version: str = raw.get("_version", "unknown")
        self._last_updated: str = raw.get("_last_updated", "unknown")

        for key, value in raw.items():
            if key.startswith("_") or not isinstance(value, dict):
                continue
            if "name" in value:
                self._db[key] = _parse_airline(value, key)

    def get(self, iata: str) -> AirlineFeeBundle | None:
        return self._db.get(iata.upper())

    def get_or_default(self, iata: str) -> AirlineFeeBundle:
        """
        Return airline fees or a conservative default for unknown carriers.
        """
        bundle = self._db.get(iata.upper())
        if bundle:
            return bundle

        # Create a default bundle
        default_fees = AirlineFees(
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
            infant_lap_fee=0,
            on_time_pct=70,
            notes="Unknown airline — using conservative default fees.",
        )
        return AirlineFeeBundle(
            iata=iata,
            name=f"Unknown ({iata})",
            family_score=50,
            on_time_pct=70,
            domestic=default_fees,
            international=default_fees,
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
