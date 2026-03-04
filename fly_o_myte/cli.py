"""
Fly-O-Myte CLI — all commands defined here.

Entry point: `fom` (registered via pyproject.toml [project.scripts])

Commands:
  setup       First-run configuration wizard
  scout       Explore date windows before committing
  watch       Start tracking a trip
  status      Morning digest of actionable trips
  check       Full recommendation for one trip
  compare     Side-by-side comparison of trips
  history     Price history sparkline
  refresh     Manual price fetch for one trip
  insight     Force fresh LLM insight (Phase 2)
  poll        Cron target — poll all active trips
  analytics   Manual analytics rebuild (Phase 2)
  pause       Pause tracking
  resume      Resume tracking
  remove      Delete a trip and its history
  profile     View family profile
  data-version  Show embedded data freshness
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from fly_o_myte import __version__

app = typer.Typer(
    name="fom",
    help="Family travel advisor — Book Now, Wait, or Monitor.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)


# Lazy imports to keep startup fast
def _get_settings():
    from fly_o_myte.config import get_settings

    return get_settings()


def _get_engine():
    from fly_o_myte.db.sqlite import create_db_engine, create_tables

    settings = _get_settings()
    engine = create_db_engine(settings.db_path)
    create_tables(engine)
    return engine


def _get_profile():
    from fly_o_myte.config import load_family_profile

    return load_family_profile()


def _get_pm():
    from fly_o_myte.tracker import build_plugin_manager_from_settings

    return build_plugin_manager_from_settings()


# ─── Version ───────────────────────────────────────────────────────────────────


def version_callback(value: bool) -> None:
    if value:
        console.print(f"fly-o-myte {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(
        None, "--version", "-V", callback=version_callback, is_eager=True
    ),
) -> None:
    """Fly-O-Myte — your family travel advisor."""


# ─── setup ─────────────────────────────────────────────────────────────────────


@app.command()
def setup() -> None:
    """First-run configuration wizard. Creates ~/.fly-o-myte/config.yaml."""
    import yaml

    from fly_o_myte.config import APP_DIR, DEFAULT_CONFIG_PATH

    APP_DIR.mkdir(parents=True, exist_ok=True)

    console.print("\n[bold]Fly-O-Myte Setup[/bold] — family travel advisor\n")
    console.print(
        "This wizard creates [dim]~/.fly-o-myte/config.yaml[/dim] with your family profile.\n"
    )

    existing: dict = {}
    if DEFAULT_CONFIG_PATH.exists():
        with DEFAULT_CONFIG_PATH.open() as f:
            existing = yaml.safe_load(f) or {}
        console.print(
            "[yellow]Existing config found — press Enter to keep current values.[/yellow]\n"
        )

    fam = existing.get("family", {})

    adults = int(Prompt.ask("Number of adults", default=str(fam.get("adults", 2))))
    origin = Prompt.ask(
        "Origin airport (IATA)", default=fam.get("origin_airport", "BNE")
    ).upper()
    state = Prompt.ask(
        "State (QLD/NSW/VIC/WA/SA/TAS/NT/ACT)", default=fam.get("state", "QLD")
    ).upper()
    school_type = Prompt.ask(
        "School type (state/independent/catholic)",
        default=fam.get("school_type", "state"),
    )
    bags = int(
        Prompt.ask(
            "Checked bags per person", default=str(fam.get("bags_per_person", 1))
        )
    )
    max_stops = int(
        Prompt.ask(
            "Max stops (0=nonstop, 1=one stop)", default=str(fam.get("max_stops", 1))
        )
    )

    children_raw = fam.get("children", [])
    console.print(f"\nCurrently {len(children_raw)} child(ren) in profile.")
    n_children = int(
        Prompt.ask("Number of children (0–6)", default=str(len(children_raw)))
    )

    children = []
    for i in range(n_children):
        existing_child = children_raw[i] if i < len(children_raw) else {}
        name = Prompt.ask(f"Child {i + 1} name", default=existing_child.get("name", ""))
        dob = Prompt.ask(
            f"Child {i + 1} date of birth (YYYY-MM-DD)",
            default=existing_child.get("dob", ""),
        )
        children.append({"name": name, "dob": dob})

    budget = fam.get("budget_threshold_aud")
    budget_str = Prompt.ask(
        "Budget threshold AUD (optional, press Enter to skip)",
        default=str(budget) if budget else "",
    )
    budget_val = float(budget_str) if budget_str else None

    alert_email = existing.get("alerts", {}).get("email", "")
    alert_email = Prompt.ask("Alert email (optional)", default=alert_email)

    config = {
        "family": {
            "adults": adults,
            "children": children,
            "origin_airport": origin,
            "state": state,
            "school_type": school_type,
            "bags_per_person": bags,
            "max_stops": max_stops,
            "preferred_departure_window": {"earliest_hour": 8, "latest_hour": 18},
            "blocked_airlines": fam.get("blocked_airlines", []),
            "budget_threshold_aud": budget_val,
        },
        "alerts": {
            "email": alert_email,
            "notify_on": "book_now",
        },
    }

    with DEFAULT_CONFIG_PATH.open("w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(f"\n[green]Config saved to {DEFAULT_CONFIG_PATH}[/green]")
    console.print("\nNext steps:")
    console.print("  1. Add API keys to [dim].env[/dim] in your working directory:")
    console.print("     TEQUILA_API_KEY=your_key_here")
    console.print(
        "  2. Run [bold]fom watch BNE SYD 2026-07-20 2026-07-27[/bold] to start tracking a trip"
    )
    console.print("  3. Add to crontab: [dim]0 7 * * * fom poll[/dim]\n")


# ─── scout ─────────────────────────────────────────────────────────────────────


@app.command()
def scout(
    origin: Annotated[str, typer.Argument(help="Origin IATA code (e.g. BNE)")],
    destination: Annotated[
        str, typer.Argument(help="Destination IATA code (e.g. SYD)")
    ],
    month: Annotated[
        str | None, typer.Option(help="Month to scout, e.g. jul-2026")
    ] = None,
    depart: Annotated[
        str | None, typer.Option(help="Specific departure date YYYY-MM-DD")
    ] = None,
    ret: Annotated[
        str | None, typer.Option("--return", help="Specific return date YYYY-MM-DD")
    ] = None,
    flex: int = typer.Option(0, help="Flex ±days around specific dates"),
    trip_length: int = typer.Option(7, help="Trip length in days (for month scouting)"),
) -> None:
    """Explore date windows across a month before committing to a trip."""

    from rich import box
    from rich.table import Table

    from fly_o_myte.calendar import get_calendar
    from fly_o_myte.display import console
    from fly_o_myte.fees import get_airline_db
    from fly_o_myte.scout import scout_flex, scout_month

    profile = _get_profile()

    pm = _get_pm()

    airline_db = get_airline_db()

    cal = get_calendar()

    if month:
        try:
            parts = month.split("-")

            month_num = datetime.strptime(parts[0], "%b").month

            year_num = int(parts[1])

        except (ValueError, IndexError):
            err_console.print(
                f"[red]Invalid month format '{month}'. Use e.g. jul-2026[/red]"
            )

            raise typer.Exit(1) from None

        console.print(f"\nScouting {origin} → {destination} for {month}...\n")

        results = scout_month(
            pm,
            profile,
            airline_db,
            cal,
            origin,
            destination,
            year_num,
            month_num,
            trip_length,
        )
    elif depart and ret:
        d = date.fromisoformat(depart)
        r = date.fromisoformat(ret)
        if flex:
            results = scout_flex(
                pm, profile, airline_db, cal, origin, destination, d, r, flex
            )
        else:
            results = scout_flex(
                pm, profile, airline_db, cal, origin, destination, d, r, 0
            )
    else:
        err_console.print("[red]Provide --month OR --depart + --return[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("No results found. Check your API key and try again.")
        return

    table = Table(title=f"Scout Results: {origin} → {destination}", box=box.ROUNDED)
    table.add_column("Depart", min_width=10)
    table.add_column("Return", min_width=10)
    table.add_column("True cost", justify="right")
    table.add_column("Airline")
    table.add_column("Stops")
    table.add_column("Depart time")
    table.add_column("School holiday")

    for r in results[:15]:
        holiday_text = r.school_holiday.label if r.school_holiday else ""
        holiday_style = "yellow" if r.school_holiday else ""
        table.add_row(
            str(r.depart_date),
            str(r.return_date),
            f"${r.true_family_cost:,.0f}",
            r.airline_code,
            str(r.stops),
            r.departure_time,
            f"[{holiday_style}]{holiday_text}[/{holiday_style}]"
            if holiday_text
            else "—",
        )

    console.print(table)


# ─── watch ─────────────────────────────────────────────────────────────────────


@app.command()
def watch(
    origin: str = typer.Argument(...),
    destination: str = typer.Argument(...),
    depart_date: str = typer.Argument(...),
    return_date: str | None = typer.Argument(None),
    label: str = typer.Option("", help="Friendly name for the trip"),
    adults: int | None = typer.Option(None),
    bags: int | None = typer.Option(None, "--bags"),
    max_stops: int | None = typer.Option(None),
    alert_email: str | None = typer.Option(None),
    alert_threshold: float | None = typer.Option(None),
) -> None:
    """Start tracking a trip and trigger an immediate price fetch."""
    from fly_o_myte.db.sqlite import Trip, get_session, insert_trip
    from fly_o_myte.tracker import poll_trip

    profile = _get_profile()
    engine = _get_engine()
    pm = _get_pm()

    trip_label = label or f"{origin}-{destination} {depart_date}"

    trip = Trip(
        label=trip_label,
        origin=origin.upper(),
        destination=destination.upper(),
        depart_date=depart_date,
        return_date=return_date,
        adults=adults or profile.adults,
        bags_per_person=bags or profile.bags_per_person,
        max_stops=max_stops if max_stops is not None else profile.max_stops,
        alert_email=alert_email or _get_settings().default_alert_email or None,
        alert_threshold_aud=alert_threshold,
    )

    with get_session(engine) as session:
        trip = insert_trip(session, trip)
        console.print(f"[green]Tracking trip #{trip.id}: {trip_label}[/green]")
        console.print("Fetching initial price...")
        snap = poll_trip(session, trip, profile, pm, send_alerts=False)
        if snap:
            console.print(
                f"Initial price: [bold]${snap.true_family_cost:,.0f} AUD[/bold]"
            )
        else:
            console.print("[yellow]No offers found — will retry on next poll.[/yellow]")


# ─── status ────────────────────────────────────────────────────────────────────


@app.command()
def status(
    all_trips: bool = typer.Option(
        False, "--all", "-a", help="Show all trips including paused"
    ),
) -> None:
    """Morning digest — actionable trips only (or all with --all)."""
    from fly_o_myte.db.sqlite import (
        get_latest_recommendation,
        get_session,
        list_active_trips,
        list_all_trips,
    )
    from fly_o_myte.display import print_status_digest

    engine = _get_engine()
    with get_session(engine) as session:
        trips = list_all_trips(session) if all_trips else list_active_trips(session)
        pairs = [
            (t, get_latest_recommendation(session, t.id))  # type: ignore[arg-type]
            for t in trips
        ]

        print_status_digest(pairs, show_all=all_trips)


# ─── check ─────────────────────────────────────────────────────────────────────


@app.command()
def check(
    trip_id: int = typer.Argument(..., help="Trip ID from `fom status`"),
) -> None:
    """Full recommendation detail for a single trip."""
    import json

    from fly_o_myte.db.sqlite import (
        get_latest_recommendation,
        get_latest_snapshot,
        get_session,
        get_trip,
    )
    from fly_o_myte.display import print_trip_detail
    from fly_o_myte.true_cost import TrueCostBreakdown

    engine = _get_engine()
    with get_session(engine) as session:
        trip = get_trip(session, trip_id)
        if not trip:
            err_console.print(f"[red]Trip {trip_id} not found.[/red]")
            raise typer.Exit(1)
        rec = get_latest_recommendation(session, trip_id)
        snap = get_latest_snapshot(session, trip_id)

        if not rec or not snap:
            console.print(
                f"No data yet for trip #{trip_id}. Run [bold]fom refresh {trip_id}[/bold]."
            )
            return

        breakdown = None
        if snap.true_cost_breakdown:
            try:
                bd = json.loads(snap.true_cost_breakdown)
                breakdown = TrueCostBreakdown(
                    base_fare_adults=bd.get("base_adults", 0),
                    base_fare_children=bd.get("base_children", 0),
                    bag_fees=bd.get("bags", 0),
                    seat_fees=bd.get("seats", 0),
                    infant_fees=bd.get("infant", 0),
                    total=bd.get("total", rec.true_family_cost),
                )
            except (ValueError, KeyError):
                pass

        print_trip_detail(trip, rec, snap, breakdown)

        # International route context label
        from fly_o_myte.recommender import RouteType, classify_route

        route_type = classify_route(trip.origin, trip.destination)
        if route_type != RouteType.DOMESTIC:
            route_label = route_type.value.replace("_", " ").title()
            console.print(f"  International route: {route_label}", style="dim")
            console.print()

        # Market context — Phase 2 analytics (skip gracefully when no data)
        from fly_o_myte.db.duckdb import query_route_context
        from fly_o_myte.display import print_route_context

        settings = _get_settings()
        route_ctx = query_route_context(
            settings.analytics_dir, trip.origin, trip.destination
        )
        if route_ctx:
            print_route_context(route_ctx)


# ─── compare ───────────────────────────────────────────────────────────────────


@app.command()
def compare(
    trip_ids: Annotated[list[int], typer.Argument(help="2–3 trip IDs to compare")],
) -> None:
    """Side-by-side comparison of 2–3 trips."""
    from fly_o_myte.db.sqlite import (
        get_latest_recommendation,
        get_latest_snapshot,
        get_session,
        get_trip,
    )
    from fly_o_myte.display import print_compare_table

    if len(trip_ids) < 2 or len(trip_ids) > 3:
        err_console.print("[red]Provide 2 or 3 trip IDs.[/red]")
        raise typer.Exit(1)

    engine = _get_engine()
    with get_session(engine) as session:
        data = []
        for tid in trip_ids:
            trip = get_trip(session, tid)
            rec = get_latest_recommendation(session, tid)
            snap = get_latest_snapshot(session, tid)
            if not trip or not rec or not snap:
                err_console.print(f"[red]No data for trip {tid}.[/red]")
                raise typer.Exit(1)
            data.append((trip, rec, snap))

        print_compare_table(data)


# ─── history ───────────────────────────────────────────────────────────────────


@app.command()
def history(
    trip_id: int = typer.Argument(...),
    limit: int = typer.Option(30, help="Number of snapshots to show"),
) -> None:
    """Show price history sparkline for a trip."""
    from fly_o_myte.db.sqlite import get_session, get_snapshots_for_trip, get_trip
    from fly_o_myte.display import print_price_history

    engine = _get_engine()
    with get_session(engine) as session:
        trip = get_trip(session, trip_id)
        if not trip:
            err_console.print(f"[red]Trip {trip_id} not found.[/red]")
            raise typer.Exit(1)
        snaps = get_snapshots_for_trip(session, trip_id, limit=limit)

        print_price_history(trip, snaps)


# ─── refresh ───────────────────────────────────────────────────────────────────


@app.command()
def refresh(
    trip_id: int = typer.Argument(...),
    no_email: bool = typer.Option(False, "--no-email"),
) -> None:
    """Manually fetch the latest price for a trip."""
    from fly_o_myte.db.sqlite import get_session, get_trip
    from fly_o_myte.tracker import poll_trip

    profile = _get_profile()
    engine = _get_engine()
    pm = _get_pm()

    with get_session(engine) as session:
        trip = get_trip(session, trip_id)
        if not trip:
            err_console.print(f"[red]Trip {trip_id} not found.[/red]")
            raise typer.Exit(1)
        console.print(f"Refreshing trip #{trip_id}: {trip.label}...")
        snap = poll_trip(session, trip, profile, pm, send_alerts=not no_email)

        if snap:
            console.print(f"[green]Updated: ${snap.true_family_cost:,.0f} AUD[/green]")
        else:
            console.print("[yellow]No offers found.[/yellow]")


# ─── poll ──────────────────────────────────────────────────────────────────────


@app.command()
def poll(
    no_email: bool = typer.Option(False, "--no-email"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Poll all active trips (cron target). Exits 0 even on partial errors."""
    from fly_o_myte.db.sqlite import get_session, list_active_trips
    from fly_o_myte.tracker import poll_all_active

    if dry_run:
        engine = _get_engine()
        with get_session(engine) as session:
            trips = list_active_trips(session)
        console.print(f"Dry run: would poll {len(trips)} active trip(s).")
        for t in trips:
            console.print(f"  #{t.id} {t.label}")
        return

    profile = _get_profile()
    engine = _get_engine()
    pm = _get_pm()

    with get_session(engine) as session:
        results = poll_all_active(session, profile, pm, send_alerts=not no_email)

    ok = sum(1 for v in results.values() if v == "ok")
    errors = sum(1 for v in results.values() if v == "error")
    console.print(f"Poll complete: {ok} ok, {errors} error(s), {len(results)} total.")


