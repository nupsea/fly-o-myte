"""
Tests for fly_o_myte/notifier.py — SMTP alert wiring.

send_book_now_alert() is tested directly with explicit Settings objects so
credentials can be varied per test without touching the lru_cached singleton.

Tracker integration tests verify the poll_trip → send_book_now_alert →
mark_email_sent wiring by pre-seeding snapshots on distinct days to force a
days_to_departure <= 7 (book_now) result.

Mock boundary:
  smtplib.SMTP only — no fly_o_myte.* patches.
  SMTP credentials injected via monkeypatch.setenv + cache_clear for tracker tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from fly_o_myte.config import DepartureWindow, FamilyProfile, Settings
from fly_o_myte.db.sqlite import (
    PriceSnapshot,
    Recommendation,
    Trip,
    get_latest_recommendation,
    insert_snapshot,
    insert_trip,
)
from fly_o_myte.notifier import send_book_now_alert
from fly_o_myte.tracker import poll_trip

# ─── Test helpers ──────────────────────────────────────────────────────────────


def _smtp_settings(**overrides) -> Settings:
    """Create Settings with test SMTP credentials; override any field via kwargs."""
    base: dict = {
        "smtp_user": "sender@example.com",
        "smtp_pass": "secret",
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "default_alert_email": "alerts@example.com",
    }
    base.update(overrides)
    return Settings(**base)


def _insert_trip(session, **kwargs) -> Trip:
    """Insert and return a Trip with sensible defaults."""
    defaults: dict = {
        "label": "BNE-SYD Easter",
        "origin": "BNE",
        "destination": "SYD",
        "depart_date": "2026-07-20",
        "return_date": "2026-07-27",
        "adults": 2,
    }
    defaults.update(kwargs)
    return insert_trip(session, Trip(**defaults))


def _make_rec(trip: Trip) -> Recommendation:
    """Build an unsaved book_now Recommendation for direct notifier tests."""
    assert trip.id is not None
    return Recommendation(
        trip_id=trip.id,
        decision="book_now",
        confidence=0.85,
        regret_risk="low",
        true_family_cost=298.0,
        rationale="Price is below the 5-snapshot average. Book this week.",
        generated_at=datetime.now(UTC).isoformat(),
    )


def _profile() -> FamilyProfile:
    return FamilyProfile(
        adults=2,
        children=[],
        origin_airport="BNE",
        state="QLD",
        bags_per_person=1,
        max_stops=1,
        preferred_departure_window=DepartureWindow(earliest_hour=8, latest_hour=18),
    )


def _seed_prior_snapshots(session, trip: Trip) -> None:
    """
    Pre-seed 3 snapshots on 3 distinct past days.

    After a subsequent poll_trip call (which adds today's snapshot), the
    recommender sees n=4 distinct days — enough to apply the
    days_to_departure <= 7 rule and return book_now.
    """
    assert trip.id is not None
    for days_ago in (3, 2, 1):
        ts = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
        insert_snapshot(
            session,
            PriceSnapshot(
                trip_id=trip.id,
                fetched_at=ts,
                source="stub",
                airline_code="QF",
                base_fare_per_adult=149.0,
                true_family_cost=298.0,
                true_cost_breakdown="{}",
                stops=0,
                departure_time="10:30",
                duration_minutes=100,
            ),
        )


# ─── Direct notifier tests ──────────────────────────────────────────────────


class TestSendBookNowAlert:
    def test_sends_email_returns_true(self, db_session):
        """Happy path: credentials set, smtplib succeeds → True, send_message called."""
        trip = _insert_trip(db_session)
        rec = _make_rec(trip)
        cfg = _smtp_settings()

        with patch("smtplib.SMTP") as mock_cls:
            mock_server = MagicMock()
            mock_cls.return_value.__enter__.return_value = mock_server
            result = send_book_now_alert(trip, rec, settings=cfg)

        assert result is True
        mock_server.send_message.assert_called_once()

    def test_returns_false_when_smtp_user_empty(self, db_session):
        """No SMTP user → False, smtplib.SMTP never instantiated."""
        trip = _insert_trip(db_session, alert_email="user@test.com")
        rec = _make_rec(trip)
        cfg = _smtp_settings(smtp_user="")

        with patch("smtplib.SMTP") as mock_cls:
            result = send_book_now_alert(trip, rec, settings=cfg)

        assert result is False
        mock_cls.assert_not_called()

    def test_returns_false_when_no_recipient(self, db_session):
        """trip.alert_email=None and default_alert_email='' → False."""
        trip = _insert_trip(db_session, alert_email=None)
        rec = _make_rec(trip)
        cfg = _smtp_settings(default_alert_email="")

        with patch("smtplib.SMTP") as mock_cls:
            result = send_book_now_alert(trip, rec, settings=cfg)

        assert result is False
        mock_cls.assert_not_called()

    def test_returns_false_on_smtp_exception(self, db_session):
        """smtplib.SMTP raises → False, exception does not propagate."""
        trip = _insert_trip(db_session)
        rec = _make_rec(trip)
        cfg = _smtp_settings()

        with patch("smtplib.SMTP") as mock_cls:
            mock_cls.side_effect = OSError("connection refused")
            result = send_book_now_alert(trip, rec, settings=cfg)

        assert result is False

    def test_subject_contains_fly_o_myte_and_trip_label(self, db_session):
        """Email subject contains 'fly-o-myte' and the trip label; no 'Travo'."""
        trip = _insert_trip(db_session, label="School Hols Trip")
        rec = _make_rec(trip)
        cfg = _smtp_settings()

        with patch("smtplib.SMTP") as mock_cls:
            mock_server = MagicMock()
            mock_cls.return_value.__enter__.return_value = mock_server
            send_book_now_alert(trip, rec, settings=cfg)

        msg = mock_server.send_message.call_args.args[0]
        subject = msg["Subject"]
        assert "fly-o-myte" in subject
        assert "School Hols Trip" in subject
        assert "Travo" not in subject
        assert "travo" not in subject

    def test_body_contains_fom_check(self, db_session):
        """Email body contains 'fom check'; no 'travo check'."""
        trip = _insert_trip(db_session)
        rec = _make_rec(trip)
        cfg = _smtp_settings()

        with patch("smtplib.SMTP") as mock_cls:
            mock_server = MagicMock()
            mock_cls.return_value.__enter__.return_value = mock_server
            send_book_now_alert(trip, rec, settings=cfg)

        msg = mock_server.send_message.call_args.args[0]
        # set_content() may base64-encode the payload — decode to get plaintext
        raw = msg.get_payload(decode=True)
        body = raw.decode() if raw else ""
        assert "fom check" in body
        assert "travo check" not in body


# ─── Tracker integration tests ───────────────────────────────────────────────


@pytest.mark.integration
class TestTrackerNotifierIntegration:
    """Tests for the poll_trip → send_book_now_alert → mark_email_sent wiring."""

    def test_book_now_with_send_alerts_true_marks_email_sent(
        self, db_session, stub_pm, monkeypatch
    ):
        """
        poll_trip with send_alerts=True and SMTP configured on a near-departure
        trip → Recommendation.email_sent == 1.

        The trip departs in 5 days.  After seeding 3 prior-day snapshots,
        poll_trip adds a 4th (today), giving n=4 distinct days.  The
        days_to_departure <= 7 rule fires → book_now → alert sent.
        """
        from fly_o_myte.config import get_settings

        near_depart = (date.today() + timedelta(days=5)).isoformat()
        trip = insert_trip(
            db_session,
            Trip(
                label="Imminent trip",
                origin="BNE",
                destination="SYD",
                depart_date=near_depart,
                adults=2,
                bags_per_person=1,
                max_stops=1,
                alert_email="family@test.com",
            ),
        )
        _seed_prior_snapshots(db_session, trip)

        # Set SMTP credentials via env so get_settings() picks them up
        monkeypatch.setenv("SMTP_USER", "sender@test.com")
        monkeypatch.setenv("SMTP_PASS", "testpass")
        get_settings.cache_clear()
        try:
            with patch("smtplib.SMTP") as mock_cls:
                mock_cls.return_value.__enter__.return_value = MagicMock()
                poll_trip(db_session, trip, _profile(), stub_pm, send_alerts=True)
        finally:
            # Restore cache so subsequent tests use original (no-SMTP) settings
            get_settings.cache_clear()

        assert trip.id is not None
        rec = get_latest_recommendation(db_session, trip.id)
        assert rec is not None
        assert rec.decision == "book_now"
        assert rec.email_sent == 1

    def test_send_alerts_false_leaves_email_unsent(self, db_session, stub_pm):
        """
        poll_trip with send_alerts=False → email_sent remains 0 even when
        the decision is book_now.
        """
        near_depart = (date.today() + timedelta(days=5)).isoformat()
        trip = insert_trip(
            db_session,
            Trip(
                label="No-alert trip",
                origin="BNE",
                destination="SYD",
                depart_date=near_depart,
                adults=2,
                bags_per_person=1,
                max_stops=1,
                alert_email="family@test.com",
            ),
        )
        _seed_prior_snapshots(db_session, trip)

        poll_trip(db_session, trip, _profile(), stub_pm, send_alerts=False)

        assert trip.id is not None
        rec = get_latest_recommendation(db_session, trip.id)
        assert rec is not None
        assert rec.decision == "book_now"
        assert rec.email_sent == 0
