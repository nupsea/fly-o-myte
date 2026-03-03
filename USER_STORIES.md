# Travo — User Stories
## Phase-wise development, all three phases

---

## Summary Table

| ID | Title | Epic | Phase |
|---|---|---|---|
| US-001 | First-run setup wizard | Setup | 1 |
| US-002 | View and edit family profile | Setup | 1 |
| US-003 | Configure API credentials | Setup | 1 |
| US-004 | Set SMTP alert preferences | Setup | 1 |
| US-005 | Check embedded data freshness | Setup | 1 |
| US-006 | Scout date windows before committing | Date Scouting | 1 |
| US-007 | Scout with flexible-day offsets | Date Scouting | 1 |
| US-008 | Start tracking a specific trip | Trip Tracking | 1 |
| US-009 | Pause and resume tracking | Trip Tracking | 1 |
| US-010 | Remove a tracked trip | Trip Tracking | 1 |
| US-011 | List all tracked trips | Trip Tracking | 1 |
| US-012 | Manual price refresh | Trip Tracking | 1 |
| US-013 | Scheduled cron poll | Trip Tracking | 1 |
| US-014 | See morning digest of actionable trips | Status & Display | 1 |
| US-015 | Full recommendation for a single trip | Status & Display | 1 |
| US-016 | Compare up to three trip options side by side | Status & Display | 1 |
| US-017 | View price history sparkline | Status & Display | 1 |
| US-018 | See true family cost breakdown | Price Intelligence | 1 |
| US-019 | Understand Jetstar vs Qantas real cost | Price Intelligence | 1 |
| US-020 | Block unwanted airlines | Price Intelligence | 1 |
| US-021 | School holiday overlap detection | Holiday Awareness | 1 |
| US-022 | Date shift suggestion for holiday pricing | Holiday Awareness | 1 |
| US-023 | Booking recommendation with confidence | Recommendations | 1 |
| US-024 | Regret risk score | Recommendations | 1 |
| US-025 | Book-now email alert | Notifications | 1 |
| US-026 | Budget threshold alert | Notifications | 1 |
| US-027 | Add new Australian state holiday calendars | Holiday Awareness | 2 |
| US-028 | Multi-city origin support | Trip Tracking | 2 |
| US-029 | DuckDB route analytics | Analytics | 2 |
| US-030 | Incremental Parquet analytics after each poll | Analytics | 2 |
| US-031 | LLM contextual insight for a trip | Insights | 2 |
| US-032 | Force refresh LLM insight | Insights | 2 |
| US-033 | Logfire tracing for LLM calls | Insights | 2 |
| US-034 | Evidence HTML report | Reporting | 2 |
| US-035 | Interactive TUI mode | TUI | 2 |
| US-036 | Amadeus price level signal integration | Price Intelligence | 2 |
| US-037 | Multi-state school calendar awareness | Holiday Awareness | 2 |
| US-038 | Add new price source plugin | Extensibility | 2 |
| US-039 | International route tracking | Trip Tracking | 3 |
| US-040 | Multi-currency true cost | Price Intelligence | 3 |
| US-041 | International school holiday calendars | Holiday Awareness | 3 |
| US-042 | Amadeus as international flight source | Price Intelligence | 3 |
| US-043 | International booking window intelligence | Recommendations | 3 |
| US-044 | Cross-country price comparison for same destination | Analytics | 3 |

---

## Epic: Setup & Configuration

### US-001 — First-run setup wizard
**Phase 1**

As a new user, I want a guided setup command so that I can configure my family profile and API keys without manually editing YAML files.

**Acceptance criteria:**
- `travo setup` walks through each field interactively with prompts and defaults
- Prompts for: number of adults, each child's name and date of birth, origin airport (default BNE), state (default QLD), school type (state/independent/catholic), bags per person, max stops, budget threshold, alert email
- Validates IATA airport codes are 3 letters uppercase
- Validates API key fields are non-empty strings if provided
- Writes a valid `~/.travo/config.yaml` on completion
- Prints a summary of the profile created
- Re-running `travo setup` shows existing values as defaults (safe to re-run)
- If `~/.travo/` does not exist, it is created automatically

