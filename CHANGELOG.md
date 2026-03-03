# Changelog

All notable changes to Travo are documented here.
Format: [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — Phase 1 (in development)

### Added
- `travo setup` — interactive first-run configuration wizard
- `travo watch` — start tracking a trip with immediate price fetch
- `travo status` — morning digest, actionable trips only
- `travo check <id>` — full recommendation with itemised cost breakdown
- `travo compare <id1> <id2>` — side-by-side trip comparison
- `travo history <id>` — price history with Unicode sparkline
- `travo refresh <id>` — manual price fetch
- `travo poll` — cron target, polls all active trips
- `travo scout` — explore date windows across a month
- `travo pause/resume/remove` — trip lifecycle management
- `travo profile` — view family profile
- `travo data-version` — show embedded data freshness
- True family cost calculator: base fare + bags + seat selection + infant fees
- Jetstar per-sector infant fee handling ($35 per sector, not per journey)
- Recommendation engine: Book Now / Wait / Monitor decision matrix
- Confidence scaling by data richness (saturates at 10+ snapshots)
- Regret risk score in AUD (Random Regret Minimisation model)
- QLD school holiday awareness (2025–2027 embedded)
- Pluggy-based price source plugin architecture
- Tequila API adapter (primary domestic source)
- Email alerts for book_now recommendations via SMTP
- SQLite persistence with WAL mode for concurrent access
- Rich terminal output

### Data
- Australian airline fee database (QF, VA, JQ, ZL, TL) — version 2026-01
- QLD school holidays 2025–2027 (data sourced from Queensland DoE)

---

## Phase 2 (planned)

### Planned additions
- DuckDB + Parquet incremental analytics layer
- All Australian state school calendars (NSW, VIC, WA, SA, TAS, NT, ACT)
- Pydantic AI LLM insights (Claude haiku + Ollama fallback)
- Pydantic Logfire observability
- Amadeus price level signal integration (LOW/TYPICAL/HIGH)
- `travo analytics` — route stats, percentiles, seasonal patterns
- `travo insight <id>` — force fresh LLM contextual insight
- `travo report` — Evidence HTML report
- `travo ui` — Textual interactive TUI

---

## Phase 3 (planned)

### Planned additions
- International routes (Amadeus as primary source)
- Multi-currency AUD conversion (Frankfurter API)
- International school holiday calendars (NZ, SG, UK, JP, TH, US)
- International booking window intelligence (120-day horizon)
