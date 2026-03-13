# Fly-O-Myte Architecture

Last reviewed: 2026-03-04 — Phase 3 complete; Phase 4 in progress (airport resolver, flex comparison, fom plan NL planner).

## Top-Level Domain Map

The package is organised into 5 functional domains:

| Domain        | Responsibility                                                   | Key Modules                              |
|---------------|------------------------------------------------------------------|------------------------------------------|
| Pricing       | Flight search via external APIs, price source plugin system      | `price_sources/`, `tracker`, `scout`     |
| Cost Engine   | True family cost (base + bags + seats + infant), family score    | `fees`, `true_cost`                      |
| Calendar      | Australian school holiday lookup (embedded YAML)                 | `calendar`                               |
| Recommendations | Decision engine: Book Now / Wait / Monitor, regret risk        | `recommender`                            |
| Intelligence  | LLM contextual insights, analytics, display, notifications       | `insights`, `analytics`, `display`, `notifier` |

## 8-Layer Dependency Rule

Within the package, imports flow **forward only**:

```
Layer 0 — price_sources.hookspecs  (FlightOffer, plugin contracts)
Layer 1 — config, db.sqlite, db.duckdb
Layer 2 — fees, calendar, currency  (load embedded data; currency rate cache)
Layer 3 — recommender, true_cost    (pure logic; import types + layer 2)
Layer 4 — price_sources.tequila, price_sources.amadeus
Layer 5 — tracker, scout, analytics, insights, notifier, planner  (orchestration)
Layer 6 — display                   (Rich output)
Layer 7 — cli                       (Typer entry-point; may import anything)
```

A module at layer N must never import from a module at layer > N.
Enforced by `tools/layer_linter.py` — part of `make ci`.

## Package Layout

```
fly_o_myte/
  __init__.py                 # __version__, __app_name__
  cli.py                      # Layer 7 — Typer app, all CLI commands
  config.py                   # Layer 1 — pydantic-settings + YAML profile
  calendar.py                 # Layer 2 — school holiday lookup (embedded YAML)
  currency.py                 # Layer 2 — Frankfurter API exchange rates (24h cache)
  fees.py                     # Layer 2 — airline fee database loader
  airports.py                 # Layer 2 — city/country name → IATA code resolver (~50 top destinations)
  true_cost.py                # Layer 3 — true family cost calculator
  recommender.py              # Layer 3 — decision engine (pure functions, no I/O)
  tracker.py                  # Layer 5 — poll cycle orchestration
  scout.py                    # Layer 5 — date range scouting + flex comparison
  analytics.py                # Layer 5 — incremental DuckDB/Parquet aggregation
  insights.py                 # Layer 5 — Pydantic AI LLM contextual insights
  notifier.py                 # Layer 5 — SMTP email alerts
  planner.py                  # Layer 5 — NL trip intent extraction (TripIntent) + structured wizard fallback
  display.py                  # Layer 6 — Rich console output
  db/
    sqlite.py                 # Layer 1 — SQLModel tables + CRUD (OLTP)
    duckdb.py                 # Layer 1 — DuckDB helpers (OLAP)
  price_sources/
    hookspecs.py              # Layer 0 — Pluggy hook specifications + FlightOffer
    serpapi.py                # Layer 4 — SerpAPI Google Flights adapter (primary)
    tequila.py                # Layer 4 — Kiwi.com Tequila API adapter (fallback)
    amadeus.py                # Layer 4 — Amadeus adapter (price level signal enrichment)
  data/
    airlines.json             # Embedded fee database (QF, VA, JQ, ZL, ...)
    school_holidays.yaml      # Embedded QLD school term calendar (Phase 1)

tools/
  layer_linter.py             # AST-based layer dependency enforcer

tests/
  conftest.py                 # Session isolation, _StubTequilaSource, fixtures
  test_recommender.py         # Decision engine (pure functions — no mocking)
  test_true_cost.py           # True cost + family score calculations
  test_calendar.py            # School holiday overlap detection
  test_tracker.py             # Poll cycle integration tests
  test_analytics.py           # DuckDB/Parquet aggregation
  test_insights.py            # Pydantic AI schema + graceful degradation
  test_cli.py                 # CLI command integration tests
```

## Data Flow: Poll Cycle

```
fom poll
  → poll_all_active() iterates active trips
      → _fetch_top_offers(n=10) calls plugin manager hook
          → SerpAPIFlightSource.search_flights() → Google Flights via SerpAPI
            (stops-filter retry: if Google returns no results with server-side
             stops filter, retries without it and filters client-side)
          → AmadeusPriceSource.get_price_level_signal() → optional enrichment
      → compute_true_cost() — bags + seats + infant — for each of top-10 offers
      → compute_family_score() — cost + stops + time + airline rating
      → insert_snapshot() × top-3 offers → SQLite (rank 1/2/3 by true family cost)
      → compute() — recommendation engine (pure functions)
      → insert_recommendation() → SQLite
      → send alert if decision == "book_now" OR price <= alert_threshold
      → update_after_snapshot() → DuckDB + Parquet
```

## Data Flow: Dual Storage

```
SQLite (fly-o-myte.db)             DuckDB + Parquet (analytics/)
  trips                →  snapshots/*.parquet     (time-series)
  price_snapshots      →  route_stats/*.parquet   (weekly aggregates)
  recommendations      →  market_context/*.parquet (LLM insights)

DuckDB sqlite_scan extension joins both in one query for LLM context.
```

## Current Implementation Status

Phases 1–3 complete. Phase 4 in progress.
- Phase 1: Domestic AU price tracking, recommendation engine, CLI, email alerts.
- Phase 2: DuckDB analytics, Amadeus enrichment, compare breakdown, market context.
- Phase 3: Multi-currency, international routes, per-country SerpAPI routing, top-3 alternatives in `fom check`.
- Phase 4 (in progress): Airport name resolver (`airports.py`), `fom flex` date comparison, `fom plan` NL trip planner, trip group tagging.
See `scripts/ralph/prd.json` for story-level status.
