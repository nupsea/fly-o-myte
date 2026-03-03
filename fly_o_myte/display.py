"""
Rich console output — all terminal display lives here.

No business logic. Receives data objects, renders them.
Snapshot-tested via Syrupy.

Decision colour coding:
  book_now → bold green
  wait     → yellow
  monitor  → dim white
"""

from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fly_o_myte.db.sqlite import PriceSnapshot, Recommendation, Trip
from fly_o_myte.true_cost import TrueCostBreakdown

console = Console()

_DECISION_STYLE: dict[str, str] = {
    "book_now": "bold green",
    "wait": "yellow",
    "monitor": "dim white",
}

_RISK_STYLE: dict[str, str] = {
    "low": "green",
    "medium": "yellow",
    "high": "red",
}


# ─── Status digest ─────────────────────────────────────────────────────────────


def print_status_digest(
    trips: list[tuple[Trip, Recommendation | None]],
    show_all: bool = False,
) -> None:
    """Print the morning digest — actionable trips only (or all if show_all)."""
    actionable = [
        (t, r) for t, r in trips if r and r.decision in ("book_now", "wait") or show_all
    ]

    if not actionable:
        console.print(
            "All trips look fine. Run [bold]fom status --all[/bold] to see everything."
        )
        return

    for trip, rec in sorted(
        actionable,
        key=lambda x: 0 if (x[1] and x[1].decision == "book_now") else 1,
    ):
        _print_digest_row(trip, rec)


def _print_digest_row(trip: Trip, rec: Recommendation | None) -> None:
    style = _DECISION_STYLE.get(rec.decision if rec else "monitor", "white")
    decision_label = rec.decision.upper().replace("_", " ") if rec else "NO DATA"

    line = Text()
    line.append(f"#{trip.id} ", style="bold")
    line.append(f"{trip.label}  ", style="bold")
    line.append(f"{trip.origin}→{trip.destination}  ")
    if rec:
        line.append(f"${rec.true_family_cost:,.0f}  ")
        line.append(decision_label, style=style)
        line.append(f"  ({rec.confidence:.0%})  {rec.days_to_departure}d to departure")
    console.print(line)


# ─── Full trip check ────────────────────────────────────────────────────────────


