"""Propagator benchmark suite — systematic integrator comparison.

Runs standardized test problems through all available propagators and
reports accuracy, runtime, and energy conservation. Used to:
- Pick the right integrator for each mission phase
- Validate new integrator implementations
- Detect regressions in integrator accuracy

Test problems:
1. **Two-body circular**: 1 AU around Sun, analytical solution available
2. **Two-body eccentric**: e=0.5, tests high-accuracy at periapsis
3. **Lunar flyby**: close encounter with Moon, tests symplectic breakdown
4. **Long-duration cruise**: 100 orbits, energy drift diagnostic

Metrics:
- Position error at end
- Energy conservation error
- Wall-clock runtime
- Number of function evaluations
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


# ══════════════════════════════════════════════════════════════════
#  Standard test problems
# ══════════════════════════════════════════════════════════════════

GM_SUN = 1.32712440018e20
GM_EARTH = 3.986e14
AU_M = 1.496e11


@dataclass
class BenchmarkProblem:
    """A standardized test problem for integrator comparison."""
    name: str
    r0: np.ndarray
    v0: np.ndarray
    mu: float                    # central body GM
    t_end: float
    analytical_r_end: Optional[np.ndarray] = None
    description: str = ""


def problem_circular_1au() -> BenchmarkProblem:
    """Circular orbit at 1 AU around the Sun — 1 year integration."""
    r0 = np.array([AU_M, 0.0, 0.0])
    v0 = np.array([0.0, np.sqrt(GM_SUN / AU_M), 0.0])
    return BenchmarkProblem(
        name="circular_1au",
        r0=r0,
        v0=v0,
        mu=GM_SUN,
        t_end=365.25 * 86400.0,
        analytical_r_end=r0.copy(),  # returns to origin
        description="Circular orbit, 1 year",
    )


def problem_eccentric() -> BenchmarkProblem:
    """Highly eccentric orbit e=0.5 at 7000km perigee."""
    r_peri = 7000e3
    a = 2 * r_peri  # e = 0.5 means aphelion = 3*perigee, a = 2*perigee
    v_peri = np.sqrt(GM_EARTH * (2 / r_peri - 1 / a))
    r0 = np.array([r_peri, 0, 0])
    v0 = np.array([0, v_peri, 0])
    # 10 orbits
    period = 2 * np.pi * np.sqrt(a ** 3 / GM_EARTH)
    return BenchmarkProblem(
        name="eccentric_e0.5",
        r0=r0,
        v0=v0,
        mu=GM_EARTH,
        t_end=10 * period,
        analytical_r_end=r0.copy(),
        description="e=0.5, 10 orbits around Earth",
    )


def problem_long_cruise() -> BenchmarkProblem:
    """100 Earth orbits — tests long-term energy drift."""
    r0 = np.array([AU_M, 0.0, 0.0])
    v0 = np.array([0.0, np.sqrt(GM_SUN / AU_M), 0.0])
    return BenchmarkProblem(
        name="long_cruise_100yr",
        r0=r0,
        v0=v0,
        mu=GM_SUN,
        t_end=100 * 365.25 * 86400,
        analytical_r_end=r0.copy(),
        description="100-year cruise, energy conservation test",
    )


# ══════════════════════════════════════════════════════════════════
#  Benchmark result
# ══════════════════════════════════════════════════════════════════

@dataclass
class IntegratorResult:
    """Outcome of running one integrator on one problem."""
    integrator: str
    problem: str
    success: bool
    r_final: np.ndarray
    v_final: np.ndarray
    position_error_m: float      # vs analytical solution
    energy_drift: float          # |E_final - E_initial| / |E_initial|
    runtime_s: float
    n_steps: int
    note: str = ""


# ══════════════════════════════════════════════════════════════════
#  Benchmark runner
# ══════════════════════════════════════════════════════════════════

def _specific_energy(r: np.ndarray, v: np.ndarray, mu: float) -> float:
    """Specific orbital energy."""
    return 0.5 * np.dot(v, v) - mu / np.linalg.norm(r)


def run_rk4(problem: BenchmarkProblem, dt: Optional[float] = None) -> IntegratorResult:
    """Run the RK4 integrator on the problem."""
    from aria.physics.gravity.nbody import NBodySystem

    sys = NBodySystem()
    sys.add_fixed_perturber(np.zeros(3), problem.mu)

    dt = dt or problem.t_end / 1000

    t0 = time.monotonic()
    r, v, _ = sys.integrate_rk4(problem.r0, problem.v0, 0.0, problem.t_end, dt)
    runtime = time.monotonic() - t0

    E0 = _specific_energy(problem.r0, problem.v0, problem.mu)
    E1 = _specific_energy(r, v, problem.mu)
    drift = abs((E1 - E0) / E0) if abs(E0) > 1e-30 else 0.0

    pos_err = (np.linalg.norm(r - problem.analytical_r_end)
               if problem.analytical_r_end is not None else float("nan"))

    return IntegratorResult(
        integrator="RK4",
        problem=problem.name,
        success=True,
        r_final=r, v_final=v,
        position_error_m=pos_err,
        energy_drift=drift,
        runtime_s=runtime,
        n_steps=int(problem.t_end / dt),
    )


def run_whfast(problem: BenchmarkProblem, dt: Optional[float] = None) -> IntegratorResult:
    """Run the Wisdom-Holman symplectic integrator."""
    from aria.physics.gravity.nbody import NBodySystem

    sys = NBodySystem()
    sys.add_fixed_perturber(np.zeros(3), problem.mu)

    dt = dt or problem.t_end / 1000

    t0 = time.monotonic()
    r, v, _, energy_err = sys.integrate_whfast(
        problem.r0, problem.v0, 0.0, problem.t_end, dt,
        central_gm=problem.mu,
    )
    runtime = time.monotonic() - t0

    pos_err = (np.linalg.norm(r - problem.analytical_r_end)
               if problem.analytical_r_end is not None else float("nan"))

    return IntegratorResult(
        integrator="WHFast",
        problem=problem.name,
        success=True,
        r_final=r, v_final=v,
        position_error_m=pos_err,
        energy_drift=energy_err,
        runtime_s=runtime,
        n_steps=int(problem.t_end / dt),
    )


def run_ias15(problem: BenchmarkProblem) -> IntegratorResult:
    """Run the IAS15 15th-order adaptive integrator."""
    from aria.physics.gravity.ias15 import integrate_ias15

    def accel(t, r):
        return -problem.mu * r / np.linalg.norm(r) ** 3

    t0 = time.monotonic()
    r, v, _, n_steps, e_err = integrate_ias15(
        accel, problem.r0, problem.v0, 0.0, problem.t_end, epsilon=1e-9,
    )
    runtime = time.monotonic() - t0

    pos_err = (np.linalg.norm(r - problem.analytical_r_end)
               if problem.analytical_r_end is not None else float("nan"))

    return IntegratorResult(
        integrator="IAS15",
        problem=problem.name,
        success=True,
        r_final=r, v_final=v,
        position_error_m=pos_err,
        energy_drift=e_err,
        runtime_s=runtime,
        n_steps=n_steps,
    )


def run_benchmark_suite() -> List[IntegratorResult]:
    """Run all standard problems on all integrators.

    Returns a list of (integrator, problem) result records that can be
    tabulated or plotted.
    """
    problems = [
        problem_circular_1au(),
        problem_eccentric(),
        problem_long_cruise(),
    ]

    results: List[IntegratorResult] = []
    for problem in problems:
        # RK4 — skip 100-year run (too slow)
        if problem.name != "long_cruise_100yr":
            try:
                results.append(run_rk4(problem))
            except Exception as e:
                results.append(IntegratorResult(
                    "RK4", problem.name, False,
                    np.zeros(3), np.zeros(3), float("nan"), float("nan"),
                    0.0, 0, str(e),
                ))

        # WHFast
        try:
            results.append(run_whfast(problem))
        except Exception as e:
            results.append(IntegratorResult(
                "WHFast", problem.name, False,
                np.zeros(3), np.zeros(3), float("nan"), float("nan"),
                0.0, 0, str(e),
            ))

        # IAS15 — skip 100-year run (quick test should be fast)
        if problem.name != "long_cruise_100yr":
            try:
                results.append(run_ias15(problem))
            except Exception as e:
                results.append(IntegratorResult(
                    "IAS15", problem.name, False,
                    np.zeros(3), np.zeros(3), float("nan"), float("nan"),
                    0.0, 0, str(e),
                ))

    return results


def format_benchmark_report(results: List[IntegratorResult]) -> str:
    """Produce a human-readable benchmark report."""
    lines = ["Integrator Benchmark Report", "=" * 60]
    lines.append(f"{'Integrator':<10} {'Problem':<20} {'Runtime':<10} "
                 f"{'PosErr(m)':<12} {'EnergyDrift':<12} {'Steps':<8}")
    lines.append("-" * 60)
    for r in results:
        lines.append(
            f"{r.integrator:<10} {r.problem:<20} "
            f"{r.runtime_s:.3f}s   "
            f"{r.position_error_m:.2e}    "
            f"{r.energy_drift:.2e}    "
            f"{r.n_steps:>6}"
        )
    return "\n".join(lines)
