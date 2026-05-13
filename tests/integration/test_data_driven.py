"""Integration tests for data-driven degradation from NASA C-MAPSS + algae data.

Tests cover:
  - Turbofan data parsing (100 engines, 20,631 rows)
  - Degradation model construction (mean curve, parametric fit)
  - Health prediction (lookup table + parametric)
  - RUL prediction (inverse mapping)
  - Equipment type scaling via real_degradation()
  - Trajectory sampling with noise
  - Algae growth model parsing
  - Algae production rate queries
  - Edge cases and boundary conditions

These tests require the bundled NASA prognostics extracts at
/tmp/turbofan_extract/ and /tmp/algae_extract/ (12 GB total — see
docs/SESSION_SUMMARY.md). When the data is missing — common on a fresh
checkout / CI without the dataset — every fixture in the module errors
identically, which used to translate into 35 cascading "errors" in the
integration sweep. We now skip the whole module instead, so the sweep
reports a single clean SKIP rather than a wall of false-positive errors.
"""

import math
from pathlib import Path

import numpy as np
import pytest

from aria.simulation.data_driven_degradation import (
    AlgaeGrowthModel,
    DataDrivenDegradation,
    EQUIPMENT_DESIGN_LIVES,
    EngineTrajectory,
    TurbofanDegradationModel,
    algae_production_rate,
    build_degradation_model,
    parse_algae_data,
    parse_turbofan_data,
    real_degradation,
    _CURVE_RESOLUTION,
)


_TURBOFAN_PATH = Path("/tmp/turbofan_extract/train_FD001.txt")
_ALGAE_PATH = Path("/tmp/algae_extract/algae.mat")

