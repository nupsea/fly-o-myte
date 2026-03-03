# Quality Score — Fly-O-Myte

Last Updated: 2026-03-03 — S14 complete (Phase 1 stories S01–S14 all pass)

Updated by ralph after each phase. Grades: A (complete), B (mostly done), C (partial), D (minimal), F (not started).

| Domain          | Implemented | Tested | Documented | Quality Grade |
|-----------------|-------------|--------|------------|---------------|
| Price Sources   | yes         | yes    | partial    | B             |
| Cost Engine     | yes         | yes    | yes        | A             |
| Calendar        | yes         | yes    | yes        | A             |
| Recommender     | yes         | yes    | yes        | A             |
| Tracker         | yes         | yes    | partial    | B             |
| Scout           | yes         | no     | partial    | C             |
| Analytics       | stub        | stub   | partial    | D             |
| Insights (LLM)  | yes         | yes    | partial    | B             |
| Notifier        | yes         | yes    | partial    | B             |
| Display         | yes         | no     | no         | C             |
| CLI             | yes         | yes    | partial    | B             |
| Dev Tooling     | yes         | n/a    | yes        | A             |

## Notes

### Phase 1 Baseline (2026-03-03)

**Cost Engine (A)**: `compute_true_cost()` fully implemented and tested — base fares, per-leg bag fees, per-leg seat fees, per-sector infant fees (Jetstar $35/sector vs Qantas $0). `compute_family_score()` composite 0–100. All 4 airlines (QF, VA, JQ, ZL) in embedded JSON. Airline fee parser produces correct values for both standard and lite fares.

**Calendar (A)**: `SchoolCalendar` loads embedded YAML, detects holiday overlaps, returns `HolidayContext`. QLD 2025–2027 term dates embedded. Correctly skips term periods (no `label` key), processes only break periods.

**Recommender (A)**: 10-rule decision matrix, confidence scaling by data richness, regret risk via Random Regret Minimisation, trend slope via pure-Python least-squares. 35+ passing unit tests — no mocking required.

**Tracker (B)**: `poll_trip()` and `poll_all_active()` fully wired — fetch → true cost → family score → snapshot → recommendation → alert. Deterministic `_StubTequilaSource` integration tests with exact cost assertions. Missing: analytics integration after poll.

**CLI (B)**: All 15 commands implemented: setup, scout, watch, status, check, compare, history, refresh, insight, poll, analytics, pause, resume, remove, profile, data-version. Basic integration tests pass. Missing: Syrupy snapshot tests for Rich output.

**Price Sources (B)**: Tequila adapter implemented with tenacity retry. S09/S13: 13 pytest-httpx unit tests covering happy path, HTTP errors, retry behaviour, param construction (children/infants, one-way/return, currency, max_stopovers), and Pluggy registration. `_StubTequilaSource` in conftest serves integration tests. SerpAPI adapter implemented — tests in S20 (Phase 2). Amadeus adapter is a stub.

**Analytics (D)**: `analytics.py` is a scaffold — incremental DuckDB/Parquet aggregation not yet implemented. Phase 2 work.

**Insights (B)**: `TravelInsight` Pydantic model, `generate_insight()` with graceful degradation (returns None when LLM unavailable). Schema validation passes. Missing: golden fixture evaluation with LLM-as-judge.

**Scout (C)**: `scout_month()` and `scout_flex()` implemented, not yet tested. CLI `scout` command wired.

**Notifier (B)**: `send_book_now_alert()` fully implemented — SMTP via stdlib smtplib, graceful degradation (returns False on missing credentials/recipient/SMTP error). S14: 8 tests covering happy path, credential checks, recipient check, exception handling, subject/body content, and tracker integration (email_sent wiring via mark_email_sent).

**Display (C)**: Rich rendering helpers implemented. Not yet tested with Syrupy snapshots.

**Dev Tooling (A)**: `make ci` runs lint → typecheck → layer-lint → data-check → test → smoke-test. Layer linter covers 21 files. `make test` runs 101 tests in <0.6s.
