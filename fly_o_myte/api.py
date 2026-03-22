"""
FastAPI Backend for Fly-O-Myte UI.
Exposes core services for scouting, tracking, and profile management.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session

from fly_o_myte.config import (
    get_settings,
    load_family_profile,
)
from fly_o_myte.db.sqlite import (
    PriceSnapshot,
    Trip,
    TripCampaign,
    archive_trip,
    create_db_engine,
    create_tables,
    delete_trip,
    get_active_variant,
    get_campaign,
    get_campaign_snapshots,
    get_campaign_variants,
    get_flex_cache,
    get_latest_recommendation,
    get_latest_snapshot,
    get_session,
    insert_campaign,
    insert_snapshot,
    insert_trip,
    list_all_trips,
    list_campaigns,
    set_flex_cache,
    set_trip_active,
)
from fly_o_myte.scheduler import (
    start_scheduler,
    stop_scheduler,
    update_campaign_schedule,
    update_trip_schedule,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the background scheduler on startup and stop it on shutdown."""
    # Ensure tables and migrations are applied before scheduler starts
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    create_tables(engine)

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Fly-O-Myte API", lifespan=lifespan)
logger = logging.getLogger(__name__)

# CORS setup for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Dependencies ────────────────────────────────────────────────────────────


def get_db():
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    create_tables(engine)
    with get_session(engine) as session:
        yield session


# ─── Models ──────────────────────────────────────────────────────────────────


class ChildModel(BaseModel):
    name: str
    dob: date


class ProfileUpdate(BaseModel):
    adults: int
    children: list[ChildModel]
    origin_airport: str
    state: str
    school_type: str
    bags_per_person: int
    max_stops: int
    default_trip_length: int
    earliest_hour: int = 8
    latest_hour: int = 18
    blocked_airlines: list[str] = []
    budget_threshold_aud: float | None = None


class TripUpdate(BaseModel):
    label: str | None = None
    adults: int | None = None
    children: list[ChildModel] | None = None
    bags_per_person: int | None = None
    max_stops: int | None = None
    is_active: bool | None = None
    group_tag: str | None = None
    alert_threshold_aud: float | None = None
    alert_email: str | None = None
    cron_schedule: str | None = None


class OfferSeed(BaseModel):
    """Scout result data passed from UI to seed the initial snapshot without a fresh API call."""

    base_fare_per_adult: float
    true_family_cost: float
    true_cost_breakdown: (
        dict  # {base_adults, base_children, bags, seats, infant, total}
    )
    airline_code: str
    stops: int
    departure_time: str | None = None
    return_departure_time: str | None = None
    return_arrival_time: str | None = None
    duration_minutes: int | None = None
    offer_raw: dict | None = None


class TripCreate(BaseModel):
    origin: str
    destination: str
    depart_date: str
    return_date: str | None = None
    label: str | None = None
    group_tag: str | None = None
    campaign_id: int | None = None  # link to existing campaign
    campaign_name: str | None = None  # auto-create campaign if provided
    cron_schedule: str | None = "0 7 * * *"
    offer_seed: OfferSeed | None = None  # if provided, skip SerpAPI poll


class TripReplace(BaseModel):
    depart_date: str
    return_date: str | None = None


class CampaignCreate(BaseModel):
    name: str
    origin: str
    destination: str
    budget_target_aud: float | None = None
    notes: str = ""
    cron_schedule: str = "0 7 * * *"
    # Optional: create first trip variant immediately
    depart_date: str | None = None
    return_date: str | None = None
    offer_seed: OfferSeed | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    budget_target_aud: float | None = None
    notes: str | None = None
    cron_schedule: str | None = None


# ─── Endpoints ───────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


# ─── Campaign Endpoints ──────────────────────────────────────────────────────


