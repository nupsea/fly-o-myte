# Technical Debt Tracker

Last reviewed: 2026-03-04 — S31 complete; TD-003 resolved S16

| ID     | Description | Priority | Owner | Created | Resolved |
|--------|-------------|----------|-------|---------|---------|
| TD-001 | API keys stored as plaintext in config.yaml — migrate to OS keychain (macOS Keychain / Linux Secret Service) | med | ralph | 2026-03-03 | open |
| TD-002 | `datetime.utcnow()` deprecated in Python 3.12+ — `db/sqlite.py` default_factory uses it; replace with `datetime.now(UTC)` throughout | low | ralph | 2026-03-03 | open |
| TD-003 | `analytics.py` is a scaffold — incremental DuckDB/Parquet aggregation not implemented. Phase 2 work. | high | ralph | 2026-03-03 | open (S16) |
| TD-004 | Notifier (`notifier.py`) SMTP send not wired into poll cycle — `poll_trip()` calls `send_alerts=False` default. | med | ralph | 2026-03-03 | resolved S14 |
| TD-005 | Tequila adapter (`price_sources/tequila.py`) lacks unit tests — httpx responses not mocked with pytest-httpx. | med | ralph | 2026-03-03 | resolved S09 |
| TD-006 | CLI `fom check` and `fom status` use `load_family_profile()` which returns defaults if no config file exists — no user-friendly error if `fom setup` has not been run. | low | ralph | 2026-03-03 | open |
| TD-007 | Syrupy snapshot tests for Rich output not yet written — `test_cli.py` only checks exit codes, not rendered output content. | low | ralph | 2026-03-03 | resolved S15 |
| TD-008 | `whenever` library not used — Python stdlib `date` arithmetic used for child age calculation. Review if timezone-aware date handling is needed for AWST routes. | low | ralph | 2026-03-03 | open |
| TD-009 | Scout command (`fom scout`) not tested — `test_cli.py` does not cover the scout command and `scout.py` has no integration tests. | med | ralph | 2026-03-03 | open (S18) |
| TD-010 | `insights.py` LLM golden fixture evaluation not implemented — only schema validation tested, no LLM-as-judge evaluation for insight quality. | med | ralph | 2026-03-03 | open (S17) |
| TD-011 | `analytics.py` reads ALL snapshots (rank 1/2/3) when building Parquet — should filter rank==1 so route analytics tracks the best-offer price trend, not averages across alternatives. | low | ralph | 2026-03-04 | open |
