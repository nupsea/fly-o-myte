"""
insert_stub_snapshot.py — inject a fake price snapshot for manual demo-review testing.

Used during DR-B gate review so you can verify fom check / fom history / fom status
output without needing a real Tequila API key.

Usage:
    uv run python scripts/ralph/insert_stub_snapshot.py <trip_id> [--price 299.0] [--airline QF]

Example:
    fom watch BNE SYD 2026-07-20 2026-07-27 --label "Test"
    uv run python scripts/ralph/insert_stub_snapshot.py 1
    fom check 1
    fom history 1
    fom status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure the repo root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fly_o_myte.config import DepartureWindow, FamilyProfile, get_settings
from fly_o_myte.db.sqlite import (
    PriceSnapshot,
    create_engine_from_path,
    create_tables,
    get_session,
    get_trip,
    insert_snapshot,
)
from fly_o_myte.fees import get_airline_db
from fly_o_myte.price_sources.hookspecs import FlightOffer
from fly_o_myte.true_cost import compute_true_cost


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert a stub price snapshot for testing."
    )
    parser.add_argument("trip_id", type=int, help="Trip ID to insert snapshot for")
    parser.add_argument(
        "--price", type=float, default=299.0, help="Base fare per adult (AUD)"
    )
    parser.add_argument("--airline", default="QF", help="Airline IATA code")
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of snapshots to insert (spread over recent days)",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine_from_path(settings.fly_o_myte_db_path)
    create_tables(engine)

    with get_session(engine) as session:
        trip = get_trip(session, args.trip_id)
        if trip is None:
            print(f"Error: trip {args.trip_id} not found.")
            return 1

        airline_db = get_airline_db()
        fees = airline_db.get(args.airline)
        if fees is None:
            print(f"Warning: airline '{args.airline}' not in database, using QF fees.")
            fees = airline_db.get("QF")

        profile = FamilyProfile(
            adults=trip.adults,
            children=[],
            origin_airport=trip.origin,
            state="QLD",
            bags_per_person=trip.bags_per_person,
            max_stops=trip.max_stops,
            preferred_departure_window=DepartureWindow(earliest_hour=8, latest_hour=18),
        )

        import random
        from datetime import timedelta

        prices = [
            args.price * (1.0 + random.uniform(-0.05, 0.05)) for _ in range(args.count)
        ]

        for i, price in enumerate(prices):
            offer = FlightOffer(
                source="stub",
                airline_code=args.airline,
                flight_number=f"{args.airline}500",
                base_fare_per_adult=price,
                currency="AUD",
                stops=0,
                departure_time="10:30",
                arrival_time="12:10",
                duration_minutes=100,
                price_level_signal="TYPICAL",
                offer_raw={},
            )

            n_sectors = 2 if trip.return_date else 1
            child_ages = profile.child_ages_at(trip.depart_date)
            breakdown = compute_true_cost(
                offer, fees, profile.adults, child_ages, n_sectors
            )

            fetched_at = datetime.now(UTC) - timedelta(days=args.count - 1 - i)

            snap = insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=trip.id,
                    fetched_at=fetched_at.isoformat(),
                    source="stub",
                    airline_code=args.airline,
                    flight_number=f"{args.airline}500",
                    base_fare_per_adult=price,
                    true_family_cost=breakdown.total,
                    true_cost_breakdown=json.dumps(
                        {
                            "base_adults": breakdown.base_adults,
                            "base_children": breakdown.base_children,
                            "bags": breakdown.bags,
                            "seats": breakdown.seats,
                            "infant": breakdown.infant,
                            "total": breakdown.total,
                        }
                    ),
                    price_level_signal="TYPICAL",
                    stops=0,
                    departure_time="10:30",
                    duration_minutes=100,
                    offer_raw="{}",
                ),
            )
            print(
                f"Inserted snapshot {snap.id}: trip={trip.id} airline={args.airline} "
                f"base=${price:.2f} true_cost=${breakdown.total:.2f}"
            )

    print(f"\nDone. Run: fom check {args.trip_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
