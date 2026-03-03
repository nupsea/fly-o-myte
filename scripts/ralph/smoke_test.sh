#!/bin/bash
# smoke_test.sh — end-to-end CLI smoke test for fly-o-myte
#
# Runs real fom commands against a temp SQLite DB (no mocking, no pytest).
# Does NOT call any external APIs — tests all commands that work without one.
#
# Usage:
#   bash scripts/ralph/smoke_test.sh
#
# Exit 0 = all commands behaved correctly.
# Exit 1 = something failed — read the output above.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Temp environment ──────────────────────────────────────────────────────────
SMOKE_DIR="$(mktemp -d)"
trap 'rm -rf "$SMOKE_DIR"' EXIT

export FLY_O_MYTE_DB_PATH="$SMOKE_DIR/smoke.db"
export FLY_O_MYTE_ANALYTICS_DIR="$SMOKE_DIR/analytics"
export FLY_O_MYTE_CONFIG_PATH="$SMOKE_DIR/config.yaml"
export FLY_O_MYTE_LOG_PATH="$SMOKE_DIR/fom.log"
export TEQUILA_API_KEY=""
export ANTHROPIC_API_KEY=""

FOM="uv run --project $REPO_ROOT fom"

PASS=0
FAIL=0

check() {
    local desc="$1"
    local exit_expected="$2"
    local contains="$3"
    shift 3
    local output
    local exit_code=0
    output=$("$@" 2>&1) || exit_code=$?
    if [ "$exit_code" -ne "$exit_expected" ]; then
        echo "FAIL [$desc]: expected exit $exit_expected, got $exit_code"
        echo "  output: $output"
        FAIL=$((FAIL + 1))
        return
    fi
    if [ -n "$contains" ] && ! echo "$output" | grep -qi "$contains"; then
        echo "FAIL [$desc]: expected output to contain '$contains'"
        echo "  output: $output"
        FAIL=$((FAIL + 1))
        return
    fi
    echo "PASS [$desc]"
    PASS=$((PASS + 1))
}

echo ""
echo "=== fly-o-myte smoke test ==="
echo "DB: $FLY_O_MYTE_DB_PATH"
echo ""

# ── Basic commands ────────────────────────────────────────────────────────────
check "version"         0 "fly-o-myte"  $FOM --version
check "help"            0 "Usage"       $FOM --help
check "data-version"    0 "QF"          $FOM data-version
check "profile"         0 "Adults"      $FOM profile

# ── Empty database ────────────────────────────────────────────────────────────
check "status (no trips)"      0 ""     $FOM status
check "status --all (no trips)" 0 ""   $FOM status --all
check "poll --dry-run"          0 "Dry" $FOM poll --dry-run
check "poll (no trips)"         0 ""    $FOM poll

# ── Trip lifecycle ─────────────────────────────────────────────────────────────
check "watch BNE→SYD"  0 "" \
    $FOM watch BNE SYD 2026-07-20 2026-07-27 --label "Smoke test"

check "status (1 trip)" 0 "" $FOM status

check "check trip 1 (no snapshots)" 0 "" $FOM check 1

check "history trip 1 (no snapshots)" 0 "" $FOM history 1

check "compare trip 1" 0 "" $FOM compare 1

# ── Pause / resume ────────────────────────────────────────────────────────────
check "pause trip 1"  0 "" $FOM pause 1
check "resume trip 1" 0 "" $FOM resume 1

# ── Error cases ───────────────────────────────────────────────────────────────
check "check nonexistent trip" 1 "not found" $FOM check 9999
check "remove nonexistent trip" 1 "not found" $FOM remove 9999 --yes

# ── Remove ────────────────────────────────────────────────────────────────────
check "remove trip 1"        0 "" $FOM remove 1 --yes
check "status (empty again)" 0 "" $FOM status

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    echo "SMOKE TEST FAILED"
    exit 1
fi
echo "SMOKE TEST PASSED"
exit 0
