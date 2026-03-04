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

        # Tip for long-haul routes with low stops
        from fly_o_myte.recommender import RouteType, classify_route

        if (
            classify_route(origin, destination) == RouteType.LONG_HAUL
            and (max_stops if max_stops is not None else profile.max_stops) <= 1
        ):
            console.print(
                "[dim]Tip: Long-haul routes often have much cheaper 2-stop options. "
                "Try adding [bold]--max-stops 2[/bold] to see more candidates.[/dim]"
            )

        console.print("Fetching initial price...")
        snap = poll_trip(session, trip, profile, pm, send_alerts=False)
        if snap:
            n_stops = snap.stops or 0
            stops_label = (
                "nonstop"
                if n_stops == 0
                else f"{n_stops} stop{'s' if n_stops > 1 else ''}"
            )
            details = f"  {snap.airline_code or '?'} · {stops_label}"
            if snap.departure_time:
                details += f" · departs {snap.departure_time}"
            console.print(
                f"Initial price: [bold]${snap.true_family_cost:,.0f} AUD[/bold]{details}"
            )
            console.print(
                f"[dim]Run [bold]fom check {trip.id}[/bold] for full breakdown and alternatives.[/dim]"
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

        # Fetch all snapshots at this fetched_at for the Alternatives table
        from fly_o_myte.db.sqlite import get_snapshots_at_fetch

        all_snaps = get_snapshots_at_fetch(session, trip_id, snap.fetched_at)
        alternatives = all_snaps if len(all_snaps) > 1 else None

        print_trip_detail(
            trip, rec, snap, breakdown, alternative_snapshots=alternatives
        )

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
            n_stops = snap.stops or 0
            stops_label = (
                "nonstop"
                if n_stops == 0
                else f"{n_stops} stop{'s' if n_stops > 1 else ''}"
            )
            details = f"  {snap.airline_code or '?'} · {stops_label}"
            if snap.departure_time:
                details += f" · departs {snap.departure_time}"
            console.print(
                f"[green]Updated: ${snap.true_family_cost:,.0f} AUD[/green]{details}"
            )
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


# ─── flex ──────────────────────────────────────────────────────────────────────


@app.command()
def flex(
    trip_id: int = typer.Argument(...),
    flex_days: int = typer.Option(3, "--flex", help="Flex range in days"),
    fix_return: bool = typer.Option(
        False, "--fix-return", help="Fix return date, vary depart"
    ),
    fix_depart: bool = typer.Option(
        False, "--fix-depart", help="Fix depart date, vary return"
    ),
    month: bool = typer.Option(
        False,
        "--month",
        help="Scan the full departure month rather than ±N days",
    ),
    refresh: bool = typer.Option(
        False, "--refresh", help="Bypass cache and fetch fresh prices"
    ),
) -> None:
    """Show ±N day date alternatives ranked by true family cost."""
    import json as _json
    from datetime import UTC, datetime, timedelta

    from rich.prompt import Prompt

    from fly_o_myte.calendar import get_calendar
    from fly_o_myte.db.sqlite import (
        Trip,
        delete_trip,
        get_flex_cache,
        get_latest_snapshot,
        get_session,
        get_trip,
        insert_trip,
        set_flex_cache,
    )
    from fly_o_myte.display import FlexResultRow, print_flex_results
    from fly_o_myte.fees import get_airline_db
    from fly_o_myte.scout import compute_price_variance_ratio, scout_flex, scout_month

    engine = _get_engine()
    with get_session(engine) as session:
        trip = get_trip(session, trip_id)
        if not trip:
            err_console.print(f"[red]Trip {trip_id} not found.[/red]")
            raise typer.Exit(1)

        depart_dt = date.fromisoformat(trip.depart_date)
        year_val = depart_dt.year
        month_val = depart_dt.month
        trip_length = (
            (date.fromisoformat(trip.return_date) - depart_dt).days
            if trip.return_date
            else 7
        )

        # Determine mode + cache key
        if month:
            flex_key = f"month_{trip.origin}_{trip.destination}_{year_val}_{month_val}"
            depart_flex_val = 0
            return_flex_val = 0  # not used in month mode
            symmetric = False
        else:
            if fix_return:
                depart_flex_val = flex_days
                return_flex_val = 0
                symmetric = False
            elif fix_depart:
                depart_flex_val = 0
                return_flex_val = flex_days
                symmetric = False
            else:
                depart_flex_val = flex_days
                return_flex_val = flex_days
                symmetric = True
            flex_key = f"{trip.origin}_{trip.destination}_{trip.depart_date}_{trip.return_date}_{depart_flex_val}_{return_flex_val}"

        # Get tracked cost from latest rank-1 snapshot
        latest_snap = get_latest_snapshot(session, trip_id)
        tracked_cost: float | None = (
            latest_snap.true_family_cost if latest_snap else None
        )

        # Check cache
        rows: list[FlexResultRow] = []
        cache_used = False

        if not refresh:
            cached = get_flex_cache(session, trip_id, flex_key)
            if cached:
                age = datetime.now(UTC) - datetime.fromisoformat(
                    cached.computed_at
                ).replace(tzinfo=UTC)
                if age < timedelta(hours=24):
                    data = _json.loads(cached.results_json)
                    rows = [
                        FlexResultRow(
                            depart_date=date.fromisoformat(d["depart_date"]),
                            return_date=date.fromisoformat(d["return_date"]),
                            true_family_cost=d["true_family_cost"],
                            airline_code=d["airline_code"],
                            stops=d["stops"],
                            departure_time=d["departure_time"],
                            school_holiday_label=d.get("school_holiday_label"),
                        )
                        for d in data
                    ]
                    cache_used = True
                    age_mins = int(age.total_seconds() // 60)
                    if age_mins < 60:
                        time_ago = f"{age_mins}m ago"
                    else:
                        time_ago = f"{int(age_mins // 60)}h ago"
                    console.print(
                        f"[dim]Using cached flex results from {time_ago}. "
                        f"Run with --refresh to fetch live prices.[/dim]"
                    )

        if not cache_used:
            # Fresh fetch
            profile = _get_profile()
            pm = _get_pm()
            airline_db = get_airline_db()
            cal = get_calendar()

            if month:
                scout_results = scout_month(
                    pm=pm,
                    profile=profile,
                    airline_db=airline_db,
                    calendar=cal,
                    origin=trip.origin,
                    destination=trip.destination,
                    year=year_val,
                    month=month_val,
                    trip_length_days=trip_length,
                )
            else:
                ret = (
                    date.fromisoformat(trip.return_date)
                    if trip.return_date
                    else depart_dt
                )
                scout_results = scout_flex(
                    pm=pm,
                    profile=profile,
                    airline_db=airline_db,
                    calendar=cal,
                    origin=trip.origin,
                    destination=trip.destination,
                    depart_date=depart_dt,
                    return_date=ret,
                    depart_flex=depart_flex_val,
                    return_flex=return_flex_val,
                )

            rows = [
                FlexResultRow(
                    depart_date=r.depart_date,
                    return_date=r.return_date,
                    true_family_cost=r.true_family_cost,
                    airline_code=r.airline_code,
                    stops=r.stops,
                    departure_time=r.departure_time,
                    school_holiday_label=r.school_holiday.label
                    if r.school_holiday
                    else None,
                )
                for r in scout_results
            ]

            # Store in cache
            cache_data = [
                {
                    "depart_date": str(row.depart_date),
                    "return_date": str(row.return_date),
                    "true_family_cost": row.true_family_cost,
                    "airline_code": row.airline_code,
                    "stops": row.stops,
                    "departure_time": row.departure_time,
                    "school_holiday_label": row.school_holiday_label,
                }
                for row in rows
            ]
            set_flex_cache(session, trip_id, flex_key, _json.dumps(cache_data))

        if not rows:
            console.print(f"No cheaper windows found within \u00b1{flex_days} days.")
            return

        # Build display title for month mode
        title_override: str | None = None
        if month:
            import calendar as _cal

            month_name = _cal.month_name[depart_dt.month]
            title_override = (
                f"Full month view: {month_name} {depart_dt.year} -- all sampled windows"
            )

        print_flex_results(
            rows,
            tracked_cost,
            trip.origin,
            trip.destination,
            title_override=title_override,
        )

        # Smart range suggestion (symmetric flex only, >= 3 results, not month mode)
        if symmetric and len(rows) >= 3 and not month:
            ratio = compute_price_variance_ratio([r.true_family_cost for r in rows])
            if ratio > 0.20:
                pct = int(ratio * 100)
                console.print(
                    f"[yellow]Prices vary significantly (\u00b1{pct}%) in this window. "
                    f"Consider running fom flex {trip_id} --flex 7 for a broader view.[/yellow]"
                )

        # Check if any are cheaper than tracked
        cheaper = [
            r
            for r in rows
            if tracked_cost is not None and r.true_family_cost < tracked_cost
        ]
        if not cheaper:
            console.print(f"No cheaper windows found within \u00b1{flex_days} days.")
            return

        # Interactive: watch a cheaper alternative?
        choices = [str(i) for i in range(1, len(rows) + 1)] + ["n"]
        answer = Prompt.ask(
            f"Watch a cheaper alternative instead? [1-{len(rows)}/n]",
            choices=choices,
            default="n",
        )
        if answer == "n":
            return

        selected_idx = int(answer) - 1
        selected = rows[selected_idx]

        action = Prompt.ask(
            f"Replace trip #{trip_id} or add as new trip?",
            choices=["replace", "add", "cancel"],
            default="cancel",
        )
        if action == "cancel":
            return

        if action == "replace":
            confirmed = Prompt.ask(
                f"This will remove trip #{trip_id} ({trip.label}). Confirm?",
                choices=["y", "n"],
                default="n",
            )
            if confirmed != "y":
                console.print("Cancelled.")
                return
            delete_trip(session, trip_id)
            new_trip = insert_trip(
                session,
                Trip(
                    label=f"{trip.origin}-{trip.destination} {selected.depart_date}",
                    origin=trip.origin,
                    destination=trip.destination,
                    depart_date=str(selected.depart_date),
                    return_date=str(selected.return_date),
                    adults=trip.adults,
                    children_json=trip.children_json,
                    bags_per_person=trip.bags_per_person,
                    max_stops=trip.max_stops,
                    alert_email=trip.alert_email,
                ),
            )
            assert new_trip.id is not None
            console.print(
                f"[green]Replaced trip #{trip_id} with new trip #{new_trip.id}.[/green]"
            )
        else:  # add
            new_trip = insert_trip(
                session,
                Trip(
                    label=f"{trip.origin}-{trip.destination} {selected.depart_date}",
                    origin=trip.origin,
                    destination=trip.destination,
                    depart_date=str(selected.depart_date),
                    return_date=str(selected.return_date),
                    adults=trip.adults,
                    children_json=trip.children_json,
                    bags_per_person=trip.bags_per_person,
                    max_stops=trip.max_stops,
                    alert_email=trip.alert_email,
                ),
            )
            assert new_trip.id is not None
            console.print(
                f"[green]Added new trip #{new_trip.id}: {selected.depart_date} \u2192 {selected.return_date}[/green]"
            )


# ─── airports ──────────────────────────────────────────────────────────────────


@app.command()
def airports(
    query: str = typer.Argument(
        ..., help="City name, country name, or IATA code to search"
    ),
) -> None:
    """Look up international airport IATA codes by city or country name."""
    from rich import box
    from rich.table import Table

    from fly_o_myte.airports import resolve_destination

    matches = resolve_destination(query)
    if not matches:
        console.print("No matches found.")
        return

    table = Table(title=f"Airports matching '{query}'", box=box.SIMPLE)
    table.add_column("IATA", style="bold")
    table.add_column("Airport / City")
    for iata, display_name in matches:
        table.add_row(iata, display_name)
    console.print(table)


# ─── plan ──────────────────────────────────────────────────────────────────────


@app.command()
def plan(
    intent_text: str | None = typer.Argument(
        None, help="Natural language trip description, e.g. 'Sri Lanka in December'"
    ),
    budget: float | None = typer.Option(
        None, "--budget", help="Maximum true family cost in AUD"
    ),
) -> None:
    """Plan a trip from a natural language idea or guided prompts."""
    import calendar as _cal

    from fly_o_myte.calendar import get_calendar
    from fly_o_myte.db.sqlite import Trip, get_session, insert_trip
    from fly_o_myte.display import FlexResultRow, print_flex_results
    from fly_o_myte.fees import get_airline_db
    from fly_o_myte.planner import TripIntent, extract_trip_intent
    from fly_o_myte.scout import scout_month
    from fly_o_myte.tracker import poll_trip

    settings = _get_settings()
    api_key: str | None = settings.anthropic_api_key or None

    intent: TripIntent = extract_trip_intent(intent_text or "", api_key)

    profile = _get_profile()
    origin = intent.origin_override or profile.origin_airport

    # Confirm origin if user specified an override
    if intent.origin_override:
        from rich.prompt import Prompt as _Prompt

        answer = _Prompt.ask(
            f"Origin: {intent.origin_override} (from your input) instead of "
            f"{profile.origin_airport} (profile). Use {intent.origin_override}?",
            choices=["y", "n"],
            default="y",
        )
        if answer != "y":
            origin = profile.origin_airport

    month_name = _cal.month_name[intent.month]
    console.print(f"\nPlanning trip to: [bold]{intent.destination_display}[/bold]")
    console.print(
        f"Searching {origin} \u2192 {intent.destination_iata} for "
        f"{month_name} {intent.year}..."
    )

    pm = _get_pm()
    airline_db = get_airline_db()
    cal = get_calendar()

    results = scout_month(
        pm=pm,
        profile=profile,
        airline_db=airline_db,
        calendar=cal,
        origin=origin,
        destination=intent.destination_iata,
        year=intent.year,
        month=intent.month,
        trip_length_days=intent.nights,
    )

    if not results:
        console.print(
            f"No results found for {month_name} {intent.year}. "
            "Check your API key or try a different destination."
        )
        return

    # Budget filter
    display_results = results
    if budget is not None:
        qualified = [r for r in results if r.true_family_cost <= budget]
        if not qualified:
            console.print(
                f"[yellow]No windows found under ${budget:,.0f}. "
                "Showing cheapest 3 for reference.[/yellow]"
            )
            display_results = results[:3]
        else:
            display_results = qualified

    # School holiday warning: flag if top results overlap a holiday
    holiday_count = sum(1 for r in display_results[:5] if r.school_holiday)
    if holiday_count > 0:
        first_holiday = next(
            r.school_holiday for r in display_results if r.school_holiday
        )
        console.print(
            f"[yellow]Note: top {holiday_count} windows overlap "
            f"{first_holiday.label} \u2014 prices are typically 15-30% higher. "
            "Cheaper windows shown below.[/yellow]"
        )

    # Display using print_flex_results (delta vs tracked = None since no tracked trip yet)
    rows = [
        FlexResultRow(
            depart_date=r.depart_date,
            return_date=r.return_date,
            true_family_cost=r.true_family_cost,
            airline_code=r.airline_code,
            stops=r.stops,
            departure_time=r.departure_time,
            school_holiday_label=r.school_holiday.label if r.school_holiday else None,
        )
        for r in display_results
    ]

    print_flex_results(rows, None, origin, intent.destination_iata)

    # Watch prompt
    from rich.prompt import Prompt as _Prompt2

    choices = [str(i) for i in range(1, len(rows) + 1)] + ["n"]
    answer = _Prompt2.ask(
        f"Start tracking one of these? [1-{len(rows)}/n]",
        choices=choices,
        default="n",
    )
    if answer == "n":
        return

    selected_idx = int(answer) - 1
    selected = display_results[selected_idx]
    trip_label = (
        f"{origin}-{intent.destination_iata} {selected.depart_date} "
        f"({intent.destination_display})"
    )

    engine = _get_engine()
    with get_session(engine) as session:
        new_trip = insert_trip(
            session,
            Trip(
                label=trip_label,
                origin=origin,
                destination=intent.destination_iata,
                depart_date=str(selected.depart_date),
                return_date=str(selected.return_date),
                adults=profile.adults,
                bags_per_person=profile.bags_per_person,
                max_stops=profile.max_stops,
            ),
        )
        assert new_trip.id is not None
        console.print(f"[green]Tracking trip #{new_trip.id}: {trip_label}[/green]")

        snap = poll_trip(session, new_trip, profile, pm, send_alerts=False)
        if snap:
            n_stops = snap.stops or 0
            stops_label = (
                "nonstop"
                if n_stops == 0
                else f"{n_stops} stop{'s' if n_stops > 1 else ''}"
            )
            console.print(
                f"  Initial price: ${snap.true_family_cost:,.0f} AUD  "
                f"{snap.airline_code} . {stops_label} . departs {snap.departure_time}"
            )
        else:
            console.print("[yellow]No offers found — will retry on next poll.[/yellow]")


if __name__ == "__main__":
    app()