def print_trip_detail(
    trip: Trip,
    rec: Recommendation,
    snapshot: PriceSnapshot,
    breakdown: TrueCostBreakdown | None = None,
    insight_text: str | None = None,
) -> None:
    """Print the full recommendation panel for `fom check <id>`."""
    decision_style = _DECISION_STYLE.get(rec.decision, "white")
    decision_label = rec.decision.upper().replace("_", " ")
    risk_style = _RISK_STYLE.get(rec.regret_risk, "white")

    # Header
    console.print()
    console.rule(f"[bold]{trip.label}[/bold]  {trip.origin} → {trip.destination}")

    # Trip info line
    dates = trip.depart_date
    if trip.return_date:
        dates += f" → {trip.return_date}"
    console.print(
        f"  Dates: {dates}   Adults: {trip.adults}   Last updated: {rec.generated_at[:16]}"
    )
    console.print()

    # Cost breakdown table
    cost_table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    cost_table.add_column(style="dim")
    cost_table.add_column(justify="right")

    if breakdown:
        cost_table.add_row("Base fare (adults)", f"${breakdown.base_fare_adults:,.0f}")
        if breakdown.base_fare_children:
            cost_table.add_row(
                "Base fare (children)", f"${breakdown.base_fare_children:,.0f}"
            )
        if breakdown.bag_fees:
            cost_table.add_row("Checked bags", f"${breakdown.bag_fees:,.0f}")
        if breakdown.seat_fees:
            cost_table.add_row("Seat selection", f"${breakdown.seat_fees:,.0f}")
        if breakdown.infant_fees:
            cost_table.add_row("Infant fees", f"${breakdown.infant_fees:,.0f}")
        cost_table.add_row("", "")
    cost_table.add_row(
        "[bold]True family cost[/bold]",
        f"[bold]${rec.true_family_cost:,.0f} AUD[/bold]",
    )
    cost_table.add_row("30-day average", f"${rec.rolling_avg_cost:,.0f}")

    trend_sign = "+" if rec.trend_slope > 0 else ""
    trend_color = "red" if rec.trend_slope > 0 else "green"
    cost_table.add_row(
        "Trend",
        f"[{trend_color}]{trend_sign}${rec.trend_slope:.1f}/day[/{trend_color}]",
    )

    console.print(cost_table)

    # Recommendation panel
    rec_text = Text()
    rec_text.append(f"  {decision_label}", style=f"bold {decision_style}")
    rec_text.append(f"  {rec.confidence:.0%} confident")
    rec_text.append("   Regret risk: ")
    rec_text.append(rec.regret_risk.upper(), style=f"bold {risk_style}")
    rec_text.append(f"\n\n  {rec.rationale}")

    if rec.regret_book_aud or rec.regret_wait_aud:
        rec_text.append(
            f"\n\n  Expected regret: "
            f"Book now ${rec.regret_book_aud:,.0f}  |  Wait ${rec.regret_wait_aud:,.0f}"
        )

    if rec.school_holiday_flag:
        rec_text.append(
            f"\n\n  School holiday: {rec.school_holiday_flag}", style="yellow"
        )

    if rec.price_level_signal:
        signal_style = (
            "green"
            if rec.price_level_signal == "LOW"
            else ("red" if rec.price_level_signal == "HIGH" else "white")
        )
        rec_text.append("\n  Market signal: ", style="dim")
        rec_text.append(rec.price_level_signal, style=signal_style)

    console.print(Panel(rec_text, border_style=decision_style))

    # LLM insight
    if insight_text:
        console.print(
            Panel(insight_text, title="[dim]AI Insight[/dim]", border_style="dim")
        )

    console.print()


# ─── Compare table ──────────────────────────────────────────────────────────────


def print_compare_table(
    trips_data: list[tuple[Trip, Recommendation, PriceSnapshot]],
) -> None:
    """Side-by-side true cost breakdown comparison of up to 3 trips."""
    totals = [rec.true_family_cost for _, rec, _ in trips_data]
    min_total = min(totals) if totals else 0.0

    table = Table(title="Trip Comparison — Cost Breakdown", box=box.ROUNDED)
    table.add_column("", style="dim", min_width=18)

    # Parse breakdowns and build column headers
    breakdowns: list[TrueCostBreakdown | None] = []
    for trip, rec, snap in trips_data:
        airline = snap.airline_code or "?"
        header = f"{airline}  {trip.origin}→{trip.destination}\n{trip.depart_date}"
        table.add_column(header, justify="right", min_width=16)

        bd: TrueCostBreakdown | None = None
        if snap.true_cost_breakdown:
            try:
                d = json.loads(snap.true_cost_breakdown)
                bd = TrueCostBreakdown(
                    base_fare_adults=d.get("base_adults", 0.0),
                    base_fare_children=d.get("base_children", 0.0),
                    bag_fees=d.get("bags", 0.0),
                    seat_fees=d.get("seats", 0.0),
                    infant_fees=d.get("infant", 0.0),
                    total=d.get("total", rec.true_family_cost),
                )
            except (ValueError, KeyError):
                pass
        breakdowns.append(bd)

    # Base fare/adult
    base_vals = [f"${snap.base_fare_per_adult:,.0f}" for _, _, snap in trips_data]
    table.add_row("Base fare/adult", *base_vals)

    # Checked bags (show if any non-zero)
    bag_vals = [f"${bd.bag_fees:,.0f}" if bd else "—" for bd in breakdowns]
    if any(bd and bd.bag_fees > 0 for bd in breakdowns):
        table.add_row("Checked bags", *bag_vals)

    # Seat selection (show if any non-zero)
    seat_vals = [f"${bd.seat_fees:,.0f}" if bd else "—" for bd in breakdowns]
    if any(bd and bd.seat_fees > 0 for bd in breakdowns):
        table.add_row("Seat selection", *seat_vals)

    # Infant fees (show if any non-zero)
    infant_vals = [f"${bd.infant_fees:,.0f}" if bd else "—" for bd in breakdowns]
    if any(bd and bd.infant_fees > 0 for bd in breakdowns):
        table.add_row("Infant fees", *infant_vals)

    # Separator
    table.add_row("", *["" for _ in trips_data])

    # TOTAL FAMILY COST — cheapest highlighted in bold green
    total_vals = []
    for _, rec, _ in trips_data:
        t = rec.true_family_cost
        s = f"${t:,.0f} AUD"
        if t == min_total:
            total_vals.append(f"[bold green]{s}[/bold green]")
        else:
            total_vals.append(f"[bold]{s}[/bold]")
    table.add_row("[bold]TOTAL FAMILY COST[/bold]", *total_vals)

    # Recommendation
    rec_vals = []
    for _, rec, _ in trips_data:
        style = _DECISION_STYLE.get(rec.decision, "white")
        decision_label = rec.decision.upper().replace("_", " ")
        rec_vals.append(f"[{style}]{decision_label}[/{style}]")
    table.add_row("Recommendation", *rec_vals)

    console.print(table)