@app.get("/campaigns")
def get_campaigns_endpoint(session: Annotated[Session, Depends(get_db)]):
    """List all campaigns with their active variant and latest recommendation."""
    campaigns = list_campaigns(session)
    result = []
    for c in campaigns:
        assert c.id is not None
        active = get_active_variant(session, c.id)
        rec = None
        snap = None
        if active and active.id is not None:
            rec = get_latest_recommendation(session, active.id)
            snap = get_latest_snapshot(session, active.id)
        variants = get_campaign_variants(session, c.id)
        result.append(
            {
                "id": c.id,
                "name": c.name,
                "origin": c.origin,
                "destination": c.destination,
                "status": c.status,
                "budget_target_aud": c.budget_target_aud,
                "notes": c.notes,
                "cron_schedule": c.cron_schedule,
                "created_at": c.created_at,
                "active_variant": active,
                "recommendation": rec,
                "latest_snapshot": snap,
                "variant_count": len(variants),
                "total_snapshots": len(get_campaign_snapshots(session, c.id)),
            }
        )
    return result


@app.post("/campaigns")
def create_campaign_endpoint(
    data: CampaignCreate, session: Annotated[Session, Depends(get_db)]
):
    """Create a campaign, optionally with a first trip variant."""
    import json as _json

    campaign = insert_campaign(
        session,
        TripCampaign(
            name=data.name,
            origin=data.origin.upper(),
            destination=data.destination.upper(),
            budget_target_aud=data.budget_target_aud,
            notes=data.notes,
            cron_schedule=data.cron_schedule,
        ),
    )
    assert campaign.id is not None
    update_campaign_schedule(campaign)

    # Auto-create first trip variant if dates provided
    if data.depart_date:
        profile = load_family_profile()
        trip = Trip(
            campaign_id=campaign.id,
            label=f"{data.origin.upper()}-{data.destination.upper()} {data.depart_date}",
            origin=data.origin.upper(),
            destination=data.destination.upper(),
            depart_date=data.depart_date,
            return_date=data.return_date,
            adults=profile.adults,
            children_json=_json.dumps(
                [{"name": c.name, "dob": str(c.dob)} for c in profile.children]
            ),
            bags_per_person=profile.bags_per_person,
            max_stops=profile.max_stops,
            cron_schedule=data.cron_schedule,
        )
        inserted_trip = insert_trip(session, trip)

        if data.offer_seed:
            seed = data.offer_seed
            insert_snapshot(
                session,
                PriceSnapshot(
                    trip_id=inserted_trip.id,
                    source="serpapi",
                    airline_code=seed.airline_code,
                    base_fare_per_adult=seed.base_fare_per_adult,
                    true_family_cost=seed.true_family_cost,
                    true_cost_breakdown=_json.dumps(seed.true_cost_breakdown),
                    stops=seed.stops,
                    departure_time=seed.departure_time,
                    return_departure_time=seed.return_departure_time,
                    return_arrival_time=seed.return_arrival_time,
                    duration_minutes=seed.duration_minutes or 0,
                    offer_raw=_json.dumps(seed.offer_raw) if seed.offer_raw else "{}",
                    rank=1,
                ),
            )

    return campaign


@app.get("/campaigns/{campaign_id}")
def get_campaign_endpoint(
    campaign_id: int, session: Annotated[Session, Depends(get_db)]
):
    """Campaign detail with all variants and aggregate info."""
    campaign = get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    variants = get_campaign_variants(session, campaign_id)
    active = get_active_variant(session, campaign_id)
    all_snaps = get_campaign_snapshots(session, campaign_id)

    rec = None
    if active and active.id is not None:
        rec = get_latest_recommendation(session, active.id)

    # Compute campaign-level stats
    costs = [s.true_family_cost for s in all_snaps if s.rank == 1]
    stats = {}
    if costs:
        stats = {
            "total_data_points": len(costs),
            "min_cost_seen": min(costs),
            "max_cost_seen": max(costs),
            "avg_cost": round(sum(costs) / len(costs), 2),
            "latest_cost": costs[-1] if costs else None,
        }

    return {
        "campaign": campaign,
        "active_variant": active,
        "variants": variants,
        "recommendation": rec,
        "stats": stats,
    }


