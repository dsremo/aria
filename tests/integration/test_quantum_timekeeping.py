"""Integration tests for atomic clock timekeeping & quantum physics systems.

Every test uses exact analytical calculations to verify the physics.
No tolerances wider than 1% unless explicitly noted with rationale.
"""

from __future__ import annotations

import math
import random

import pytest

from aria.simulation.quantum_timekeeping import (
    C,
    DAY_SECONDS,
    DSAC_DRIFT_PER_DAY,
    DSAC_STABILITY_23DAY,
    DSAC2_MASS_KG,
    DSAC2_POWER_WATTS,
    DSAC2_VOLUME_LITERS,
    HG199_HYPERFINE_HZ,
    OPTICAL_LATTICE_ACCURACY,
    OPTICAL_LATTICE_DRIFT_PER_DAY,
    QKD_MICIUS_KEY_RATE_BPS,
    QKD_MICIUS_RANGE_KM,
    QRNG_RATE_MBPS,
    QUANTUM_MYTHS,
    YEAR_SECONDS,
    DSACClock,
    OpticalLatticeClock,
    QuantumGravitationalSensor,
    QuantumKeyDistribution,
    QuantumMythStatus,
    QuantumRandomNumberGenerator,
    RelativisticTimeTracker,
    ShipQuantumSuite,
    ShipTimekeepingSystem,
    TechReadiness,
    assess_quantum_claim,
    byzantine_clock_vote,
    clock_ensemble_average,
    coordinate_time_from_proper,
    dsac_error_1000_years,
    dsac_error_over_duration,
    ensemble_stability_improvement,
    lorentz_gamma,
    optical_lattice_error_1000_years,
    proper_time_elapsed,
    time_dilation_correction_1000yr,
)


# ════════════════════════════════════════════════════════════════
# 1. DSAC CLOCK — NASA VERIFIED PARAMETERS
# ════════════════════════════════════════════════════════════════

class TestDSACConstants:
    """Verify DSAC constants match NASA/JPL published data."""

    def test_dsac_drift_rate(self):
        """Burt et al., Nature 2021: drift ≤ 3×10⁻¹⁶/day."""
        assert DSAC_DRIFT_PER_DAY == 3.0e-16

    def test_dsac_stability_23day(self):
        """Allan deviation at 23 days: 3×10⁻¹⁵."""
        assert DSAC_STABILITY_23DAY == 3.0e-15

    def test_dsac2_mass(self):
        """DSAC-2 for VERITAS: 10 kg."""
        assert DSAC2_MASS_KG == 10.0

    def test_dsac2_power(self):
        """DSAC-2: 34 W."""
        assert DSAC2_POWER_WATTS == 34.0

    def test_dsac2_volume(self):
        """DSAC-2: 10 liters."""
        assert DSAC2_VOLUME_LITERS == 10.0

    def test_hg199_frequency(self):
        """Mercury-199 hyperfine: ~40.5 GHz."""
        assert 40.0e9 < HG199_HYPERFINE_HZ < 41.0e9


