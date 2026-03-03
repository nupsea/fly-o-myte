# Ralph — Fly-O-Myte Agent Instructions

You are an autonomous coding agent. Humans steer; agents execute.
Read this file as a MAP. Follow the links below for deeper context.

## Deep Context (read before starting any story)

- Architecture & layer rule → `docs/ARCHITECTURE.md`
- Golden principles → `docs/design-docs/core-beliefs.md`
- Quality grades per domain → `docs/QUALITY_SCORE.md`
- Known tech debt → `docs/exec-plans/tech-debt-tracker.md`
- Tool references (uv, pluggy, sqlmodel, pydantic-ai) → `docs/references/`

## Your Task Loop

1. Read `scripts/ralph/prd.json` — tech stack, stories, data model
2. Read `scripts/ralph/progress.txt` — check `## Codebase Patterns` section first
3. Check you are on the branch matching `prd.branchName`. Create from main if missing.
4. Pick the **lowest priority number** story where `passes: false`
4a. If the story has `"type": "demo-review"`, check for `scripts/ralph/demo-reviews/[story-id]-approved.md` containing `APPROVED` on line 1. If absent: output `BLOCKED: Demo Review Gate [id] requires human approval` and stop. Do NOT implement code for demo-review stories.
5. Implement that single story — stay focused, minimal changes
6. Run quality checks: `make ci`
6a. If the story touches `tracker.py`, `cli.py`, or `display.py`: also run `bash scripts/ralph/smoke_test.sh`. Paste the summary line ("X passed, Y failed") into the progress note. Fix any failures before committing.
7. If a check fails: read the error — it contains remediation instructions. Fix, do not bypass.
8. Commit: `feat: [Story ID] - [Story Title]`
9. Set `passes: true` for the completed story in `scripts/ralph/prd.json`
10. Append progress to `scripts/ralph/progress.txt`
11. Run `python scripts/ralph/doc_gardener.py` and fix any stale doc warnings.

## Eleven Invariants (enforced mechanically — never violate)

1. `uv` only. Never pip, Poetry, or pipenv. `uv run` for all commands.
2. Python >=3.11. Specified in `pyproject.toml requires-python`.
3. Layer order: hookspecs(0) → config/db(1) → fees/calendar(2) → pure-logic(3) → price-plugins(4) → orchestration(5) → display(6) → cli(7). No reverse imports. Enforced by `tools/layer_linter.py`.
4. Validate at every boundary. `FlightOffer`, `TrueCostBreakdown`, `RecommendationResult` are typed dataclasses. No raw dicts across module boundaries.
5. No `print()` in package code outside `cli.py` and `display.py`. Use `logging.getLogger(__name__)`.
6. No change outside a prd.json story. Every file modification maps to a story ID.
7. Docs are the system of record. Discoveries go in `docs/`. CLAUDE.md stays under 100 lines.
8. Every new module or command must have at least one test.
9. Child ages are computed at the **travel date**, not today. Use `FamilyProfile.child_ages_at(depart_date)`.
10. LLM features degrade gracefully. If no API key, return `None` and suppress the section — never crash.
11. Never patch `fly_o_myte.*` internals in tests. Only mock at process boundaries: HTTP responses via `pytest-httpx`, SMTP via `smtplib` mock. Use real Pluggy plugins (`_StubTequilaSource`) for price source tests. A test that patches internal functions proves nothing about runtime behaviour.

## Progress Report Format

APPEND to `scripts/ralph/progress.txt` (never replace or truncate):
```
## [ISO timestamp] - [Story ID] - [Story Title]
- Implemented: [what was built]
- Files changed: [list]
- Learnings:
  - [pattern/gotcha discovered]
---
```

## Codebase Patterns

Maintained in `## Codebase Patterns` section at TOP of `progress.txt`.

## Stop Condition

All stories `passes: true` → reply: `<promise>COMPLETE</promise>`
Blocked on demo-review gate → reply: `BLOCKED: Demo Review Gate [id] requires human approval. See scripts/ralph/demo-reviews/README.md.` and stop.
Otherwise end normally; the next iteration continues.