@app.put("/campaigns/{campaign_id}")
def update_campaign_endpoint(
    campaign_id: int,
    data: CampaignUpdate,
    session: Annotated[Session, Depends(get_db)],
):
    campaign = get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if data.name is not None:
        campaign.name = data.name
    if data.status is not None:
        campaign.status = data.status
    if data.budget_target_aud is not None:
        campaign.budget_target_aud = data.budget_target_aud
    if data.notes is not None:
        campaign.notes = data.notes
    if data.cron_schedule is not None:
        campaign.cron_schedule = data.cron_schedule

    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    update_campaign_schedule(campaign)
    return campaign


@app.delete("/campaigns/{campaign_id}")
def delete_campaign_endpoint(
    campaign_id: int, session: Annotated[Session, Depends(get_db)]
):
    """Soft-delete: set status=cancelled, archive all variants."""
    campaign = get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign.status = "cancelled"
    session.add(campaign)

    # Archive all variants
    for variant in get_campaign_variants(session, campaign_id):
        if variant.id is not None:
            archive_trip(session, variant.id)

    session.commit()
    update_campaign_schedule(campaign)
    return {"status": "cancelled"}


@app.get("/campaigns/{campaign_id}/history")
def get_campaign_history(
    campaign_id: int,
    session: Annotated[Session, Depends(get_db)],
    limit: int = 100,
):
    """Full price history across all variants in a campaign."""
    campaign = get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    snaps = get_campaign_snapshots(session, campaign_id)
    # Return most recent first, limited
    snaps.reverse()
    return snaps[:limit]


@app.get("/airports/search")
def search_airports(q: str):
    from fly_o_myte.airports import resolve_destination
    from fly_o_myte.price_sources.serpapi import _AU_AIRPORTS

    # Get international matches
    results = resolve_destination(q)

    # Common AU city name lookups (from planner.py)
    _AU_CITY = {
        "SYDNEY": "SYD",
        "MELBOURNE": "MEL",
        "BRISBANE": "BNE",
        "PERTH": "PER",
        "ADELAIDE": "ADL",
        "DARWIN": "DRW",
        "HOBART": "HBA",
        "CANBERRA": "CBR",
        "GOLD COAST": "OOL",
        "CAIRNS": "CNS",
        "TOWNSVILLE": "TSV",
        "ROCKHAMPTON": "ROK",
        "MACKAY": "MKY",
    }

    # Add AU domestic matches
    q_upper = q.upper()
    q_lower = q.lower()

    # Match by city name
    for city, code in _AU_CITY.items():
        if q_lower in city.lower() or q_upper in code:
            if not any(r[0] == code for r in results):
                results.append((code, f"{city.title()} (Australia)"))

    # Direct code match from _AU_AIRPORTS if not already found
    for code in _AU_AIRPORTS:
        if q_upper in code:
            if not any(r[0] == code for r in results):
                results.append((code, f"{code} (Australia)"))

    return [{"value": r[0], "label": r[1]} for r in results]


@app.get("/profile")
def get_profile():
    profile = load_family_profile()
    settings = get_settings()
    # Flatten window for easier UI binding
    res = {
        "adults": profile.adults,
        "children": [{"name": c.name, "dob": str(c.dob)} for c in profile.children],
        "origin_airport": profile.origin_airport,
        "state": profile.state,
        "school_type": profile.school_type,
        "bags_per_person": profile.bags_per_person,
        "max_stops": profile.max_stops,
        "default_trip_length": profile.default_trip_length,
        "earliest_hour": profile.preferred_departure_window.earliest_hour,
        "latest_hour": profile.preferred_departure_window.latest_hour,
        "blocked_airlines": profile.blocked_airlines,
        "budget_threshold_aud": profile.budget_threshold_aud,
        "alert_email": settings.default_alert_email,
    }
    return res


