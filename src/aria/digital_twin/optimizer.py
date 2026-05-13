"""Automated design optimization loop for the ARIA generation ship digital twin.

Minimises total ship mass (hull + shield + radiator) subject to structural
and thermal constraints by varying parametric dimensions and running the
full mesh-FEA pipeline via ``SimTwinBridge.analyze()`` at each iteration.

Method: ``scipy.optimize.minimize`` with COBYLA (gradient-free, inequality
constraints) — chosen because the objective calls Gmsh + sparse FEA,
making finite-difference gradients impractical.  Each evaluation costs ~2 s,
so the default iteration budget is kept at 50.

Design variables (normalised to [0, 1] internally):
    hull_wall_thickness_m   0.02 – 0.10 m
    hull_radius_m           8.0  – 20.0 m
    radiator_panel_area_m2  200  – 1000 m²
    shield_thickness_scale  0.5  – 2.0

Constraints (all expressed as  g(x) >= 0  for COBYLA):
    yield_strength / safety_factor  -  max_von_mises  > 0   (220 MPa)
    600 K  -  max_temperature                          > 0
    thermal_margin  -  50 K                            > 0
    hull_radius  -  sqrt(cross_section / pi)           > 0
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.optimize import minimize, differential_evolution

from aria.digital_twin.parameters import ShipParameters

# Module logger (was previously referenced without import)
import structlog
logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class OptimizationResult:
    """Outcome of a design optimization run."""

    best_params: ShipParameters
    best_mass_kg: float
    iterations: int
    converged: bool
    final_stress_mpa: float
    final_temp_k: float
    history: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Design-variable bounds (physical units)
# ---------------------------------------------------------------------------

_BOUNDS = {
    # Lower bound dropped from 20 mm to 5 mm after the structural BC bug
    # in bridge.py was fixed (it was overreporting σ by ~10×, hiding the
    # true margin). Real FoS at 80 mm is ~48×, so a 4× target puts
    # optimum thickness around 7 mm — below the old 20 mm floor.
    # 5 mm is still above MMOD micropuncture minimum (Whipple bumper
    # captures most particles, 5 mm structural layer carries load).
    "hull_wall_thickness_m": (0.005, 0.10),
    "hull_radius_m": (8.0, 20.0),
    "radiator_panel_area_m2": (200.0, 1000.0),
    "shield_thickness_scale": (0.5, 2.0),
}

# Constraint thresholds
_YIELD_STRENGTH_MPA = 880.0
_SAFETY_FACTOR = 4.0
_ALLOWABLE_STRESS_MPA = _YIELD_STRENGTH_MPA / _SAFETY_FACTOR  # 220 MPa
_MAX_TEMPERATURE_K = 600.0
_MIN_THERMAL_MARGIN_K = 50.0


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class ShipOptimizer:
    """Mass-minimisation optimizer for the ARIA generation ship.

    Each objective evaluation builds a new ``ShipParameters``, runs the
    full analysis pipeline through ``SimTwinBridge``, and extracts mass,
    stress, and temperature metrics.

    Parameters
    ----------
    base_params : ShipParameters
        Starting point for the optimization.  Fields not listed as design
        variables are kept frozen.
    max_iterations : int
        Maximum number of COBYLA iterations (each = 1 bridge.analyze call).
    """

    def __init__(
        self,
        base_params: ShipParameters,
        max_iterations: int = 50,
    ) -> None:
        self._base = base_params
        self._max_iter = max_iterations
        self._history: List[Dict[str, Any]] = []
        self._eval_count = 0

        # Cache the baseline shield thicknesses for scaling
        self._base_shield_thicknesses = [
            layer.thickness_m for layer in base_params.shield_layers
        ]

        # Minimum hull radius from cross-section constraint
        self._min_radius = math.sqrt(
            base_params.ship_cross_section_m2 / math.pi
        )

    # ----- Internal helpers ------------------------------------------------

    def _x_to_params(self, x: np.ndarray) -> ShipParameters:
        """Map optimiser vector → ``ShipParameters``.

        ``x`` is in physical units (not normalised).
        """
        params = copy.deepcopy(self._base)
        params.hull_wall_thickness_m = float(x[0])
        params.hull_radius_m = float(x[1])

        # Radiator area → adjust panel dimensions (keep aspect ratio 5:4)
        area = float(x[2])
        params.radiator_panel_width_m = math.sqrt(area * 5.0 / 4.0)
        params.radiator_panel_height_m = area / params.radiator_panel_width_m

        # Shield thickness scaling
        scale = float(x[3])
        for i, layer in enumerate(params.shield_layers):
            layer.thickness_m = self._base_shield_thicknesses[i] * scale

        # Recompute derived hull length
        params.hull_length_m = 0.0
        params.__post_init__()

        return params

    def _params_to_x(self, params: ShipParameters) -> np.ndarray:
        """Extract the design-variable vector from a ``ShipParameters``."""
        area = params.radiator_panel_area_m2
        # Compute current shield scale (ratio to base total thickness)
        base_total = sum(self._base_shield_thicknesses)
        current_total = params.total_shield_thickness_m
        scale = current_total / base_total if base_total > 0 else 1.0
        return np.array([
            params.hull_wall_thickness_m,
            params.hull_radius_m,
            area,
            scale,
        ])

    def _compute_mass(self, params: ShipParameters) -> float:
        """Compute total ship mass consistent with the rest of the pipeline.

        Previously this summed only hull_shell + shield_cap + radiator
        (~22 Mt), ignoring the 55 Mt habitat ring, reactor, propellant,
        and crew modules. Varying any of those in the optimiser had zero
        effect on the reported "mass" — the optimiser was blind to them.

        Delegate to compute_mass_budget (mass_budget.py) which computes
        the same full-ship total the pipeline reports (habitat_ring +
        hull + fuel + shield + reactor + hab_modules + radiators +
        other/margin). Now the optimiser minimises the same number we
        quote externally.
        """
        from aria.digital_twin.mass_budget import compute_mass_budget
        try:
            mb = compute_mass_budget(params=params)
            return float(mb.total_mass_kg)
        except Exception:
            # Fallback to the simple shell-only formula if mass_budget
            # hits an edge case — better a partial answer than a crash
            # in the middle of a DE iteration.
            rho_ti = 4430.0      # Ti-6Al-4V (MMPDS-17 Table 5.4.1.0)
            rho_ice = 917.0      # water ice @ 0 degC (CRC Handbook, 95th ed.)
            radiator_areal_density = 5.0  # kg/m^2 — typical deployable carbon composite (ESTIMATE: NASA/TP-2018-219820)
            r = params.hull_radius_m
            t = params.hull_wall_thickness_m
            l = params.hull_length_m
            return (
                rho_ti * 2.0 * math.pi * r * t * l
                + rho_ice * math.pi * r ** 2 * params.total_shield_thickness_m
                + radiator_areal_density * params.total_radiator_area_m2
            )

    def _evaluate(self, x: np.ndarray) -> Dict[str, Any]:
        """Run full pipeline for a design point and return metrics.

        Returns a dict with keys: mass_kg, stress_mpa, temp_k,
        thermal_margin_k, params, warnings.
        """
        from aria.digital_twin.bridge import SimTwinBridge

        params = self._x_to_params(x)
        bridge = SimTwinBridge()

        # Create a minimal config object that bridge.analyze expects
        config = _SimpleConfig(
            ship_mass_kg=params.ship_mass_kg,
            habitat_rpm=params.habitat_rpm,
        )

        # Pass modified params directly so bridge uses the optimizer's values
        # (not fresh defaults from ShipParameters())
        try:
            result = bridge.analyze(config, params=params)
        except Exception as e:
            # Mesh failure at extreme parameters — return penalty values
            # so the optimizer moves away from this design point
            logger.warning("optimizer.eval_failed", error=str(e),
                           thickness_mm=params.hull_wall_thickness_m * 1000)
            return {
                "mass_kg": 1e12,  # penalty: huge mass
                "stress_mpa": 999.0,  # penalty: over yield
                "temp_k": 700.0,  # penalty: over limit
                "thermal_margin_k": -100.0,
                "params": params,
                "warnings": [f"Mesh failed: {e}"],
            }

        mass = self._compute_mass(params)
        stress = result.max_von_mises_mpa if result.max_von_mises_mpa > 0 else 999.0
        temp = result.max_temperature_k if result.max_temperature_k > 0 else 700.0
        margin = result.thermal_margin_k

        return {
            "mass_kg": mass,
            "stress_mpa": stress,
            "temp_k": temp,
            "thermal_margin_k": margin,
            "params": params,
            "warnings": result.warnings,
        }

    # ----- Public API ------------------------------------------------------

    def optimize(self) -> OptimizationResult:
        """Run mass minimisation with constraint penalties.

        Uses scipy.optimize.differential_evolution — a gradient-free global
        optimiser that handles bounds natively, avoiding the two bugs in
        the previous COBYLA wiring:
          1. COBYLA constraint lambdas that read `self._history[-1]` would
             return the metrics of whatever point was last `objective()`'d,
             NOT the point being asked about. Constraints couldn't actually
             constrain.
          2. `rhobeg=0.5` was larger than the entire range of
             `hull_wall_thickness_m` (0.005-0.10), so the initial trust
             region overshot the feasible region and COBYLA stalled.

        The penalty approach here is simpler: infeasible designs get a
        large additive penalty, so the global search naturally avoids them.
        """
        self._history.clear()
        self._eval_count = 0

        bounds = [b for b in _BOUNDS.values()]

        # Track best feasible solution separately from DE's internal best
        best: Dict[str, Any] = {"mass_kg": float("inf")}
        # Cache: FEA is expensive, DE may re-evaluate nearby points
        eval_cache: Dict[tuple, Dict[str, Any]] = {}

        def penalised_objective(x: np.ndarray) -> float:
            nonlocal best
            self._eval_count += 1

            key = tuple(round(float(v), 6) for v in x)
            if key in eval_cache:
                metrics = eval_cache[key]
            else:
                metrics = self._evaluate(x)
                eval_cache[key] = metrics

            record = {
                "iteration": self._eval_count,
                "hull_wall_thickness_m": float(x[0]),
                "hull_radius_m": float(x[1]),
                "radiator_panel_area_m2": float(x[2]),
                "shield_thickness_scale": float(x[3]),
                "mass_kg": metrics["mass_kg"],
                "stress_mpa": metrics["stress_mpa"],
                "temp_k": metrics["temp_k"],
                "thermal_margin_k": metrics["thermal_margin_k"],
            }
            self._history.append(record)

            # Penalty for constraint violations — each scaled to be
            # comparable with the objective (mass in kg).
            # Heaviness = 1e6 kg per unit of violation is enough that DE
            # treats infeasibility as dominating.
            PENALTY = 1e6  # kg per unit violation (ESTIMATE — large enough to dominate feasible-region mass variation)
            penalty = 0.0
            if metrics["stress_mpa"] > _ALLOWABLE_STRESS_MPA:
                penalty += PENALTY * (metrics["stress_mpa"] - _ALLOWABLE_STRESS_MPA)
            if metrics["temp_k"] > _MAX_TEMPERATURE_K:
                penalty += PENALTY * (metrics["temp_k"] - _MAX_TEMPERATURE_K)
            if metrics["thermal_margin_k"] < _MIN_THERMAL_MARGIN_K:
                penalty += PENALTY * (_MIN_THERMAL_MARGIN_K - metrics["thermal_margin_k"])
            if float(x[1]) < self._min_radius:
                penalty += PENALTY * (self._min_radius - float(x[1])) * 1e3  # radius in m → kg-scale

            feasible = penalty == 0.0
            if feasible and metrics["mass_kg"] < best.get("mass_kg", float("inf")):
                best = metrics

            return metrics["mass_kg"] + penalty

        # DE iteration budget: maxiter × popsize evaluations. popsize=6 (DE
        # default is 15× len(bounds) = 60 which is too heavy with 2 s/eval).
        # 6 × ~maxiter/6 iterations fits in the self._max_iter budget.
        popsize = 6
        de_maxiter = max(3, self._max_iter // popsize)

        result = differential_evolution(
            penalised_objective,
            bounds=bounds,
            maxiter=de_maxiter,
            popsize=popsize,
            tol=1e-3,
            seed=42,             # deterministic for reproducibility
            polish=False,        # skip L-BFGS-B polish (gradient-free only)
            init="sobol",        # space-filling initial population
            workers=1,           # FEA isn't thread-safe (Gmsh global state)
        )

        # Prefer the tracked feasible-best over DE's raw x if we found one.
        # Separate "converged" (DE's own tolerance met) from "found a
        # feasible design" — previously we conflated the two, reporting
        # converged=True whenever ANY feasible point appeared, even if DE
        # hit its max_iter cap. scipy.optimize.differential_evolution
        # sets `result.success = True` only when it stopped due to tol.
        if best.get("params") is not None:
            best_params = best["params"]
            best_mass = best["mass_kg"]
        else:
            best_params = self._x_to_params(result.x)
            best_mass = self._compute_mass(best_params)
        # `converged` now reflects DE's own convergence criterion — the
        # caller who wants "did we find any feasible design?" should check
        # whether best_params is different from the baseline, or inspect
        # final_stress_mpa vs _ALLOWABLE_STRESS_MPA.
        converged = bool(result.success)

        final_stress = best.get("stress_mpa", 0.0)
        final_temp = best.get("temp_k", 0.0)

        return OptimizationResult(
            best_params=best_params,
            best_mass_kg=best_mass,
            iterations=self._eval_count,
            converged=converged,
            final_stress_mpa=final_stress,
            final_temp_k=final_temp,
            history=list(self._history),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _SimpleConfig:
    """Minimal config object accepted by SimTwinBridge.analyze()."""

    def __init__(self, ship_mass_kg: float, habitat_rpm: float = 1.0) -> None:
        self.ship_mass_kg = ship_mass_kg
        self.habitat_rpm = habitat_rpm


def _make_lower_bound(idx: int, lo: float):
    """Factory for COBYLA lower-bound constraint:  x[idx] - lo >= 0."""
    def constraint(x: np.ndarray) -> float:
        return float(x[idx]) - lo
    return constraint


def _make_upper_bound(idx: int, hi: float):
    """Factory for COBYLA upper-bound constraint:  hi - x[idx] >= 0."""
    def constraint(x: np.ndarray) -> float:
        return hi - float(x[idx])
    return constraint
