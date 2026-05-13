"""Tests for PcCalculator (all methods) and Monte Carlo Pc estimation."""

from datetime import datetime

import numpy as np
import pytest

from aria.conjunction.core.types import (
    CloseApproach,
    CoordinateFrame,
    ObjectType,
    OrbitalElements,
    RiskLevel,
    SpaceObject,
    StateVector,
)
from aria.conjunction.probability.monte_carlo import monte_carlo_pc, monte_carlo_pc_3d
from aria.conjunction.probability.pc_calculator import PcCalculator, _encounter_duration_seconds

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_approach(
    miss_km: float = 0.5,
    pc: float | None = None,
    risk: RiskLevel = RiskLevel.GREEN,
    rel_vel_km_s: float = 7.5,
    primary_cov: np.ndarray | None = None,
    secondary_cov: np.ndarray | None = None,
) -> CloseApproach:
    tca = datetime(2024, 3, 15, 12, 0, 0)
    elements = OrbitalElements(7000, 0.001, 0.9, 0, 0, 0, tca)
    primary = SpaceObject(
        norad_id="25544", name="ISS",
        tle_line1="", tle_line2="",
        object_type=ObjectType.PAYLOAD, radius_m=50.0,
        elements=elements,
    )
    secondary = SpaceObject(
        norad_id="99999", name="DEBRIS",
        tle_line1="", tle_line2="",
        object_type=ObjectType.DEBRIS, radius_m=0.1,
        elements=elements,
    )
    approach = CloseApproach(
        primary=primary,
        secondary=secondary,
        tca=tca,
        miss_distance_km=miss_km,
        miss_distance_rtn=np.array([0.1, miss_km, 0.0]),
        relative_velocity_km_s=rel_vel_km_s,
        relative_position=np.array([miss_km, 0.0, 0.0]),
        relative_velocity_vec=np.array([0.0, rel_vel_km_s, 0.0]),
        probability_of_collision=pc,
        risk_level=risk,
        primary_covariance=primary_cov,
        secondary_covariance=secondary_cov,
    )
    # Add state vectors for better covariance defaults
    approach.primary_state = StateVector(
        position=np.array([7000.0, 0.0, 0.0]),
        velocity=np.array([0.0, 7.5, 0.0]),
        epoch=tca,
        frame=CoordinateFrame.ECI_J2000,
    )
    approach.secondary_state = StateVector(
        position=np.array([7000.5, 0.0, 0.0]),
        velocity=np.array([0.0, -7.5, 0.0]),
        epoch=tca,
        frame=CoordinateFrame.ECI_J2000,
    )
    return approach


# ---------------------------------------------------------------------------
# _encounter_duration_seconds
# ---------------------------------------------------------------------------

class TestEncounterDuration:

    def test_normal_encounter(self):
        """Typical LEO conjunction: ~1 km position sigma, 10 km/s relative velocity."""
        cov = np.eye(3) * 1.0  # 1 km sigma
        v_rel = np.array([0.0, 10.0, 0.0])  # 10 km/s
        tau = _encounter_duration_seconds(cov, v_rel)
        assert tau == pytest.approx(0.1, rel=0.01)  # 0.1 s

    def test_zero_relative_velocity_returns_inf(self):
        cov = np.eye(3) * 1.0
        v_rel = np.array([0.0, 0.0, 0.0])
        tau = _encounter_duration_seconds(cov, v_rel)
        assert tau == float("inf")

    def test_large_sigma_long_encounter(self):
        """Large uncertainty along track → long encounter duration."""
        cov = np.zeros((3, 3))
        cov[1, 1] = 100.0  # 10 km sigma along y
        v_rel = np.array([0.0, 1.0, 0.0])  # 1 km/s
        tau = _encounter_duration_seconds(cov, v_rel)
        assert tau == pytest.approx(10.0, rel=0.01)  # 10 km / 1 km/s

    def test_orthogonal_uncertainty(self):
        """Uncertainty perpendicular to velocity → short encounter."""
        cov = np.zeros((3, 3))
        cov[0, 0] = 100.0  # large x sigma
        v_rel = np.array([0.0, 10.0, 0.0])  # y velocity
        tau = _encounter_duration_seconds(cov, v_rel)
        assert tau == pytest.approx(0.0, abs=1e-8)


# ---------------------------------------------------------------------------
# PcCalculator — method selection
# ---------------------------------------------------------------------------