@app.put("/profile")
def update_profile(update: ProfileUpdate):
    import yaml

    settings = get_settings()
    path = settings.config_path

    # Load existing to preserve keys
    existing = {}
    if path.exists():
        with path.open() as f:
            existing = yaml.safe_load(f) or {}

    config = existing.copy()
    fam = config.get("family", {})
    fam.update(
        {
            "adults": update.adults,
            "children": [{"name": c.name, "dob": str(c.dob)} for c in update.children],
            "origin_airport": update.origin_airport,
            "state": update.state,
            "school_type": update.school_type,
            "bags_per_person": update.bags_per_person,
            "max_stops": update.max_stops,
            "default_trip_length": update.default_trip_length,
            "preferred_departure_window": {
                "earliest_hour": update.earliest_hour,
                "latest_hour": update.latest_hour,
            },
            "blocked_airlines": update.blocked_airlines,
            "budget_threshold_aud": update.budget_threshold_aud,
        }
    )
    config["family"] = fam

    with path.open("w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    return {"status": "success"}


@app.get("/trips")
def get_trips(session: Annotated[Session, Depends(get_db)]):
    trips = list_all_trips(session)
    result = []
    for trip in trips:
        assert trip.id is not None
        rec = get_latest_recommendation(session, trip.id)
        snap = get_latest_snapshot(session, trip.id)
        campaign_name = None
        if trip.campaign_id:
            campaign = get_campaign(session, trip.campaign_id)
            campaign_name = campaign.name if campaign else None
        result.append(
            {
                "id": trip.id,
                "label": trip.label,
                "origin": trip.origin,
                "destination": trip.destination,
                "depart_date": trip.depart_date,
                "return_date": trip.return_date,
                "adults": trip.adults,
                "children": trip.children,
                "bags_per_person": trip.bags_per_person,
                "max_stops": trip.max_stops,
                "is_active": bool(trip.is_active),
                "recommendation": rec,
                "latest_snapshot": snap,
                "group_tag": trip.group_tag,
                "campaign_id": trip.campaign_id,
                "campaign_name": campaign_name,
                "alert_threshold_aud": trip.alert_threshold_aud,
                "alert_email": trip.alert_email,
                "cron_schedule": trip.cron_schedule,
            }
        )
    return result


@app.post("/trips")
def watch_trip(data: TripCreate, session: Annotated[Session, Depends(get_db)]):
    import json as _json

    profile = load_family_profile()
    trip_label = data.label or f"{data.origin}-{data.destination} {data.depart_date}"
    origin = data.origin.upper()
    destination = data.destination.upper()

    # Resolve or create campaign
    campaign_id = data.campaign_id
    if not campaign_id:
        campaign_name = data.campaign_name or trip_label
        campaign = insert_campaign(
            session,
            TripCampaign(
                name=campaign_name,
                origin=origin,
                destination=destination,
                cron_schedule=data.cron_schedule or "0 7 * * *",
            ),
        )
        campaign_id = campaign.id
        update_campaign_schedule(campaign)

    trip = Trip(
        campaign_id=campaign_id,
        label=trip_label,
        origin=origin,
        destination=destination,
        depart_date=data.depart_date,
        return_date=data.return_date,
        adults=profile.adults,
        children_json=_json.dumps(
            [{"name": c.name, "dob": str(c.dob)} for c in profile.children]
        ),
        bags_per_person=profile.bags_per_person,
        max_stops=profile.max_stops,
        group_tag=data.group_tag,
        alert_threshold_aud=profile.budget_threshold_aud,
        alert_email=None,
        cron_schedule=data.cron_schedule or "0 7 * * *",
    )

    inserted = insert_trip(session, trip)
    assert inserted.id is not None
    update_trip_schedule(inserted)

    if data.offer_seed:
        seed = data.offer_seed
        insert_snapshot(
            session,
            PriceSnapshot(
                trip_id=inserted.id,
                source="serpapi",
                airline_code=seed.airline_code,
                base_fare_per_adult=seed.base_fare_per_adult,
                true_family_cost=seed.true_family_cost,
                true_cost_breakdown=_json.dumps(seed.true_cost_breakdown),
                stops=seed.stops,
                departure_time=seed.departure_time,
                return_departure_time=seed.return_departure_time,
                return_arrival_time=seed.return_arrival_time,
                duration_minutes=seed.duration_minutes or 0,
                offer_raw=_json.dumps(seed.offer_raw) if seed.offer_raw else "{}",
                rank=1,
            ),
        )
        logging.info(
            "Trip %s seeded from scout data: $%.0f (%s)",
            inserted.id,
            seed.true_family_cost,
            seed.airline_code,
        )
    else:
        from fly_o_myte.tracker import build_plugin_manager_from_settings, poll_trip

        pm = build_plugin_manager_from_settings()
        poll_trip(session, inserted, profile, pm, send_alerts=True)

    return inserted


@app.put("/trips/{trip_id}")
def update_trip_endpoint(
    trip_id: int, update: TripUpdate, session: Annotated[Session, Depends(get_db)]
):
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if update.label is not None:
        trip.label = update.label
    if update.adults is not None:
        trip.adults = update.adults
    if update.children is not None:
        import json as _json

        trip.children_json = _json.dumps(
            [{"name": c.name, "dob": str(c.dob)} for c in update.children]
        )
    if update.bags_per_person is not None:
        trip.bags_per_person = update.bags_per_person
    if update.max_stops is not None:
        trip.max_stops = update.max_stops
    if update.is_active is not None:
        trip.is_active = 1 if update.is_active else 0
    if update.group_tag is not None:
        trip.group_tag = update.group_tag
    if update.alert_threshold_aud is not None:
        trip.alert_threshold_aud = update.alert_threshold_aud
    if update.alert_email is not None:
        trip.alert_email = update.alert_email
    if update.cron_schedule is not None:
        trip.cron_schedule = update.cron_schedule

    session.add(trip)
    session.commit()
    session.refresh(trip)

    # Sync scheduler with updated trip
    update_trip_schedule(trip)

    return trip


@app.delete("/trips/{trip_id}")
def remove_trip(trip_id: int, session: Annotated[Session, Depends(get_db)]):
    trip = session.get(Trip, trip_id)
    success = delete_trip(session, trip_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trip not found")

    if trip:
        trip.is_active = 0  # set to inactive so scheduler removes it
        update_trip_schedule(trip)

    return {"status": "deleted"}


@app.get("/trips/{trip_id}/history")
def get_trip_history(
    trip_id: int, session: Annotated[Session, Depends(get_db)], limit: int = 30
):
    from sqlmodel import col, select

    from fly_o_myte.db.sqlite import PriceSnapshot

    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # Fetch all snapshots, ordered by time descending, then rank ascending
    q = (
        select(PriceSnapshot)
        .where(PriceSnapshot.trip_id == trip_id)
        .order_by(col(PriceSnapshot.fetched_at).desc(), col(PriceSnapshot.rank).asc())
        .limit(limit * 3)  # Allow for rank 1, 2, 3 per fetch
    )
    snaps = list(session.exec(q))
    return snaps


@app.post("/trips/{trip_id}/toggle")
def toggle_trip(trip_id: int, session: Annotated[Session, Depends(get_db)]):
    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    new_state = not bool(trip.is_active)
    set_trip_active(session, trip_id, active=new_state)
    trip.is_active = 1 if new_state else 0
    update_trip_schedule(trip)
    return {"status": "updated", "is_active": new_state}


@app.post("/trips/{trip_id}/refresh")
def refresh_trip(trip_id: int, session: Annotated[Session, Depends(get_db)]):
    from fly_o_myte.tracker import build_plugin_manager_from_settings, poll_trip

    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()

    snap = poll_trip(session, trip, profile, pm, send_alerts=True)
    return snap


@app.post("/trips/{trip_id}/replace")
def replace_trip_endpoint(
    trip_id: int, session: Annotated[Session, Depends(get_db)], data: TripReplace
):
    """Archive the old trip variant and create a new one under the same campaign.

    This preserves ALL price history — the recommender can use snapshots from
    all variants in the campaign for smarter initial recommendations.
    """
    from fly_o_myte.tracker import build_plugin_manager_from_settings, poll_trip

    old_trip = session.get(Trip, trip_id)
    if not old_trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()

    # Archive the old variant (soft-delete — keeps all history)
    archive_trip(session, trip_id)

    # Create new variant under the SAME campaign
    new_trip = Trip(
        campaign_id=old_trip.campaign_id,
        label=f"{old_trip.origin}-{old_trip.destination} {data.depart_date}",
        origin=old_trip.origin,
        destination=old_trip.destination,
        depart_date=data.depart_date,
        return_date=data.return_date,
        adults=old_trip.adults,
        children_json=old_trip.children_json,
        bags_per_person=old_trip.bags_per_person,
        max_stops=old_trip.max_stops,
        alert_email=old_trip.alert_email,
        alert_threshold_aud=old_trip.alert_threshold_aud,
        group_tag=old_trip.group_tag,
        cron_schedule=old_trip.cron_schedule,
    )

    inserted = insert_trip(session, new_trip)
    assert inserted.id is not None
    update_trip_schedule(inserted)

    # Poll the new variant — it will use campaign-level history automatically
    poll_trip(session, inserted, profile, pm, send_alerts=True)

    return inserted


@app.post("/poll")
def poll_trips():
    from fly_o_myte.tracker import build_plugin_manager_from_settings, poll_all_active

    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()
    settings = get_settings()
    engine = create_db_engine(settings.db_path)

    with get_session(engine) as session:
        results = poll_all_active(session, profile, pm, send_alerts=True)

    return results


@app.get("/cron")
def get_cron():
    from fly_o_myte.scheduler import _scheduler

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "next_run": job.next_run_time.isoformat()
                if job.next_run_time
                else None,
                "trigger": str(job.trigger),
            }
        )

    return {"active": _scheduler.running, "jobs": jobs, "job_count": len(jobs)}


