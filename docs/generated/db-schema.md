# Database Schema — Fly-O-Myte

Last reviewed: 2026-03-04 — S31: added `rank` field to `pricesnapshot`; `get_snapshots_at_fetch()` CRUD added.

Auto-generated from `fly_o_myte/db/sqlite.py`. Regenerate after schema changes with:
```bash
uv run python -c "from fly_o_myte.db.sqlite import *; import inspect; print(inspect.getsource(__import__('fly_o_myte.db.sqlite', fromlist=['Trip'])))"
```

## SQLite Tables (via SQLModel)

### `trip`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER PK | autoincrement | |
| label | TEXT | required | e.g. "Easter BNE-SYD 2026" |
| origin | TEXT | required | IATA airport code |
| destination | TEXT | required | IATA airport code |
| depart_date | TEXT | required | YYYY-MM-DD |
| return_date | TEXT | NULL | YYYY-MM-DD (None = one-way) |
| adults | INTEGER | 2 | |
| children_json | TEXT | "[]" | JSON: [{name, dob}, ...] |
| bags_per_person | INTEGER | 1 | |
| max_stops | INTEGER | 1 | |
| is_active | INTEGER | 1 | 1 = active, 0 = paused |
| created_at | TEXT | now | ISO 8601 |
| alert_threshold_aud | REAL | NULL | alert if price drops below |
| alert_email | TEXT | NULL | override profile email |

### `pricesnapshot`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER PK | autoincrement | |
| trip_id | INTEGER FK | required | → trip.id |
| fetched_at | TEXT | now | ISO 8601 |
| source | TEXT | required | "tequila" / "stub" |
| airline_code | TEXT | required | IATA carrier code |
| flight_number | TEXT | NULL | |
| base_fare_per_adult | REAL | required | AUD |
| true_family_cost | REAL | required | AUD — full family total |
| true_cost_breakdown | TEXT | required | JSON: {base_adults, base_children, bags, seats, infant, total} |
| price_level_signal | TEXT | NULL | "LOW" / "TYPICAL" / "HIGH" |
| stops | INTEGER | 0 | |
| departure_time | TEXT | NULL | HH:MM |
| duration_minutes | INTEGER | NULL | |
| family_score | REAL | NULL | 0–100 composite |
| offer_raw | TEXT | "{}" | JSON from price source |
| rank | INTEGER | 1 | Offer rank by true family cost: 1=best, 2=second, 3=third (S31) |

### `recommendation`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| id | INTEGER PK | autoincrement | |
| trip_id | INTEGER FK | required | → trip.id |
| generated_at | TEXT | now | ISO 8601 |
| decision | TEXT | required | "book_now" / "wait" / "monitor" |
| confidence | REAL | required | 0.0–1.0 |
| regret_risk | TEXT | required | "low" / "medium" / "high" |
| regret_book_aud | REAL | 0 | expected regret if booking now |
| regret_wait_aud | REAL | 0 | expected regret if waiting |
| true_family_cost | REAL | required | from latest snapshot |
| rolling_avg_cost | REAL | required | rolling average |
| trend_slope | REAL | 0 | AUD/day — negative = falling |
| days_to_departure | INTEGER | required | calendar days |
| price_level_signal | TEXT | NULL | |
| school_holiday_flag | TEXT | NULL | holiday label if overlap |
| rationale | TEXT | required | human-readable explanation |
| email_sent | INTEGER | 0 | 1 if alert was sent |

## DuckDB / Parquet (Phase 2)

Parquet files written to `~/.fly-o-myte/analytics/`. Schemas defined in `fly_o_myte/analytics.py`.
See `docs/ARCHITECTURE.md` §Data Flow for the incremental analytics pipeline.