---

### US-002 — View and edit family profile
**Phase 1**

As a user, I want to view my current family profile in the terminal so that I can confirm what Travo knows about my family.

**Acceptance criteria:**
- `travo profile` prints the loaded family profile in a readable table
- Shows: adults, children (names + ages as of today), origin airport, state, school type, bags/person, max stops, blocked airlines, budget threshold
- Child ages are computed dynamically from DOB — not stored as static values
- A child turning 2 between today and the travel date is shown with a note that their infant/child classification may differ at travel time

---

### US-003 — Configure API credentials
**Phase 1**

As a user, I want to store my API keys securely via environment variables so that credentials never appear in YAML files committed to version control.

**Acceptance criteria:**
- `TEQUILA_API_KEY`, `ANTHROPIC_API_KEY`, `SMTP_PASS` are read from env vars or `.env` file only (not from config.yaml)
- `travo setup` prints instructions to add keys to `.env` rather than collecting them interactively
- `travo status` shows a warning if TEQUILA_API_KEY is missing
- App starts successfully with missing optional keys (ANTHROPIC_API_KEY, SMTP_*) — those features gracefully degrade

---

### US-004 — Set SMTP alert preferences
**Phase 1**

As a user, I want to configure email alerts so that I am notified when Travo recommends booking without having to manually run `travo status` every day.

**Acceptance criteria:**
- `alert_email` in config.yaml (or `DEFAULT_ALERT_EMAIL` env var) is the default notification recipient
- Individual trips can override with `--alert-email` on `travo watch`
- `travo setup` asks for SMTP host, port, user (username); password via env var only
- `travo poll` sends email only for `book_now` decisions not yet emailed (`email_sent = 0`)
- Once emailed, `email_sent` is set to 1 — no duplicate alerts for the same recommendation

---

### US-005 — Check embedded data freshness
**Phase 1**

As a user, I want to know when the airline fee database and school holiday data were last updated so that I can judge whether to trust the numbers.

**Acceptance criteria:**
- `travo data-version` prints: data version (e.g. "2026-01"), last updated date, and list of airlines in the database
- Shows which states are supported in the school holiday calendar
- Shows a warning if the data version is older than 180 days
- No network call — reads from embedded JSON/YAML only

---

## Epic: Date Scouting

### US-006 — Scout date windows before committing
**Phase 1**

As a user, I want to explore flight prices across a month before choosing specific dates so that I can pick the cheapest window for my family.

**Acceptance criteria:**
- `travo scout BNE SYD --month jul-2026` searches a sample of dates across July 2026
- Output shows a table: date range, true family cost, airline, stops, departure time, school holiday flag
- Rows are sorted by true family cost ascending
- School holiday periods are highlighted in the table
- Minimum 8 sample date windows shown (weekly intervals across the month)
- Results are not saved to the database — scout is read-only

---

### US-007 — Scout with flexible-day offsets
**Phase 1**

As a user, I want to see how shifting my trip by 1–3 days affects the price so that I can avoid peak pricing by adjusting dates slightly.

**Acceptance criteria:**
- `travo scout BNE SYD --depart 2026-07-20 --return 2026-07-27 --flex 3` shows the base trip plus all combinations within ±3 days
- True family cost shown for each combination
- School holiday overlap shown per combination
- Best option (lowest cost + no holiday overlap) highlighted
- Maximum ±7 day flexibility supported

---

## Epic: Trip Tracking

### US-008 — Start tracking a specific trip
**Phase 1**

As a user, I want to start tracking a specific route and date pair so that Travo builds up price history and can give me a reliable recommendation over time.

