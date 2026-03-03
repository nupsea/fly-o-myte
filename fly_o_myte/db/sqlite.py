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
from datetime import datetime
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
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    alert_threshold_aud: float | None = None
    alert_email: str | None = None

    @property
    def children(self) -> list[dict]:
        return json.loads(self.children_json)


class PriceSnapshot(SQLModel, table=True):
    """One price observation for a trip — collected each poll cycle."""

    id: int | None = Field(default=None, primary_key=True)
    trip_id: int = Field(index=True, foreign_key="trip.id")
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
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


class Recommendation(SQLModel, table=True):
    """Booking recommendation generated after each poll."""

    id: int | None = Field(default=None, primary_key=True)
    trip_id: int = Field(index=True, foreign_key="trip.id")
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
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
    SQLModel.metadata.create_all(engine)


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
    """Delete trip and all related snapshots and recommendations."""
    trip = session.get(Trip, trip_id)
    if not trip:
        return False
    # Delete related rows
    for snap in get_snapshots_for_trip(session, trip_id):
        session.delete(snap)
    for rec in get_recommendations_for_trip(session, trip_id):
        session.delete(rec)
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
        .order_by(col(PriceSnapshot.fetched_at).desc())
        .limit(1)
    )
    return result.first()


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
