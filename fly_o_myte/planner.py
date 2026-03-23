"""
Natural language trip planner — fly_o_myte/planner.py (layer 5).

Uses OpenAI to extract a TripIntent from natural language text
(e.g. 'Sri Lanka in December'). Falls back to structured Rich prompts
when OPENAI_API_KEY is not set.

Invariant 10: fom plan never crashes when API key absent. It always falls
back to structured prompts and prints what capability is lost.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel  # used for _LLMExtract structured validation

logger = logging.getLogger(__name__)

# Maps short month names to month numbers
_MONTH_MAP: dict[str, int] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class TripIntent:
    """Fully-resolved trip intent from NL extraction or structured prompts."""

    destination_iata: str
    destination_display: str
    month: int  # 1-12
    year: int
    nights: int
    flex_days: int
    origin_override: str | None  # IATA code if user specified 'from <city>'


class _LLMExtract(BaseModel):
    """Schema for Pydantic AI extraction output from natural language."""

    destination_query: str  # destination as mentioned, e.g. "Sri Lanka", "Tokyo"
    month: int  # departure month 1-12
    year: int  # departure year
    nights: int = 7  # trip length in nights
    flex_days: int = 3  # date flexibility in days
    origin_override_query: str | None = None  # city if 'from <city>' mentioned


def extract_trip_intent(text: str, api_key: str | None) -> TripIntent:
    """
    Parse a trip intent from natural language or structured prompts.

    With api_key: uses OpenAI GPT-4o-mini to extract fields.
    Without api_key: interactive Rich prompt wizard.

    Never raises — always returns a TripIntent.
    """
    if api_key:
        try:
            return _extract_with_llm(text, api_key)
        except Exception as exc:
            logger.warning("LLM extraction failed, falling back to wizard: %s", exc)
            return _extract_with_wizard(text)
    return _extract_with_wizard(text)


def _extract_with_llm(text: str, api_key: str) -> TripIntent:
    """Call OpenAI Chat Completions API to extract structured intent from text.

    Uses GPT-4o-mini with Pydantic model validation for type-safe structured
    output. Falls back to wizard on any error.
    """
    import json

    import httpx

    today = datetime.now()
    prompt = (
        f"Today's date is {today.strftime('%Y-%m-%d')}.\n"
        f'Extract trip details from this text: "{text}"\n\n'
        "If the user does not specify a year, assume the next upcoming occurrence "
        "of the mentioned month (this year if it hasn't passed, otherwise next year).\n\n"
        "Return ONLY valid JSON with these fields:\n"
        '{"destination_query": "destination as mentioned",'
        ' "month": month_number_1_to_12,'
        ' "year": year_4_digits,'
        ' "nights": trip_length_in_nights_default_7,'
        ' "flex_days": flexibility_days_default_3,'
        ' "origin_override_query": "origin city if from-city mentioned else null"}'
    )

    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "max_tokens": 256,
            "messages": [
                {"role": "system", "content": "You are a travel assistant. Respond with valid JSON only, no markdown."},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data["choices"][0]["message"]["content"]
    parsed = json.loads(raw_text)
    extracted = _LLMExtract(**parsed)

    destination_iata, destination_display = _resolve_single_destination(
        extracted.destination_query
    )

    origin_override: str | None = None
    if extracted.origin_override_query:
        origin_override = _resolve_origin(extracted.origin_override_query)

    return TripIntent(
        destination_iata=destination_iata,
        destination_display=destination_display,
        month=extracted.month,
        year=extracted.year,
        nights=extracted.nights,
        flex_days=extracted.flex_days,
        origin_override=origin_override,
    )


def _extract_with_wizard(text: str) -> TripIntent:
    """Interactive prompt wizard for users without OPENAI_API_KEY."""
    from rich.console import Console
    from rich.prompt import Prompt

    con = Console()
    con.print(
        "[yellow]Note: OPENAI_API_KEY not set. Using structured prompts. "
        "(Set this key to enable natural language input like "
        '"Sri Lanka in December".)[/yellow]'
    )

    # --- Destination ---
    destination_iata, destination_display = "", ""
    while not destination_iata:
        query = Prompt.ask("Destination (city or country name)")
        destination_iata, destination_display = _resolve_single_destination(query)
        if not destination_iata:
            con.print(
                "[dim]No match found. Try a city name, country name, or IATA code.[/dim]"
            )
        else:
            con.print(f"  [dim]{destination_iata} \u2014 {destination_display}[/dim]")

    # --- Month ---
    month, year = 0, 0
    while not month:
        month_raw = Prompt.ask("Departure month (e.g. dec-2026)")
        if not month_raw.strip():
            con.print("[dim]Please enter a month, e.g. dec-2026.[/dim]")
            continue
        try:
            month, year = _parse_month_year(month_raw)
        except ValueError:
            con.print(
                f"[dim]Could not parse '{month_raw}'. Try formats like: dec-2026, 12-2026, december 2026.[/dim]"
            )

    # --- Nights ---
    nights = 0
    while nights <= 0:
        nights_raw = Prompt.ask("Trip length (nights)", default="7")
        try:
            nights = int(nights_raw)
            if nights <= 0:
                con.print("[dim]Nights must be a positive number.[/dim]")
        except ValueError:
            con.print("[dim]Please enter a number, e.g. 7.[/dim]")

    # --- Flex ---
    flex_days = -1
    while flex_days < 0:
        flex_raw = Prompt.ask("Date flexibility (\u00b1days)", default="3")
        try:
            flex_days = int(flex_raw)
            if flex_days < 0:
                con.print("[dim]Flexibility must be 0 or more days.[/dim]")
        except ValueError:
            con.print("[dim]Please enter a number, e.g. 3.[/dim]")

    return TripIntent(
        destination_iata=destination_iata,
        destination_display=destination_display,
        month=month,
        year=year,
        nights=nights,
        flex_days=flex_days,
        origin_override=None,
    )


def _resolve_single_destination(query: str) -> tuple[str, str]:
    """
    Resolve a destination query to a single (IATA, display_name).

    0 matches  → returns ("", "")
    1 match    → returns that match directly (no prompt)
    >1 matches → prints numbered list, prompts user to pick
    """
    from rich.console import Console
    from rich.prompt import Prompt

    from fly_o_myte.airports import resolve_destination

    matches = resolve_destination(query)
    con = Console()

    if not matches:
        return ("", "")

    if len(matches) == 1:
        return matches[0]

    # Multiple matches — prompt user to pick
    con.print(f"\nMultiple destinations match '[bold]{query}[/bold]':")
    for i, (iata, display) in enumerate(matches, start=1):
        con.print(f"  {i}. {iata} \u2014 {display}")

    choices = [str(i) for i in range(1, len(matches) + 1)]
    pick = Prompt.ask("Select destination number", choices=choices)
    idx = int(pick) - 1
    return matches[idx]


def _resolve_origin(query: str) -> str | None:
    """Resolve a city/country name to an IATA airport code."""
    from fly_o_myte.airports import resolve_destination
    from fly_o_myte.price_sources.serpapi import _AU_AIRPORTS

    # Try international airports
    matches = resolve_destination(query)
    if matches:
        return matches[0][0]

    # Try AU domestic airport code directly
    q = query.strip().upper()
    if q in _AU_AIRPORTS:
        return q

    # Common AU city name lookups
    _AU_CITY: dict[str, str] = {
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
    return _AU_CITY.get(q)


def _parse_month_year(text: str) -> tuple[int, int]:
    """
    Parse 'dec-2026', 'December 2026', '12-2026', '2026-12' etc.
    Returns (month, year) as integers.
    Raises ValueError if unparseable.
    """
    text = text.strip().lower().replace("/", "-").replace(" ", "-")
    parts = [p for p in re.split(r"[-_]", text) if p]

    if len(parts) >= 2:
        p0, p1 = parts[0], parts[-1]

        # "dec-2026" or "december-2026"
        if p0 in _MONTH_MAP:
            return (_MONTH_MAP[p0], int(p1))

        # "12-2026"
        try:
            m = int(p0)
            if 1 <= m <= 12:
                return (m, int(p1))
        except ValueError:
            pass

        # "2026-12" or "2026-dec"
        try:
            y = int(p0)
            if y > 2000:
                if p1 in _MONTH_MAP:
                    return (_MONTH_MAP[p1], y)
                m2 = int(p1)
                if 1 <= m2 <= 12:
                    return (m2, y)
        except ValueError:
            pass

    # Single word: "december" → use datetime.strptime
    if len(parts) == 1:
        try:
            dt = datetime.strptime(parts[0][:3], "%b")
            current_year = datetime.now().year
            return (dt.month, current_year + 1)
        except ValueError:
            pass

    raise ValueError(f"Cannot parse month/year from '{text}'")


# ─── Agent Loop (function-calling planner for UI) ────────────────────────────

PLANNER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_family_profile",
            "description": "Get the family's travel profile: adults, children ages, home airport, state, school type, bags, budget.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_school_holidays",
            "description": "Get school holiday dates for a state and year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "AU state code, e.g. QLD"},
                    "year": {"type": "integer"},
                },
                "required": ["state", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_destination",
            "description": "Resolve a city/country name to IATA airport code(s).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "City, country, or airport name"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Submit the final trip plan when confident. Only call this when you have enough information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination_iata": {"type": "string"},
                    "destination_display": {"type": "string"},
                    "origin_iata": {"type": "string"},
                    "depart_earliest": {"type": "string", "description": "ISO date or null"},
                    "depart_latest": {"type": "string", "description": "ISO date or null"},
                    "return_latest": {"type": "string", "description": "ISO date or null"},
                    "nights": {"type": "integer", "description": "Trip length in nights"},
                    "flex_days": {"type": "integer", "description": "Date flexibility +/-days"},
                    "month": {"type": "integer", "description": "Departure month 1-12 (for month-mode scouting)"},
                    "year": {"type": "integer"},
                    "confidence": {"type": "number", "description": "0.0-1.0 confidence score"},
                    "reasoning": {"type": "string", "description": "Brief explanation for the user"},
                },
                "required": [
                    "destination_iata", "destination_display", "origin_iata",
                    "nights", "confidence", "reasoning",
                ],
            },
        },
    },
]


def _handle_get_family_profile(profile) -> str:
    """Return family profile as JSON for the LLM."""
    import json
    from datetime import date as _date

    today = _date.today()
    children_info = []
    for child in profile.children:
        age = (
            today.year - child.dob.year
            - ((today.month, today.day) < (child.dob.month, child.dob.day))
        )
        children_info.append({"name": child.name, "age": age})

    return json.dumps({
        "adults": profile.adults,
        "children": children_info,
        "origin_airport": profile.origin_airport,
        "state": profile.state,
        "school_type": profile.school_type,
        "bags_per_person": profile.bags_per_person,
        "budget_threshold_aud": profile.budget_threshold_aud,
        "default_trip_length": profile.default_trip_length,
    })


def _handle_get_school_holidays(calendar, state: str, year: int) -> str:
    """Return school holiday periods as JSON."""
    import json

    periods = calendar.list_periods(state, year)
    return json.dumps([
        {"label": p.label, "start": p.start.isoformat(), "end": p.end.isoformat()}
        for p in periods
    ])


def _handle_resolve_destination(query: str) -> str:
    """Resolve destination query to IATA codes, return JSON."""
    import json

    from fly_o_myte.airports import resolve_destination

    matches = resolve_destination(query)
    if not matches:
        # Try AU city names as fallback
        origin = _resolve_origin(query)
        if origin:
            return json.dumps([{"iata": origin, "display": f"{query.title()} (Australia)"}])
        return json.dumps([])

    return json.dumps([{"iata": iata, "display": display} for iata, display in matches])


def _execute_tool(name: str, args: dict, profile, calendar) -> str:
    """Dispatch a tool call to the appropriate handler."""
    import json

    if name == "get_family_profile":
        return _handle_get_family_profile(profile)
    elif name == "get_school_holidays":
        return _handle_get_school_holidays(calendar, args["state"], args["year"])
    elif name == "resolve_destination":
        return _handle_resolve_destination(args["query"])
    return json.dumps({"error": f"Unknown tool: {name}"})


def build_scout_params(intent: dict, profile) -> dict:
    """Translate a plan intent dict into ScoutRequest-compatible params.

    Modes:
      - Has depart_earliest + return_latest → exact-date mode with flex
      - Has month + year only → months mode
    """
    origin = intent.get("origin_iata") or profile.origin_airport
    destination = intent["destination_iata"]
    nights = intent.get("nights", profile.default_trip_length)
    flex_days = intent.get("flex_days", 3)

    depart_earliest = intent.get("depart_earliest")
    return_latest = intent.get("return_latest")

    if depart_earliest and return_latest:
        # Exact-date mode
        return {
            "origin": origin,
            "destination": destination,
            "depart_date": depart_earliest,
            "return_date": return_latest,
            "flex_days": flex_days,
            "trip_length": nights,
        }

    # Month mode
    month = intent.get("month")
    year = intent.get("year")
    if month and year:
        # Build month strings covering the trip length
        months = []
        from calendar import monthrange
        m, y = month, year
        # Start with the primary month, add extras if trip is long
        for _ in range(min(4, max(1, (nights // 28) + 1))):
            month_str = datetime(y, m, 1).strftime("%b-%Y").lower()
            months.append(month_str)
            m += 1
            if m > 12:
                m = 1
                y += 1
        return {
            "origin": origin,
            "destination": destination,
            "months": months,
            "trip_length": nights,
        }

    # Fallback: current month + 1
    now = datetime.now()
    fallback_month = now.month + 1 if now.month < 12 else 1
    fallback_year = now.year if now.month < 12 else now.year + 1
    month_str = datetime(fallback_year, fallback_month, 1).strftime("%b-%Y").lower()
    return {
        "origin": origin,
        "destination": destination,
        "months": [month_str],
        "trip_length": nights,
    }


def _text_messages(working_messages: list[dict]) -> list[dict]:
    """Return only user/assistant text messages from the working history.

    Strips the system message (index 0), tool-call rounds, and tool result
    messages so the returned list is clean, JSON-serializable, and suitable
    for display and for passing back on the next request.
    """
    result = []
    for m in working_messages[1:]:  # skip system
        role = m.get("role")
        content = m.get("content")
        if role == "user" and content:
            result.append({"role": "user", "content": content})
        elif role == "assistant" and content and not m.get("tool_calls"):
            result.append({"role": "assistant", "content": content})
    return result


def run_planner_loop(
    messages: list[dict],
    api_key: str,
    profile,
    calendar,
    max_iterations: int = 10,
) -> dict:
    """Run the agent loop. Returns one of:
      {"type": "plan", "intent": {...}, "scout_params": {...}, "messages": [...]}
      {"type": "message", "content": "...", "messages": [...]}
      {"type": "error", "content": "..."}
    """
    import json

    import httpx

    from datetime import date

    # Pre-load family profile so the LLM already has context in the system message
    profile_json = _handle_get_family_profile(profile)

    system_msg = {
        "role": "system",
        "content": (
            f"You are a travel planning assistant for an Australian family. "
            f"Today is {date.today().isoformat()}.\n\n"
            f"FAMILY PROFILE:\n{profile_json}\n\n"
            f"TOOL RULE — you MUST call resolve_destination before using any IATA code. "
            f"Never guess or recall an IATA code from memory. "
            f"This applies to every destination in every message, including follow-up "
            f"suggestions and alternatives raised mid-conversation. "
            f"If resolve_destination returns no matches, say so and ask the user to clarify.\n\n"
            f"WORKFLOW — for each destination the user wants to plan:\n"
            f"1. Call resolve_destination to get the IATA code.\n"
            f"2. Call get_school_holidays to check overlap with the travel period "
            f"(use state from the family profile and the year from the request).\n"
            f"3. Call submit_plan with your best interpretation of the trip.\n\n"
            f"DEFAULTS — apply when the user has not specified otherwise:\n"
            f"- Origin: {profile.origin_airport} (family home airport)\n"
            f"- Trip length: use the user's stated duration; "
            f"if not stated use default_trip_length from the profile\n"
            f"- Year: the next upcoming occurrence of the mentioned month\n"
            f"- Flex days: 3\n\n"
            f"CLARIFY only when you genuinely cannot proceed — for example, when the "
            f"destination name is ambiguous across distinct cities. "
            f"In all other cases make a reasonable assumption, record it in the "
            f"reasoning field of submit_plan, and proceed."
        ),
    }

    working_messages = [system_msg] + messages

    for _ in range(max_iterations):
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "messages": working_messages,
                "tools": PLANNER_TOOLS,
                "tool_choice": "auto",
                "temperature": 0.1,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        choice = data["choices"][0]
        msg = choice["message"]

        # Append assistant message to working history
        working_messages.append(msg)

        # No tool calls → LLM is speaking to user
        if not msg.get("tool_calls"):
            return {
                "type": "message",
                "content": msg.get("content", ""),
                "messages": _text_messages(working_messages),
            }

        # Process tool calls
        for tc in msg["tool_calls"]:
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])

            if fn_name == "submit_plan":
                intent = fn_args
                scout_params = build_scout_params(intent, profile)
                return {
                    "type": "plan",
                    "intent": intent,
                    "scout_params": scout_params,
                    "messages": _text_messages(working_messages),
                }

            result = _execute_tool(fn_name, fn_args, profile, calendar)
            working_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })

    return {"type": "error", "content": "Max iterations reached"}