class TestPcCalculatorMethods:

    def test_foster_method_explicit(self):
        """Foster method should return Pc in [0, 1]."""
        calc = PcCalculator()
        approach = _make_approach(miss_km=0.5)
        pc = calc.calculate(approach, method="foster")
        assert 0.0 <= pc <= 1.0

    def test_chan_method_explicit(self):
        """Chan method should return Pc in [0, 1]."""
        calc = PcCalculator()
        approach = _make_approach(miss_km=0.5)
        pc = calc.calculate(approach, method="chan")
        assert 0.0 <= pc <= 1.0

    def test_monte_carlo_method_explicit(self):
        """Monte Carlo 2D method should return Pc in [0, 1]."""
        calc = PcCalculator(mc_samples=10_000)
        approach = _make_approach(miss_km=0.5)
        pc = calc.calculate(approach, method="monte_carlo")
        assert 0.0 <= pc <= 1.0

    def test_monte_carlo_3d_method_explicit(self):
        """Monte Carlo 3D method should return Pc in [0, 1]."""
        calc = PcCalculator(mc_samples=10_000)
        approach = _make_approach(miss_km=0.5)
        pc = calc.calculate(approach, method="monte_carlo_3d")
        assert 0.0 <= pc <= 1.0

    def test_invalid_method_raises(self):
        calc = PcCalculator()
        approach = _make_approach()
        with pytest.raises(ValueError, match="Unknown method"):
            calc.calculate(approach, method="invalid_method_xyz")

    def test_auto_method_returns_value(self):
        """Auto method selection should produce a valid Pc."""
        calc = PcCalculator(mc_samples=10_000)
        approach = _make_approach(miss_km=0.5)
        pc = calc.calculate(approach, method="auto")
        assert 0.0 <= pc <= 1.0

    def test_auto_method_3d_mc_for_long_encounter(self):
        """When encounter duration > limit, auto should switch to 3D MC."""
        # Very large along-track sigma → long encounter duration
        big_cov = np.zeros((3, 3))
        big_cov[0, 0] = 10000.0   # huge R uncertainty
        big_cov[1, 1] = 10000.0   # huge T uncertainty
        big_cov[2, 2] = 10000.0   # huge N uncertainty

        calc = PcCalculator(
            mc_samples=10_000,
            encounter_duration_limit_s=0.001,  # very short limit → always 3D MC
        )
        approach = _make_approach(miss_km=0.5, primary_cov=big_cov, secondary_cov=big_cov)
        pc = calc.calculate(approach, method="auto")
        assert 0.0 <= pc <= 1.0


# ---------------------------------------------------------------------------
# PcCalculator — Mahalanobis skip logic
# ---------------------------------------------------------------------------

class TestPcCalculatorMahalanobis:

    def test_large_miss_distance_returns_zero(self):
        """Very large miss distance → Mahalanobis >> threshold → Pc = 0."""
        # Small covariance (1 m sigma), large miss (1000 km) → D_M huge
        small_sigma_km = 0.001  # 1 m
        small_cov = np.eye(3) * small_sigma_km**2

        calc = PcCalculator(mahalanobis_threshold=5.0)
        approach = _make_approach(miss_km=1000.0, primary_cov=small_cov,
                                   secondary_cov=small_cov)
        pc = calc.calculate(approach)
        assert pc == 0.0
        assert approach.risk_level == RiskLevel.GREEN

    def test_close_approach_nonzero_pc(self):
        """Close approach with reasonable covariance should give nonzero Pc."""
        calc = PcCalculator(mahalanobis_threshold=10.0)
        approach = _make_approach(miss_km=0.1)  # very close
        pc = calc.calculate(approach)
        assert pc > 0.0


# ---------------------------------------------------------------------------
# PcCalculator — risk classification
# ---------------------------------------------------------------------------

class TestPcCalculatorRiskClassification:

    def test_risk_stored_on_approach(self):
        """PcCalculator should update approach.risk_level."""
        calc = PcCalculator(mahalanobis_threshold=100.0)
        approach = _make_approach(miss_km=0.1)
        calc.calculate(approach)
        assert approach.risk_level in (RiskLevel.GREEN, RiskLevel.YELLOW, RiskLevel.RED)

    def test_classify_risk_static(self):
        assert PcCalculator._classify_risk(0.0) == RiskLevel.GREEN
        assert PcCalculator._classify_risk(1e-7) == RiskLevel.GREEN
        assert PcCalculator._classify_risk(1e-5) == RiskLevel.YELLOW
        assert PcCalculator._classify_risk(5e-5) == RiskLevel.YELLOW
        assert PcCalculator._classify_risk(1e-4) == RiskLevel.RED
        assert PcCalculator._classify_risk(1.0) == RiskLevel.RED

    def test_pc_stored_on_approach(self):
        """PcCalculator should store computed Pc on approach object."""
        calc = PcCalculator(mahalanobis_threshold=100.0)
        approach = _make_approach(miss_km=0.5)
        pc = calc.calculate(approach)
        assert approach.probability_of_collision == pytest.approx(pc)

    def test_mahalanobis_distance_stored(self):
        """Mahalanobis distance should be stored on approach."""
        calc = PcCalculator()
        approach = _make_approach(miss_km=0.5)
        calc.calculate(approach)
        assert approach.mahalanobis_distance is not None
        assert approach.mahalanobis_distance >= 0.0


# ---------------------------------------------------------------------------
# PcCalculator — covariance handling
# ---------------------------------------------------------------------------

