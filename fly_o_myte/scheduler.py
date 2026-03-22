"""
Application-level background scheduler for flight polling.

Campaign-aware: schedules one cron job per active campaign, polling the
campaign's current active trip variant.  Survives date changes because the
campaign is the stable anchor.

Also supports legacy per-trip scheduling for backward compatibility.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fly_o_myte.config import get_settings, load_family_profile
from fly_o_myte.db.sqlite import (
    TripCampaign,
    Trip,
    create_db_engine,
    get_active_variant,
    get_session,
    list_campaigns,
)
from fly_o_myte.tracker import build_plugin_manager_from_settings, poll_trip

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler = BackgroundScheduler()


def start_scheduler():
    """Start the background scheduler and sync jobs from the database."""
    if not _scheduler.running:
        _scheduler.start()
        sync_scheduler_from_db()
        logger.info("Background scheduler started")


def stop_scheduler():
    """Shut down the background scheduler."""
    if _scheduler.running:
        _scheduler.shutdown()
        logger.info("Background scheduler stopped")


def sync_scheduler_from_db():
    """
    Remove all existing polling jobs and re-add them for all active campaigns.
    Each campaign gets one cron job that polls its current active trip variant.
    """
    settings = get_settings()
    engine = create_db_engine(settings.db_path)

    # Remove all current polling jobs (both legacy per-trip and campaign-level)
    for job in _scheduler.get_jobs():
        if job.id.startswith("poll_trip_") or job.id.startswith("poll_campaign_"):
            _scheduler.remove_job(job.id)

    with get_session(engine) as session:
        campaigns = list_campaigns(session)
        scheduled = 0
        for campaign in campaigns:
            if campaign.status == "active":
                assert campaign.id is not None
                _add_campaign_job(campaign)
                scheduled += 1

    logger.debug("Scheduler synced: %d active campaigns scheduled", scheduled)


def update_campaign_schedule(campaign: TripCampaign):
    """Update or add a specific campaign's schedule without a full sync."""
    job_id = f"poll_campaign_{campaign.id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if campaign.status == "active":
        _add_campaign_job(campaign)


def update_trip_schedule(trip: Trip):
    """Legacy: update schedule when a trip changes.

    Looks up the trip's campaign and reschedules at campaign level.
    Falls back to per-trip scheduling if no campaign is attached.
    """
    if trip.campaign_id:
        settings = get_settings()
        engine = create_db_engine(settings.db_path)
        with get_session(engine) as session:
            from fly_o_myte.db.sqlite import get_campaign

            campaign = get_campaign(session, trip.campaign_id)
            if campaign:
                update_campaign_schedule(campaign)
                return

    # Fallback: legacy per-trip scheduling
    job_id = f"poll_trip_{trip.id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)
    if trip.is_active and not trip.is_archived:
        _add_trip_job_legacy(trip)


def _add_campaign_job(campaign: TripCampaign):
    """Add a cron job for a campaign using its cron_schedule."""
    job_id = f"poll_campaign_{campaign.id}"
    try:
        _scheduler.add_job(
            _run_campaign_poll,
            trigger=CronTrigger.from_crontab(campaign.cron_schedule),
            id=job_id,
            args=[campaign.id],
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace if machine was asleep
        )
        logger.info(
            "Scheduled campaign %d (%s) at '%s'",
            campaign.id,
            campaign.name,
            campaign.cron_schedule,
        )
    except Exception as e:
        logger.error(
            "Failed to schedule campaign %d with cron '%s': %s",
            campaign.id,
            campaign.cron_schedule,
            e,
        )


def _add_trip_job_legacy(trip: Trip):
    """Legacy: schedule a single trip (no campaign)."""
    job_id = f"poll_trip_{trip.id}"
    try:
        _scheduler.add_job(
            _run_trip_poll_legacy,
            trigger=CronTrigger.from_crontab(trip.cron_schedule),
            id=job_id,
            args=[trip.id],
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "Scheduled trip %d (%s) at '%s'", trip.id, trip.label, trip.cron_schedule
        )
    except Exception as e:
        logger.error(
            "Failed to schedule trip %d with cron '%s': %s",
            trip.id,
            trip.cron_schedule,
            e,
        )


def _run_campaign_poll(campaign_id: int):
    """Worker function for campaign-level scheduled polls."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()

    with get_session(engine) as session:
        trip = get_active_variant(session, campaign_id)
        if not trip:
            logger.warning(
                "Scheduled poll skipped: campaign %d has no active variant",
                campaign_id,
            )
            return

        try:
            logger.info(
                "Running scheduled poll for campaign %d, variant %d (%s)",
                campaign_id,
                trip.id,
                trip.label,
            )
            poll_trip(session, trip, profile, pm, send_alerts=True)
        except Exception as e:
            logger.error(
                "Error during scheduled poll for campaign %d: %s",
                campaign_id,
                e,
                exc_info=True,
            )


def _run_trip_poll_legacy(trip_id: int):
    """Legacy worker for per-trip scheduled polls (trips without campaigns)."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()

    with get_session(engine) as session:
        trip = session.get(Trip, trip_id)
        if not trip or not trip.is_active or trip.is_archived:
            logger.warning(
                "Scheduled poll skipped: trip %d is missing/inactive/archived",
                trip_id,
            )
            return

        try:
            logger.info(
                "Running scheduled poll for trip %d (%s)", trip_id, trip.label
            )
            poll_trip(session, trip, profile, pm, send_alerts=True)
        except Exception as e:
            logger.error(
                "Error during scheduled poll for trip %d: %s",
                trip_id,
                e,
                exc_info=True,
            )
