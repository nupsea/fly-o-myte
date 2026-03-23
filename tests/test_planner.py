"""
Tests for fly_o_myte/planner.py — TripIntent extraction + agent loop.

Tests:
  - LLM extraction path: mocked OpenAI API via pytest-httpx
  - Fallback wizard path: monkeypatched rich.prompt.Prompt.ask
  - Origin override: 'from Sydney' resolves to SYD
  - Agent loop: run_planner_loop with tool calls and submit_plan
"""

from __future__ import annotations

import json

import pytest


class TestExtractTripIntent:
    """Tests for extract_trip_intent() covering LLM and wizard paths."""

    def test_extract_llm_sri_lanka_december(self, httpx_mock):
        """LLM path: mocked OpenAI API returns Sri Lanka December → CMB month=12."""
        from fly_o_myte.planner import extract_trip_intent

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"destination_query": "sri lanka", "month": 12, "year": 2026, "nights": 7, "flex_days": 3, "origin_override_query": null}',
                        }
                    }
                ],
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
            url="https://api.openai.com/v1/chat/completions",
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"destination_query": "sri lanka", "month": 12, "year": 2026, "nights": 7, "flex_days": 3, "origin_override_query": "Sydney"}',
                        }
                    }
                ],
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

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
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


class TestRunPlannerLoop:
    """Tests for the agent loop: run_planner_loop()."""

    def _make_profile(self):
        """Create a minimal FamilyProfile for testing."""
        from datetime import date

        from fly_o_myte.config import Child, FamilyProfile

        return FamilyProfile(
            adults=2,
            children=[
                Child(name="Alice", dob=date(2018, 5, 10)),
                Child(name="Bob", dob=date(2021, 8, 15)),
            ],
            origin_airport="BNE",
            state="QLD",
            default_trip_length=14,
        )

    def _make_calendar(self):
        """Create a SchoolCalendar with test data."""
        from fly_o_myte.calendar import SchoolCalendar

        return SchoolCalendar({
            "QLD": {
                2026: {
                    "christmas": {
                        "label": "Christmas holidays",
                        "start": "2026-12-13",
                        "end": "2027-01-25",
                    }
                }
            }
        })

    def test_loop_confident_plan(self, httpx_mock):
        """LLM calls get_family_profile, resolve_destination, then submit_plan."""
        from fly_o_myte.planner import run_planner_loop

        # Round 1: LLM calls get_family_profile + resolve_destination
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "get_family_profile",
                                    "arguments": "{}",
                                },
                            },
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {
                                    "name": "resolve_destination",
                                    "arguments": json.dumps({"query": "Bangalore"}),
                                },
                            },
                        ],
                    }
                }],
            },
        )

        # Round 2: LLM calls submit_plan
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_3",
                                "type": "function",
                                "function": {
                                    "name": "submit_plan",
                                    "arguments": json.dumps({
                                        "destination_iata": "BLR",
                                        "destination_display": "Bangalore Kempegowda",
                                        "origin_iata": "BNE",
                                        "nights": 30,
                                        "month": 12,
                                        "year": 2026,
                                        "flex_days": 3,
                                        "confidence": 0.88,
                                        "reasoning": "Dec overlaps QLD Christmas holidays.",
                                    }),
                                },
                            }
                        ],
                    }
                }],
            },
        )

        profile = self._make_profile()
        calendar = self._make_calendar()

        result = run_planner_loop(
            messages=[{"role": "user", "content": "Bengaluru in December for 30 days"}],
            api_key="test-key",
            profile=profile,
            calendar=calendar,
        )

        assert result["type"] == "plan"
        assert result["intent"]["destination_iata"] == "BLR"
        assert result["intent"]["confidence"] == 0.88
        assert result["intent"]["nights"] == 30
        assert "scout_params" in result
        assert result["scout_params"]["origin"] == "BNE"
        assert result["scout_params"]["destination"] == "BLR"

    def test_loop_asks_user(self, httpx_mock):
        """LLM returns a plain text message (no tool calls) → type=message."""
        from fly_o_myte.planner import run_planner_loop

        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Could you tell me when you'd like to travel?",
                    }
                }],
            },
        )

        profile = self._make_profile()
        calendar = self._make_calendar()

        result = run_planner_loop(
            messages=[{"role": "user", "content": "somewhere warm"}],
            api_key="test-key",
            profile=profile,
            calendar=calendar,
        )

        assert result["type"] == "message"
        assert "when" in result["content"].lower()
        assert len(result["messages"]) >= 2  # user + assistant

    def test_loop_max_iterations(self, httpx_mock):
        """Loop returns error after max_iterations of non-terminating tool calls."""
        from fly_o_myte.planner import run_planner_loop

        # Always return a get_family_profile tool call (never terminates)
        for _ in range(3):
            httpx_mock.add_response(
                url="https://api.openai.com/v1/chat/completions",
                json={
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": f"call_loop",
                                "type": "function",
                                "function": {
                                    "name": "get_family_profile",
                                    "arguments": "{}",
                                },
                            }],
                        }
                    }],
                },
            )

        profile = self._make_profile()
        calendar = self._make_calendar()

        result = run_planner_loop(
            messages=[{"role": "user", "content": "test"}],
            api_key="test-key",
            profile=profile,
            calendar=calendar,
            max_iterations=3,
        )

        assert result["type"] == "error"
        assert "iterations" in result["content"].lower()


