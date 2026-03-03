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
from datetime import datetime
from email.message import EmailMessage

from fly_o_myte.config import Settings, get_settings
from fly_o_myte.db.sqlite import Recommendation, Trip

logger = logging.getLogger(__name__)


def send_book_now_alert(
    trip: Trip,
    rec: Recommendation,
    settings: Settings | None = None,
) -> bool:
    """
    Send a book_now email alert for a trip.

    Returns True if the email was sent successfully, False otherwise.
    Does not raise — failures are logged as warnings only.
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

    subject = f"[fly-o-myte] Book Now — {trip.label}"
    body = _build_email_body(trip, rec)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_user
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


def _build_email_body(trip: Trip, rec: Recommendation) -> str:
    generated = rec.generated_at[:16].replace("T", " ")
    lines = [
        f"Travo Booking Alert — {datetime.utcnow().strftime('%d %b %Y')}",
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
        "Decision:    BOOK NOW",
        f"Confidence:  {rec.confidence:.0%}",
        f"True cost:   ${rec.true_family_cost:,.0f} AUD (family total)",
        f"Regret risk: {rec.regret_risk.upper()}",
        "",
        "Why:",
        rec.rationale,
        "",
        f"Generated:   {generated} UTC",
        "",
        "---",
        "Travo — your family travel advisor",
        f"Run `fom check {trip.id}` for the full breakdown.",
    ]
    return "\n".join(lines)
