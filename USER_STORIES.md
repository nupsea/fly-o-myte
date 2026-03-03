# fly-o-myte — User Stories
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
| US-042 | SerpAPI international routing | Price Intelligence | 3 |
| US-043 | International booking window intelligence | Recommendations | 3 |
| US-044 | Cross-country price comparison for same destination | Analytics | 3 |
| US-045 | Async / batched polling for scaling | Trip Tracking | 2 |
| US-046 | Dynamic iCal school holiday fetching | Holiday Awareness | 2 |
| US-047 | Recommender robustness to intra-day refreshes | Recommendations | 1 |
| US-048 | Automated Performance Regression Testing | Quality Assurance | 2 |
| US-049 | LLM Evaluation "Judge" Harness | Quality Assurance | 2 |
| US-050 | Automated Dependency Security Scan | Quality Assurance | 1 |
| US-051 | Compare true cost breakdown table | Status & Display | 2 |
| US-052 | Route market context in trip check | Analytics | 2 |
| US-053 | Amadeus international price signal | Price Intelligence | 3 |

---

## Price Source Architecture (context for all stories)

**Primary adapter (manual use)**: SerpAPI Google Flights (`SERPAPI_API_KEY`). Set in `.env` for live `fom poll` runs. Never called in CI or during development — CI always sets `SERPAPI_API_KEY=''`.

**Legacy fallback**: Kiwi.com Tequila (`TEQUILA_API_KEY`). Sign-up broken as of 2026. Fallback path in tracker when no SerpAPI key configured.

**Phase 2 enrichment**: Amadeus Flight Price Analysis (`AMADEUS_CLIENT_ID`/`AMADEUS_CLIENT_SECRET`). Optional. Provides market price level signal (LOW/TYPICAL/HIGH) when SerpAPI returns none.

**Phase 3 international**: SerpAPI with per-country `gl` routing — BNE→SIN uses `gl=sg`, BNE→LHR uses `gl=gb`, BNE→NRT uses `gl=jp`.

**Test doubles**: All integration tests use `_StubTequilaSource` from `conftest.py` — a real Pluggy plugin that never makes HTTP calls. No MagicMock for price source tests.

---


## Epic: Setup & Configuration

### US-001 — First-run setup wizard
**Phase 1**

As a new user, I want a guided setup command so that I can configure my family profile and API keys without manually editing YAML files.

**Acceptance criteria:**
- `fom setup` walks through each field interactively with prompts and defaults
- Prompts for: number of adults, each child's name and date of birth, origin airport (default BNE), state (default QLD), school type (state/independent/catholic), bags per person, max stops, budget threshold, alert email
- Validates IATA airport codes are 3 letters uppercase
- Validates API key fields are non-empty strings if provided
- Writes a valid `~/.fly-o-myte/config.yaml` on completion
- Prints a summary of the profile created
- Re-running `fom setup` shows existing values as defaults (safe to re-run)
- If `~/.fly-o-myte/` does not exist, it is created automatically

---

### US-002 — View and edit family profile
**Phase 1**

As a user, I want to view my current family profile in the terminal so that I can confirm what fly-o-myte knows about my family.

**Acceptance criteria:**
- `fom profile` prints the loaded family profile in a readable table
- Shows: adults, children (names + ages as of today), origin airport, state, school type, bags/person, max stops, blocked airlines, budget threshold
- Child ages are computed dynamically from DOB — not stored as static values
- A child turning 2 between today and the travel date is shown with a note that their infant/child classification may differ at travel time

---

### US-003 — Configure API credentials
**Phase 1**

As a user, I want to store my API keys securely via environment variables so that credentials never appear in YAML files committed to version control.

**Acceptance criteria:**
- `SERPAPI_API_KEY`, `ANTHROPIC_API_KEY`, `SMTP_PASS` are read from env vars or `.env` file only (not from config.yaml)
- `TEQUILA_API_KEY` is the legacy fallback — supported but secondary; `fom setup` does not prompt for it
- `fom setup` prints instructions to add `SERPAPI_API_KEY` to `.env` rather than collecting it interactively
- `fom status` shows a warning if both `SERPAPI_API_KEY` and `TEQUILA_API_KEY` are missing (no price source configured)
- App starts successfully with missing optional keys (`ANTHROPIC_API_KEY`, `SMTP_*`, `AMADEUS_*`) — those features gracefully degrade
- `.env` is in `.gitignore` — never committed to version control

