"""
Natural language trip planner — fly_o_myte/planner.py (layer 5).

Uses Pydantic AI to extract a TripIntent from natural language text
(e.g. 'Sri Lanka in December'). Falls back to structured Rich prompts
when ANTHROPIC_API_KEY is not set.

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

    With api_key: uses Pydantic AI (Claude haiku) to extract fields.
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
    """Call Anthropic messages API to extract structured intent from text.

    Uses the Anthropic API directly with Pydantic model validation for
    type-safe structured output. Falls back to wizard on any error.
    """
    import json

    import httpx

    prompt = (
        f'Extract trip details from this text: "{text}"\n\n'
        "Return ONLY valid JSON with these fields:\n"
        '{"destination_query": "destination as mentioned",'
        ' "month": month_number_1_to_12,'
        ' "year": year_4_digits,'
        ' "nights": trip_length_in_nights_default_7,'
        ' "flex_days": flexibility_days_default_3,'
        ' "origin_override_query": "origin city if from-city mentioned else null"}'
    )

    response = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 256,
            "system": "You are a travel assistant. Respond with valid JSON only, no markdown.",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    raw_text = data["content"][0]["text"]
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
    """Interactive prompt wizard for users without ANTHROPIC_API_KEY."""
    from rich.console import Console
    from rich.prompt import Prompt

    con = Console()
    con.print(
        "[yellow]Note: ANTHROPIC_API_KEY not set. Using structured prompts. "
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