# ─── insight ───────────────────────────────────────────────────────────────────


@app.command()
def insight(
    trip_id: int = typer.Argument(...),
    provider: str = typer.Option("auto", help="LLM provider: auto|claude|ollama"),
) -> None:
    """Force a fresh LLM insight for a trip (Phase 2)."""
    from fly_o_myte.db.sqlite import (
        get_latest_recommendation,
        get_latest_snapshot,
        get_session,
        get_trip,
    )
    from fly_o_myte.insights import generate_insight

    engine = _get_engine()
    with get_session(engine) as session:
        trip = get_trip(session, trip_id)
        rec = get_latest_recommendation(session, trip_id)
        snap = get_latest_snapshot(session, trip_id)

        if not trip or not rec or not snap:
            err_console.print(f"[red]No data for trip {trip_id}.[/red]")
            raise typer.Exit(1)

        console.print(f"Generating insight for trip #{trip_id}...")
        depart = date.fromisoformat(trip.depart_date)
        result = generate_insight(
            origin=trip.origin,
            destination=trip.destination,
            depart_date=depart,
            current_cost=rec.true_family_cost,
            avg_cost=rec.rolling_avg_cost,
            trend_slope=rec.trend_slope,
            school_holiday_label=rec.school_holiday_flag,
            price_level_signal=rec.price_level_signal,
            n_snapshots=0,
            provider=provider,
        )

        if result:
            from rich.panel import Panel

            console.print(Panel(result.summary, title="AI Insight"))
            console.print(
                f"Price impact: {result.price_impact}  |  Event type: {result.event_type}  |  Confidence: {result.confidence:.0%}"
            )
        else:
            console.print(
                "[yellow]Insight unavailable — check LLM credentials.[/yellow]"
            )