---

### US-004 — Set SMTP alert preferences
**Phase 1**

As a user, I want to configure email alerts so that I am notified when fly-o-myte recommends booking without having to manually run `fom status` every day.

**Acceptance criteria:**
- `alert_email` in config.yaml (or `DEFAULT_ALERT_EMAIL` env var) is the default notification recipient
- Individual trips can override with `--alert-email` on `fom watch`
- `fom setup` asks for SMTP host, port, user (username); password via env var only
- `fom poll` sends email only for `book_now` decisions not yet emailed (`email_sent = 0`)
- Once emailed, `email_sent` is set to 1 — no duplicate alerts for the same recommendation

---

### US-005 — Check embedded data freshness
**Phase 1**

As a user, I want to know when the airline fee database and school holiday data were last updated so that I can judge whether to trust the numbers.

**Acceptance criteria:**
- `fom data-version` prints: data version (e.g. "2026-01"), last updated date, and list of airlines in the database
- Shows which states are supported in the school holiday calendar
- Shows a warning if the data version is older than 180 days
- No network call — reads from embedded JSON/YAML only

---

## Epic: Date Scouting

### US-006 — Scout date windows before committing
**Phase 1**

As a user, I want to explore flight prices across a month before choosing specific dates so that I can pick the cheapest window for my family.

**Acceptance criteria:**
- `fom scout BNE SYD --month jul-2026` searches a sample of dates across July 2026
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
- `fom scout BNE SYD --depart 2026-07-20 --return 2026-07-27 --flex 3` shows the base trip plus all combinations within ±3 days
- True family cost shown for each combination
- School holiday overlap shown per combination
- Best option (lowest cost + no holiday overlap) highlighted
- Maximum ±7 day flexibility supported

---

## Epic: Trip Tracking

### US-008 — Start tracking a specific trip
**Phase 1**

As a user, I want to start tracking a specific route and date pair so that fly-o-myte builds up price history and can give me a reliable recommendation over time.

**Acceptance criteria:**
- `fom watch BNE SYD 2026-07-20 2026-07-27 --label "Winter SYD trip"` creates a trip record
- Trip is stored in SQLite with is_active = 1
- An immediate price fetch is triggered on watch (not deferred to next poll)
- Output confirms the trip ID and label
- Duplicate trips (same origin, destination, depart_date) are detected and user is warned before creating
- `--adults`, `--children`, `--bags`, `--max-stops` flags override the family profile for this trip

---

### US-009 — Pause and resume tracking
**Phase 1**

As a user, I want to pause tracking a trip temporarily so that fly-o-myte doesn't poll it during periods I'm not actively planning.

**Acceptance criteria:**
- `fom pause <id>` sets is_active = 0 for the trip
- `fom resume <id>` sets is_active = 1
- `fom status` does not show paused trips by default
- `fom status --all` shows paused trips with a PAUSED indicator
- Pausing does not delete any price history

---

### US-010 — Remove a tracked trip
**Phase 1**

As a user, I want to permanently delete a trip and all its price history so that my database stays clean.

**Acceptance criteria:**
- `fom remove <id>` asks for confirmation before deleting: "Remove trip 'Winter SYD trip' and all 14 snapshots? [y/N]"
- On confirmation, deletes the trip, all price_snapshots, and all recommendations for that trip_id
- Prints confirmation: "Trip 3 removed."
- `fom remove <id> --yes` skips confirmation (for scripting)
- Non-existent ID prints an error and exits with code 1

---

### US-011 — List all tracked trips
**Phase 1**

As a user, I want to see all trips I am tracking so that I have a quick overview of my tracked routes.

**Acceptance criteria:**
- `fom status --all` lists all trips (active + paused) in a table
- Columns: ID, label, route, dates, status (ACTIVE/PAUSED), snapshots collected, latest recommendation
- Output fits in 100-column terminal width without wrapping

---

### US-012 — Manual price refresh
**Phase 1**

As a user, I want to trigger an immediate price fetch for a specific trip so that I can see the current price without waiting for the next scheduled poll.

