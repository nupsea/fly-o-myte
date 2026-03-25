"""
Integration tests for the planner → scout pipeline.

Tests the full chain:
    POST /planner/chat  →  scout_params  →  POST /scout  →  results

No external APIs are called:
  - OpenAI:   intercepted via pytest-httpx (httpx_mock)
  - Tequila/SerpAPI: replaced with _StubTequilaSource via monkeypatch

Test classes:
  TestPlannerChatEndpoint     — /planner/chat contract
  TestScoutEndpointWithStub   — /scout with stub price source
  TestPlannerToScoutPipeline  — end-to-end: planner params fed into /scout
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

# ─── Shared fake settings ──────────────────────────────────────────────────────


class _FakeSettings:
    """Minimal settings stub — only exposes fields used by the tested endpoints."""

    openai_api_key = "test-integ-key"


class _NoKeySettings:
    """Settings stub with no OpenAI key."""

    openai_api_key = ""


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    """FastAPI TestClient that lives for the duration of one test."""
    from fly_o_myte.api import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def with_openai_key(monkeypatch):
    """Patch get_settings in the api module so openai_api_key is non-empty."""
    import fly_o_myte.api as api_mod

    monkeypatch.setattr(api_mod, "get_settings", lambda: _FakeSettings())


@pytest.fixture
def without_openai_key(monkeypatch):
    """Patch get_settings to simulate no OpenAI key — works even if env has a real key."""
    import fly_o_myte.api as api_mod

    monkeypatch.setattr(api_mod, "get_settings", lambda: _NoKeySettings())


@pytest.fixture
def with_stub_pm(monkeypatch, stub_pm):
    """Replace build_plugin_manager_from_settings with the deterministic stub."""
    import fly_o_myte.tracker as tracker_mod

    monkeypatch.setattr(
        tracker_mod, "build_plugin_manager_from_settings", lambda: stub_pm
    )


# ─── Planner chat endpoint ─────────────────────────────────────────────────────


@pytest.mark.integration
class TestPlannerChatEndpoint:
    """Tests for POST /planner/chat — OpenAI mocked via httpx_mock."""

    def _openai_tool_response(self, tool_calls: list[dict]) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls,
                    }
                }
            ]
        }

    def _openai_text_response(self, text: str) -> dict:
        return {"choices": [{"message": {"role": "assistant", "content": text}}]}

    def test_missing_api_key_returns_error(self, api_client, without_openai_key):
        """Without an OpenAI key the endpoint returns type=error immediately.
        Uses without_openai_key fixture to override any real key in the environment."""
        resp = api_client.post(
            "/planner/chat",
            json={
                "messages": [{"role": "user", "content": "Bali in July for 10 days"}]
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "error"
        assert "key" in data["content"].lower()

    def test_plan_response_has_required_fields(
        self, api_client, with_openai_key, httpx_mock
    ):
        """Full agent loop: resolve_destination + submit_plan → type=plan."""
        # Round 1: LLM calls resolve_destination
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json=self._openai_tool_response(
                [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "resolve_destination",
                            "arguments": json.dumps({"query": "Bali"}),
                        },
                    },
                ]
            ),
        )
        # Round 2: LLM calls get_school_holidays
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json=self._openai_tool_response(
                [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "get_school_holidays",
                            "arguments": json.dumps({"state": "QLD", "year": 2026}),
                        },
                    },
                ]
            ),
        )
        # Round 3: LLM submits the plan
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json=self._openai_tool_response(
                [
                    {
                        "id": "call_3",
                        "type": "function",
                        "function": {
                            "name": "submit_plan",
                            "arguments": json.dumps(
                                {
                                    "destination_iata": "DPS",
                                    "destination_display": "Bali Ngurah Rai",
                                    "origin_iata": "BNE",
                                    "nights": 10,
                                    "month": 7,
                                    "year": 2026,
                                    "flex_days": 3,
                                    "confidence": 0.90,
                                    "reasoning": "July overlaps QLD mid-year school holidays.",
                                }
                            ),
                        },
                    },
                ]
            ),
        )

        resp = api_client.post(
            "/planner/chat",
            json={
                "messages": [{"role": "user", "content": "Bali in July for 10 days"}]
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["type"] == "plan"
        assert data["intent"]["destination_iata"] == "DPS"
        assert data["intent"]["confidence"] == 0.90
        assert data["intent"]["nights"] == 10

        # scout_params must have the right keys for /scout to consume
        sp = data["scout_params"]
        assert sp["origin"] == "BNE"
        assert sp["destination"] == "DPS"
        assert "months" in sp or ("depart_date" in sp and "return_date" in sp)
        assert sp.get("trip_length") == 10 or "depart_date" in sp

    def test_clarification_returns_message_type(
        self, api_client, with_openai_key, httpx_mock
    ):
        """LLM returns plain text (no tool calls) → type=message."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json=self._openai_text_response(
                "Which Bali airport do you prefer: DPS or another nearby option?"
            ),
        )

        resp = api_client.post(
            "/planner/chat",
            json={"messages": [{"role": "user", "content": "somewhere warm"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "message"
        assert len(data["content"]) > 0
        # messages history is returned for follow-up
        assert isinstance(data["messages"], list)
        assert len(data["messages"]) >= 1

    def test_messages_list_is_serialisable(
        self, api_client, with_openai_key, httpx_mock
    ):
        """Returned messages must be clean {role, content} dicts — no tool_call objects."""
        httpx_mock.add_response(
            url="https://api.openai.com/v1/chat/completions",
            json=self._openai_text_response("What month were you thinking?"),
        )

        resp = api_client.post(
            "/planner/chat",
            json={"messages": [{"role": "user", "content": "somewhere warm"}]},
        )
        data = resp.json()
        for msg in data["messages"]:
            assert set(msg.keys()) <= {"role", "content"}, (
                f"Message has unexpected keys: {msg.keys()}"
            )
            assert msg["role"] in ("user", "assistant")
            assert isinstance(msg["content"], str)


# ─── Scout endpoint with stub ──────────────────────────────────────────────────


@pytest.mark.integration
class TestScoutEndpointWithStub:
    """Tests for POST /scout using the deterministic stub price source."""

    def test_months_mode_returns_results(self, api_client, with_stub_pm):
        """Months mode with stub returns at least one result with required fields."""
        resp = api_client.post(
            "/scout",
            json={
                "origin": "BNE",
                "destination": "SYD",
                "months": ["jul-2026"],
                "trip_length": 7,
            },
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        r = results[0]
        assert "depart_date" in r
        assert "return_date" in r
        assert "true_family_cost" in r
        assert r["true_family_cost"] > 0

    def test_exact_date_mode_returns_results(self, api_client, with_stub_pm):
        """Exact-date mode with stub returns results for the requested window."""
        resp = api_client.post(
            "/scout",
            json={
                "origin": "BNE",
                "destination": "SYD",
                "depart_date": "2026-07-20",
                "return_date": "2026-07-27",
                "flex_days": 0,
            },
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["depart_date"] == "2026-07-20"

    def test_exact_date_with_flex_returns_multiple_windows(
        self, api_client, with_stub_pm
    ):
        """flex_days=3 should produce 7 windows (±3 days)."""
        resp = api_client.post(
            "/scout",
            json={
                "origin": "BNE",
                "destination": "SYD",
                "depart_date": "2026-07-20",
                "return_date": "2026-07-27",
                "flex_days": 3,
            },
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 7

    def test_invalid_month_format_returns_400(self, api_client, with_stub_pm):
        """Month strings that don't match 'mon-yyyy' format return HTTP 400."""
        resp = api_client.post(
            "/scout",
            json={
                "origin": "BNE",
                "destination": "SYD",
                "months": ["July-2026"],  # wrong capitalisation / format
                "trip_length": 7,
            },
        )
        assert resp.status_code == 400

    def test_no_months_no_dates_returns_400(self, api_client, with_stub_pm):
        """Omitting both months and exact dates returns HTTP 400."""
        resp = api_client.post(
            "/scout",
            json={
                "origin": "BNE",
                "destination": "SYD",
            },
        )
        assert resp.status_code == 400

    def test_results_sorted_by_cost_ascending(self, api_client, with_stub_pm):
        """Results from /scout are sorted by true_family_cost ascending."""
        resp = api_client.post(
            "/scout",
            json={
                "origin": "BNE",
                "destination": "SYD",
                "months": ["jul-2026"],
                "trip_length": 7,
            },
        )
        costs = [r["true_family_cost"] for r in resp.json()]
        assert costs == sorted(costs)


# ─── Full pipeline: planner params → scout ────────────────────────────────────


@pytest.mark.integration
class TestPlannerToScoutPipeline:
    """
    End-to-end: build_scout_params output fed directly into /scout.
    Proves the param contract between the two endpoints is consistent.
    No OpenAI calls needed — build_scout_params is a pure function.
    """

    def _make_profile(self):
        from fly_o_myte.config import FamilyProfile

        return FamilyProfile(origin_airport="BNE", default_trip_length=14)

    def test_months_mode_params_accepted_by_scout(self, api_client, with_stub_pm):
        """scout_params from build_scout_params (month mode) are accepted by /scout."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "SYD",
            "origin_iata": "BNE",
            "month": 7,
            "year": 2026,
            "nights": 7,
            "flex_days": 3,
        }
        params = build_scout_params(intent, self._make_profile())

        resp = api_client.post("/scout", json=params)
        assert resp.status_code == 200, f"Scout rejected planner params: {resp.text}"
        assert len(resp.json()) >= 1

    def test_exact_date_params_accepted_by_scout(self, api_client, with_stub_pm):
        """scout_params from build_scout_params (exact-date mode) are accepted by /scout."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "SYD",
            "origin_iata": "BNE",
            "depart_earliest": "2026-07-20",
            "return_latest": "2026-07-27",
            "nights": 7,
            "flex_days": 0,
        }
        params = build_scout_params(intent, self._make_profile())

        resp = api_client.post("/scout", json=params)
        assert resp.status_code == 200, f"Scout rejected planner params: {resp.text}"
        assert len(resp.json()) >= 1

    def test_multi_month_long_trip_params_accepted(self, api_client, with_stub_pm):
        """A 35-night trip spanning Dec→Jan produces months=['dec-2026','jan-2027'],
        which /scout must accept as a valid 2-month window."""
        from fly_o_myte.planner import build_scout_params

        intent = {
            "destination_iata": "BLR",
            "origin_iata": "BNE",
            "month": 12,
            "year": 2026,
            "nights": 35,
            "flex_days": 3,
        }
        params = build_scout_params(intent, self._make_profile())

        # Verify the month list looks right before sending
        assert params["months"] == ["dec-2026", "jan-2027"]

        resp = api_client.post("/scout", json=params)
        assert resp.status_code == 200, (
            f"Scout rejected multi-month params: {resp.text}"
        )
        assert len(resp.json()) >= 1

    def test_planner_result_fields_map_to_scout_response_fields(
        self, api_client, with_stub_pm
    ):
        """Scout response fields match what the UI expects from the planner flow."""
        from fly_o_myte.planner import build_scout_params

        params = build_scout_params(
            {
                "destination_iata": "SYD",
                "origin_iata": "BNE",
                "month": 7,
                "year": 2026,
                "nights": 7,
            },
            self._make_profile(),
        )
        resp = api_client.post("/scout", json=params)
        assert resp.status_code == 200
        r = resp.json()[0]

        # Fields the UI accesses in Scout.tsx result cards
        required_fields = {
            "depart_date",
            "return_date",
            "trip_length_days",
            "true_family_cost",
            "airline_code",
            "stops",
            "departure_time",
            "arrival_time",
            "duration_minutes",
        }
        missing = required_fields - set(r.keys())
        assert not missing, f"Scout response missing fields: {missing}"
