# Design Docs Index

All design decisions for Fly-O-Myte are versioned here.

## Documents

| File | Description |
|------|-------------|
| `core-beliefs.md` | 18 golden principles — canonical source of truth for all engineering values |

## Key Decisions

| Decision | Rationale | Doc Reference |
|----------|-----------|---------------|
| SQLite + DuckDB dual storage | SQLite for concurrent writes (cron + manual), DuckDB for analytics queries | `ARCHITECTURE.md` §Data Flow |
| Pluggy for price sources | Allows new providers without touching core business logic | `ARCHITECTURE.md` §Package Layout |
| Pydantic AI (not LangGraph) | Single-agent structured output; LangGraph is for complex multi-agent state machines | `core-beliefs.md` §10 |
| Embedded YAML/JSON for data | No Australian school holiday API exists; static data updated 2-3x/year is stable | `core-beliefs.md` §8 |
| 8-layer dependency rule | Prevents circular imports, enables independent testing per layer | `core-beliefs.md` §5 |
| Child ages at travel date | Infant/child classification must use departure date, not today | `core-beliefs.md` §18 |