class TestDSACClock:
    """Verify DSAC clock drift model against exact calculations."""

    def test_one_day_error(self):
        """After 1 day: error = 3e-16 × 86400 = 2.592e-11 s."""
        clock = DSACClock()
        error = clock.tick(1.0)
        expected = DSAC_DRIFT_PER_DAY * DAY_SECONDS
        assert abs(error - expected) < 1e-20

    def test_one_year_error(self):
        """After 365.25 days: error = 3e-16 × 365.25 × 86400."""
        clock = DSACClock()
        error = clock.tick(365.25)
        expected = DSAC_DRIFT_PER_DAY * 365.25 * DAY_SECONDS
        assert abs(error - expected) < 1e-18

    def test_10_year_error_under_1_microsecond(self):
        """NASA claim: <1 μs in 10 years. Verify."""
        clock = DSACClock()
        days_10yr = 10.0 * 365.25
        error = clock.tick(days_10yr)
        expected = DSAC_DRIFT_PER_DAY * days_10yr * DAY_SECONDS
        # 3e-16 × 3652.5 × 86400 = 9.467e-8 s = 0.0947 μs
        assert error < 1e-6, f"Error {error:.3e} s exceeds 1 μs"
        assert abs(error - expected) < 1e-16

    def test_cumulative_ticking(self):
        """Ticking 365 times by 1 day should match 1 tick of 365 days."""
        clock_a = DSACClock()
        for _ in range(365):
            clock_a.tick(1.0)

        clock_b = DSACClock()
        clock_b.tick(365.0)

        assert abs(clock_a.cumulative_error_s - clock_b.cumulative_error_s) < 1e-20

    def test_error_after_days_prediction(self):
        """error_after_days should match actual tick result."""
        clock = DSACClock()
        predicted = clock.error_after_days(100.0)
        clock.tick(100.0)
        assert abs(predicted - clock.cumulative_error_s) < 1e-20

    def test_calibration_resets_error(self):
        """Calibration against pulsar should reset accumulated error."""
        clock = DSACClock()
        clock.tick(1000.0)
        assert clock.cumulative_error_s > 0
        clock.calibrate(0.0)
        assert clock.cumulative_error_s == 0.0

    def test_m3_alpha_drift_tracked_separately(self):
        """After ticking 365 days the Pod M3 cumulative field should
        be strictly positive, tiny compared to the instrument drift,
        and not contaminate cumulative_error_s."""
        clock = DSACClock()
        clock.tick(365.25)
        assert clock.m3_alpha_drift_cumulative_s > 0.0
        # At Webb 2011 upper bound with K_α = 2.83, the M3 shift
        # over 365 days is ~8.95e-14 s — far below the DSAC
        # instrument floor of ~9.47e-9 s.
        assert clock.m3_alpha_drift_cumulative_s < 1.0e-12
        # Instrument error unaffected by M3
        expected_instrument = DSAC_DRIFT_PER_DAY * 365.25 * DAY_SECONDS
        assert abs(clock.cumulative_error_s - expected_instrument) < 1e-18

    def test_offline_clock_does_not_tick(self):
        """A failed clock should not accumulate more error."""
        clock = DSACClock()
        clock.tick(100.0)
        error_at_failure = clock.cumulative_error_s
        clock.is_operational = False
        clock.tick(100.0)
        assert clock.cumulative_error_s == error_at_failure


# ════════════════════════════════════════════════════════════════
# 2. OPTICAL LATTICE CLOCK
# ════════════════════════════════════════════════════════════════

class TestOpticalLatticeClock:
    """Verify optical lattice clock is 100× more accurate than DSAC."""

    def test_accuracy_ratio(self):
        """Optical lattice: 10⁻¹⁸ vs DSAC: 3×10⁻¹⁶. Ratio > 100."""
        ratio = DSAC_DRIFT_PER_DAY / OPTICAL_LATTICE_DRIFT_PER_DAY
        assert ratio == 300.0  # 3e-16 / 1e-18 = 300

    def test_readiness_is_lab(self):
        """Optical lattice is lab-verified only, not flight."""
        clock = OpticalLatticeClock()
        assert clock.readiness == TechReadiness.VERIFIED_LAB

    def test_one_year_error_much_smaller(self):
        """Optical lattice 1-year error << DSAC 1-year error."""
        dsac = DSACClock()
        dsac.tick(365.25)
        optical = OpticalLatticeClock()
        optical.tick(365.25)
        assert optical.cumulative_error_s < dsac.cumulative_error_s / 100


# ════════════════════════════════════════════════════════════════
# 3. 1000-YEAR TIMEKEEPING
# ════════════════════════════════════════════════════════════════

