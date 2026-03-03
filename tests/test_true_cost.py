"""
Tests for true family cost calculator (true_cost.py).

All pure function tests — no I/O required.
Critical test cases: Jetstar per-sector infant fee, Qantas free inclusions.
"""

from __future__ import annotations

from datetime import date

import pytest

from fly_o_myte.true_cost import compute_family_score, compute_true_cost


class TestQantasCost:
    """Qantas: bags included, zero seat fees, free domestic infant."""

    def test_qantas_no_bag_fee_standard(self, qantas_fees):
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.bag_fees == 0.0

    def test_qantas_no_seat_fee_standard(self, qantas_fees):
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.seat_fees == 0.0

    def test_qantas_free_domestic_infant(self, qantas_fees):
        """Lap infant (age 1) on Qantas domestic — zero infant fee."""
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[1],  # lap infant
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.infant_fees == 0.0

    def test_qantas_two_adults_return(self, qantas_fees):
        """2 adults, return trip, no children — only base fare."""
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.base_fare_adults == pytest.approx(298.0)
        assert result.total == pytest.approx(298.0)

    def test_qantas_family_of_four_return(self, qantas_fees):
        """2 adults + 2 children (age 5, 8) — includes child fares, no ancillary fees."""
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[5, 8],
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.bag_fees == 0.0
        assert result.seat_fees == 0.0
        assert result.infant_fees == 0.0
        # 2 adults × $149 + 2 children × ($149 × 0.90)
        expected = 2 * 149.0 + 2 * 149.0 * 0.90
        assert result.total == pytest.approx(expected)