**Acceptance criteria:**
- `fom refresh <id>` calls the price source API and saves a new snapshot
- Prints the new true family cost and how it compares to the previous snapshot
- If the API call fails, prints the error and retains the last known snapshot
- Respects tenacity retry (3 attempts with exponential backoff) before failing

---

### US-013 — Scheduled cron poll
**Phase 1**

As a user, I want a command I can run from cron to automatically poll all active trips so that price history is built without daily manual effort.

**Acceptance criteria:**
- `fom poll` fetches prices for all active trips sequentially
- Uses SerpAPI (primary) or Tequila (fallback) based on which key is configured in `.env`
- Prints a one-line summary per trip: "Trip 1: $1,840 (was $1,920) — BOOK NOW"
- On error for one trip, logs the error and continues to the next trip (does not abort)
- Exits with code 0 even if some trips had fetch errors (errors logged only)
- Suitable for: `0 7 * * * fom poll >> ~/.fly-o-myte/fly-o-myte.log 2>&1`
- `fom poll --dry-run` shows which trips would be polled without making API calls

---

## Epic: Status & Display

### US-014 — Morning digest of actionable trips
**Phase 1**

As a user, I want a concise morning status view that only highlights trips that need attention so that I'm not overwhelmed with noise.

**Acceptance criteria:**
- `fom status` shows only trips with `book_now` or `wait` recommendation, or trips that haven't been polled in 48+ hours
- Maximum 5 lines per trip in digest mode
- Each entry shows: label, route, true family cost, recommendation, confidence, days to departure
- `book_now` trips are shown at the top, formatted prominently (bold or coloured)
- If no trips need attention: prints "All trips look fine. Run `fom status --all` to see everything."
- Runs in < 1 second (reads from database, no API calls)

---

### US-015 — Full recommendation for a single trip
**Phase 1**

As a user, I want to see the complete recommendation detail for a trip so that I understand the reasoning behind the book/wait/monitor decision.

**Acceptance criteria:**
- `fom check <id>` displays:
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
- `fom compare <id1> <id2> [id3]` shows a side-by-side comparison table
- Columns per trip: label, true cost, airline, stops, depart time, recommendation, family score
- Best option in each column is highlighted
- Up to 3 trips supported
- Syrupy snapshot test covers this output

---

### US-017 — View price history sparkline
**Phase 1**

As a user, I want to see how the price of a trip has changed over time so that I can understand whether prices are rising or falling.

**Acceptance criteria:**
- `fom history <id>` shows a chronological table of price snapshots
- Includes a Unicode sparkline of price trend (using block characters)
- Shows: date, true family cost, change from previous, price level signal, airline
- Most recent snapshot at the bottom
- `--limit N` to show only the last N snapshots (default: 30)

---

### US-051 — Compare true cost breakdown table
**Phase 2** (maps to S22)

As a user comparing two Jetstar vs Qantas trips, I want the compare command to show the full fee breakdown side by side so that I can see exactly why one trip costs more even with a lower base fare.

**Acceptance criteria:**
- `fom compare <id1> <id2>` shows a Rich table with rows: Base fare/adult, Bags, Seats, Infant fees, TOTAL FAMILY COST
- Each column is headed with trip airline, route, and departure date
- The cheapest TOTAL is highlighted (bold or green)
- `fom compare <id1> <id2> <id3>` supports 3-column comparison
- Syrupy snapshot updated — compare output matches new baseline

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

As a user, I want fly-o-myte to show me when a "cheap" Jetstar fare is actually more expensive for my family than Qantas once all fees are included so that I'm not misled by headline fares.

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
- `fom watch ... --block JQ` adds Jetstar to the blocked list for that trip only
- Blocked airlines are filtered before any cost computation or display
- `fom profile` shows currently blocked airlines

---

### US-036 — Amadeus price level signal integration
**Phase 2** (maps to S21)

As a user, I want fly-o-myte to enrich recommendations with an external market price benchmark so that the book/wait decision has context beyond my own price history alone.

