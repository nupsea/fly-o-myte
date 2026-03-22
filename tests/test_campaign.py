"""
Tests for the TripCampaign entity and campaign-aware features.

Covers:
  - Campaign CRUD (create, list, get, update)
  - Trip-to-campaign linking
  - Date change preserves history (archive instead of delete)
  - Campaign-level snapshot aggregation
  - Recency-weighted recommender integration
  - Migration backfill for orphan trips
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import create_engine

from fly_o_myte.db.sqlite import (
    PriceSnapshot,
    Trip,
    TripCampaign,
    archive_trip,
    create_tables,
    get_active_variant,
    get_campaign,
    get_campaign_snapshots,
    get_campaign_variants,
    get_session,
    insert_campaign,
    insert_snapshot,
    insert_trip,
    list_campaigns,
)
from fly_o_myte.recommender import SnapshotPoint, build_campaign_snapshots


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def campaign_engine():
    """Fresh in-memory engine for campaign tests."""
    engine = create_engine("sqlite:///:memory:")
    create_tables(engine)
    return engine


@pytest.fixture
def campaign_session(campaign_engine):
    with get_session(campaign_engine) as session:
        yield session


@pytest.fixture
def sample_campaign(campaign_session) -> TripCampaign:
    return insert_campaign(
        campaign_session,
        TripCampaign(
            name="Dec India Trip",
            origin="BNE",
            destination="BLR",
            budget_target_aud=3000.0,
            cron_schedule="0 7 * * *",
        ),
    )


# ─── Campaign CRUD ────────────────────────────────────────────────────────────


class TestCampaignCRUD:
    def test_create_campaign(self, campaign_session):
        campaign = insert_campaign(
            campaign_session,
            TripCampaign(name="Easter Trip", origin="BNE", destination="SYD"),
        )
        assert campaign.id is not None
        assert campaign.name == "Easter Trip"
        assert campaign.status == "active"
        assert campaign.notes == ""

    def test_list_campaigns(self, campaign_session, sample_campaign):
        campaigns = list_campaigns(campaign_session)
        assert len(campaigns) >= 1
        assert any(c.name == "Dec India Trip" for c in campaigns)

    def test_list_campaigns_excludes_cancelled(self, campaign_session):
        c = insert_campaign(
            campaign_session,
            TripCampaign(name="Cancelled Trip", origin="SYD", destination="MEL"),
        )
        c.status = "cancelled"
        campaign_session.add(c)
        campaign_session.commit()

        campaigns = list_campaigns(campaign_session, include_cancelled=False)
        assert not any(c2.name == "Cancelled Trip" for c2 in campaigns)

        all_campaigns = list_campaigns(campaign_session, include_cancelled=True)
        assert any(c2.name == "Cancelled Trip" for c2 in all_campaigns)

    def test_get_campaign(self, campaign_session, sample_campaign):
        fetched = get_campaign(campaign_session, sample_campaign.id)
        assert fetched is not None
        assert fetched.name == "Dec India Trip"

    def test_get_campaign_missing(self, campaign_session):
        assert get_campaign(campaign_session, 99999) is None


# ─── Trip-to-Campaign linking ─────────────────────────────────────────────────


class TestTripCampaignLinking:
    def test_trip_with_campaign_id(self, campaign_session, sample_campaign):
        trip = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="BNE-BLR Dec 15",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-15",
                return_date="2027-01-10",
            ),
        )
        assert trip.campaign_id == sample_campaign.id

    def test_active_variant(self, campaign_session, sample_campaign):
        insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="BNE-BLR Dec 15",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-15",
                return_date="2027-01-10",
            ),
        )
        active = get_active_variant(campaign_session, sample_campaign.id)
        assert active is not None
        assert active.depart_date == "2026-12-15"

    def test_campaign_variants(self, campaign_session, sample_campaign):
        t1 = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="Variant 1",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-15",
            ),
        )
        t2 = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="Variant 2",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-20",
            ),
        )
        variants = get_campaign_variants(campaign_session, sample_campaign.id)
        assert len(variants) == 2


# ─── Date change preserves history ────────────────────────────────────────────


class TestDateChangePreservesHistory:
    def test_archive_does_not_delete_snapshots(self, campaign_session, sample_campaign):
        """The core bug fix: archiving a trip must NOT delete price snapshots."""
        trip = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="Original dates",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-15",
                return_date="2027-01-10",
            ),
        )
        # Add some price history
        for i in range(5):
            insert_snapshot(
                campaign_session,
                PriceSnapshot(
                    trip_id=trip.id,
                    true_family_cost=3000.0 - i * 50,
                    base_fare_per_adult=800.0,
                    rank=1,
                ),
            )

        # Archive (simulate date change)
        archive_trip(campaign_session, trip.id)

        # Verify trip is archived but not deleted
        archived = campaign_session.get(Trip, trip.id)
        assert archived is not None
        assert archived.is_archived == 1
        assert archived.is_active == 0

        # Verify snapshots are still there
        campaign_snaps = get_campaign_snapshots(
            campaign_session, sample_campaign.id
        )
        assert len(campaign_snaps) == 5

    def test_new_variant_sees_old_history(self, campaign_session, sample_campaign):
        """After date change, campaign-level query returns ALL snapshots."""
        # Create and populate original variant
        t1 = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="V1",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-15",
            ),
        )
        for i in range(3):
            insert_snapshot(
                campaign_session,
                PriceSnapshot(
                    trip_id=t1.id,
                    true_family_cost=3000.0 + i * 100,
                    base_fare_per_adult=800.0,
                    rank=1,
                ),
            )

        # Archive and create new variant (date change)
        archive_trip(campaign_session, t1.id)
        t2 = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="V2",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-20",
            ),
        )
        insert_snapshot(
            campaign_session,
            PriceSnapshot(
                trip_id=t2.id,
                true_family_cost=2900.0,
                base_fare_per_adult=750.0,
                rank=1,
            ),
        )

        # Campaign-level query returns ALL snapshots
        all_snaps = get_campaign_snapshots(campaign_session, sample_campaign.id)
        assert len(all_snaps) == 4  # 3 from v1 + 1 from v2

        # Active variant is v2
        active = get_active_variant(campaign_session, sample_campaign.id)
        assert active is not None
        assert active.id == t2.id

    def test_archived_trip_not_in_active_list(self, campaign_session, sample_campaign):
        """Archived variants should not appear in list_active_trips."""
        from fly_o_myte.db.sqlite import list_active_trips

        t1 = insert_trip(
            campaign_session,
            Trip(
                campaign_id=sample_campaign.id,
                label="To archive",
                origin="BNE",
                destination="BLR",
                depart_date="2026-12-15",
            ),
        )
        archive_trip(campaign_session, t1.id)

        active = list_active_trips(campaign_session)
        assert not any(t.id == t1.id for t in active)


# ─── Campaign-level snapshot aggregation ──────────────────────────────────────


class TestBuildCampaignSnapshots:
    def _make_snapshot(
        self, trip_id: int, cost: float, ts: datetime, rank: int = 1
    ) -> PriceSnapshot:
        return PriceSnapshot(
            id=None,
            trip_id=trip_id,
            fetched_at=ts.isoformat(),
            true_family_cost=cost,
            base_fare_per_adult=cost * 0.3,
            rank=rank,
        )

    def test_empty_returns_empty(self):
        assert build_campaign_snapshots([], current_variant_id=1) == []

    def test_single_variant_full_weight(self):
        """Current variant snapshots should pass through unblended."""
        base = datetime(2026, 12, 1, 9, 0)
        snaps = [
            self._make_snapshot(1, 3000.0, base),
            self._make_snapshot(1, 3100.0, base + timedelta(days=1)),
        ]
        result = build_campaign_snapshots(snaps, current_variant_id=1)
        assert len(result) == 2
        assert result[0].true_family_cost == 3000.0
        assert result[1].true_family_cost == 3100.0

    def test_multi_variant_blending(self):
        """Archived variant costs should be blended toward campaign average."""
        base = datetime(2026, 12, 1, 9, 0)
        snaps = [
            # Archived variant (trip_id=1) — older
            self._make_snapshot(1, 2000.0, base),
            self._make_snapshot(1, 2200.0, base + timedelta(days=1)),
            # Current variant (trip_id=2) — newer
            self._make_snapshot(2, 3000.0, base + timedelta(days=5)),
            self._make_snapshot(2, 3100.0, base + timedelta(days=6)),
        ]
        result = build_campaign_snapshots(snaps, current_variant_id=2)
        assert len(result) == 4

        # Current variant snapshots should be unblended
        current_snaps = [s for s in result if s.true_family_cost >= 3000.0]
        assert len(current_snaps) == 2

        # Archived variant snapshots should be blended (not original values)
        archived_snaps = [s for s in result if s.true_family_cost < 3000.0]
        assert len(archived_snaps) == 2
        # They should be between original cost and campaign average
        campaign_avg = (2000 + 2200 + 3000 + 3100) / 4  # 2575
        for s in archived_snaps:
            assert s.true_family_cost >= 2000.0  # not less than original
            assert s.true_family_cost <= campaign_avg + 1  # not more than average

    def test_rank_2_filtered_out(self):
        """Only rank-1 snapshots should be included."""
        base = datetime(2026, 12, 1, 9, 0)
        snaps = [
            self._make_snapshot(1, 3000.0, base, rank=1),
            self._make_snapshot(1, 4000.0, base, rank=2),
        ]
        result = build_campaign_snapshots(snaps, current_variant_id=1)
        assert len(result) == 1
        assert result[0].true_family_cost == 3000.0

    def test_sorted_by_time(self):
        """Result should be sorted oldest-first for correct trend calculation."""
        base = datetime(2026, 12, 1, 9, 0)
        snaps = [
            self._make_snapshot(1, 3100.0, base + timedelta(days=3)),
            self._make_snapshot(1, 3000.0, base),
        ]
        result = build_campaign_snapshots(snaps, current_variant_id=1)
        assert result[0].fetched_at < result[1].fetched_at
