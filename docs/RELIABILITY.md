# Reliability — Fly-O-Myte

## CLI Response Time Targets

| Command         | Target (p95) | Notes |
|-----------------|-------------|-------|
| `fom status`    | < 200ms     | SQLite read only — no network |
| `fom check <id>`| < 500ms     | SQLite + calendar + recommender |
| `fom poll`      | < 30s       | One Tequila API call per active trip |
| `fom scout`     | < 60s       | Up to 8 Tequila API calls (date sampling) |
| `fom refresh`   | < 10s       | Single API call + snapshot write |
| `fom insight`   | < 15s       | LLM call (Claude haiku or Ollama) |

## Data Freshness Requirements

| Data | Freshness Target | Mechanism |
|------|-----------------|-----------|
| Price snapshots | Daily (cron) | `fom poll` at 07:00 via crontab |
| Airline fee DB | 3–4× per year | Manual update to `airlines.json` + `make data-check` |
| School holiday calendar | Annual | Manual update to `school_holidays.yaml` for new year |
| LLM insights | 7 days or price change > 10% | Cache TTL in `insights.py` |

## Cron Setup

```bash
# Recommended crontab entry — polls all active trips at 07:00 daily
0 7 * * * /Users/$USER/.local/bin/fom poll >> ~/.fly-o-myte/fom.log 2>&1
```

## Failure Modes

| Failure | Behaviour | Recovery |
|---------|-----------|----------|
| Tequila API unreachable | `poll_trip()` returns `None`, logs warning, continues to next trip | Retry next cron run |
| Tequila rate limit | tenacity retries with exponential backoff (3 attempts, 2–10s wait) | Auto-recovers |
| LLM unavailable | `generate_insight()` returns `None` — recommendation still shown | Set `ANTHROPIC_API_KEY` or start Ollama |
| SQLite write conflict | WAL mode handles concurrent readers; single writer per process | No action needed |
| Missing airline in DB | `get_or_default()` returns conservative estimate with a $40 bag fee | Update `airlines.json` |

## Concurrency

SQLite is opened in WAL mode. `fom poll` (cron) and `fom refresh` (manual) can run simultaneously without write conflicts. DuckDB analytics are written after the SQLite snapshot — a partial analytics write does not corrupt the OLTP data.
