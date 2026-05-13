#!/usr/bin/env bash
# ARIA CI Smoke Test — runs on every push / PR.
# Exits non-zero on any failure.
set -euo pipefail

echo "=== ARIA CI Smoke Test ==="

# 1. Python unit tests (fast tier, ~2.5 min)
echo "[1/4] Running Python unit tests..."
python -m pytest tests/unit/ -q --tb=line -m "not slow and not noncore" -x
echo "  PASS: Unit tests"

# 2. TypeScript type check
echo "[2/4] TypeScript check..."
cd web
npx tsc --noEmit
echo "  PASS: TypeScript"

# 3. Frontend production build
echo "[3/4] Frontend build..."
npx vite build --mode production
echo "  PASS: Frontend build"
cd ..

# 4. Import smoke — verify all critical modules load
echo "[4/4] Import smoke test..."
python -c "
from aria.digital_twin.parameters import ShipParameters
from aria.digital_twin.mass_budget import compute_mass_budget
from aria.digital_twin.solver import FEASolver
from aria.simulator.tick_engine import get_tick_engine
from aria.simulator.event_bus import get_event_bus
print('  All critical imports OK')
"

echo ""
echo "=== ALL CHECKS PASSED ==="