**Acceptance criteria:**
- Amadeus adapter calls the `itinerary-price-metrics` endpoint when `AMADEUS_CLIENT_ID` is configured
- `price_level_signal` in PriceSnapshot is populated from Amadeus when SerpAPI returns no signal and Amadeus is configured
- Amadeus priceMetrics mapped: LOW/MEDIUM_LOW → 'LOW', MEDIUM/MEDIUM_HIGH → 'TYPICAL', HIGH → 'HIGH'
- If Amadeus returns no signal, field is NULL and engine uses TYPICAL as default
- Amadeus credentials not required — feature degrades gracefully without them
- Signal appears in `fom check <id>` output: "Market signal: LOW (below market average)"
- OAuth2 token cached in memory — not re-fetched on every call while valid

---

### US-040 — Multi-currency true cost
**Phase 3** (maps to S25)

As a user tracking international routes, I want true family costs shown in AUD even for international routes so that I can compare domestic and international options directly.

**Acceptance criteria:**
- Exchange rates fetched from Frankfurter API (`https://api.frankfurter.app/latest?from=AUD`)
- Rate is cached in memory for 24 hours — not fetched on every search
- All displayed prices converted to AUD before storage and display
- Source currency shown in parentheses: "$1,840 AUD (SGD 1,560 at 0.84)"
- No network call if the route is already AUD-denominated
- Returns 1.0 (no conversion) gracefully if Frankfurter API is unavailable

---

## Epic: Holiday Awareness

### US-021 — School holiday overlap detection
**Phase 1**

As a user, I want fly-o-myte to automatically flag when my trip dates overlap QLD school holidays so that I understand why prices may be elevated and can plan accordingly.

**Acceptance criteria:**
- Every trip evaluation checks the departure and return dates against `school_holidays.yaml`
- `HolidayContext` is passed to the recommender with `label`, `overlap_days`, `is_fully_within`
- `fom check <id>` shows: "School holiday overlap: Mid-year holidays (8 days). Dates are fixed — holiday pricing rarely improves."
- Trips fully outside school holidays show no holiday flag
- Partial overlap (e.g. 3 days into a 2-week holiday) shows: "Partial overlap: 3 days"

---

### US-022 — Date shift suggestion for holiday pricing
**Phase 1**

As a user, I want fly-o-myte to suggest shifting my trip dates by 1–3 days to avoid holiday pricing so that I can save money with minimal inconvenience.

**Acceptance criteria:**
- When a trip partially overlaps a school holiday, `fom check <id>` shows: "Tip: shifting your return date 2 days earlier avoids the Mid-year holiday window entirely"
- Suggestion only shown when the trip is not fully within the holiday period (`is_fully_within = False`)
- Suggestion shows the adjusted dates and indicates the overlap would be eliminated
- No API call is made to price the suggested dates — this is advisory only

---

### US-027 — Add Australian state holiday calendars
**Phase 2** (maps to S19)

As a user outside Queensland, I want fly-o-myte to recognise school holidays for NSW, VIC, WA, SA, TAS, NT, and ACT so that families across Australia are fully supported.

**Acceptance criteria:**
- `school_holidays.yaml` is extended with all Australian states for 2025–2027
- `state` in FamilyProfile selects which state's calendar to use
- `fom data-version` lists which states have data and which years are covered
- No code change required when adding new state data — calendar loader is data-driven
- `fom check <id>` uses the state from the family profile unless overridden by the trip

---

### US-041 — International school holiday calendars
**Phase 3** (maps to S27)

As a user planning international trips, I want fly-o-myte to apply the destination country's school holiday calendar so that I understand local demand patterns at my destination.