class TestBuildScoutParams:
    """Tests for build_scout_params()."""

    def _make_profile(self):
        from fly_o_myte.config import FamilyProfile
        return FamilyProfile(origin_airport="BNE", default_trip_length=14)

    def test_months_mode(self):
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "BLR",
            "origin_iata": "BNE",
            "month": 12,
            "year": 2026,
            "nights": 30,
            "flex_days": 3,
        }
        params = build_scout_params(intent, self._make_profile())

        assert params["origin"] == "BNE"
        assert params["destination"] == "BLR"
        assert "months" in params
        assert params["months"][0] == "dec-2026"
        assert params["trip_length"] == 30

    def test_exact_date_mode(self):
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "CMB",
            "origin_iata": "BNE",
            "depart_earliest": "2026-12-15",
            "return_latest": "2027-01-15",
            "nights": 30,
            "flex_days": 3,
        }
        params = build_scout_params(intent, self._make_profile())

        assert params["depart_date"] == "2026-12-15"
        assert params["return_date"] == "2027-01-15"
        assert params["flex_days"] == 3

    def test_uses_profile_origin_when_missing(self):
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "SIN",
            "month": 6,
            "year": 2026,
            "nights": 7,
        }
        params = build_scout_params(intent, self._make_profile())

        assert params["origin"] == "BNE"

    def test_months_format_matches_scout_request(self):
        """Month strings must be lowercase 'mon-yyyy' to match ScoutRequest validation."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "NAN",
            "origin_iata": "BNE",
            "month": 1,
            "year": 2027,
            "nights": 7,
            "flex_days": 3,
        }
        params = build_scout_params(intent, self._make_profile())

        assert params["months"] == ["jan-2027"]

    def test_long_trip_spans_two_months(self):
        """A 35-night trip starting in December should include January too."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "BLR",
            "origin_iata": "BNE",
            "month": 12,
            "year": 2026,
            "nights": 35,
        }
        params = build_scout_params(intent, self._make_profile())

        assert "dec-2026" in params["months"]
        assert "jan-2027" in params["months"]

    def test_exact_mode_keys_match_scout_request(self):
        """Exact-mode params must use 'depart_date'/'return_date', not 'depart_earliest'/'return_latest'."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "LHR",
            "origin_iata": "SYD",
            "depart_earliest": "2026-06-20",
            "return_latest": "2026-07-10",
            "nights": 20,
            "flex_days": 2,
        }
        params = build_scout_params(intent, self._make_profile())

        # Must use the ScoutRequest field names
        assert "depart_date" in params
        assert "return_date" in params
        assert "depart_earliest" not in params
        assert "return_latest" not in params
        assert params["depart_date"] == "2026-06-20"
        assert params["return_date"] == "2026-07-10"

    def test_no_month_no_date_falls_back_gracefully(self):
        """Intent with neither month nor exact dates should still return valid params."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "DPS",
            "origin_iata": "BNE",
            "nights": 10,
        }
        params = build_scout_params(intent, self._make_profile())

        assert params["origin"] == "BNE"
        assert params["destination"] == "DPS"
        assert "months" in params
        assert len(params["months"]) >= 1


class TestToolHandlers:
    """Tests for individual tool handler functions."""

    def test_handle_get_family_profile(self):
        from datetime import date

        from fly_o_myte.config import Child, FamilyProfile
        from fly_o_myte.planner import _handle_get_family_profile

        profile = FamilyProfile(
            adults=2,
            children=[Child(name="Alice", dob=date(2018, 5, 10))],
            origin_airport="BNE",
        )
        result = json.loads(_handle_get_family_profile(profile))

        assert result["adults"] == 2
        assert result["origin_airport"] == "BNE"
        assert len(result["children"]) == 1
        assert result["children"][0]["name"] == "Alice"

    def test_handle_get_school_holidays(self):
        from fly_o_myte.calendar import SchoolCalendar
        from fly_o_myte.planner import _handle_get_school_holidays

        cal = SchoolCalendar({
            "QLD": {
                2026: {
                    "christmas": {
                        "label": "Christmas holidays",
                        "start": "2026-12-13",
                        "end": "2027-01-25",
                    }
                }
            }
        })
        result = json.loads(_handle_get_school_holidays(cal, "QLD", 2026))

        assert len(result) == 1
        assert result[0]["label"] == "Christmas holidays"

    def test_handle_resolve_destination(self):
        from fly_o_myte.planner import _handle_resolve_destination

        result = json.loads(_handle_resolve_destination("sri lanka"))

        assert any(m["iata"] == "CMB" for m in result)