pytestmark = pytest.mark.skipif(
    not _TURBOFAN_PATH.exists() or not _ALGAE_PATH.exists(),
    reason=(
        "NASA C-MAPSS / algae extracts not present at /tmp/turbofan_extract "
        "and /tmp/algae_extract — run the prognostics fetch script before "
        "exercising this module."
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def turbofan_trajectories():
    """Parse NASA C-MAPSS data once for all tests."""
    return parse_turbofan_data()


@pytest.fixture(scope="module")
def degradation_model(turbofan_trajectories):
    """Build degradation model once for all tests."""
    return build_degradation_model(turbofan_trajectories)


@pytest.fixture(scope="module")
def dd(degradation_model):
    """DataDrivenDegradation instance backed by real data."""
    return DataDrivenDegradation(degradation_model)


@pytest.fixture(scope="module")
def algae_model():
    """Parse NASA algae data once for all tests."""
    return parse_algae_data()


# ──────────────────────────────────────────────────────────────────────
# 1. Turbofan Data Parsing
# ──────────────────────────────────────────────────────────────────────


class TestTurbofanParsing:
    def test_parses_100_engines(self, turbofan_trajectories):
        assert len(turbofan_trajectories) == 100

    def test_engine_ids_sequential(self, turbofan_trajectories):
        ids = [t.engine_id for t in turbofan_trajectories]
        assert ids == list(range(1, 101))

    def test_trajectories_have_valid_health(self, turbofan_trajectories):
        for traj in turbofan_trajectories:
            assert traj.health_curve.min() >= 0.0
            assert traj.health_curve.max() <= 1.0

    def test_cycle_fractions_span_0_to_1(self, turbofan_trajectories):
        for traj in turbofan_trajectories:
            assert abs(traj.cycle_fraction[0]) < 1e-6
            assert abs(traj.cycle_fraction[-1] - 1.0) < 1e-6

    def test_lifetimes_reasonable(self, turbofan_trajectories):
        lifetimes = [t.max_cycle for t in turbofan_trajectories]
        # FD001 engines range roughly 128-362 cycles
        assert min(lifetimes) >= 100
        assert max(lifetimes) <= 400
        assert 150 < np.mean(lifetimes) < 250

    def test_missing_data_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_turbofan_data("/nonexistent/path")


# ──────────────────────────────────────────────────────────────────────
# 2. Degradation Model Construction
# ──────────────────────────────────────────────────────────────────────


class TestDegradationModel:
    def test_model_has_100_engines(self, degradation_model):
        assert degradation_model.n_engines == 100

    def test_alpha_in_reasonable_range(self, degradation_model):
        # Turbofan degradation is typically super-linear: 1 < alpha < 3
        assert 0.5 < degradation_model.alpha < 4.0

    def test_mean_curve_starts_at_1(self, degradation_model):
        assert abs(degradation_model.mean_curve[0] - 1.0) < 0.02

    def test_mean_curve_ends_low(self, degradation_model):
        # At end of life, health should be significantly degraded
        assert degradation_model.mean_curve[-1] < 0.3

    def test_mean_curve_monotone_nonincreasing(self, degradation_model):
        curve = degradation_model.mean_curve
        diffs = np.diff(curve)
        assert np.all(diffs <= 1e-10), "Mean curve should be non-increasing"

    def test_curve_resolution(self, degradation_model):
        assert len(degradation_model.mean_curve) == _CURVE_RESOLUTION
        assert len(degradation_model.curve_fractions) == _CURVE_RESOLUTION

    def test_lifetime_statistics(self, degradation_model):
        assert degradation_model.mean_lifetime_cycles > 100
        assert degradation_model.std_lifetime_cycles > 0


# ──────────────────────────────────────────────────────────────────────
# 3. Health Prediction
# ──────────────────────────────────────────────────────────────────────


class TestHealthPrediction:
    def test_new_equipment_is_healthy(self, dd):
        health = dd.predict_health(0.0, design_life_years=50.0)
        assert health >= 0.95

    def test_old_equipment_is_degraded(self, dd):
        health = dd.predict_health(50.0, design_life_years=50.0)
        assert health < 0.3

    def test_midlife_is_intermediate(self, dd):
        health = dd.predict_health(25.0, design_life_years=50.0)
        assert 0.3 < health < 0.95

    def test_health_decreases_with_age(self, dd):
        ages = [0, 10, 20, 30, 40, 50]
        healths = [dd.predict_health(a, 50.0) for a in ages]
        for i in range(1, len(healths)):
            assert healths[i] <= healths[i - 1] + 0.02  # Small tolerance for noise

    def test_parametric_vs_lookup_broadly_agree(self, dd):
        for age in [10, 25, 40]:
            h_lookup = dd.predict_health(age, 50.0, use_parametric=False)
            h_param = dd.predict_health(age, 50.0, use_parametric=True)
            assert abs(h_lookup - h_param) < 0.30, (
                f"Parametric and lookup disagree too much at age={age}: "
                f"lookup={h_lookup:.3f}, param={h_param:.3f}"
            )

    def test_health_clamped_to_unit_interval(self, dd):
        # Age beyond design life
        h = dd.predict_health(100.0, 50.0)
        assert 0.0 <= h <= 1.0

        # Negative age
        h = dd.predict_health(-5.0, 50.0)
        assert 0.0 <= h <= 1.0

    def test_noise_adds_variation(self, dd):
        rng = np.random.default_rng(42)
        samples = [
            dd.predict_health(25.0, 50.0, noise_std=0.05, rng=rng)
            for _ in range(50)
        ]
        # With noise, samples should show variation
        assert np.std(samples) > 0.01


# ──────────────────────────────────────────────────────────────────────
# 4. RUL Prediction
# ──────────────────────────────────────────────────────────────────────


class TestRULPrediction:
    def test_perfect_health_full_rul(self, dd):
        rul = dd.predict_rul(1.0, design_life_years=50.0)
        assert rul >= 45.0  # Close to full life

    def test_zero_health_zero_rul(self, dd):
        rul = dd.predict_rul(0.0, design_life_years=50.0)
        assert rul <= 2.0  # Near end

    def test_rul_decreases_with_lower_health(self, dd):
        healths = [1.0, 0.8, 0.5, 0.2, 0.0]
        ruls = [dd.predict_rul(h, 50.0) for h in healths]
        for i in range(1, len(ruls)):
            assert ruls[i] <= ruls[i - 1] + 0.5

    def test_rul_scales_with_design_life(self, dd):
        rul_50 = dd.predict_rul(0.5, design_life_years=50.0)
        rul_100 = dd.predict_rul(0.5, design_life_years=100.0)
        # RUL should roughly double when design life doubles
        assert 1.5 < rul_100 / max(rul_50, 0.01) < 2.5

    def test_parametric_rul(self, dd):
        rul = dd.predict_rul(0.5, 50.0, use_parametric=True)
        assert 0 < rul < 50


# ──────────────────────────────────────────────────────────────────────
# 5. Equipment Type Scaling (real_degradation)
# ──────────────────────────────────────────────────────────────────────


class TestRealDegradation:
    def test_pump_degrades_faster_than_hull(self):
        # Pump has 25y design life, hull has 200y
        pump_h = real_degradation("pump", 20.0, seed=42)
        hull_h = real_degradation("hull_panel", 20.0, seed=42)
        assert pump_h < hull_h, "Short-lived pump should degrade faster than hull"

    def test_zero_age_is_healthy(self):
        h = real_degradation("generic", 0.0, seed=42)
        assert h >= 0.85

    def test_deterministic_with_same_seed(self):
        # Clear the cache to ensure consistency
        h1 = real_degradation("pump", 15.0, seed=99)
        h2 = real_degradation("pump", 15.0, seed=99)
        assert h1 == h2

    def test_different_seeds_give_different_values(self):
        h1 = real_degradation("sensor", 10.0, seed=1)
        h2 = real_degradation("sensor", 10.0, seed=2)
        # Seeds affect per-unit scatter — values should differ slightly
        # (they might occasionally be equal due to small noise, so check many)
        differences = 0
        for s in range(20):
            a = real_degradation("sensor", 10.0, seed=s)
            b = real_degradation("sensor", 10.0, seed=s + 100)
            if abs(a - b) > 0.001:
                differences += 1
        assert differences > 10

    def test_all_equipment_types_valid(self):
        for eq_type in EQUIPMENT_DESIGN_LIVES:
            h = real_degradation(eq_type, 5.0, seed=42)
            assert 0.0 <= h <= 1.0, f"{eq_type} returned health={h}"

    def test_unknown_equipment_uses_generic(self):
        h = real_degradation("totally_unknown_widget", 10.0, seed=42)
        assert 0.0 <= h <= 1.0


# ──────────────────────────────────────────────────────────────────────
# 6. Trajectory Sampling
# ──────────────────────────────────────────────────────────────────────


class TestTrajectorySampling:
    def test_trajectory_shape(self, dd):
        times, health = dd.sample_trajectory(design_life_years=30, n_points=50)
        assert len(times) == 50
        assert len(health) == 50

    def test_trajectory_monotone(self, dd):
        _, health = dd.sample_trajectory(design_life_years=30, seed=42)
        diffs = np.diff(health)
        assert np.all(diffs <= 1e-10)

    def test_trajectory_bounded(self, dd):
        _, health = dd.sample_trajectory(design_life_years=30, seed=42)
        assert health.min() >= 0.0
        assert health.max() <= 1.0

    def test_different_seeds_differ(self, dd):
        _, h1 = dd.sample_trajectory(seed=1)
        _, h2 = dd.sample_trajectory(seed=2)
        assert not np.allclose(h1, h2)


# ──────────────────────────────────────────────────────────────────────
# 7. Degradation Rate
# ──────────────────────────────────────────────────────────────────────


class TestDegradationRate:
    def test_rate_is_nonnegative(self, dd):
        for age in [0, 10, 25, 40, 50]:
            rate = dd.get_degradation_rate(age, 50.0)
            assert rate >= 0.0

    def test_rate_increases_with_age(self, dd):
        # Degradation accelerates (alpha > 1)
        rate_early = dd.get_degradation_rate(5.0, 50.0)
        rate_late = dd.get_degradation_rate(40.0, 50.0)
        assert rate_late > rate_early


# ──────────────────────────────────────────────────────────────────────
# 8. Precomputed Model (no data files)
# ──────────────────────────────────────────────────────────────────────


class TestPrecomputedModel:
    def test_from_precomputed_works(self):
        dd = DataDrivenDegradation.from_precomputed(alpha=2.0, mean_lifetime=200.0)
        assert dd.model.alpha == 2.0
        h = dd.predict_health(25.0, 50.0)
        assert 0.0 < h < 1.0

    def test_parametric_exact(self):
        dd = DataDrivenDegradation.from_precomputed(alpha=2.0, mean_lifetime=100.0)
        # At t/T = 0.5: health = 1 - 0.5^2 = 0.75
        h = dd.predict_health(25.0, 50.0, use_parametric=True)
        assert abs(h - 0.75) < 0.01


# ──────────────────────────────────────────────────────────────────────
# 9. Algae Growth Model
# ──────────────────────────────────────────────────────────────────────


class TestAlgaeModel:
    def test_three_raceways(self, algae_model):
        assert algae_model.n_raceways == 3
        assert len(algae_model.growth_curves) == 3

    def test_density_range(self, algae_model):
        # Spirulina density in the dataset peaks around 2 g/L
        assert 1.0 < algae_model.max_density < 5.0

    def test_growth_curve_length(self, algae_model):
        assert len(algae_model.mean_growth_curve) > 100

    def test_lag_phase_exists(self, algae_model):
        assert algae_model.lag_phase_days > 0
        assert algae_model.lag_phase_days < 100

    def test_doubling_time_finite(self, algae_model):
        assert 0 < algae_model.doubling_time_days < 200

    def test_missing_algae_data_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_algae_data("/nonexistent/algae.mat")


class TestAlgaeProductionRate:
    def test_returns_expected_keys(self):
        result = algae_production_rate(50, 50)
        assert "density_g_per_L" in result
        assert "growth_rate_g_per_L_per_day" in result
        assert "normalized_productivity" in result

    def test_density_nonnegative(self):
        for day in [1, 50, 100, 200, 300]:
            result = algae_production_rate(day, day)
            assert result["density_g_per_L"] >= 0.0

    def test_normalized_productivity_bounded(self):
        for day in [1, 50, 100, 200, 354]:
            result = algae_production_rate(day, day)
            assert 0.0 <= result["normalized_productivity"] <= 1.0

    def test_growth_rate_positive_during_growth(self):
        # During mid-growth phase, rate should be positive
        result = algae_production_rate(50, 50)
        assert result["growth_rate_g_per_L_per_day"] > 0
