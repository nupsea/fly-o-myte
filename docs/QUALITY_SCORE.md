# Quality Score — Fly-O-Myte

Last Updated: 2026-03-03 — Phase 1 baseline

Updated by ralph after each phase. Grades: A (complete), B (mostly done), C (partial), D (minimal), F (not started).

| Domain          | Implemented | Tested | Documented | Quality Grade |
|-----------------|-------------|--------|------------|---------------|
| Price Sources   | yes         | no     | partial    | C             |
| Cost Engine     | yes         | yes    | yes        | A             |
| Calendar        | yes         | yes    | yes        | A             |
| Recommender     | yes         | yes    | yes        | A             |
| Tracker         | yes         | yes    | partial    | B             |
| Scout           | yes         | no     | partial    | C             |
| Analytics       | stub        | stub   | partial    | D             |
| Insights (LLM)  | yes         | yes    | partial    | B             |
| Notifier        | yes         | no     | no         | D             |
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

**Price Sources (C)**: Tequila adapter implemented with tenacity retry. `_StubTequilaSource` in conftest serves integration tests. Missing: unit tests for Tequila adapter, Amadeus adapter is a stub.

**Analytics (D)**: `analytics.py` is a scaffold — incremental DuckDB/Parquet aggregation not yet implemented. Phase 2 work.

**Insights (B)**: `TravelInsight` Pydantic model, `generate_insight()` with graceful degradation (returns None when LLM unavailable). Schema validation passes. Missing: golden fixture evaluation with LLM-as-judge.

**Scout (C)**: `scout_date_windows()` implemented, not yet tested. CLI `scout` command wired.

**Notifier (D)**: `send_alert()` SMTP skeleton exists. Not tested. Email send not integrated into poll cycle.

**Display (C)**: Rich rendering helpers implemented. Not yet tested with Syrupy snapshots.

**Dev Tooling (A)**: `make ci` runs lint → typecheck → layer-lint → data-check → test. Layer linter covers 20 files. `make test` runs 80 tests in <0.5s.
