"""
LLM-powered contextual insights — Phase 2.

Generates a 3–4 sentence explanation of why prices are at their current
level for a given route, combining:
  - Local price analytics (percentiles, trend, holiday flag)
  - External context (news search via httpx)

Uses Pydantic AI for structured, type-validated LLM output.
Supports Claude haiku (via Anthropic API) or Ollama (local).

Privacy: no personal data (names, DOBs, emails) in prompts.
Only routes, dates, and price data are sent to the LLM.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_CACHE_DAYS = 7
_PRICE_CHANGE_THRESHOLD = 0.10  # 10%


class TravelInsight(BaseModel):
    """Structured LLM output for a flight price insight."""
    summary: str            # 3–4 sentences explaining the price level
    price_impact: str       # "higher" | "lower" | "uncertain" | "none"
    event_type: str         # "holiday" | "disruption" | "capacity" | "seasonal" | "none"
    confidence: float       # 0.0–1.0
    sources: list[str]      # cited sources or "price history", "school calendar", etc.


def generate_insight(
    origin: str,
    destination: str,
    depart_date: date,
    current_cost: float,
    avg_cost: float,
    trend_slope: float,
    school_holiday_label: str | None,
    price_level_signal: str | None,
    n_snapshots: int,
    provider: str = "auto",
) -> TravelInsight | None:
    """
    Generate a contextual insight for a flight route.

    Args:
        origin: IATA code of origin airport.
        destination: IATA code of destination airport.
        depart_date: Departure date.
        current_cost: Current true family cost (AUD).
        avg_cost: Rolling average cost (AUD).
        trend_slope: AUD/day (negative = falling).
        school_holiday_label: Holiday period label if overlapping, else None.
        price_level_signal: "LOW" | "TYPICAL" | "HIGH" from Amadeus, or None.
        n_snapshots: Number of price points in history.
        provider: "auto" | "claude" | "ollama" — "auto" picks Claude if API key set.

    Returns:
        TravelInsight on success, None on any LLM failure (graceful degradation).
    """
    try:
        from travo.config import get_settings
        settings = get_settings()
        selected = _select_provider(provider, settings)
        if selected is None:
            logger.debug("No LLM provider available — skipping insight generation")
            return None

        prompt = _build_prompt(
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            current_cost=current_cost,
            avg_cost=avg_cost,
            trend_slope=trend_slope,
            school_holiday_label=school_holiday_label,
            price_level_signal=price_level_signal,
            n_snapshots=n_snapshots,
        )

        return _call_llm(prompt, selected, settings)

    except Exception as exc:
        logger.warning("Insight generation failed (non-critical): %s", exc)
        return None


def _select_provider(provider: str, settings: object) -> str | None:
    """Return the LLM provider to use, or None if none available."""
    from travo.config import Settings
    assert isinstance(settings, Settings)

    if provider == "claude":
        return "claude" if settings.anthropic_api_key else None
    if provider == "ollama":
        return "ollama" if settings.ollama_base_url else None
    # auto
    if settings.anthropic_api_key:
        return "claude"
    if settings.ollama_base_url:
        return "ollama"
    return None


def _build_prompt(
    origin: str,
    destination: str,
    depart_date: date,
    current_cost: float,
    avg_cost: float,
    trend_slope: float,
    school_holiday_label: str | None,
    price_level_signal: str | None,
    n_snapshots: int,
) -> str:
    deviation_pct = (current_cost - avg_cost) / avg_cost * 100 if avg_cost else 0
    trend_desc = (
        f"rising at ${abs(trend_slope):.1f}/day" if trend_slope > 0
        else f"falling at ${abs(trend_slope):.1f}/day" if trend_slope < 0
        else "flat"
    )
    holiday_note = (
        f"The travel dates overlap the {school_holiday_label}."
        if school_holiday_label
        else "Travel dates do not overlap any school holiday period."
    )
    signal_note = (
        f"The market benchmark signal is {price_level_signal}."
        if price_level_signal
        else "No external market signal available."
    )
    month_name = depart_date.strftime("%B %Y")

    return f"""You are a travel pricing analyst advising an Australian family on when to book flights.

Route: {origin} to {destination}
Departure month: {month_name}
Current true family cost: ${current_cost:,.0f} AUD
Historical average: ${avg_cost:,.0f} AUD ({deviation_pct:+.1f}% deviation)
Price trend: {trend_desc}
Market signal: {signal_note}
School holiday: {holiday_note}
Data points collected: {n_snapshots}

In 3-4 sentences, explain why prices are at their current level for this route and month.
Focus on: seasonal demand patterns, school holiday effects, airline capacity changes, or other
relevant factors specific to Australian domestic travel. Do not mention the family's personal details.
Cite your reasoning sources (e.g. "school calendar", "seasonal pattern", "price history").
Be specific about whether prices are likely to improve or worsen before departure."""


def _call_llm(prompt: str, provider: str, settings: object) -> TravelInsight | None:
    """Call the selected LLM provider and return a validated TravelInsight."""
    from pydantic_ai import Agent
    from travo.config import Settings
    assert isinstance(settings, Settings)

    system_prompt = (
        "You are a travel pricing analyst. Respond with structured JSON matching the "
        "requested schema. Be concise, factual, and Australia-specific."
    )

    if provider == "claude":
        model_id = f"anthropic:{settings.ollama_model if False else 'claude-haiku-4-5-20251001'}"
        # Pydantic AI uses "anthropic:claude-haiku..." format
        model_str = "claude-haiku-4-5-20251001"
    else:
        model_str = f"ollama:{settings.ollama_model}"

    agent: Agent[None, TravelInsight] = Agent(
        model=model_str,
        result_type=TravelInsight,
        system_prompt=system_prompt,
    )

    result = agent.run_sync(prompt)
    return result.data