# ─── analytics ─────────────────────────────────────────────────────────────────


@app.command()
def analytics(
    rebuild: bool = typer.Option(False, "--rebuild", help="Full rebuild from SQLite"),
) -> None:
    """Show route analytics summary or rebuild the analytics store (Phase 2)."""
    from fly_o_myte.analytics import rebuild_all

    settings = _get_settings()
    if rebuild:
        console.print("Rebuilding analytics from SQLite...")
        rebuild_all(settings.analytics_dir, settings.db_path)
        console.print("[green]Rebuild complete.[/green]")
    else:
        console.print(
            "Analytics summary not yet implemented. Use --rebuild to rebuild Parquet store."
        )


# ─── pause / resume / remove ───────────────────────────────────────────────────


@app.command()
def pause(trip_id: int = typer.Argument(...)) -> None:
    """Pause price tracking for a trip."""
    from fly_o_myte.db.sqlite import get_session, set_trip_active

    with get_session(_get_engine()) as session:
        set_trip_active(session, trip_id, active=False)
    console.print(f"Trip #{trip_id} paused.")


@app.command()
def resume(trip_id: int = typer.Argument(...)) -> None:
    """Resume price tracking for a paused trip."""
    from fly_o_myte.db.sqlite import get_session, set_trip_active

    with get_session(_get_engine()) as session:
        set_trip_active(session, trip_id, active=True)
    console.print(f"Trip #{trip_id} resumed.")