@app.post("/cron")
def update_cron_global():
    # This is now handled per-trip, but we can keep it as a 'sync all' trigger
    from fly_o_myte.scheduler import sync_scheduler_from_db

    sync_scheduler_from_db()
    return {"status": "synced"}


class ScoutRequest(BaseModel):
    origin: str
    destination: str
    months: list[str] | None = None  # e.g. ["dec-2026", "jan-2027"]
    trip_length: int = 7
    depart_date: str | None = None
    return_date: str | None = None
    flex_days: int = 0


def _map_scout_result(r):
    """Normalise ScoutResult to dict for API response."""
    return {
        "depart_date": str(r.depart_date),
        "return_date": str(r.return_date),
        "trip_length_days": r.trip_length_days,
        "true_family_cost": r.true_family_cost,
        "base_fare_per_adult": r.base_fare_per_adult,
        "airline_code": r.airline_code,
        "stops": r.stops,
        "departure_time": r.departure_time,
        "arrival_time": r.arrival_time,
        "return_departure_time": r.return_departure_time,
        "return_arrival_time": r.return_arrival_time,
        "duration_minutes": r.duration_minutes,
        "school_holiday": r.school_holiday,
        "breakdown": r.breakdown.as_dict() if r.breakdown else {},
        "fly_o_myte_legs": r.fly_o_myte_legs,
        "offer_raw": r.offer_raw,
    }