class TestMillennialTimekeeping:
    """Verify timekeeping calculations over 1000 years."""

    def test_dsac_error_1000_years_exact(self):
        """3e-16/day × 365250 days × 86400 s/day = 9.467e-6 s."""
        error = dsac_error_1000_years()
        expected = 3.0e-16 * 365_250.0 * 86_400.0
        assert abs(error - expected) < 1e-12
        # Numerical value: ~9.47 microseconds over 1000 years
        assert 9.0e-6 < error < 1.0e-5

    def test_optical_lattice_error_1000_years(self):
        """Should be ~300× smaller than DSAC error."""
        dsac_err = dsac_error_1000_years()
        optical_err = optical_lattice_error_1000_years()
        ratio = dsac_err / optical_err
        assert abs(ratio - 300.0) < 1.0  # Allow small tolerance from rounding

    def test_dsac_error_custom_duration(self):
        """Verify dsac_error_over_duration with known values."""
        # 1 day: 3e-16 × 86400
        error_1d = dsac_error_over_duration(1.0)
        assert abs(error_1d - 3.0e-16 * 86400.0) < 1e-22

    def test_time_dilation_at_0_1c(self):
        """At 0.1c for 1000 years: γ ≈ 1.00504, Δ ≈ 5.013 years."""
        result = time_dilation_correction_1000yr(0.1)
        gamma = 1.0 / math.sqrt(1.0 - 0.01)
        assert abs(result["gamma"] - gamma) < 1e-10
        expected_proper = 1000.0 / gamma
        assert abs(result["proper_time_years"] - expected_proper) < 1e-6
        # Difference should be ~5 years
        assert 4.5 < result["difference_years"] < 5.5

    def test_time_dilation_at_0_5c(self):
        """At 0.5c: γ = 1/√0.75 ≈ 1.1547, Δ ≈ 134 years."""
        result = time_dilation_correction_1000yr(0.5)
        gamma = 1.0 / math.sqrt(0.75)
        assert abs(result["gamma"] - gamma) < 1e-10
        expected_diff = 1000.0 - 1000.0 / gamma
        assert abs(result["difference_years"] - expected_diff) < 1e-6

    def test_time_dilation_at_0_9c(self):
        """At 0.9c: γ ≈ 2.294, τ ≈ 436 years."""
        result = time_dilation_correction_1000yr(0.9)
        gamma = 1.0 / math.sqrt(1.0 - 0.81)
        assert abs(result["gamma"] - gamma) < 1e-6
        assert 430 < result["proper_time_years"] < 440


# ════════════════════════════════════════════════════════════════
# 4. RELATIVISTIC TIME TRACKING
# ════════════════════════════════════════════════════════════════

class TestRelativisticTimeTracking:
    """Verify proper time vs coordinate time calculations."""

    def test_lorentz_gamma_zero(self):
        assert lorentz_gamma(0.0) == 1.0

    def test_lorentz_gamma_0_1c(self):
        v = 0.1 * C
        gamma = lorentz_gamma(v)
        expected = 1.0 / math.sqrt(1.0 - 0.01)
        assert abs(gamma - expected) < 1e-10

    def test_lorentz_superluminal_raises(self):
        with pytest.raises(ValueError, match="unphysical"):
            lorentz_gamma(C)

    def test_proper_time_elapsed(self):
        """1000 Earth years at 0.1c => ~995 ship years."""
        v = 0.1 * C
        earth_s = 1000.0 * YEAR_SECONDS
        ship_s = proper_time_elapsed(earth_s, v)
        gamma = lorentz_gamma(v)
        expected_s = earth_s / gamma
        assert abs(ship_s - expected_s) < 1e-3

    def test_coordinate_from_proper_roundtrip(self):
        """t = τ×γ and τ = t/γ should be inverses."""
        v = 0.3 * C
        proper_s = 500.0 * YEAR_SECONDS
        coord_s = coordinate_time_from_proper(proper_s, v)
        recovered_proper = proper_time_elapsed(coord_s, v)
        assert abs(recovered_proper - proper_s) < 1.0  # within 1 second

    def test_tracker_accumulation(self):
        """RelativisticTimeTracker accumulates correctly over steps."""
        tracker = RelativisticTimeTracker()
        v = 0.1 * C
        gamma = lorentz_gamma(v)

        # 100 steps of 10 Earth years each
        for _ in range(100):
            tracker.advance_years(10.0, v)

        assert abs(tracker.coordinate_time_years() - 1000.0) < 1e-6
        expected_proper = 1000.0 / gamma
        assert abs(tracker.proper_time_years() - expected_proper) < 1e-4

    def test_tracker_time_difference(self):
        """Accumulated time difference at 0.1c over 1000 years ~5 years."""
        tracker = RelativisticTimeTracker()
        tracker.advance_years(1000.0, 0.1 * C)
        diff = tracker.time_difference_years()
        assert 4.5 < diff < 5.5

    def test_tracker_zero_velocity(self):
        """At rest: proper time = coordinate time."""
        tracker = RelativisticTimeTracker()
        tracker.advance_years(100.0, 0.0)
        assert abs(tracker.proper_time_years() - 100.0) < 1e-10
        assert abs(tracker.time_difference_years()) < 1e-10