@app.command()
def remove(
    trip_id: int = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a trip and all its price history."""
    from fly_o_myte.db.sqlite import (
        delete_trip,
        get_session,
        get_snapshots_for_trip,
        get_trip,
    )

    engine = _get_engine()
    with get_session(engine) as session:
        trip = get_trip(session, trip_id)
        if not trip:
            err_console.print(f"[red]Trip {trip_id} not found.[/red]")
            raise typer.Exit(1)
        n_snaps = len(get_snapshots_for_trip(session, trip_id))
        if not yes:
            confirmed = Confirm.ask(
                f"Remove trip '{trip.label}' and all {n_snaps} snapshots?"
            )
            if not confirmed:
                console.print("Cancelled.")
                return
        delete_trip(session, trip_id)

    console.print(f"[green]Trip {trip_id} removed.[/green]")


# ─── profile ───────────────────────────────────────────────────────────────────


@app.command()
def profile() -> None:
    """View your family profile."""
    from rich import box
    from rich.table import Table

    p = _get_profile()
    table = Table(title="Family Profile", box=box.SIMPLE)
    table.add_column("Setting", style="dim")
    table.add_column("Value")
    table.add_row("Adults", str(p.adults))
    table.add_row("Children", str(len(p.children)))
    for i, child in enumerate(p.children):
        today = date.today()
        age = (
            today.year
            - child.dob.year
            - ((today.month, today.day) < (child.dob.month, child.dob.day))
        )
        table.add_row(f"  Child {i + 1}", f"{child.name} (age {age}, DOB {child.dob})")
    table.add_row("Origin airport", p.origin_airport)
    table.add_row("State", p.state)
    table.add_row("School type", p.school_type)
    table.add_row("Bags/person", str(p.bags_per_person))
    table.add_row("Max stops", str(p.max_stops))
    table.add_row("Blocked airlines", ", ".join(p.blocked_airlines) or "None")
    if p.budget_threshold_aud:
        table.add_row("Budget threshold", f"${p.budget_threshold_aud:,.0f} AUD")
    console.print(table)


# ─── data-version ──────────────────────────────────────────────────────────────


@app.command(name="data-version")
def data_version() -> None:
    """Show embedded airline and school holiday data freshness."""
    from fly_o_myte.display import print_data_version
    from fly_o_myte.fees import get_airline_db

    db = get_airline_db()
    print_data_version(db.version, db.last_updated, db.all_codes())


if __name__ == "__main__":
    app()