@app.post("/scout")
def scout_flights(req: ScoutRequest):
    from datetime import date

    from fly_o_myte.calendar import get_calendar
    from fly_o_myte.fees import get_airline_db
    from fly_o_myte.scout import scout_flex, scout_month
    from fly_o_myte.tracker import build_plugin_manager_from_settings

    # ─── 1. Validation ────────────────────────────────────────────────────────
    if req.months:
        if len(req.months) > 4:
            raise HTTPException(
                status_code=400,
                detail="Cannot scout more than 4 months at once (max 90-day window).",
            )

        try:
            parsed_months = []
            for m in req.months:
                parsed_months.append(datetime.strptime(m, "%b-%Y"))

            parsed_months.sort()
            span_months = (parsed_months[-1].year - parsed_months[0].year) * 12 + (
                parsed_months[-1].month - parsed_months[0].month
            )

            if span_months > 3:
                raise HTTPException(
                    status_code=400,
                    detail="Selected months must be within a 3-month range.",
                )

            # Basic trip length sanity check
            if req.trip_length < 1 or req.trip_length > 90:
                raise HTTPException(
                    status_code=400, detail="Trip length must be between 1 and 90 days."
                )

        except ValueError as e:
            raise HTTPException(
                status_code=400, detail="Invalid month format. Use 'jan-2026'."
            ) from e

    # ─── 2. Execution ─────────────────────────────────────────────────────────
    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()
    airline_db = get_airline_db()
    cal = get_calendar()

    from fly_o_myte.price_sources.hookspecs import PriceSourceError

    if req.months:
        all_results = []
        errors = []
        for m_str in req.months:
            try:
                parts = m_str.split("-")
                month_num = datetime.strptime(parts[0], "%b").month
                year_num = int(parts[1])
                results = scout_month(
                    pm,
                    profile,
                    airline_db,
                    cal,
                    req.origin.upper(),
                    req.destination.upper(),
                    year_num,
                    month_num,
                    req.trip_length,
                )
                all_results.extend(results)
            except Exception as e:
                logging.error(f"Error scouting month {m_str}: {e}")
                errors.append(f"{m_str}: {str(e)}")

        if not all_results and errors:
            raise HTTPException(
                status_code=502, detail=f"All price sources failed: {'; '.join(errors)}"
            )

        # Explicitly map ScoutResult to dict to ensure all fields reach the UI
        return [
            _map_scout_result(r)
            for r in sorted(all_results, key=lambda res: res.true_family_cost)
        ]

    elif req.depart_date and req.return_date:
        try:
            d = date.fromisoformat(req.depart_date)
            r = date.fromisoformat(req.return_date)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail="Invalid date format. Use YYYY-MM-DD."
            ) from e
        try:
            results = scout_flex(
                pm,
                profile,
                airline_db,
                cal,
                req.origin.upper(),
                req.destination.upper(),
                d,
                r,
                req.flex_days,
            )
            return [_map_scout_result(r) for r in results]
        except PriceSourceError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=400, detail="Provide months OR depart/return dates"
        )


