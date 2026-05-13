"""Tests for the digital-twin design optimiser.

Validates that ShipOptimizer can be instantiated, run, track history,
and produce results that satisfy structural and thermal constraints.
The full pipeline (mesh + FEA) runs at each iteration so tests that
call optimize() are necessarily integration-level and slower (~2 s per
eval).  Lighter unit tests exercise the helper methods in isolation.
"""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from aria.digital_twin.optimizer import (
    OptimizationResult,
    ShipOptimizer,
    _ALLOWABLE_STRESS_MPA,
    _BOUNDS,
    _MAX_TEMPERATURE_K,
    _MIN_THERMAL_MARGIN_K,
    _SimpleConfig,
)
from aria.digital_twin.parameters import ShipParameters


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_params():
    """Default ship parameters as the optimisation starting point."""
    return ShipParameters()


@pytest.fixture
def optimizer(default_params):
    """ShipOptimizer with low iteration count for testing."""
    return ShipOptimizer(default_params, max_iterations=5)


# ---------------------------------------------------------------------------
# Mock bridge to avoid real Gmsh + FEA in fast tests
# ---------------------------------------------------------------------------

def _make_mock_analyze(stress_mpa=100.0, temp_k=480.0, margin_k=120.0):
    """Return a mock bridge.analyze that returns controlled metrics."""
    from aria.digital_twin.bridge import TwinAnalysisResult

    def mock_analyze(config):
        result = TwinAnalysisResult()
        result.max_von_mises_mpa = stress_mpa
        result.max_temperature_k = temp_k
        result.thermal_margin_k = margin_k
        result.computed_mass_kg = 1e7
        result.warnings = []
        return result

    return mock_analyze


# ---------------------------------------------------------------------------
# 1. Optimizer creation
# ---------------------------------------------------------------------------

class TestOptimizerCreation:

    def test_creates_with_default_params(self, default_params):
        opt = ShipOptimizer(default_params)
        assert opt._max_iter == 50

    def test_creates_with_custom_iterations(self, default_params):
        opt = ShipOptimizer(default_params, max_iterations=10)
        assert opt._max_iter == 10

    def test_base_params_stored(self, optimizer, default_params):
        assert optimizer._base.hull_radius_m == default_params.hull_radius_m

    def test_min_radius_computed(self, optimizer, default_params):
        expected = math.sqrt(default_params.ship_cross_section_m2 / math.pi)
        assert abs(optimizer._min_radius - expected) < 1e-6


# ---------------------------------------------------------------------------
# 2. Design-variable mapping
# ---------------------------------------------------------------------------

class TestVariableMapping:

    def test_params_to_x_round_trip(self, optimizer, default_params):
        """x → params → x should be idempotent."""
        x0 = optimizer._params_to_x(default_params)
        params = optimizer._x_to_params(x0)
        x1 = optimizer._params_to_x(params)
        np.testing.assert_allclose(x0, x1, rtol=1e-6)

    def test_x_vector_length(self, optimizer, default_params):
        x = optimizer._params_to_x(default_params)
        assert len(x) == 4

    def test_thickness_mapping(self, optimizer):
        x = np.array([0.04, 12.0, 500.0, 1.0])
        params = optimizer._x_to_params(x)
        assert params.hull_wall_thickness_m == pytest.approx(0.04)

    def test_radius_mapping(self, optimizer):
        x = np.array([0.05, 15.0, 500.0, 1.0])
        params = optimizer._x_to_params(x)
        assert params.hull_radius_m == pytest.approx(15.0)

    def test_radiator_area_mapping(self, optimizer):
        x = np.array([0.05, 12.0, 600.0, 1.0])
        params = optimizer._x_to_params(x)
        assert params.radiator_panel_area_m2 == pytest.approx(600.0, rel=1e-3)

    def test_shield_scale_mapping(self, optimizer, default_params):
        base_total = default_params.total_shield_thickness_m
        x = np.array([0.05, 12.0, 500.0, 1.5])
        params = optimizer._x_to_params(x)
        assert params.total_shield_thickness_m == pytest.approx(
            base_total * 1.5, rel=1e-4
        )


