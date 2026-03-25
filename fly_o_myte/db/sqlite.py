"""
SQLite persistence layer — transactional data store.

Tables:
  trips             — watched trips (origin, destination, dates, family config)
  price_snapshots   — price history per trip
  recommendations   — booking recommendations per trip

Uses SQLModel (Pydantic + SQLAlchemy). WAL mode enabled for concurrent
CLI access (cron poll + manual refresh running simultaneously).
"""

from __future__ import annotations

import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Field, Session, SQLModel, col, create_engine, select

# ─── Table models ─────────────────────────────────────────────────────────────


class TripCampaign(SQLModel, table=True):
    """A planning intent — the stable anchor across date changes.

    Represents a family's intent to take a trip (e.g. 'Dec India Trip').
    Persists across date adjustments, watch/monitor changes, and multiple
    trip variants.  All analytics and history aggregate at this level.
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)  # e.g. "Dec India Trip"
    origin: str = Field(index=True)  # IATA code
    destination: str = Field(index=True)  # IATA code
    status: str = "active"  # active | completed | cancelled
    budget_target_aud: float | None = None
    notes: str = Field(default="")
    cron_schedule: str = Field(default="0 7 * * *")
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class Trip(SQLModel, table=True):
    """A tracked flight search — one date-specific variant of a campaign."""

    id: int | None = Field(default=None, primary_key=True)
    campaign_id: int | None = Field(
        default=None, foreign_key="tripcampaign.id", index=True
    )
    label: str = Field(index=True)  # e.g. "Easter BNE-SYD 2026"
    origin: str = Field(index=True)  # IATA code
    destination: str = Field(index=True)  # IATA code
    depart_date: str  # YYYY-MM-DD
    return_date: str | None = None  # YYYY-MM-DD, None = one-way
    adults: int = 2
    children_json: str = "[]"  # JSON: [{name, dob}, ...]
    bags_per_person: int = 1
    max_stops: int = 1
    is_active: int = 1  # 1 = tracking, 0 = paused
    is_archived: int = 0  # 1 = soft-deleted variant, kept for history
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    alert_threshold_aud: float | None = None
    alert_email: str | None = None
    cron_schedule: str = Field(
        default="0 7 * * *"
    )  # cron string for per-trip polling (S44)

    group_tag: str | None = (
        None  # optional group label for multi-option trip sets (S36)
    )

    @property
    def children(self) -> list[dict]:
        return json.loads(self.children_json)


class PriceSnapshot(SQLModel, table=True):
    """One price observation for a trip — collected each poll cycle."""

    id: int | None = Field(default=None, primary_key=True)
    trip_id: int = Field(index=True, foreign_key="trip.id")
    fetched_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: str = "tequila"  # "tequila" | "amadeus"
    airline_code: str | None = None  # IATA carrier code
    flight_number: str | None = None
    base_fare_per_adult: float = 0.0  # AUD, from API
    true_family_cost: float = 0.0  # AUD, computed by true_cost module
    true_cost_breakdown: str = "{}"  # JSON: {base, bags, seats, infant}
    price_level_signal: str | None = None  # "LOW" | "TYPICAL" | "HIGH"
    stops: int | None = None
    departure_time: str | None = None  # HH:MM
    return_departure_time: str | None = None  # HH:MM
    return_arrival_time: str | None = None  # HH:MM
    duration_minutes: int | None = None
    family_score: float | None = None  # 0–100
    offer_raw: str = "{}"  # JSON blob for debugging
    rank: int = Field(default=1)  # 1=best true cost, 2=second, 3=third (S31)


class FlexCache(SQLModel, table=True):
    """Cached flex-scouting results — avoids burning SerpAPI quota on repeated calls."""

    id: int | None = Field(default=None, primary_key=True)
    trip_id: int = Field(index=True, foreign_key="trip.id")
    flex_key: str = Field(index=True)  # deterministic string of search params
    computed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    results_json: str = "[]"  # JSON: list of FlexResultRow-compatible dicts


class Recommendation(SQLModel, table=True):
    """Booking recommendation generated after each poll."""

    id: int | None = Field(default=None, primary_key=True)
    trip_id: int = Field(index=True, foreign_key="trip.id")
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    decision: str = "monitor"  # "book_now" | "wait" | "monitor"
    confidence: float = 0.5  # 0.0–1.0
    regret_risk: str = "medium"  # "low" | "medium" | "high"
    regret_book_aud: float = 0.0  # expected regret if book now
    regret_wait_aud: float = 0.0  # expected regret if wait
    true_family_cost: float = 0.0  # at time of recommendation
    rolling_avg_cost: float = 0.0
    trend_slope: float = 0.0  # AUD/day, negative = falling
    days_to_departure: int = 0
    price_level_signal: str | None = None
    school_holiday_flag: str | None = None  # None or holiday label
    rationale: str = ""
    email_sent: int = 0  # 0/1 boolean


# ─── Engine factory ───────────────────────────────────────────────────────────


def create_db_engine(db_path: Path):
    """
    Create the SQLite engine.
    Enables WAL mode so concurrent readers + one writer don't block each other.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_tables(engine) -> None:
    """Create all tables and perform lightweight migrations."""
    SQLModel.metadata.create_all(engine)

    import logging

    import sqlalchemy

    _logger = logging.getLogger(__name__)

    with engine.connect() as conn:
        # Migration S31: rank column on pricesnapshot
        res = conn.execute(sqlalchemy.text("PRAGMA table_info(pricesnapshot)"))
        if "rank" not in [row[1] for row in res]:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE pricesnapshot ADD COLUMN rank INTEGER DEFAULT 1"
                )
            )
            conn.commit()

        # Migration S36: group_tag column on trip
        res2 = conn.execute(sqlalchemy.text("PRAGMA table_info(trip)"))
        if "group_tag" not in [row[1] for row in res2]:
            conn.execute(sqlalchemy.text("ALTER TABLE trip ADD COLUMN group_tag TEXT"))
            conn.commit()
            _logger.debug("Migrated trip table: added group_tag column")

        # Migration S44: cron_schedule column on trip
        res3 = conn.execute(sqlalchemy.text("PRAGMA table_info(trip)"))
        if "cron_schedule" not in [row[1] for row in res3]:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE trip ADD COLUMN cron_schedule TEXT DEFAULT '0 7 * * *'"
                )
            )
            conn.commit()
            _logger.debug("Migrated trip table: added cron_schedule column")

        # Migration S100: return journey times on pricesnapshot
        res4 = conn.execute(sqlalchemy.text("PRAGMA table_info(pricesnapshot)"))
        columns = [row[1] for row in res4]
        if "return_departure_time" not in columns:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE pricesnapshot ADD COLUMN return_departure_time TEXT"
                )
            )
        if "return_arrival_time" not in columns:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE pricesnapshot ADD COLUMN return_arrival_time TEXT"
                )
            )
        conn.commit()

        # Migration CAMPAIGN-1: campaign_id and is_archived on trip
        res5 = conn.execute(sqlalchemy.text("PRAGMA table_info(trip)"))
        trip_cols = [row[1] for row in res5]
        if "campaign_id" not in trip_cols:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE trip ADD COLUMN campaign_id INTEGER REFERENCES tripcampaign(id)"
                )
            )
            conn.commit()
            _logger.debug("Migrated trip table: added campaign_id column")
        if "is_archived" not in trip_cols:
            conn.execute(
                sqlalchemy.text(
                    "ALTER TABLE trip ADD COLUMN is_archived INTEGER DEFAULT 0"
                )
            )
            conn.commit()
            _logger.debug("Migrated trip table: added is_archived column")

        # Migration CAMPAIGN-2: auto-wrap orphan trips in campaigns
        orphans = conn.execute(
            sqlalchemy.text(
                "SELECT id, label, origin, destination, cron_schedule, created_at "
                "FROM trip WHERE campaign_id IS NULL"
            )
        ).fetchall()
        for orphan in orphans:
            tid, label, origin, dest, cron, created = orphan
            result = conn.execute(
                sqlalchemy.text(
                    "INSERT INTO tripcampaign (name, origin, destination, status, notes, cron_schedule, created_at) "
                    "VALUES (:name, :origin, :dest, 'active', '', :cron, :created)"
                ),
                {
                    "name": label,
                    "origin": origin,
                    "dest": dest,
                    "cron": cron,
                    "created": created,
                },
            )
            campaign_id = result.lastrowid
            conn.execute(
                sqlalchemy.text("UPDATE trip SET campaign_id = :cid WHERE id = :tid"),
                {"cid": campaign_id, "tid": tid},
            )
        if orphans:
            conn.commit()
            _logger.info("Auto-migrated %d orphan trip(s) into campaigns", len(orphans))