**Acceptance criteria:**
- `travo watch BNE SYD 2026-07-20 2026-07-27 --label "Winter SYD trip"` creates a trip record
- Trip is stored in SQLite with is_active = 1
- An immediate price fetch is triggered on watch (not deferred to next poll)
- Output confirms the trip ID and label
- Duplicate trips (same origin, destination, depart_date) are detected and user is warned before creating
- `--adults`, `--children`, `--bags`, `--max-stops` flags override the family profile for this trip

---

### US-009 — Pause and resume tracking
**Phase 1**

As a user, I want to pause tracking a trip temporarily so that Travo doesn't poll it during periods I'm not actively planning.

**Acceptance criteria:**
- `travo pause <id>` sets is_active = 0 for the trip
- `travo resume <id>` sets is_active = 1
- `travo status` does not show paused trips by default
- `travo status --all` shows paused trips with a PAUSED indicator
- Pausing does not delete any price history

---

### US-010 — Remove a tracked trip
**Phase 1**

As a user, I want to permanently delete a trip and all its price history so that my database stays clean.

**Acceptance criteria:**
- `travo remove <id>` asks for confirmation before deleting: "Remove trip 'Winter SYD trip' and all 14 snapshots? [y/N]"
- On confirmation, deletes the trip, all price_snapshots, and all recommendations for that trip_id
- Prints confirmation: "Trip 3 removed."
- `travo remove <id> --yes` skips confirmation (for scripting)
- Non-existent ID prints an error and exits with code 1

---

### US-011 — List all tracked trips
**Phase 1**

As a user, I want to see all trips I am tracking so that I have a quick overview of my tracked routes.

**Acceptance criteria:**
- `travo status --all` lists all trips (active + paused) in a table
- Columns: ID, label, route, dates, status (ACTIVE/PAUSED), snapshots collected, latest recommendation
- Output fits in 100-column terminal width without wrapping

---

### US-012 — Manual price refresh
**Phase 1**

As a user, I want to trigger an immediate price fetch for a specific trip so that I can see the current price without waiting for the next scheduled poll.

**Acceptance criteria:**
- `travo refresh <id>` calls the price source API and saves a new snapshot
- Prints the new true family cost and how it compares to the previous snapshot
- If the API call fails, prints the error and retains the last known snapshot
- Respects tenacity retry (3 attempts with exponential backoff) before failing

---

### US-013 — Scheduled cron poll
**Phase 1**

As a user, I want a command I can run from cron to automatically poll all active trips so that price history is built without daily manual effort.

**Acceptance criteria:**
- `travo poll` fetches prices for all active trips sequentially
- Prints a one-line summary per trip: "Trip 1: $1,840 (was $1,920) — BOOK NOW"
- On error for one trip, logs the error and continues to the next trip (does not abort)
- Exits with code 0 even if some trips had fetch errors (errors logged only)
- Suitable for: `0 7 * * * travo poll >> ~/.travo/travo.log 2>&1`
- `travo poll --dry-run` shows which trips would be polled without making API calls

---

## Epic: Status & Display

### US-014 — Morning digest of actionable trips
**Phase 1**

As a user, I want a concise morning status view that only highlights trips that need attention so that I'm not overwhelmed with noise.

**Acceptance criteria:**
- `travo status` shows only trips with `book_now` or `wait` recommendation, or trips that haven't been polled in 48+ hours
- Maximum 5 lines per trip in digest mode
- Each entry shows: label, route, true family cost, recommendation, confidence, days to departure
- `book_now` trips are shown at the top, formatted prominently (bold or coloured)
- If no trips need attention: prints "All trips look fine. Run `travo status --all` to see everything."
- Runs in < 1 second (reads from database, no API calls)

---

### US-015 — Full recommendation for a single trip
**Phase 1**

As a user, I want to see the complete recommendation detail for a trip so that I understand the reasoning behind the book/wait/monitor decision.

**Acceptance criteria:**
- `travo check <id>` displays:
  - Trip label, route, departure and return dates
  - True family cost (current) with itemised breakdown (base, bags, seats, infant)
  - Rolling 30-day average, trend (rising/falling AUD/day)
  - Recommendation: BOOK NOW / WAIT / MONITOR
  - Confidence percentage and data richness (e.g. "Based on 12 price points")
  - Regret risk: LOW / MEDIUM / HIGH with expected AUD regret for each option
  - Rationale paragraph
  - School holiday flag if applicable
  - Last updated timestamp
