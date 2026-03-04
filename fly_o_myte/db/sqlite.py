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


class Trip(SQLModel, table=True):
    """A tracked flight search — the core entity."""

    id: int | None = Field(default=None, primary_key=True)
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
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    alert_threshold_aud: float | None = None
    alert_email: str | None = None

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

    # Lightweight migration for S31 (rank column)
    with engine.connect() as conn:
        # Check if column exists
        res = conn.execute(
            __import__("sqlalchemy").text("PRAGMA table_info(pricesnapshot)")
        )
        columns = [row[1] for row in res]
        if "rank" not in columns:
            conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE pricesnapshot ADD COLUMN rank INTEGER DEFAULT 1"
                )
            )
            conn.commit()


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
    return list(session.exec(select(Trip).where(Trip.is_active == 1)))


def list_all_trips(session: Session) -> list[Trip]:
    return list(session.exec(select(Trip).order_by(col(Trip.created_at).desc())))


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
