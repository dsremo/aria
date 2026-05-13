"""ARIA CLI — Quick test runner for validation."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def handle_test(args: argparse.Namespace, output_json: bool = False) -> None:
    cmd = getattr(args, "command", None)
    if cmd == "quick":
        _quick_test()
    elif cmd == "full":
        _full_test()
    elif cmd == "smoke":
        _smoke_test()
    else:
        print("Usage: aria test <quick|full|smoke>")


def _quick_test() -> None:
    """Run a quick validation — 30 seconds max."""
    print("\n  ARIA Quick Validation\n")
    checks = []

    # 1. Import check
    t0 = time.time()
    try:
        from aria.simulation.generation_ship import GenerationShipSimulation
        from aria.simulation.mission_runner import MissionRunner
        from aria.dashboard.health_dashboard import HealthDashboard
        from aria.notifications.alerter import AlertNotifier
        checks.append(("Imports", True, time.time() - t0))
    except Exception as e:
        checks.append(("Imports", False, time.time() - t0))

    # 2. Basilisk
    t0 = time.time()
    try:
        from aria.simulation.basilisk_runner import BasiliskSimRunner, SimConfig, OrbitConfig
        runner = BasiliskSimRunner(SimConfig(output_interval_s=60.0))
        runner.setup()
        frames = runner.step(60.0)
        checks.append(("Basilisk", len(frames) > 0, time.time() - t0))
    except Exception:
        checks.append(("Basilisk", False, time.time() - t0))

    # 3. Interstellar sim
    t0 = time.time()
    try:
        from aria.simulation.interstellar import InterstellarSimulation
        sim = InterstellarSimulation(seed=42)
        events = sim.simulate_year()
        checks.append(("Interstellar", True, time.time() - t0))
    except Exception:
        checks.append(("Interstellar", False, time.time() - t0))

    # 4. Generation ship
    t0 = time.time()
    try:
        from aria.simulation.generation_ship import GenerationShipSimulation, GenerationShipConfig
        sim = GenerationShipSimulation(GenerationShipConfig.breakthrough(seed=42))
        r = sim.run(10)
        checks.append(("GenShip 10yr", r.total_events > 0, time.time() - t0))
    except Exception:
        checks.append(("GenShip 10yr", False, time.time() - t0))

    # 5. Dashboard
    t0 = time.time()
    try:
        from aria.dashboard.health_dashboard import HealthDashboard
        d = HealthDashboard()
        d.update_power(battery_soc=80)
        snap = d.snapshot()
        checks.append(("Dashboard", snap.overall_status == "NOMINAL", time.time() - t0))
    except Exception:
        checks.append(("Dashboard", False, time.time() - t0))

    # Print results
    total_time = sum(c[2] for c in checks)
    passed = sum(1 for c in checks if c[1])
    for name, ok, dt in checks:
        status = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {status} {name:<20} {dt:.3f}s")

    print(f"\n  {passed}/{len(checks)} passed in {total_time:.2f}s")
    if passed < len(checks):
        sys.exit(1)


def _full_test() -> None:
    """Run full pytest suite."""
    print("\n  Running full test suite...\n")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"],
        cwd=str(Path(__file__).resolve().parents[3]),  # aria-core root
    )
    sys.exit(result.returncode)


def _smoke_test() -> None:
    """Run smoke tests only."""
    print("\n  Running smoke tests...\n")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/integration/test_system_smoke.py", "-v", "--tb=short"],
        cwd=str(Path(__file__).resolve().parents[3]),  # aria-core root
    )
    sys.exit(result.returncode)