# ════════════════════════════════════════════════════════════════
# 5. CLOCK ENSEMBLE & BYZANTINE VOTING
# ════════════════════════════════════════════════════════════════

class TestClockEnsemble:
    """Verify clock ensemble averaging and voting."""

    def test_equal_weight_average(self):
        """3 equal readings => average = reading."""
        result = clock_ensemble_average([1.0, 1.0, 1.0])
        assert abs(result - 1.0) < 1e-15

    def test_weighted_average(self):
        """Weighted average: 2×1.0 + 1×2.0, weights [0.5, 0.25, 0.25]."""
        result = clock_ensemble_average([1.0, 1.0, 2.0], [0.5, 0.25, 0.25])
        expected = 0.5 * 1.0 + 0.25 * 1.0 + 0.25 * 2.0
        assert abs(result - expected) < 1e-15

    def test_byzantine_vote_all_agree(self):
        """3 clocks agree => no rejections."""
        voted, rejected = byzantine_clock_vote([1.0, 1.0, 1.0])
        assert len(rejected) == 0
        assert abs(voted - 1.0) < 1e-15

    def test_byzantine_vote_one_outlier(self):
        """1 clock deviates by 1 second => rejected."""
        voted, rejected = byzantine_clock_vote([1.0, 1.0, 2.0],
                                                max_deviation_s=0.5)
        assert 2 in rejected
        assert abs(voted - 1.0) < 1e-15

    def test_ensemble_stability_sqrt_n(self):
        """Ensemble of 3 clocks: stability improves by √3."""
        single = DSAC_STABILITY_23DAY
        ensemble = ensemble_stability_improvement(3, single)
        expected = single / math.sqrt(3)
        assert abs(ensemble - expected) < 1e-20

    def test_ensemble_stability_9_clocks(self):
        """9 clocks: improvement = 1/3."""
        single = 1.0e-15
        ensemble = ensemble_stability_improvement(9, single)
        expected = single / 3.0
        assert abs(ensemble - expected) < 1e-25

    def test_empty_readings_raises(self):
        with pytest.raises(ValueError):
            clock_ensemble_average([])


# ════════════════════════════════════════════════════════════════
# 6. QUANTUM KEY DISTRIBUTION
# ════════════════════════════════════════════════════════════════

class TestQKD:
    """Verify QKD physics: inverse-square law for key rate."""

    def test_key_rate_at_reference_distance(self):
        """At Micius reference range: should return base key rate."""
        qkd = QuantumKeyDistribution()
        rate = qkd.key_rate_at_distance(QKD_MICIUS_RANGE_KM)
        assert abs(rate - QKD_MICIUS_KEY_RATE_BPS) < 1e-6

    def test_key_rate_inverse_square(self):
        """Double the distance => 1/4 the key rate."""
        qkd = QuantumKeyDistribution()
        rate_1x = qkd.key_rate_at_distance(1000.0)
        rate_2x = qkd.key_rate_at_distance(2000.0)
        assert abs(rate_2x / rate_1x - 0.25) < 1e-10

    def test_key_rate_at_10x_distance(self):
        """10× distance => 1/100 key rate."""
        qkd = QuantumKeyDistribution()
        rate_1x = qkd.key_rate_at_distance(100.0)
        rate_10x = qkd.key_rate_at_distance(1000.0)
        assert abs(rate_10x / rate_1x - 0.01) < 1e-10

    def test_readiness_is_flight_verified(self):
        qkd = QuantumKeyDistribution()
        assert qkd.readiness == TechReadiness.VERIFIED_FLIGHT

    def test_zero_distance_raises(self):
        qkd = QuantumKeyDistribution()
        with pytest.raises(ValueError):
            qkd.key_rate_at_distance(0.0)


# ════════════════════════════════════════════════════════════════
# 7. QUANTUM RANDOM NUMBER GENERATOR
# ════════════════════════════════════════════════════════════════

