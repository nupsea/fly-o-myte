# Core Beliefs — Fly-O-Myte Golden Principles

These principles govern all engineering decisions for this project. They apply the Harness Engineering framework to a local-first family travel CLI. Every agent working on this codebase must read and apply them.

---

## 1. CLAUDE.md is the Table of Contents, Not the Encyclopedia

Keep `scripts/ralph/CLAUDE.md` under 100 lines. It is a map, not a manual. All deep context lives in `docs/`. Agents start with the table of contents, follow links to relevant documentation, and are never overwhelmed upfront.

**Rationale**: An agent given a 5,000-line CLAUDE.md wastes context on irrelevant information. A concise map pointing to the right doc gets the agent to the relevant detail faster.

---

## 2. Repository is the System of Record

All architectural decisions, design choices, patterns, and conventions live as versioned markdown in `docs/`. If it is not in the repo, the agent cannot see it — and the knowledge is lost when the conversation ends.

**Rationale**: Agents have no persistent memory across sessions. The repository is the only shared, durable memory.

---

## 3. Progressive Disclosure

Agents start with CLAUDE.md as a map, follow links to relevant `docs/`, and are never overwhelmed upfront. Documentation is layered: table of contents → domain overview → deep detail.

---

## 4. Enforce Invariants Mechanically

Use custom linters with remediation instructions in error messages. Layer violations are caught by `tools/layer_linter.py`. Data integrity is verified by `make data-check`. Never rely on "the agent will remember the rule."

**Rationale**: Rules that are not mechanically enforced will be violated. Mechanical enforcement catches violations before they merge.

---

## 5. 8-Layer Forward-Only Dependency Rule

Imports flow forward only: hookspecs → config/db → data loaders → pure logic → price plugins → orchestration → display → cli. No reverse imports. Enforced by the layer linter.

**Rationale**: A strict layer order prevents circular dependencies, makes the codebase predictable for agents, and keeps each layer independently testable.

---

## 6. One Answer, Not Fifty Options

Every command ends with a clear recommendation: **Book Now / Wait / Monitor**. The CLI does not surface raw data without a conclusion. The `compute()` function always returns a decision.

**Rationale**: The value proposition is removing cognitive load from the user. Showing options without a recommendation is not neutral — it transfers the decision burden back to the user.

---

## 7. Family-First Arithmetic

A family of 2 adults + children on Jetstar at $99/person is not cheaper than Qantas at $149/person once you add bags + seat selection + infant fees. `compute_true_cost()` always calculates the real number. No comparison should use base fares alone.

**Rationale**: The base fare shown on booking sites is systematically lower than what Australian families actually pay. Correcting for this is the core of the value proposition.

---

## 8. Australian-Native, Not Retrofit

Built for Australian school terms, Australian airlines, AUD pricing, AEST/AWST timezones. Not a US tool retrofitted for Australia. School holiday data is embedded in the package — no external API dependency.

---

## 9. Quiet Unless Actionable

`fom status` outputs at most 5 lines. Only highlights trips that need action today. Silence is information — no output means "nothing to do." Never output verbose data when there is no recommendation to act on.

---

## 10. Local-First, Plugin-Extensible

All decision logic runs locally. Price data providers are Pluggy plugins — add new sources (Amadeus, scrapers) without touching core business logic. No telemetry, no cloud sync, no persistent external service required to run the tool.

---

## 11. Parse and Validate at Every Boundary

Never pass raw dicts across module boundaries. `FlightOffer`, `TrueCostBreakdown`, `RecommendationResult`, `TravelInsight` are all typed dataclasses/Pydantic models. External API responses are parsed immediately on ingestion.

---

## 12. Execution Plans are First-Class Artifacts

Active plans live in `docs/exec-plans/active/`, completed plans in `docs/exec-plans/completed/`, known debt in `docs/exec-plans/tech-debt-tracker.md`. All versioned in the repo.

---

## 13. Quality Grading in docs/QUALITY_SCORE.md

Grades each functional domain, tracks gaps over time. Updated by ralph after each phase. Without explicit quality tracking, quality is invisible.

---

## 14. uv Only — Never pip

`uv` is the sole package manager. `uv run` for all commands in CI and Makefile. Never use pip, Poetry, or pipenv. `uv sync --all-extras` before running `make ci`.

---

## 15. Structured Logging Only

No `print()` in package code (outside `cli.py` and `display.py`). Use `logger = logging.getLogger(__name__)`. The root logger is configured in `cli.py` at startup.

---

## 16. Tests Must Be Deterministic

Integration tests use `_StubTequilaSource` (a real Pluggy plugin returning a fixed `FlightOffer`), never `MagicMock`. Cost assertions are exact (`pytest.approx`), not ranges. Flaky tests are bugs.

**Rationale**: A test suite that cannot be trusted provides no safety net. Deterministic stubs make expected values calculable from first principles.

---

## 17. Graceful Degradation for LLM Features

When no LLM provider is configured (no `ANTHROPIC_API_KEY`, no Ollama), `insights.generate_insight()` returns `None` and the CLI suppresses the insight section — no crash, no error message. The recommendation engine works entirely without LLM.

---

## 18. Children's Ages at Travel Date, Not Today

`FamilyProfile.child_ages_at(travel_date)` computes ages at the departure date. A child who turns 2 between search and departure is treated as a toddler (lap infant) now and a seated child then. Never compute ages from `date.today()`.

**Rationale**: Getting this wrong causes Jetstar infant fee calculations to be off by $35/sector/child — a material error on a family trip.