# ─── Price history ──────────────────────────────────────────────────────────────


def print_price_history(trip: Trip, snapshots: list[PriceSnapshot]) -> None:
    """Chronological price history with Unicode sparkline."""
    if not snapshots:
        console.print("No price history for this trip yet.")
        return

    costs = [s.true_family_cost for s in snapshots]
    sparkline = _sparkline(costs)

    table = Table(
        title=f"Price History — {trip.label}  ({trip.origin}→{trip.destination})",
        box=box.SIMPLE,
    )
    table.add_column("Date", style="dim")
    table.add_column("True cost", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Signal")
    table.add_column("Airline")
    table.add_column("Source", style="dim")

    for i, snap in enumerate(snapshots):
        prev_cost = snapshots[i - 1].true_family_cost if i > 0 else None
        change = ""
        if prev_cost:
            diff = snap.true_family_cost - prev_cost
            sign = "+" if diff >= 0 else ""
            color = "red" if diff > 0 else "green"
            change = f"[{color}]{sign}${diff:,.0f}[/{color}]"

        signal = snap.price_level_signal or "—"
        signal_color = (
            "green" if signal == "LOW" else ("red" if signal == "HIGH" else "white")
        )

        table.add_row(
            snap.fetched_at[:10],
            f"${snap.true_family_cost:,.0f}",
            change,
            f"[{signal_color}]{signal}[/{signal_color}]",
            snap.airline_code or "—",
            snap.source,
        )

    console.print(table)
    console.print(f"  Trend: {sparkline}")
    console.print()


def _sparkline(values: list[float], width: int = 20) -> str:
    """Generate a Unicode block sparkline for a list of values."""
    blocks = " ▁▂▃▄▅▆▇█"
    if not values or len(values) < 2:
        return "—"
    lo, hi = min(values), max(values)
    rng = hi - lo
    if rng < 1:
        return "─" * min(len(values), width)
    chars = []
    for v in values[-width:]:
        idx = int((v - lo) / rng * (len(blocks) - 1))
        chars.append(blocks[idx])
    return "".join(chars)


# ─── Data version ───────────────────────────────────────────────────────────────


def print_data_version(version: str, last_updated: str, airlines: list[str]) -> None:
    table = Table(title="Embedded Data Version", box=box.SIMPLE)
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Data version", version)
    table.add_row("Last updated", last_updated)
    table.add_row("Airlines in DB", ", ".join(sorted(airlines)))
    console.print(table)