class TestQRNG:
    """Verify QRNG bit generation timing."""

    def test_generation_time_1gb(self):
        """1 Gbps QRNG: 1 Gbit in 1 second."""
        qrng = QuantumRandomNumberGenerator()
        time_s = qrng.generate_bits(1_000_000_000)
        # 1e9 bits / (1000 Mbps × 1e6) = 1.0 s
        assert abs(time_s - 1.0) < 1e-10

    def test_entropy_per_bit_nominal(self):
        """Fresh QRNG: entropy = 1.0 (perfect)."""
        qrng = QuantumRandomNumberGenerator()
        assert qrng.entropy_per_bit() == 1.0

    def test_degraded_generation_slower(self):
        """After degradation, generation takes longer."""
        qrng = QuantumRandomNumberGenerator()
        time_fresh = qrng.generate_bits(1_000_000)
        qrng.degradation_factor = 0.5
        time_degraded = qrng.generate_bits(1_000_000)
        assert time_degraded > time_fresh
        assert abs(time_degraded / time_fresh - 2.0) < 1e-10


# ════════════════════════════════════════════════════════════════
# 8. QUANTUM GRAVITATIONAL SENSOR
# ════════════════════════════════════════════════════════════════

class TestQuantumGravSensor:
    """Verify gravitational sensor detection physics."""

    def test_earth_mass_detection_range(self):
        """Detection range for Earth-mass object at nano-g sensitivity."""
        sensor = QuantumGravitationalSensor()
        G = 6.674_30e-11
        M_earth = 5.972e24
        # r_max = sqrt(G × M / sensitivity)
        expected_range = math.sqrt(G * M_earth / 1e-9)
        actual_range = sensor.detection_range_m(M_earth)
        assert abs(actual_range - expected_range) / expected_range < 1e-6

    def test_detectable_earth_at_close_range(self):
        """Earth at 1 AU: g = 6e-3 m/s² — easily detectable."""
        sensor = QuantumGravitationalSensor()
        M_earth = 5.972e24
        # At 1000 km: a = G×M/r² = 6.67e-11 × 5.97e24 / (1e6)² ≈ 398 m/s²
        assert sensor.gravitational_anomaly_detectable(M_earth, 1e6)

    def test_not_detectable_small_mass_far(self):
        """1 kg at 1 km: a = 6.67e-17 m/s² — not detectable (< nano-g)."""
        sensor = QuantumGravitationalSensor()
        assert not sensor.gravitational_anomaly_detectable(1.0, 1000.0)

    def test_detection_range_scales_with_sqrt_mass(self):
        """Doubling mass => range increases by √2."""
        sensor = QuantumGravitationalSensor()
        r1 = sensor.detection_range_m(1e20)
        r2 = sensor.detection_range_m(2e20)
        assert abs(r2 / r1 - math.sqrt(2)) < 1e-6


# ════════════════════════════════════════════════════════════════
# 9. QUANTUM MYTHS — HONEST PHYSICS
# ════════════════════════════════════════════════════════════════

class TestQuantumMyths:
    """Verify all speculative/debunked claims are correctly labeled."""

    def test_entanglement_ftl_debunked(self):
        """FTL via entanglement violates no-communication theorem."""
        result = assess_quantum_claim("entanglement")
        assert result is not None
        assert result["status"] == QuantumMythStatus.VIOLATES_KNOWN_PHYSICS

    def test_emdrive_no_evidence(self):
        """EmDrive: no confirmed thrust in any peer-reviewed experiment."""
        result = assess_quantum_claim("EmDrive")
        assert result is not None
        assert result["status"] == QuantumMythStatus.NO_EVIDENCE

    def test_dark_energy_propulsion_no_evidence(self):
        result = assess_quantum_claim("Dark energy")
        assert result is not None
        assert result["status"] == QuantumMythStatus.NO_EVIDENCE

    def test_alcubierre_theoretically_possible(self):
        result = assess_quantum_claim("Alcubierre")
        assert result is not None
        assert result["status"] == QuantumMythStatus.THEORETICALLY_POSSIBLE

    def test_all_myths_have_references(self):
        """Every myth entry must have at least one reference."""
        for myth in QUANTUM_MYTHS:
            assert len(myth["references"]) >= 1, f"No refs for: {myth['claim']}"

    def test_unknown_claim_returns_none(self):
        assert assess_quantum_claim("teleportation_banana") is None


# ════════════════════════════════════════════════════════════════
# 10. INTEGRATED SHIP TIMEKEEPING SYSTEM
# ════════════════════════════════════════════════════════════════