class TestJetstarCost:
    """Jetstar: bag fees per person per leg, $35 infant fee per SECTOR."""

    def test_jetstar_bag_fee_per_pax_per_leg(self, jetstar_fees):
        """Return trip: bags charged per person, per direction."""
        result = compute_true_cost(
            airline=jetstar_fees,
            base_fare_per_adult=99.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        # 2 adults × $55/bag × 2 legs
        assert result.bag_fees == pytest.approx(2 * 55.0 * 2)

    def test_jetstar_infant_fee_per_sector(self, jetstar_fees):
        """Jetstar charges $35 per infant per sector (sector = one-way leg)."""
        result = compute_true_cost(
            airline=jetstar_fees,
            base_fare_per_adult=99.0,
            adults=2,
            child_ages=[1],  # one lap infant
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        # Return trip = 2 sectors × 1 infant × $35
        assert result.infant_fees == pytest.approx(2 * 1 * 35.0)

    def test_jetstar_one_way_infant_one_sector(self, jetstar_fees):
        """One-way trip: infant charged for 1 sector only."""
        result = compute_true_cost(
            airline=jetstar_fees,
            base_fare_per_adult=99.0,
            adults=2,
            child_ages=[1],
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=None,  # one-way
        )
        assert result.infant_fees == pytest.approx(1 * 1 * 35.0)

    def test_jetstar_seat_fee_per_pax_per_leg(self, jetstar_fees):
        """Seat selection: $8 per seat per leg."""
        result = compute_true_cost(
            airline=jetstar_fees,
            base_fare_per_adult=99.0,
            adults=2,
            child_ages=[5],  # one seated child
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        # 3 seated pax × $8 × 2 legs
        assert result.seat_fees == pytest.approx(3 * 8.0 * 2)

    def test_jetstar_vs_qantas_family_of_four(self, qantas_fees, jetstar_fees):
        """
        Classic comparison: Jetstar $99 vs Qantas $149 for family of 4 (2A+2C+1 infant).
        Jetstar must be MORE expensive once fees are included.
        """
        family = {
            "adults": 2,
            "child_ages": [5, 8, 1],
            "bags_per_person": 1,
            "depart_date": date(2026, 7, 20),
            "return_date": date(2026, 7, 27),
        }

        qantas = compute_true_cost(
            airline=qantas_fees, base_fare_per_adult=149.0, **family
        )
        jetstar = compute_true_cost(
            airline=jetstar_fees, base_fare_per_adult=99.0, **family
        )

        assert jetstar.total > qantas.total, (
            f"Jetstar ${jetstar.total:.0f} should be > Qantas ${qantas.total:.0f} "
            "once bags + seats + infant fees are included"
        )


class TestChildAgeClassification:
    """Age at travel date determines lap infant vs seated child."""

    def test_age_2_is_seated_child_not_infant(self, qantas_fees):
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[2],  # exactly 2 = seated child
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.infant_fees == 0.0
        assert result.base_fare_children > 0  # child fare charged

    def test_age_1_is_lap_infant(self, qantas_fees):
        result = compute_true_cost(
            airline=qantas_fees,
            base_fare_per_adult=149.0,
            adults=2,
            child_ages=[1],  # age 1 = lap infant
            bags_per_person=1,
            depart_date=date(2026, 7, 20),
            return_date=date(2026, 7, 27),
        )
        assert result.base_fare_children == 0.0  # no seat purchased
        assert result.infant_fees == 0.0  # Qantas free domestic


class TestInternationalCost:
    """International airlines: verify bag and infant fees load and compute correctly."""

    def test_sq_bags_included_no_bag_fee(self):
        """Singapore Airlines: 30kg bag included, bag_fees must be zero."""
        from fly_o_myte.fees import get_airline_db

        sq = get_airline_db().get("SQ")
        assert sq is not None, "SQ must be present in airline DB"
        result = compute_true_cost(
            airline=sq,
            base_fare_per_adult=680.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 9, 18),
            return_date=date(2026, 9, 28),
        )
        assert result.bag_fees == 0.0

    def test_sq_infant_fee_per_sector_return_trip(self):
        """SQ infant fee ($55/sector) × 1 infant × 2 sectors = $110 for a return trip."""
        from fly_o_myte.fees import get_airline_db

        sq = get_airline_db().get("SQ")
        assert sq is not None
        result = compute_true_cost(
            airline=sq,
            base_fare_per_adult=680.0,
            adults=2,
            child_ages=[1],  # one lap infant
            bags_per_person=1,
            depart_date=date(2026, 9, 18),
            return_date=date(2026, 9, 28),
        )
        assert result.infant_fees == pytest.approx(55.0 * 1 * 2)

    def test_ek_bags_included_no_bag_fee(self):
        """Emirates: 23kg bag included on standard economy, bag_fees must be zero."""
        from fly_o_myte.fees import get_airline_db

        ek = get_airline_db().get("EK")
        assert ek is not None, "EK must be present in airline DB"
        result = compute_true_cost(
            airline=ek,
            base_fare_per_adult=950.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 11, 20),
            return_date=date(2026, 12, 4),
        )
        assert result.bag_fees == 0.0

    def test_ek_seat_selection_fee_applied(self):
        """Emirates: $25 seat fee per seat per leg — 2 adults return = $100 total."""
        from fly_o_myte.fees import get_airline_db

        ek = get_airline_db().get("EK")
        assert ek is not None
        result = compute_true_cost(
            airline=ek,
            base_fare_per_adult=950.0,
            adults=2,
            child_ages=[],
            bags_per_person=1,
            depart_date=date(2026, 11, 20),
            return_date=date(2026, 12, 4),
        )
        # 2 adults × $25/seat × 2 legs
        assert result.seat_fees == pytest.approx(2 * 25.0 * 2)

    def test_all_twelve_international_carriers_load(self):
        """All 12 required international carriers must be present in the DB."""
        from fly_o_myte.fees import get_airline_db

        db = get_airline_db()
        for iata in (
            "SQ",
            "EK",
            "CX",
            "NZ",
            "QR",
            "TG",
            "NH",
            "JL",
            "BA",
            "MH",
            "GA",
            "AI",
        ):
            airline = db.get(iata)
            assert airline is not None, f"{iata} missing from airline DB"
            assert airline.bag1_fee >= 0, f"{iata} bag1_fee invalid"
            assert 0 <= airline.family_score <= 100, f"{iata} family_score out of range"


class TestFamilyScore:
    def test_nonstop_qantas_scores_high(self, qantas_fees):
        score = compute_family_score(
            airline=qantas_fees,
            true_cost=1200.0,
            avg_cost_on_route=1400.0,
            stops=0,
            departure_hour=10,
        )
        assert score > 75  # nonstop + Qantas + below average = high score

    def test_one_stop_scores_lower_than_nonstop(self, qantas_fees):
        nonstop = compute_family_score(
            airline=qantas_fees,
            true_cost=1400.0,
            avg_cost_on_route=1400.0,
            stops=0,
            departure_hour=10,
        )
        one_stop = compute_family_score(
            airline=qantas_fees,
            true_cost=1400.0,
            avg_cost_on_route=1400.0,
            stops=1,
            departure_hour=10,
        )
        assert nonstop > one_stop

    def test_early_morning_departure_penalised(self, qantas_fees):
        preferred = compute_family_score(
            airline=qantas_fees,
            true_cost=1400.0,
            avg_cost_on_route=1400.0,
            stops=0,
            departure_hour=10,
        )
        early = compute_family_score(
            airline=qantas_fees,
            true_cost=1400.0,
            avg_cost_on_route=1400.0,
            stops=0,
            departure_hour=5,
        )
        assert preferred > early

    def test_score_in_range(self, jetstar_fees):
        score = compute_family_score(
            airline=jetstar_fees,
            true_cost=1600.0,
            avg_cost_on_route=1400.0,
            stops=1,
            departure_hour=7,
        )
        assert 0 <= score <= 100