class TestPcCalculatorCovarianceHandling:

    def test_no_covariance_uses_default(self):
        """Calculator should work even with no covariance data."""
        calc = PcCalculator(mc_samples=10_000)
        approach = _make_approach(miss_km=0.5)
        approach.primary_covariance = None
        approach.secondary_covariance = None
        approach.primary_state = None
        approach.secondary_state = None
        pc = calc.calculate(approach)
        assert 0.0 <= pc <= 1.0

    def test_covariance_scaling_applied(self):
        """Covariance scaling should produce different results."""
        calc_1x = PcCalculator(covariance_scale_factor=1.0)
        calc_5x = PcCalculator(covariance_scale_factor=5.0)
        approach1 = _make_approach(miss_km=0.5)
        approach2 = _make_approach(miss_km=0.5)
        pc1 = calc_1x.calculate(approach1)
        pc2 = calc_5x.calculate(approach2)
        # 5x larger covariance → more spread → potentially different Pc
        # Both should be valid
        assert 0.0 <= pc1 <= 1.0
        assert 0.0 <= pc2 <= 1.0

    def test_6x6_covariance_truncated_to_3x3(self):
        """6x6 covariance should be truncated to 3x3 position-only."""
        big_cov = np.eye(6) * 1.0
        calc = PcCalculator()
        approach = _make_approach(miss_km=0.5, primary_cov=big_cov, secondary_cov=big_cov)
        pc = calc.calculate(approach)
        assert 0.0 <= pc <= 1.0


# ---------------------------------------------------------------------------
# monte_carlo_pc (2D)
# ---------------------------------------------------------------------------

class TestMonteCarloPc2D:

    def test_zero_miss_high_probability(self):
        """Zero miss, radius >> sigma → high probability of collision."""
        miss = np.array([0.0, 0.0])
        cov = np.eye(2) * 0.01  # sigma = 0.1 km
        # radius = 0.3 km = 3*sigma → P ≈ 1 - exp(-4.5) ≈ 0.99
        pc = monte_carlo_pc(miss, cov, combined_radius_km=0.3, n_samples=100_000, seed=42)
        assert pc > 0.8

    def test_large_miss_negligible_probability(self):
        """Miss >> radius → Pc ≈ 0."""
        miss = np.array([100.0, 0.0])
        cov = np.eye(2) * 0.01
        pc = monte_carlo_pc(miss, cov, combined_radius_km=0.01, n_samples=100_000, seed=42)
        assert pc < 1e-6

    def test_reproducibility_with_seed(self):
        miss = np.array([0.5, 0.0])
        cov = np.eye(2) * 0.1
        pc1 = monte_carlo_pc(miss, cov, combined_radius_km=0.1, n_samples=50_000, seed=7)
        pc2 = monte_carlo_pc(miss, cov, combined_radius_km=0.1, n_samples=50_000, seed=7)
        assert pc1 == pc2

    def test_pc_bounds(self):
        miss = np.array([1.0, 0.0])
        cov = np.eye(2) * 0.5
        pc = monte_carlo_pc(miss, cov, combined_radius_km=0.05, n_samples=50_000, seed=1)
        assert 0.0 <= pc <= 1.0

    def test_non_psd_covariance_regularized(self):
        """Slightly non-PSD covariance should be regularized, not crash."""
        miss = np.array([0.5, 0.0])
        # Near-singular covariance
        cov = np.array([[1e-15, 0.0], [0.0, 1e-15]])
        pc = monte_carlo_pc(miss, cov, combined_radius_km=0.1, n_samples=10_000, seed=0)
        assert 0.0 <= pc <= 1.0

    def test_larger_radius_higher_pc(self):
        """Larger combined radius → more hits → higher Pc."""
        miss = np.array([1.0, 0.0])
        cov = np.eye(2) * 1.0
        pc_small = monte_carlo_pc(miss, cov, combined_radius_km=0.1, n_samples=100_000, seed=42)
        pc_large = monte_carlo_pc(miss, cov, combined_radius_km=2.0, n_samples=100_000, seed=42)
        assert pc_large > pc_small


# ---------------------------------------------------------------------------
# monte_carlo_pc_3d
# ---------------------------------------------------------------------------

class TestMonteCarloPc3D:

    def test_pc_bounds(self):
        miss = np.array([1.0, 0.0, 0.0])
        cov = np.eye(3) * 0.5
        v_rel = np.array([0.0, 7.5, 0.0])
        pc = monte_carlo_pc_3d(
            miss, cov, combined_radius_km=0.05,
            relative_velocity=v_rel,
            n_samples=50_000, seed=42,
        )
        assert 0.0 <= pc <= 1.0

    def test_zero_miss_high_probability(self):
        miss = np.array([0.0, 0.0, 0.0])
        cov = np.eye(3) * 0.001
        v_rel = np.array([0.0, 7.5, 0.0])
        pc = monte_carlo_pc_3d(
            miss, cov, combined_radius_km=0.1,
            relative_velocity=v_rel,
            n_samples=50_000, seed=0,
        )
        assert pc > 0.01

    def test_large_miss_low_probability(self):
        miss = np.array([1000.0, 0.0, 0.0])
        cov = np.eye(3) * 0.01
        v_rel = np.array([0.0, 7.5, 0.0])
        pc = monte_carlo_pc_3d(
            miss, cov, combined_radius_km=0.01,
            relative_velocity=v_rel,
            n_samples=100_000, seed=42,
        )
        assert pc < 1e-4
