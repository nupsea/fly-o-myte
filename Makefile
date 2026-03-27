.PHONY: install dev test test-integration test-slow test-e2e ci lint typecheck layer-lint data-check clean

# ─── Install ──────────────────────────────────────────────────────────────────

install:
	uv sync --all-extras
	cd ui && npm install
# ─── Development ──────────────────────────────────────────────────────────────

dev:
	@echo "Starting Fly-O-Myte development services..."
	@$(MAKE) app

app:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════╗"
	@echo "║           ✈  Fly-O-Myte  — Starting Up              ║"
	@echo "╚══════════════════════════════════════════════════════╝"
	@echo ""
	@lsof -ti:8001 | xargs kill -9 2>/dev/null || true
	@echo "[$(shell date '+%H:%M:%S')] 🔧 Backend: http://localhost:8001"
	@echo "[$(shell date '+%H:%M:%S')] 🌐 Frontend: http://localhost:5173"
	@echo ""
	@(trap 'kill 0' SIGINT; \
	  uv run uvicorn fly_o_myte.api:app --host 0.0.0.0 --port 8001 --log-level info --reload & \
	  cd ui && npm run dev & \
	  wait)

# ─── Tests ────────────────────────────────────────────────────────────────────

# Fast: unit + integration tests only (no real API calls)
# This is the default test target — safe to run without API keys.
test:
	uv run pytest

# Integration tests only (real in-memory SQLite, mocked price sources)
test-integration:
	uv run pytest -m integration -v

# Slow: real Tequila API calls — requires TEQUILA_API_KEY in .env
test-slow:
	uv run pytest -m slow -v

# E2E: full CLI invocation with live services
test-e2e:
	uv run pytest -m e2e -v

# ─── Quality ──────────────────────────────────────────────────────────────────

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run pyright .

layer-lint:
	uv run python tools/layer_linter.py

data-check:
	uv run python -c "\
from fly_o_myte.fees import get_airline_db; \
db = get_airline_db(); \
assert 'QF' in db.all_codes() and 'JQ' in db.all_codes(), 'airline DB corrupt'; \
from fly_o_myte.calendar import get_calendar; \
from datetime import date; \
cal = get_calendar(); \
ctx = cal.check_overlap('QLD', date(2026, 7, 1), date(2026, 7, 10)); \
assert ctx is not None, 'QLD holiday check failed'; \
print('Data OK:', db.version, '|', len(db.all_codes()), 'airlines |', len(cal.supported_states()), 'state(s)')"

# ─── CI (all gates — run before pushing) ──────────────────────────────────────

smoke-test:
	bash scripts/ralph/smoke_test.sh

ci: install lint typecheck layer-lint data-check test smoke-test
	@echo "CI passed."

# ─── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned."