# ---------------------------------------------------------------------------
# 3. Mass computation
# ---------------------------------------------------------------------------

class TestMassComputation:

    def test_mass_positive(self, optimizer, default_params):
        mass = optimizer._compute_mass(default_params)
        assert mass > 0

    def test_thicker_hull_heavier(self, optimizer):
        # _x_to_params triggers __post_init__ which re-derives
        # hull_length from the structural-mass-fraction formula
        #   L = struct_mass / (rho * 2*pi*R * t)
        # so thicker t -> shorter L and shell mass stays constant
        # (rho * 2*pi*R * t * L = struct_mass by construction).
        # Pin L to the same value after re-derivation so thickness
        # is the only free variable.
        thin  = optimizer._x_to_params(np.array([0.03, 12.0, 500.0, 1.0]))
        thick = optimizer._x_to_params(np.array([0.08, 12.0, 500.0, 1.0]))
        thick.hull_length_m = thin.hull_length_m
        assert optimizer._compute_mass(thick) > optimizer._compute_mass(thin)

    def test_larger_radius_heavier(self, optimizer):
        small = optimizer._x_to_params(np.array([0.05, 9.0, 500.0, 1.0]))
        large = optimizer._x_to_params(np.array([0.05, 18.0, 500.0, 1.0]))
        assert optimizer._compute_mass(large) > optimizer._compute_mass(small)

    def test_more_shielding_heavier(self, optimizer):
        thin_shield = optimizer._x_to_params(np.array([0.05, 12.0, 500.0, 0.6]))
        thick_shield = optimizer._x_to_params(np.array([0.05, 12.0, 500.0, 1.8]))
        assert optimizer._compute_mass(thick_shield) > optimizer._compute_mass(thin_shield)


# ---------------------------------------------------------------------------
# 4. Optimization with mocked bridge (fast)
# ---------------------------------------------------------------------------

class TestOptimizationMocked:

    @patch("aria.digital_twin.optimizer.ShipOptimizer._evaluate")
    def test_optimize_returns_result(self, mock_eval, optimizer):
        """Optimizer returns an OptimizationResult even with mock."""
        mock_eval.side_effect = lambda x: {
            "mass_kg": optimizer._compute_mass(optimizer._x_to_params(x)),
            "stress_mpa": 100.0,
            "temp_k": 480.0,
            "thermal_margin_k": 120.0,
            "params": optimizer._x_to_params(x),
            "warnings": [],
        }
        result = optimizer.optimize()
        assert isinstance(result, OptimizationResult)

    @patch("aria.digital_twin.optimizer.ShipOptimizer._evaluate")
    def test_history_recorded(self, mock_eval, optimizer):
        mock_eval.side_effect = lambda x: {
            "mass_kg": optimizer._compute_mass(optimizer._x_to_params(x)),
            "stress_mpa": 100.0,
            "temp_k": 480.0,
            "thermal_margin_k": 120.0,
            "params": optimizer._x_to_params(x),
            "warnings": [],
        }
        result = optimizer.optimize()
        assert len(result.history) > 0
        assert "iteration" in result.history[0]
        assert "mass_kg" in result.history[0]

    @patch("aria.digital_twin.optimizer.ShipOptimizer._evaluate")
    def test_best_mass_recorded(self, mock_eval, optimizer):
        mock_eval.side_effect = lambda x: {
            "mass_kg": optimizer._compute_mass(optimizer._x_to_params(x)),
            "stress_mpa": 100.0,
            "temp_k": 480.0,
            "thermal_margin_k": 120.0,
            "params": optimizer._x_to_params(x),
            "warnings": [],
        }
        result = optimizer.optimize()
        assert result.best_mass_kg > 0

    @patch("aria.digital_twin.optimizer.ShipOptimizer._evaluate")
    def test_result_has_valid_params(self, mock_eval, optimizer):
        mock_eval.side_effect = lambda x: {
            "mass_kg": optimizer._compute_mass(optimizer._x_to_params(x)),
            "stress_mpa": 100.0,
            "temp_k": 480.0,
            "thermal_margin_k": 120.0,
            "params": optimizer._x_to_params(x),
            "warnings": [],
        }
        result = optimizer.optimize()
        p = result.best_params
        lo, hi = _BOUNDS["hull_wall_thickness_m"]
        # Params should be within or near bounds (COBYLA may slightly overshoot)
        assert p.hull_wall_thickness_m >= lo - 0.01
        assert p.hull_wall_thickness_m <= hi + 0.01

    @patch("aria.digital_twin.optimizer.ShipOptimizer._evaluate")
    def test_constraints_in_result(self, mock_eval, optimizer):
        """When mock returns feasible metrics, result should reflect them."""
        mock_eval.side_effect = lambda x: {
            "mass_kg": optimizer._compute_mass(optimizer._x_to_params(x)),
            "stress_mpa": 150.0,
            "temp_k": 490.0,
            "thermal_margin_k": 110.0,
            "params": optimizer._x_to_params(x),
            "warnings": [],
        }
        result = optimizer.optimize()
        # Best should be feasible
        assert result.final_stress_mpa <= _ALLOWABLE_STRESS_MPA
        assert result.final_temp_k <= _MAX_TEMPERATURE_K