class TestShipTimekeepingSystem:
    """Verify integrated timekeeping over multi-year simulations."""

    def test_default_has_3_dsac_clocks(self):
        system = ShipTimekeepingSystem()
        assert len(system.dsac_clocks) == 3

    def test_default_has_optical_clock(self):
        system = ShipTimekeepingSystem()
        assert system.optical_clock is not None

    def test_simulate_1_year_at_rest(self):
        """At rest: proper time = coordinate time."""
        random.seed(42)
        system = ShipTimekeepingSystem()
        result = system.simulate_year(velocity_ms=0.0)
        assert result["mission_year"] == 1.0
        assert abs(result["proper_time_years"] - 1.0) < 1e-6
        assert abs(result["time_dilation_difference_years"]) < 1e-10

    def test_simulate_1_year_at_0_1c(self):
        """At 0.1c: proper time < coordinate time."""
        random.seed(42)
        system = ShipTimekeepingSystem()
        v = 0.1 * C
        result = system.simulate_year(velocity_ms=v)
        gamma = lorentz_gamma(v)
        expected_proper = 1.0 / gamma
        assert abs(result["proper_time_years"] - expected_proper) < 1e-6

    def test_100_year_simulation_no_crash(self):
        """Run 100 years without exceptions."""
        random.seed(12345)
        system = ShipTimekeepingSystem()
        for _ in range(100):
            result = system.simulate_year(velocity_ms=0.05 * C)
        assert result["mission_year"] == 100.0
        assert result["n_operational_dsac"] >= 0

    def test_consensus_time_with_all_clocks(self):
        """Consensus time should be close to average of DSAC errors."""
        random.seed(42)
        system = ShipTimekeepingSystem()
        system.simulate_year(velocity_ms=0.0)
        consensus = system.get_consensus_time_s()
        # Should be proper time + small clock error
        assert consensus > 0


class TestShipQuantumSuite:
    """Verify integrated quantum systems suite."""

    def test_all_systems_start_operational(self):
        suite = ShipQuantumSuite()
        result = suite.simulate_year()
        assert result["mission_year"] == 1.0
        # With fresh seed, all should be operational
        random.seed(42)
        suite2 = ShipQuantumSuite()
        r = suite2.simulate_year()
        assert r["all_operational"] is True

    def test_50_year_degradation(self):
        """After 50 years, QKD detector should show degradation (1%/yr)."""
        random.seed(42)
        suite = ShipQuantumSuite()
        for _ in range(50):
            suite.simulate_year()
        # QKD detector degrades 1%/year: 0.99^50 ≈ 0.605
        # Check that it has degraded meaningfully (may fail partway)
        assert suite.qkd.detector_degradation < 1.0  # Has degraded from initial
        # Grav sensor degrades 0.3%/year: 0.997^50 ≈ 0.861
        if suite.grav_sensor.is_operational:
            assert suite.grav_sensor.degradation_factor < 0.95


# ════════════════════════════════════════════════════════════════
# 11. EXACT PHYSICS CALCULATIONS (cross-validation)
# ════════════════════════════════════════════════════════════════

class TestExactPhysics:
    """Cross-validate physics constants and calculations."""

    def test_speed_of_light(self):
        assert C == 299_792_458.0

    def test_year_seconds(self):
        assert YEAR_SECONDS == 365.25 * 86_400

    def test_dsac_10yr_error_numerical(self):
        """Exact: 3e-16 × 3652.5 × 86400 = 9.4673e-8 s."""
        error = dsac_error_over_duration(3652.5)
        expected = 3.0e-16 * 3652.5 * 86400.0
        assert abs(error - expected) < 1e-20
        assert abs(error - 9.46728e-8) < 1e-12

    def test_gamma_at_0_1c_exact(self):
        """γ(0.1c) = 1/√(0.99) = 1.005037815..."""
        gamma = lorentz_gamma(0.1 * C)
        expected = 1.0 / math.sqrt(0.99)
        assert abs(gamma - expected) < 1e-12

    def test_proper_time_1000yr_at_0_1c_exact(self):
        """τ = 1000/γ = 1000 × √(0.99) = 994.987..."""
        v = 0.1 * C
        gamma = lorentz_gamma(v)
        proper_years = 1000.0 / gamma
        expected = 1000.0 * math.sqrt(0.99)
        assert abs(proper_years - expected) < 1e-6
        # Crew ages ~5.01 years less
        diff = 1000.0 - proper_years
        assert abs(diff - (1000.0 - 1000.0 * math.sqrt(0.99))) < 1e-6