@contextmanager
def get_session(engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


# ─── CRUD helpers ─────────────────────────────────────────────────────────────


def insert_trip(session: Session, trip: Trip) -> Trip:
    session.add(trip)
    session.commit()
    session.refresh(trip)
    return trip


def get_trip(session: Session, trip_id: int) -> Trip | None:
    return session.get(Trip, trip_id)


def list_active_trips(session: Session) -> list[Trip]:
    return list(
        session.exec(select(Trip).where(Trip.is_active == 1, Trip.is_archived == 0))
    )


def list_all_trips(session: Session) -> list[Trip]:
    return list(
        session.exec(
            select(Trip)
            .where(Trip.is_archived == 0)
            .order_by(col(Trip.created_at).desc())
        )
    )


def set_trip_active(session: Session, trip_id: int, active: bool) -> None:
    trip = session.get(Trip, trip_id)
    if trip:
        trip.is_active = 1 if active else 0
        session.commit()


def delete_trip(session: Session, trip_id: int) -> bool:
    """Delete trip and all related snapshots, recommendations, and flex cache."""
    trip = session.get(Trip, trip_id)
    if not trip:
        return False
    # Delete related rows
    for snap in get_snapshots_for_trip(session, trip_id):
        session.delete(snap)
    for rec in get_recommendations_for_trip(session, trip_id):
        session.delete(rec)
    for fc in session.exec(select(FlexCache).where(FlexCache.trip_id == trip_id)):
        session.delete(fc)
    session.delete(trip)
    session.commit()
    return True


def insert_snapshot(session: Session, snapshot: PriceSnapshot) -> PriceSnapshot:
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def get_snapshots_for_trip(
    session: Session, trip_id: int, limit: int | None = None
) -> list[PriceSnapshot]:
    q = (
        select(PriceSnapshot)
        .where(PriceSnapshot.trip_id == trip_id)
        .order_by(PriceSnapshot.fetched_at)
    )
    if limit:
        q = q.limit(limit)
    return list(session.exec(q))


def get_latest_snapshot(session: Session, trip_id: int) -> PriceSnapshot | None:
    result = session.exec(
        select(PriceSnapshot)
        .where(PriceSnapshot.trip_id == trip_id)
        .order_by(col(PriceSnapshot.fetched_at).desc(), col(PriceSnapshot.rank).asc())
        .limit(1)
    )
    return result.first()


def get_snapshots_at_fetch(
    session: Session, trip_id: int, fetched_at: str
) -> list[PriceSnapshot]:
    """Get all snapshots for a trip at a specific fetched_at timestamp, ordered by rank."""
    return list(
        session.exec(
            select(PriceSnapshot)
            .where(PriceSnapshot.trip_id == trip_id)
            .where(PriceSnapshot.fetched_at == fetched_at)
            .order_by(col(PriceSnapshot.rank).asc())
        )
    )


def insert_recommendation(session: Session, rec: Recommendation) -> Recommendation:
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def get_recommendations_for_trip(
    session: Session, trip_id: int
) -> list[Recommendation]:
    return list(
        session.exec(
            select(Recommendation)
            .where(Recommendation.trip_id == trip_id)
            .order_by(col(Recommendation.generated_at).desc())
        )
    )


def get_latest_recommendation(session: Session, trip_id: int) -> Recommendation | None:
    result = session.exec(
        select(Recommendation)
        .where(Recommendation.trip_id == trip_id)
        .order_by(col(Recommendation.generated_at).desc())
        .limit(1)
    )
    return result.first()


def get_unsent_book_now_recs(session: Session) -> list[Recommendation]:
    """For email notification: book_now decisions not yet emailed."""
    return list(
        session.exec(
            select(Recommendation)
            .where(Recommendation.decision == "book_now")
            .where(Recommendation.email_sent == 0)
        )
    )


def mark_email_sent(session: Session, rec_id: int) -> None:
    rec = session.get(Recommendation, rec_id)
    if rec:
        rec.email_sent = 1
        session.commit()


# ─── Campaign CRUD helpers ─────────────────────────────────────────────────────


def insert_campaign(session: Session, campaign: TripCampaign) -> TripCampaign:
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    return campaign


def get_campaign(session: Session, campaign_id: int) -> TripCampaign | None:
    return session.get(TripCampaign, campaign_id)


def list_campaigns(
    session: Session, include_cancelled: bool = False
) -> list[TripCampaign]:
    q = select(TripCampaign).order_by(col(TripCampaign.created_at).desc())
    if not include_cancelled:
        q = q.where(TripCampaign.status != "cancelled")
    return list(session.exec(q))


def get_active_variant(session: Session, campaign_id: int) -> Trip | None:
    """Return the single active (non-archived) trip variant for a campaign."""
    result = session.exec(
        select(Trip)
        .where(
            Trip.campaign_id == campaign_id,
            Trip.is_active == 1,
            Trip.is_archived == 0,
        )
        .limit(1)
    )
    return result.first()


def get_campaign_variants(
    session: Session, campaign_id: int, include_archived: bool = True
) -> list[Trip]:
    """Return all trip variants for a campaign, newest first."""
    q = (
        select(Trip)
        .where(Trip.campaign_id == campaign_id)
        .order_by(col(Trip.created_at).desc())
    )
    if not include_archived:
        q = q.where(Trip.is_archived == 0)
    return list(session.exec(q))


def get_campaign_snapshots(session: Session, campaign_id: int) -> list[PriceSnapshot]:
    """Return all snapshots across all variants in a campaign, ordered by time."""
    variant_ids = [
        t.id
        for t in session.exec(select(Trip).where(Trip.campaign_id == campaign_id))
        if t.id is not None
    ]
    if not variant_ids:
        return []
    return list(
        session.exec(
            select(PriceSnapshot)
            .where(col(PriceSnapshot.trip_id).in_(variant_ids))
            .order_by(PriceSnapshot.fetched_at)
        )
    )


def archive_trip(session: Session, trip_id: int) -> None:
    """Soft-delete a trip variant — keeps all history intact."""
    trip = session.get(Trip, trip_id)
    if trip:
        trip.is_archived = 1
        trip.is_active = 0
        session.commit()


# ─── FlexCache helpers ─────────────────────────────────────────────────────────


def get_flex_cache(session: Session, trip_id: int, flex_key: str) -> FlexCache | None:
    """Return cached flex results for a trip+key, or None if absent."""
    result = session.exec(
        select(FlexCache)
        .where(FlexCache.trip_id == trip_id)
        .where(FlexCache.flex_key == flex_key)
        .limit(1)
    )
    return result.first()


def set_flex_cache(
    session: Session, trip_id: int, flex_key: str, results_json: str
) -> FlexCache:
    """Upsert a FlexCache entry, replacing any existing entry for the same key."""
    existing = get_flex_cache(session, trip_id, flex_key)
    if existing:
        session.delete(existing)
        session.flush()
    cache = FlexCache(
        trip_id=trip_id,
        flex_key=flex_key,
        computed_at=datetime.now(UTC).isoformat(),
        results_json=results_json,
    )
    session.add(cache)
    session.commit()
    session.refresh(cache)
    return cache