@app.get("/trips/{trip_id}/flex")
def get_trip_flex(
    trip_id: int, session: Annotated[Session, Depends(get_db)], flex_days: int = 3
):
    import json as _json

    from fly_o_myte.calendar import get_calendar
    from fly_o_myte.fees import get_airline_db
    from fly_o_myte.price_sources.hookspecs import PriceSourceError
    from fly_o_myte.scout import scout_flex
    from fly_o_myte.tracker import build_plugin_manager_from_settings

    trip = session.get(Trip, trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    assert trip.id is not None
    settings = get_settings()
    flex_key = f"{trip.depart_date}|{trip.return_date}|{flex_days}"

    # Check FlexCache (SQLite-persisted, survives restarts)
    if settings.serpapi_cache_ttl_hours > 0:
        cached = get_flex_cache(session, trip.id, flex_key)
        if cached:
            computed_at = datetime.fromisoformat(cached.computed_at)
            now = datetime.now(UTC)
            if computed_at.tzinfo is None:
                computed_at = computed_at.replace(tzinfo=UTC)
            age_hours = (now - computed_at).total_seconds() / 3600
            if age_hours < settings.serpapi_cache_ttl_hours:
                logger.debug(
                    "FlexCache HIT for trip %d key %s (age %.1fh)",
                    trip.id,
                    flex_key,
                    age_hours,
                )
                return _json.loads(cached.results_json)

    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()
    airline_db = get_airline_db()
    cal = get_calendar()

    d = date.fromisoformat(trip.depart_date)
    r = (
        date.fromisoformat(trip.return_date)
        if trip.return_date
        else d + timedelta(days=7)
    )

    try:
        results = scout_flex(
            pm, profile, airline_db, cal, trip.origin, trip.destination, d, r, flex_days
        )
    except PriceSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    mapped_results = [_map_scout_result(r) for r in results]

    if settings.serpapi_cache_ttl_hours > 0 and results:
        set_flex_cache(
            session,
            trip.id,
            flex_key,
            _json.dumps(mapped_results),
        )

    return mapped_results


@app.post("/planner")
def plan_trip(intent_text: str):
    from fly_o_myte.planner import extract_trip_intent

    settings = get_settings()
    api_key = settings.anthropic_api_key or None

    # We don't want the interactive wizard if API key is missing
    # In the UI, we might handle the "wizard" differently, but for now
    # let's assume it only works with API key or returns a basic intent
    if not api_key:
        # Fallback to a very simple manual parse or error
        # For the demo, let's pretend we can parse it if it follows a simple pattern
        # or just return a default intent
        return {"error": "Anthropic API key required for natural language planning"}

    intent = extract_trip_intent(intent_text, api_key)
    return intent


@app.post("/recompute")
def recompute_costs(session: Annotated[Session, Depends(get_db)]):
    """
    Recompute true_family_cost for all snapshots using the current family profile.
    Also updates the trip's own adults/children/bags metadata to match profile.
    """
    import json as _json

    from sqlmodel import select

    from fly_o_myte.db.sqlite import PriceSnapshot
    from fly_o_myte.fees import get_airline_db
    from fly_o_myte.recommender import classify_route
    from fly_o_myte.true_cost import compute_true_cost

    profile = load_family_profile()
    airline_db = get_airline_db()
    trips = list_all_trips(session)
    updated_trips = 0
    updated_snaps = 0

    for trip in trips:
        # Update trip metadata from profile
        trip.adults = profile.adults
        trip.children_json = _json.dumps(
            [{"name": c.name, "dob": str(c.dob)} for c in profile.children]
        )
        trip.bags_per_person = profile.bags_per_person
        trip.max_stops = profile.max_stops
        session.add(trip)

        depart = date.fromisoformat(trip.depart_date)
        ret = date.fromisoformat(trip.return_date) if trip.return_date else None
        child_ages = profile.child_ages_at(depart)
        route_type = classify_route(trip.origin, trip.destination)

        snaps = list(
            session.exec(select(PriceSnapshot).where(PriceSnapshot.trip_id == trip.id))
        )
        for snap in snaps:
            bundle = airline_db.get_or_default(snap.airline_code or "")
            bd = compute_true_cost(
                airline_bundle=bundle,
                base_fare_per_adult=snap.base_fare_per_adult,
                adults=trip.adults,
                child_ages=child_ages,
                bags_per_person=trip.bags_per_person,
                depart_date=depart,
                return_date=ret,
                stops=snap.stops or 0,
                route_type=route_type,
            )
            snap.true_family_cost = bd.total
            snap.true_cost_breakdown = _json.dumps(bd.as_dict())
            session.add(snap)
            updated_snaps += 1

        if snaps:
            updated_trips += 1

    session.commit()
    return {"updated_trips": updated_trips, "updated_snapshots": updated_snaps}


@app.get("/analytics/{origin}/{destination}")
def get_analytics(origin: str, destination: str):
    from fly_o_myte.db.duckdb import query_route_context

    settings = get_settings()
    ctx = query_route_context(
        settings.analytics_dir, origin.upper(), destination.upper()
    )
    return ctx