**Acceptance criteria:**
- Initial support: NZ, Singapore (SG), United Kingdom (GB), Japan (JP), Thailand (TH), USA (US)
- Both origin state holidays (school's out → demand spike) and destination holidays (tourism peak) are shown
- Each shown as separate flags: "QLD school holiday" and "Singapore school holiday"
- Data sourced from embedded YAML, updated with package releases
- `fom check <id>` on international trip shows destination holiday flag when applicable

---

## Epic: Recommendations

### US-023 — Booking recommendation with confidence
**Phase 1**

As a user, I want a single clear recommendation — Book Now, Wait, or Monitor — with a confidence score so that I know what to do without analysing the data myself.

**Acceptance criteria:**
- `fom check <id>` always shows one of: BOOK NOW / WAIT / MONITOR
- Confidence shown as percentage (e.g. "76% confident")
- Confidence is scaled by data richness: 1 snapshot = ~25% of full confidence; 10+ snapshots = full confidence
- Rationale paragraph explains the key factors driving the decision (price vs average, trend direction, days to departure, market signal, holiday context)
- With < 3 snapshots: recommendation is always MONITOR with note "Building price history — check back in N more days"

---

### US-024 — Regret risk score
**Phase 1**

As a user, I want to see the expected financial regret (in AUD) for each possible decision so that I can understand the cost of being wrong.

**Acceptance criteria:**
- `fom check <id>` shows: "Regret if you book now: $80. Regret if you wait: $220."
- Regret risk classified as LOW / MEDIUM / HIGH based on relative regret amounts
- LOW = book regret < 50% of wait regret (clear signal to book)
- HIGH = wait regret < 50% of book regret (clear signal to wait)
- MEDIUM = between (no dominant option)
- Shown alongside confidence in the recommendation panel

---

### US-043 — International booking window intelligence
**Phase 3** (maps to S28)

As a user planning international trips, I want fly-o-myte to apply different booking window rules for international routes so that the recommendations reflect how international airfare pricing actually works.

**Acceptance criteria:**
- Routes classified by type: DOMESTIC, TRANS_TASMAN, ASIA_PACIFIC, LONG_HAUL
- Each route type has distinct booking windows (min/optimal/max days to departure)
- DOMESTIC: optimal 60 days. TRANS_TASMAN: 90 days. ASIA_PACIFIC: 120 days. LONG_HAUL: 180 days
- LONG_HAUL at 180 days with LOW signal triggers BOOK_NOW (earlier than domestic)
- Rationale notes: "International route (ASIA_PACIFIC) — optimal booking window is 3–6 months out"
- Route-level booking window data stored in route_stats Parquet for learning over time

---

## Epic: Notifications & Alerts

### US-025 — Book-now email alert
**Phase 1**

As a user, I want to receive an email when fly-o-myte recommends booking so that I don't miss the window even if I haven't checked the app.

**Acceptance criteria:**
- Email is sent automatically at end of `fom poll` when decision = book_now and email_sent = 0
- Email subject: "[fly-o-myte] Book Now — {trip label}"
- Email body includes: route, dates, true family cost, confidence, regret risk, rationale, link to run `fom check <id>`
- Email is not re-sent on subsequent polls for the same recommendation (email_sent = 1)
- A new email is sent if the next recommendation is a new book_now (new recommendation row)
- `fom poll --no-email` suppresses alerts for that run

---

### US-026 — Budget threshold alert
**Phase 1**

As a user, I want to receive an alert when the true family cost drops below my budget threshold so that I know the trip has become affordable.

**Acceptance criteria:**
- `alert_threshold_aud` set per trip via `fom watch ... --alert-threshold 1500`
- When `true_family_cost <= alert_threshold_aud`, email is sent regardless of book_now decision
- Alert subject: "[fly-o-myte] Price Alert — {trip label} now ${cost}"
- Threshold alert is sent once per price-drop event (not every poll)
- `fom check <id>` shows the configured threshold in the trip detail

---

## Epic: Analytics

### US-029 — DuckDB route analytics
**Phase 2** (maps to S16)

As a user, I want to query aggregated route statistics so that I can see seasonal pricing patterns and benchmark current prices against historical norms.

**Acceptance criteria:**
- `fom analytics` shows a summary of route stats across all tracked trips
- Displays per route: price percentiles (p25, median, p75), school holiday premium (holiday avg / non-holiday avg), trend direction
- Backed by Parquet files in `~/.fly-o-myte/analytics/`
- Query runs in < 2 seconds on a typical laptop with 1 year of data

---

### US-030 — Incremental Parquet analytics after each poll
**Phase 2** (maps to S16)

As a user, I want analytics to update automatically after each poll so that route stats are always current without needing a separate command.

**Acceptance criteria:**
- After each successful snapshot save, DuckDB appends the snapshot to the quarterly Parquet partition
- Route stats for the affected route are recomputed in the same DuckDB session (< 100ms)
- Parquet files are partitioned by year-quarter to avoid rewriting the entire dataset
- Analytics update failure does not abort the poll cycle — error is logged, poll continues
- `fom analytics --rebuild` performs a full rebuild from SQLite (recovery command)

---

### US-052 — Route market context in trip check
**Phase 2** (maps to S23)

As a user, I want `fom check` to show how the current price compares to historical market data for that route so that I can tell whether today's price is genuinely cheap or just average.

**Acceptance criteria:**
- `fom check <id>` displays: "Market context: p25=$X / median=$Y / p75=$Z (N samples)" when analytics data available
- Context sourced from route_stats Parquet via DuckDB query
- School holiday premium shown: "Holiday premium: +18% vs non-holiday periods" when data available
- Section omitted silently when no analytics data exists yet (graceful degradation)
- At least 5 snapshots required before context section is shown

---

### US-044 — Cross-country price comparison for same destination
**Phase 3**

As a user planning an international trip, I want to compare prices from different Australian departure cities to the same destination so that I can see if flying from a different city saves money.

**Acceptance criteria:**
- `fom analytics --destination SIN --month aug-2026` shows price comparison by origin city
- Only cities tracked in the database are shown (not all AU cities)
- True family cost used for all comparisons (includes bags, seats)
- Note shown if connecting flight is required from origin to the gateway city

---

## Epic: LLM Insights

### US-031 — LLM contextual insight for a trip
**Phase 2**

As a user, I want fly-o-myte to explain why prices are at their current level so that I understand whether an unusual price is due to an event, seasonal demand, capacity change, or something else.

**Acceptance criteria:**
- `fom check <id>` includes a 3–4 sentence insight below the recommendation
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
- `fom insight <id>` generates a fresh insight regardless of cache
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
- `fom analytics --llm-usage` shows a local summary of LLM calls from the Parquet store

---

## Epic: Reporting

### US-034 — Evidence HTML report
**Phase 2**

As a user, I want to generate an HTML report of my tracked trips and analytics so that I can share a readable summary with my partner or save it for reference.

**Acceptance criteria:**
- `fom report` generates an HTML file at `~/.fly-o-myte/reports/fly-o-myte_report_{date}.html`
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
- `fom ui` launches a Textual TUI application
- Left panel: list of tracked trips (scrollable), colour-coded by recommendation
- Right panel: trip detail view with price history, recommendation, and rationale
- Keyboard navigation: arrow keys to select trip, Enter to expand detail, R to refresh, Q to quit
- Real-time update: pressing R triggers a live price fetch and updates the panel in place
- Works in any 80×24 or larger terminal

---

## Epic: Extensibility

### US-038 — Add new price source plugin
**Phase 2**

As a developer, I want to add a new flight price source by implementing a Pluggy plugin so that fly-o-myte can pull data from multiple APIs without changing core business logic.

**Acceptance criteria:**
- A new price source requires implementing only three methods: `source_name()`, `supports_route()`, `search_flights()`
- New source is registered in `tracker.py` with `pm.register(NewSource())`
- If a source raises `PriceSourceError`, the tracker logs the error and falls back to the next registered source
- Sources are tried in registration order; first successful result is used
- `fom poll --verbose` shows which source provided the data for each trip

---

## Epic: International (Phase 3)

### US-039 — International route tracking
**Phase 3**

As a user planning an overseas family holiday, I want to track international routes with the same true-cost and recommendation features so that I'm not limited to domestic flights.

**Acceptance criteria:**
- `fom watch BNE SIN 2026-09-18 2026-09-28` creates an international trip
- SerpAPI with correct `gl` routing used as the price source for international routes
- True family cost includes international infant fees (`infant_lap_fee_intl` from airline DB)
- Currency conversion to AUD applied automatically
- School holiday check uses both origin state (QLD) and destination country calendar
- `fom check <id>` shows 'International route (ASIA_PACIFIC)' context

---

### US-042 — SerpAPI international routing
**Phase 3** (maps to S26)

As a user, I want SerpAPI to return accurate prices for international routes by using the correct country locale so that I see prices as local travellers would.

**Acceptance criteria:**
- Domestic AU routes: `gl=au` — pricing in AUD
- BNE→SIN: `gl=sg` — Singapore locale pricing
- BNE→LHR: `gl=gb` — UK locale pricing
- BNE→NRT: `gl=jp` — Japan locale pricing
- Top 50 international airport IATA codes mapped to destination country
- International airline names mapped to IATA codes: Singapore Airlines→SQ, Emirates→EK, Cathay Pacific→CX, etc.

---

### US-053 — Amadeus international price signal
**Phase 3** (maps to S29)

As a user tracking international routes, I want Amadeus to provide market price signals for ASIA_PACIFIC and LONG_HAUL routes so that the recommendation engine has reliable market context for routes where my own history is limited.

**Acceptance criteria:**
- For ASIA_PACIFIC and LONG_HAUL routes, Amadeus `itinerary-price-metrics` called when `AMADEUS_CLIENT_ID` set
- For DOMESTIC routes, SerpAPI `price_insights` used first; Amadeus only if signal is None
- Signal appears in `fom check <id>` output alongside route type
- Works seamlessly with SerpAPI offers — signal enrichment is a post-fetch step
- Without Amadeus credentials, signal is None (not an error)

---

## Epic: Architecture & Scaling

### US-045 — Async / batched polling for scaling
**Phase 2**

As a power user tracking dozens or hundreds of trips, I want the scheduled cron poll to run efficiently and without hitting API rate limits so that I don't experience timeouts or multi-hour poll cycles.

**Acceptance criteria:**
- `poll_all_active` uses an asynchronous thread pool or `asyncio` with `httpx.AsyncClient` to fetch prices concurrently.
- Concurrency limit is configurable (e.g. max 5 simultaneous requests).
- Implements a global rate limiter to respect SerpAPI/Amadeus limits.
- The DB writes are still serialized or batched safely into SQLite.

---

### US-046 — Dynamic iCal school holiday fetching
**Phase 2**

As an admin, I want school holidays to be fetched dynamically from public iCal feeds (or an API) so that the embedded `school_holidays.yaml` doesn't become stale and require constant package updates.

**Acceptance criteria:**
- `fom` can fetch and cache standard `.ics` format calendars.
- State calendars are auto-updated once every 30 days.
- User can override the default feed with a custom school calendar URL.

---

## Epic: Quality Assurance & Performance

### US-048 — Automated Performance Regression Testing
**Phase 2**

As a power user, I want the CLI to remain fast even when I have 100+ trips in my database so that my morning status check is always nearly instantaneous.

**Acceptance criteria:**
- A performance test suite (benchmarking) runs as part of the CI pipeline.
- `fom status` with a local database containing 100 trips and 3,000 snapshots must execute in < 500ms.
- Any regression above 1 second causes the benchmark gate to fail.

---

### US-049 — LLM Evaluation "Judge" Harness
**Phase 2**

As an engineer, I want a deterministic way to evaluate the quality of LLM-generated insights so that model changes (e.g., Haiku 3.5 to 4.0) don't silently degrade the product's advice.

**Acceptance criteria:**
- Implementation of Story `S17` in `prd.json`.
- 10 golden fixture JSON files covering: QLD school holiday peak, off-season, price drop >15%, price spike, nonstop preference scenarios.
- An eval test that uses a second LLM call as judge to grade insights: mentions holiday, gives direction, cites source.
- Aggregate pass rate >= 80% required for Phase 2 stability.
- Golden fixture tests marked `@pytest.mark.slow` — skipped in CI unless `ANTHROPIC_API_KEY` set.

---

### US-050 — Automated Dependency Security Scan
**Phase 1**

As a privacy-conscious user, I want the tool I run locally to be free of known vulnerable dependencies so that my system is never compromised by an outdated third-party library.

**Acceptance criteria:**
- `osv-scanner` (or `safety`) is integrated into `make ci`.
- Any known vulnerability with a CVSS score > 7.0 blocks the build.
- The scan checks all transitive dependencies from `uv.lock`.

---

### US-047 — Recommender robustness to intra-day refreshes
**Phase 1**

As a user, I want manual `fom refresh` runs to not mathematically skew the recommendation average so that checking the price multiple times in one day doesn't artificially flatten the trendline.

**Acceptance criteria:**
- The recommendation engine's `rolling_average` and `trend_slope` calculations group snapshots by date.
- Multiple snapshots on the same day are collapsed to just the latest value for that day before performing statistical calculations.
- Data richness confidence scaling still appropriately reflects the number of *distinct days* of history rather than raw clicks.

---
