"""
Tests for fly_o_myte/planner.py — TripIntent extraction.

Tests:
  - LLM extraction path: mocked Anthropic API via pytest-httpx
  - Fallback wizard path: monkeypatched rich.prompt.Prompt.ask
  - Origin override: 'from Sydney' resolves to SYD
"""

from __future__ import annotations

import pytest


class TestExtractTripIntent:
    """Tests for extract_trip_intent() covering LLM and wizard paths."""

    def test_extract_llm_sri_lanka_december(self, httpx_mock):
        """LLM path: mocked Anthropic API returns Sri Lanka December → CMB month=12."""
        from fly_o_myte.planner import extract_trip_intent

        # Mock the Anthropic messages API — direct httpx call with JSON text response
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json={
                "id": "msg_01test",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": '{"destination_query": "sri lanka", "month": 12, "year": 2026, "nights": 7, "flex_days": 3, "origin_override_query": null}',
                    }
                ],
                "model": "claude-haiku-4-5-20251001",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        )

        intent = extract_trip_intent("Sri Lanka in December", api_key="test_key_1234")

        assert intent.destination_iata == "CMB"
        assert (
            "Sri Lanka" in intent.destination_display
            or "Colombo" in intent.destination_display
        )
        assert intent.month == 12
        assert intent.year == 2026
        assert intent.nights == 7
        assert intent.origin_override is None

    def test_extract_llm_origin_override_sydney(self, httpx_mock):
        """LLM path: 'from Sydney' in text resolves origin_override to SYD."""
        from fly_o_myte.planner import extract_trip_intent

        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json={
                "id": "msg_02test",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": '{"destination_query": "sri lanka", "month": 12, "year": 2026, "nights": 7, "flex_days": 3, "origin_override_query": "Sydney"}',
                    }
                ],
                "model": "claude-haiku-4-5-20251001",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 110, "output_tokens": 55},
            },
        )

        intent = extract_trip_intent(
            "from Sydney to Sri Lanka in December", api_key="test_key_1234"
        )

        assert intent.destination_iata == "CMB"
        assert intent.origin_override == "SYD"

    def test_extract_wizard_fallback(self, monkeypatch):
        """Fallback path: api_key=None uses structured prompt wizard."""
        from fly_o_myte.planner import extract_trip_intent

        # Simulate user inputs: destination, month, nights, flex
        answers = iter(["Sri Lanka", "dec-2026", "7", "3"])
        monkeypatch.setattr(
            "rich.prompt.Prompt.ask",
            lambda *args, **kwargs: next(answers),
        )

        intent = extract_trip_intent("", api_key=None)

        assert intent.destination_iata == "CMB"
        assert intent.month == 12
        assert intent.year == 2026
        assert intent.nights == 7
        assert intent.flex_days == 3
        assert intent.origin_override is None

    def test_extract_wizard_falls_back_on_llm_error(self, httpx_mock, monkeypatch):
        """When LLM call fails (HTTP 500), falls back to wizard gracefully."""
        from fly_o_myte.planner import extract_trip_intent

        # Mock returns HTTP 500 — triggers raise_for_status → exception → fallback
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            status_code=500,
            json={"error": {"type": "api_error", "message": "Server error"}},
        )

        # Fallback wizard input
        answers = iter(["Sri Lanka", "dec-2026", "7", "3"])
        monkeypatch.setattr(
            "rich.prompt.Prompt.ask",
            lambda *args, **kwargs: next(answers),
        )

        # Should not raise — falls back to wizard
        intent = extract_trip_intent("Sri Lanka in December", api_key="test_key_bad")
        assert intent.destination_iata == "CMB"
        assert intent.month == 12


class TestParseMonthYear:
    """Tests for the _parse_month_year helper."""

    def test_dec_2026(self):
        from fly_o_myte.planner import _parse_month_year

        assert _parse_month_year("dec-2026") == (12, 2026)

    def test_december_2026(self):
        from fly_o_myte.planner import _parse_month_year

        assert _parse_month_year("december-2026") == (12, 2026)

    def test_july_2026(self):
        from fly_o_myte.planner import _parse_month_year

        assert _parse_month_year("jul-2026") == (7, 2026)

    def test_numeric_12_2026(self):
        from fly_o_myte.planner import _parse_month_year

        assert _parse_month_year("12-2026") == (12, 2026)

    def test_2026_12(self):
        from fly_o_myte.planner import _parse_month_year

        assert _parse_month_year("2026-12") == (12, 2026)

    def test_invalid_raises(self):
        from fly_o_myte.planner import _parse_month_year

        with pytest.raises(ValueError):
            _parse_month_year("not-a-date")


class TestResolveOrigin:
    """Tests for _resolve_origin helper."""

    def test_sydney_resolves_to_syd(self):
        from fly_o_myte.planner import _resolve_origin

        assert _resolve_origin("Sydney") == "SYD"

    def test_melbourne_resolves_to_mel(self):
        from fly_o_myte.planner import _resolve_origin

        assert _resolve_origin("Melbourne") == "MEL"

    def test_case_insensitive(self):
        from fly_o_myte.planner import _resolve_origin

        assert _resolve_origin("SYDNEY") == "SYD"
        assert _resolve_origin("sydney") == "SYD"

    def test_unknown_returns_none(self):
        from fly_o_myte.planner import _resolve_origin

        result = _resolve_origin("zzzzunknown")
        assert result is None