# ---------------------------------------------------------------------------
# 5. Constraint constants
# ---------------------------------------------------------------------------

class TestConstraintConstants:

    def test_allowable_stress(self):
        assert _ALLOWABLE_STRESS_MPA == pytest.approx(220.0)

    def test_max_temperature(self):
        assert _MAX_TEMPERATURE_K == 600.0

    def test_min_thermal_margin(self):
        assert _MIN_THERMAL_MARGIN_K == 50.0


# ---------------------------------------------------------------------------
# 6. SimpleConfig
# ---------------------------------------------------------------------------

class TestSimpleConfig:

    def test_config_attributes(self):
        cfg = _SimpleConfig(ship_mass_kg=1e8, habitat_rpm=1.5)
        assert cfg.ship_mass_kg == 1e8
        assert cfg.habitat_rpm == 1.5

    def test_config_default_rpm(self):
        cfg = _SimpleConfig(ship_mass_kg=5e7)
        assert cfg.habitat_rpm == 1.0


# ---------------------------------------------------------------------------
# 7. OptimizationResult dataclass
# ---------------------------------------------------------------------------

class TestOptimizationResult:

    def test_result_fields(self, default_params):
        res = OptimizationResult(
            best_params=default_params,
            best_mass_kg=1e7,
            iterations=10,
            converged=True,
            final_stress_mpa=180.0,
            final_temp_k=500.0,
        )
        assert res.converged is True
        assert res.iterations == 10
        assert res.history == []

    def test_result_with_history(self, default_params):
        h = [{"iteration": 1, "mass_kg": 1e7}]
        res = OptimizationResult(
            best_params=default_params,
            best_mass_kg=1e7,
            iterations=1,
            converged=False,
            final_stress_mpa=200.0,
            final_temp_k=550.0,
            history=h,
        )
        assert len(res.history) == 1
        assert res.history[0]["iteration"] == 1


# ---------------------------------------------------------------------------
# 8. Real end-to-end optimizer (NO mocks — actual mesh + FEA)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestOptimizerRealE2E:
    """Run the optimizer with actual meshing and FEA. Slow (~3 min per test
    after the 9ec4375 switch from COBYLA to differential_evolution, because
    DE does ~128 FEA evaluations at ~1.5 s each rather than COBYLA's ~3).

    MUST be marked @pytest.mark.slow or it will hang the fast tier.
    """

    def test_real_optimizer_runs(self):
        """Real geometry → mesh → FEA → optimizer loop (3 iterations)."""
        params = ShipParameters()
        optimizer = ShipOptimizer(params, max_iterations=3)
        result = optimizer.optimize()
        assert result.best_mass_kg > 0
        assert result.iterations >= 1
        assert result.final_stress_mpa >= 0
        assert result.final_temp_k >= 0

    def test_real_optimizer_produces_valid_params(self):
        params = ShipParameters()
        optimizer = ShipOptimizer(params, max_iterations=3)
        result = optimizer.optimize()
        bp = result.best_params
        # Params should be within bounds
        assert 0.02 <= bp.hull_wall_thickness_m <= 0.10
        assert 8.0 <= bp.hull_radius_m <= 20.0
