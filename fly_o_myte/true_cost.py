"""
True family cost calculator.

Computes the full cost a family actually pays — base fares + bag fees
+ seat selection fees + infant fees — so that a $99 Jetstar fare and
a $149 Qantas fare are compared on equal footing.

All inputs are passed explicitly. No I/O, no side effects.
Fully testable without any mocking.

Key rules:
  - Bag fees: per person, per leg (we quote return round-trip by default)
  - Seat selection: per person per leg
  - Infant fees: Jetstar charges per SECTOR (each one-way leg)
    Qantas / Rex charge nothing for domestic lap infants
  - Children age 2–11 need a seat (priced same as adults in most APIs)
  - Children age 0–1 are lap infants (no seat purchased)
  - Child fares from APIs are typically ~90% of adult base fare
    (estimated if not returned separately)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fly_o_myte.fees import AirlineFees


@dataclass(frozen=True)
class TrueCostBreakdown:
    """Itemised cost breakdown for a family trip."""

    base_fare_adults: float  # AUD — adults × base fare per adult
    base_fare_children: float  # AUD — seated children × estimated child fare
    bag_fees: float  # AUD — all bags for all pax
    seat_fees: float  # AUD — seat selection for all pax
    infant_fees: float  # AUD — lap infant fees (may be 0)
    total: float  # AUD — sum of all above

    def as_dict(self) -> dict:
        return {
            "base_adults": round(self.base_fare_adults, 2),
            "base_children": round(self.base_fare_children, 2),
            "bags": round(self.bag_fees, 2),
            "seats": round(self.seat_fees, 2),
            "infant": round(self.infant_fees, 2),
            "total": round(self.total, 2),
        }


def compute_true_cost(
    airline: AirlineFees,
    base_fare_per_adult: float,
    adults: int,
    child_ages: list[int],
    bags_per_person: int,
    depart_date: date,
    return_date: date | None,
    fare_type: str = "standard",
) -> TrueCostBreakdown:
    """
    Compute the true family cost for a given flight offer.

    Args:
        airline: AirlineFees for the operating carrier.
        base_fare_per_adult: Fare per adult from the API (AUD).
        adults: Number of adults.
        child_ages: Ages of children at the departure date (not DOB —
                    caller uses FamilyProfile.child_ages_at(depart_date)).
        bags_per_person: Checked bags per travelling person.
        depart_date: Outbound departure date.
        return_date: Return date (None = one-way).
        fare_type: "standard" | "lite" — affects bag and seat fee tier.

    Returns:
        TrueCostBreakdown with itemised and total AUD cost.
    """
    n_legs = 2 if return_date else 1
    lap_infants = sum(1 for age in child_ages if age < 2)
    seated_children = sum(1 for age in child_ages if 2 <= age < 12)
    total_seated_pax = adults + seated_children

    # Base fares
    base_adults = base_fare_per_adult * adults
    # Child fares are typically ~90% of adult fare (API may not return separately)
    child_fare_per_child = base_fare_per_adult * 0.90
    base_children = child_fare_per_child * seated_children

    # Bag fees — charged per person per leg for return trips
    # Most Australian airlines charge per direction (not round-trip bundled)
    bag_fees = airline.bag_fee(bags_per_person, fare_type) * total_seated_pax * n_legs

    # Seat selection — per seat per leg
    seat_fees = airline.seat_fee(total_seated_pax, fare_type) * n_legs

    # Infant fees — domestic only in Phase 1
    # Jetstar: per sector per infant (sector = each one-way leg)
    # Qantas / Rex: free domestic
    infant_fees = airline.infant_domestic_fee(lap_infants, n_sectors=n_legs)

    total = base_adults + base_children + bag_fees + seat_fees + infant_fees

    return TrueCostBreakdown(
        base_fare_adults=base_adults,
        base_fare_children=base_children,
        bag_fees=bag_fees,
        seat_fees=seat_fees,
        infant_fees=infant_fees,
        total=total,
    )


def compute_family_score(
    airline: AirlineFees,
    true_cost: float,
    avg_cost_on_route: float,
    stops: int,
    departure_hour: int,
    preferred_earliest: int = 8,
    preferred_latest: int = 18,
) -> float:
    """
    Compute the family flight score (0–100).

    Weights:
      - True cost vs route average:  40%
      - Stops:                        25%
      - Departure time quality:       15%
      - Airline family rating:        20%

    Higher is better.
    """
    # Cost score: 100 if at or below average, scales down up to 50% above
    if avg_cost_on_route > 0:
        cost_ratio = true_cost / avg_cost_on_route
        cost_score = max(0.0, 1.0 - max(0.0, cost_ratio - 1.0) * 2.0) * 100
    else:
        cost_score = 50.0

    # Stops score: 100 = nonstop, 60 = 1 stop, 20 = 2+ stops
    stops_score = {0: 100, 1: 60}.get(stops, 20)

    # Departure time score: penalise early/late departures
    if preferred_earliest <= departure_hour <= preferred_latest:
        time_score = 100.0
    elif departure_hour < preferred_earliest:
        penalty = (preferred_earliest - departure_hour) * 15
        time_score = max(0.0, 100.0 - penalty)
    else:
        penalty = (departure_hour - preferred_latest) * 15
        time_score = max(0.0, 100.0 - penalty)

    # Airline family score
    airline_score = float(airline.family_score)

    return round(
        cost_score * 0.40
        + stops_score * 0.25
        + time_score * 0.15
        + airline_score * 0.20,
        1,
    )