- Output is stable enough for Syrupy snapshot tests

---

### US-016 — Compare trip options side by side
**Phase 1**

As a user, I want to see multiple trip options compared in a table so that I can quickly decide which is best for my family.

**Acceptance criteria:**
- `travo compare <id1> <id2> [id3]` shows a side-by-side comparison table
- Columns per trip: label, true cost, airline, stops, depart time, recommendation, family score
- Best option in each column is highlighted
- Up to 3 trips supported
- Syrupy snapshot test covers this output

---

### US-017 — View price history sparkline
**Phase 1**

As a user, I want to see how the price of a trip has changed over time so that I can understand whether prices are rising or falling.

**Acceptance criteria:**
- `travo history <id>` shows a chronological table of price snapshots
- Includes a Unicode sparkline of price trend (using block characters)
- Shows: date, true family cost, change from previous, price level signal, airline
- Most recent snapshot at the bottom
- `--limit N` to show only the last N snapshots (default: 30)

---

## Epic: Price Intelligence

### US-018 — True family cost breakdown
**Phase 1**

As a user, I want to see an itemised breakdown of what my family will actually pay so that I am not surprised by fees at checkout.

**Acceptance criteria:**
- Every price display includes: base fare (adults), base fare (children), bags, seat selection, infant fees
- Totals are in AUD throughout
- A note is shown when using conservative default fees for unknown airlines
- For Jetstar, infant fees are shown as "per sector × number of sectors" (e.g. "$35 × 2 = $70")

---

### US-019 — Understand Jetstar vs Qantas real cost
**Phase 1**

As a user, I want Travo to show me when a "cheap" Jetstar fare is actually more expensive for my family than Qantas once all fees are included so that I'm not misled by headline fares.

**Acceptance criteria:**
- When the cheapest offer is not from the highest-family-score airline, a note is shown: "Qantas costs $86 more per booking but includes bags + free seat selection"
- True family cost is always the primary sort key, not base fare
- Family score is displayed alongside true cost so quality is visible

---

### US-020 — Block unwanted airlines
**Phase 1**

As a user, I want to exclude specific airlines from consideration so that I never see offers from carriers I refuse to fly.

**Acceptance criteria:**
- `blocked_airlines` in config.yaml lists IATA codes to exclude (e.g. `["TL"]`)
- `travo watch ... --block JQ` adds Jetstar to the blocked list for that trip only
- Blocked airlines are filtered before any cost computation or display
- `travo profile` shows currently blocked airlines

---

### US-036 — Amadeus price level signal integration
**Phase 2**

As a user, I want Travo to use Amadeus Flight Price Analysis signals (LOW / TYPICAL / HIGH) so that the recommendation engine has an external market benchmark, not just its own price history.

**Acceptance criteria:**
- Amadeus adapter is registered as a secondary plugin (after Tequila)
- `price_level_signal` field in PriceSnapshot is populated from Amadeus when available
- If Amadeus returns no signal, field is NULL and engine uses TYPICAL as default
- Amadeus credentials not required — feature degrades gracefully without them
- Signal appears in `travo check <id>` output: "Market signal: LOW (below market average)"

---

### US-040 — Multi-currency true cost
**Phase 3**

As a user, I want true family costs shown in AUD even for international routes so that I can compare domestic and international options directly.

**Acceptance criteria:**
- Exchange rates fetched from Frankfurter API (`https://api.frankfurter.app/latest?from=AUD`)
- Rate is cached for 24 hours — not fetched on every search
- All displayed prices converted to AUD before storage and display
- Source currency shown in parentheses: "$1,840 AUD (¥189,400 JPY at 0.0097)"
- No network call if the route is already AUD-denominated

---

## Epic: Holiday Awareness

