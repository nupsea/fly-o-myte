# Demo Review Gate

Stories with `"type": "demo-review"` in `prd.json` require human approval before ralph
implements the next story in sequence.

## Why Demo Reviews Exist

Some stories produce user-visible output (Rich panels, email templates, Syrupy snapshot
baselines) where human aesthetic judgement matters. Agents implement logic well but can
misjudge layout, wording, or output density. Demo reviews catch this early.

## How It Works

1. Ralph reaches a story with `"type": "demo-review"` and `"passes": false`.
2. Ralph outputs: `BLOCKED: Demo Review Gate [id] requires human approval.` and stops.
3. The human reviews the current CLI/email/display output.
4. If approved, the human creates the approval file (see below).
5. On the next ralph run, the gate is open and ralph sets `passes: true` and continues.

## Creating an Approval File

For story `S15`:

```bash
# 1. Review the output
fom status
fom check 1

# 2. If satisfied, create the approval file
cat > scripts/ralph/demo-reviews/S15-approved.md << 'EOF'
APPROVED

Reviewed: 2026-03-03
Reviewer: sethurama
Notes: Rich panels and Syrupy baselines look correct. Snapshot output matches design doc.
EOF
```

The file must have `APPROVED` on line 1 (exact text, no leading spaces).

## Current Gates

| Story | Title | When it fires | Status |
|-------|-------|---------------|--------|
| DR-A | Smoke test — basic CLI flow | After S10 (tracker complete) | Pending |
| DR-B | Smoke test — poll cycle + recommendation output | After S14 (notifier wired) | Pending |
| S15 | Syrupy display snapshots | After DR-B approved | Pending |

### DR-A — What to Check

Run `bash scripts/ralph/smoke_test.sh` and confirm 0 failures. Then manually:

```bash
fom watch BNE SYD 2026-07-20 2026-07-27 --label "Easter trip"
fom status          # trip listed
fom check 1         # no crash — shows "no price history yet" gracefully
fom data-version    # all 4 airlines with fees
fom remove 1 --yes  # clean removal confirmed
```

### DR-B — What to Check

Run `bash scripts/ralph/smoke_test.sh` (still 0 failures). Then verify the poll cycle
produces visible, correct output:

```bash
fom watch BNE SYD 2026-07-20 2026-07-27 --label "Test"
# Insert a snapshot (with real key, or via the Python helper below)
fom poll   # OR: uv run python scripts/ralph/insert_stub_snapshot.py 1
fom check 1         # recommendation panel must render with a real rationale sentence
fom history 1       # sparkline renders (even with 1 data point)
fom status          # decision badge visible (MONITOR / WAIT / BOOK NOW)
```

The rationale must be a complete English sentence — not `None`, not empty, not a traceback.

## What Happens After Approval

Ralph reads the approval file, sets `passes: true` for the story in `prd.json`, appends
a progress note, and continues to the next story. The approval file is kept permanently
as an audit trail.
