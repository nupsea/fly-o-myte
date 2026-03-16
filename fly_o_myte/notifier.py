"""
Email notifier — SMTP alerts for book_now recommendations.

Sends a plain-text email when the recommender produces a book_now decision
and the trip has an alert_email configured.

Uses stdlib smtplib — no third-party email library required.
Credentials come from Settings (SMTP_USER / SMTP_PASS env vars).
"""

from __future__ import annotations

import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage

from fly_o_myte.config import Settings, get_settings
from fly_o_myte.db.sqlite import Recommendation, Trip

logger = logging.getLogger(__name__)


def send_book_now_alert(
    trip: Trip,
    rec: Recommendation,
    settings: Settings | None = None,
    is_initial: bool = False,
) -> bool:
    """
    Send an email alert for a trip (either Book Now or Initial Tracking).

    Returns True if the email was sent successfully, False otherwise.
    """
    cfg = settings or get_settings()

    recipient = trip.alert_email or cfg.default_alert_email
    if not recipient:
        logger.debug(
            "No alert email configured for trip %s — skipping notification", trip.id
        )
        return False

    if not cfg.smtp_user or not cfg.smtp_pass:
        logger.warning(
            "SMTP credentials not configured — cannot send alert for trip %s", trip.id
        )
        return False

    decision_label = rec.decision.replace("_", " ").upper()
    if is_initial:
        subject = f"[fly-o-myte] Tracking Started: {decision_label} — {trip.label}"
    else:
        subject = f"[fly-o-myte] Price Alert: {decision_label} — {trip.label}"

    body = _build_email_body(trip, rec, is_initial)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.default_alert_email or cfg.smtp_user
    msg["To"] = recipient
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_pass)
            server.send_message(msg)
        logger.info("Alert sent for trip %s to %s", trip.id, recipient)
        return True
    except Exception as exc:
        logger.warning("Failed to send alert for trip %s: %s", trip.id, exc)
        return False


def _build_email_body(trip: Trip, rec: Recommendation, is_initial: bool = False) -> str:
    generated = rec.generated_at[:16].replace("T", " ")
    header = "Initial Tracking Report" if is_initial else "Price Alert"

    lines = [
        f"fly-o-myte {header} — {datetime.now(UTC).strftime('%d %b %Y')}",
        "=" * 50,
        "",
        f"Trip:        {trip.label}",
        f"Route:       {trip.origin} → {trip.destination}",
        f"Departure:   {trip.depart_date}",
    ]
    if trip.return_date:
        lines.append(f"Return:      {trip.return_date}")

    lines += [
        "",
        f"Decision:    {rec.decision.replace('_', ' ').upper()}",
        f"Confidence:  {rec.confidence:.0%}",
        f"True cost:   ${rec.true_family_cost:,.0f} AUD (family total)",
        f"Regret risk: {rec.regret_risk.upper()}",
        "",
        "Rationale:",
        rec.rationale,
        "",
        f"Generated:   {generated} UTC",
        "",
        "---",
        "fly-o-myte — your family travel advisor",
        f"Run `fom check {trip.id}` for the full breakdown.",
    ]
    return "\n".join(lines)