### US-021 — School holiday overlap detection
**Phase 1**

As a user, I want Travo to automatically flag when my trip dates overlap QLD school holidays so that I understand why prices may be elevated and can plan accordingly.

**Acceptance criteria:**
- Every trip evaluation checks the departure and return dates against `school_holidays.yaml`
- `HolidayContext` is passed to the recommender with `label`, `overlap_days`, `is_fully_within`
- `travo check <id>` shows: "School holiday overlap: Mid-year holidays (8 days). Dates are fixed — holiday pricing rarely improves."
- Trips fully outside school holidays show no holiday flag
- Partial overlap (e.g. 3 days into a 2-week holiday) shows: "Partial overlap: 3 days"

---

### US-022 — Date shift suggestion for holiday pricing
**Phase 1**

As a user, I want Travo to suggest shifting my trip dates by 1–3 days to avoid holiday pricing so that I can save money with minimal inconvenience.

**Acceptance criteria:**
- When a trip partially overlaps a school holiday, `travo check <id>` shows: "Tip: shifting your return date 2 days earlier avoids the Mid-year holiday window entirely"
- Suggestion only shown when the trip is not fully within the holiday period (`is_fully_within = False`)
- Suggestion shows the adjusted dates and indicates the overlap would be eliminated
- No API call is made to price the suggested dates — this is advisory only

---

### US-027 — Add Australian state holiday calendars
**Phase 2**

As a user, I want Travo to recognise school holidays for NSW, VIC, WA, SA, TAS, NT, and ACT so that families outside Queensland are fully supported.

**Acceptance criteria:**
- `school_holidays.yaml` is extended with all Australian states for 2025–2027
- `state` in FamilyProfile selects which state's calendar to use
- `travo data-version` lists which states have data and which years are covered
- No code change required when adding new state data — calendar loader is data-driven
- `travo check <id>` uses the state from the family profile unless overridden by the trip

---

### US-041 — International school holiday calendars
**Phase 3**

As a user planning international trips, I want Travo to apply the destination country's school holiday calendar so that I understand local demand patterns at my destination.

