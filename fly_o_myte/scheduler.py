"""
Application-level background scheduler for flight polling.
Replaces OS-level crontab with an internal APScheduler-based system.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fly_o_myte.config import get_settings, load_family_profile
from fly_o_myte.db.sqlite import Trip, create_db_engine, get_session, list_active_trips
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
    Remove all existing 'poll_trip' jobs and re-add them for all active trips.
    Call this when trips are added, updated, or deleted.
    """
    settings = get_settings()
    engine = create_db_engine(settings.db_path)

    # Remove all current polling jobs
    for job in _scheduler.get_jobs():
        if job.id.startswith("poll_trip_"):
            _scheduler.remove_job(job.id)

    with get_session(engine) as session:
        active_trips = list_active_trips(session)
        for trip in active_trips:
            assert trip.id is not None
            _add_trip_job(trip)

    logger.debug("Scheduler synced: %d active trips scheduled", len(active_trips))


def update_trip_schedule(trip: Trip):
    """Update or add a specific trip's schedule without a full sync."""
    job_id = f"poll_trip_{trip.id}"
    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if trip.is_active:
        _add_trip_job(trip)


def _add_trip_job(trip: Trip):
    """Add a job for a specific trip using its cron_schedule."""
    job_id = f"poll_trip_{trip.id}"
    try:
        _scheduler.add_job(
            _run_scheduled_poll,
            trigger=CronTrigger.from_crontab(trip.cron_schedule),
            id=job_id,
            args=[trip.id],
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace if machine was asleep
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


def _run_scheduled_poll(trip_id: int):
    """Worker function executed by APScheduler."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    profile = load_family_profile()
    pm = build_plugin_manager_from_settings()

    with get_session(engine) as session:
        trip = session.get(Trip, trip_id)
        if not trip or not trip.is_active:
            logger.warning(
                "Scheduled poll skipped: trip %d is missing or inactive", trip_id
            )
            return

        try:
            logger.info("Running scheduled poll for trip %d (%s)", trip_id, trip.label)
            poll_trip(session, trip, profile, pm, send_alerts=True)
        except Exception as e:
            logger.error(
                "Error during scheduled poll for trip %d: %s", trip_id, e, exc_info=True
            )