**Acceptance criteria:**
- Initial support: NZ, Singapore, UK, Japan, Thailand, USA
- Both origin state holidays (school's out → demand spike) and destination holidays (tourism peak) are shown
- Each shown as separate flags: "QLD school holiday" and "Singapore school holiday"
- Data sourced from embedded YAML, updated with package releases

---

## Epic: Recommendations

### US-023 — Booking recommendation with confidence
**Phase 1**

As a user, I want a single clear recommendation — Book Now, Wait, or Monitor — with a confidence score so that I know what to do without analysing the data myself.

**Acceptance criteria:**
- `travo check <id>` always shows one of: BOOK NOW / WAIT / MONITOR
- Confidence shown as percentage (e.g. "76% confident")
- Confidence is scaled by data richness: 1 snapshot = ~25% of full confidence; 10+ snapshots = full confidence
- Rationale paragraph explains the key factors driving the decision (price vs average, trend direction, days to departure, market signal, holiday context)
- With < 3 snapshots: recommendation is always MONITOR with note "Building price history — check back in N more days"

---

### US-024 — Regret risk score
**Phase 1**

As a user, I want to see the expected financial regret (in AUD) for each possible decision so that I can understand the cost of being wrong.

**Acceptance criteria:**
- `travo check <id>` shows: "Regret if you book now: $80. Regret if you wait: $220."
- Regret risk classified as LOW / MEDIUM / HIGH based on relative regret amounts
- LOW = book regret < 50% of wait regret (clear signal to book)
- HIGH = wait regret < 50% of book regret (clear signal to wait)
- MEDIUM = between (no dominant option)
- Shown alongside confidence in the recommendation panel

---

### US-043 — International booking window intelligence
**Phase 3**

As a user planning international trips, I want Travo to apply different booking window rules for international routes so that the recommendations reflect how international airfare pricing actually works.

**Acceptance criteria:**
- International routes (origin/destination in different countries) use separate decision rules
- Book-early pressure applied sooner: international book_now triggered at 120 days vs 45 days domestic
- Rationale notes: "International route — optimal booking window is 3–6 months out"
- Route-level booking window data stored in route_stats Parquet for learning over time

---

## Epic: Notifications & Alerts

### US-025 — Book-now email alert
**Phase 1**

As a user, I want to receive an email when Travo recommends booking so that I don't miss the window even if I haven't checked the app.

**Acceptance criteria:**
- Email is sent automatically at end of `travo poll` when decision = book_now and email_sent = 0
- Email subject: "[Travo] Book Now — {trip label}"
- Email body includes: route, dates, true family cost, confidence, regret risk, rationale
- Email is not re-sent on subsequent polls for the same recommendation (email_sent = 1)
- A new email is sent if the next recommendation is a new book_now (new recommendation row)
- `travo poll --no-email` suppresses alerts for that run

---

### US-026 — Budget threshold alert
**Phase 1**

As a user, I want to receive an alert when the true family cost drops below my budget threshold so that I know the trip has become affordable.

**Acceptance criteria:**
- `alert_threshold_aud` set per trip via `travo watch ... --alert-threshold 1500`
- When `true_family_cost <= alert_threshold_aud`, email is sent regardless of book_now decision
- Alert subject: "[Travo] Price Alert — {trip label} now ${cost}"
- Threshold alert is sent once per price-drop event (not every poll)
- `travo check <id>` shows the configured threshold in the trip detail

---

## Epic: Analytics

### US-029 — DuckDB route analytics
**Phase 2**

As a user, I want to query aggregated route statistics so that I can see seasonal pricing patterns and benchmark current prices against historical norms.

**Acceptance criteria:**
- `travo analytics` shows a summary of route stats across all tracked trips
- Displays per route: price percentiles (p25, median, p75), school holiday premium (holiday avg / non-holiday avg), trend direction
- Backed by Parquet files in `~/.travo/analytics/`
- Query runs in < 2 seconds on a typical laptop with 1 year of data

---

### US-030 — Incremental Parquet analytics after each poll
**Phase 2**

As a user, I want analytics to update automatically after each poll so that route stats are always current without needing a separate command.

**Acceptance criteria:**
- After each successful snapshot save, DuckDB appends the snapshot to the quarterly Parquet partition
- Route stats for the affected route are recomputed in the same DuckDB session (< 100ms)
- Parquet files are partitioned by year-quarter to avoid rewriting the entire dataset
- Analytics update failure does not abort the poll cycle — error is logged, poll continues
- `travo analytics --rebuild` performs a full rebuild from SQLite (recovery command)

---

### US-044 — Cross-country price comparison for same destination
**Phase 3**

As a user planning an international trip, I want to compare prices from different Australian departure cities to the same destination so that I can see if flying from a different city saves money.

**Acceptance criteria:**
- `travo analytics --destination NRT --month aug-2026` shows price comparison by origin city
- Only cities tracked in the database are shown (not all AU cities)
- True family cost used for all comparisons (includes bags, seats)
- Note shown if connecting flight is required from origin to the gateway city

---

## Epic: LLM Insights

### US-031 — LLM contextual insight for a trip
**Phase 2**

As a user, I want Travo to explain why prices are at their current level so that I understand whether an unusual price is due to an event, seasonal demand, capacity change, or something else.

**Acceptance criteria:**
- `travo check <id>` includes a 3–4 sentence insight below the recommendation
- Insight explains: price relative to historical norm, known events affecting demand, seasonal pattern
- Insight is generated by Claude haiku (or local Ollama if Anthropic key not set)
- No personal data (names, DOBs, email) is sent to the LLM — only route, dates, price data
- Insight is cached for 7 days; re-used if price change < 10% since last generation
- If LLM is unavailable, insight section is omitted silently — recommendation still works

---

### US-032 — Force refresh LLM insight
**Phase 2**

As a user, I want to force a fresh LLM insight when I think something has changed so that I get updated context without waiting for the cache to expire.

**Acceptance criteria:**
- `travo insight <id>` generates a fresh insight regardless of cache
- Prints: model used, tokens consumed, generation time
- Writes new insight to `market_context` Parquet with `generated_by` and `model_used` fields
- `--provider claude` or `--provider ollama` overrides the default provider for one call

---

### US-033 — Logfire tracing for LLM calls
**Phase 2**

As a user who cares about LLM cost and quality, I want all LLM calls traced so that I can monitor usage, cost, and quality drift over time.

**Acceptance criteria:**
- Every Pydantic AI call emits a Logfire span with: model, input tokens, output tokens, latency, cost estimate, route context (no personal data)
- Tracing is enabled only when `LOGFIRE_TOKEN` is set
- Without the token, app works normally with no tracing (no error)
- `travo analytics --llm-usage` shows a local summary of LLM calls from the Parquet store

---

## Epic: Reporting

### US-034 — Evidence HTML report
**Phase 2**

As a user, I want to generate an HTML report of my tracked trips and analytics so that I can share a readable summary with my partner or save it for reference.

**Acceptance criteria:**
- `travo report` generates an HTML file at `~/.travo/reports/travo_report_{date}.html`
- Includes: all active trips with latest recommendation, price history charts, route comparison table, school holiday calendar overlay
- Opens in the default browser automatically after generation
- Built with Evidence (SQL-based reporting framework querying DuckDB/Parquet)
- Generation takes < 10 seconds on typical data volume

---

## Epic: TUI

### US-035 — Interactive TUI mode
**Phase 2**

As a user, I want an interactive terminal dashboard so that I can navigate all my trips without running individual commands.

**Acceptance criteria:**
- `travo ui` launches a Textual TUI application
- Left panel: list of tracked trips (scrollable), colour-coded by recommendation
- Right panel: trip detail view with price history, recommendation, and rationale
- Keyboard navigation: arrow keys to select trip, Enter to expand detail, R to refresh, Q to quit
- Real-time update: pressing R triggers a live price fetch and updates the panel in place
- Works in any 80×24 or larger terminal

---

## Epic: Extensibility

### US-038 — Add new price source plugin
**Phase 2**

As a developer, I want to add a new flight price source by implementing a Pluggy plugin so that Travo can pull data from multiple APIs without changing core business logic.

**Acceptance criteria:**
- A new price source requires implementing only three methods: `source_name()`, `supports_route()`, `search_flights()`
- New source is registered in `tracker.py` with `pm.register(NewSource())`
- If a source raises `PriceSourceError`, the tracker logs the error and falls back to the next registered source
- Sources are tried in registration order; first successful result is used
- `travo poll --verbose` shows which source provided the data for each trip

---

## Epic: International (Phase 3)

### US-039 — International route tracking
**Phase 3**

As a user planning an overseas family holiday, I want to track international routes with the same true-cost and recommendation features so that I'm not limited to domestic flights.

**Acceptance criteria:**
- `travo watch BNE NRT 2026-09-20 2026-10-03` creates an international trip
- Amadeus is used as the primary source for international routes
- True family cost includes international infant fees (`infant_lap_fee_intl` from airline DB)
- Currency conversion to AUD applied automatically
- School holiday check uses both origin state (QLD) and destination country calendar

---

### US-042 — Amadeus as international flight source
**Phase 3**

As a user, I want Amadeus to supply both flight prices and historical price level signals for international routes so that recommendations have market context beyond my own price history.

**Acceptance criteria:**
- `AmadeusPriceSource` plugin implements all three hookspec methods
- `supports_route()` returns True only for international routes (origin country != destination country)
- `price_level_signal` is populated from Amadeus `Flight Price Analysis` endpoint (LOW/TYPICAL/HIGH)
- Amadeus credentials stored in env vars (AMADEUS_CLIENT_ID, AMADEUS_CLIENT_SECRET)
- Without Amadeus credentials, international routes still work — price_level_signal is NULL

---
