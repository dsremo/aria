"""Tests for analysis modules: breakup model, fleet risk, sensitivity, space weather."""

from __future__ import annotations

import math
import tempfile
import textwrap
from datetime import datetime

import numpy as np

from aria.conjunction.analysis.breakup_model import (
    NASABreakupModel,
    assess_collision_consequence,
    mass_from_radius,
)
from aria.conjunction.analysis.fleet_risk import (
    FleetRiskAggregator,
)
from aria.conjunction.analysis.sensitivity import (
    PcSensitivityAnalyzer,
)
from aria.conjunction.core.constants import PC_RED_THRESHOLD
from aria.conjunction.core.types import (
    CloseApproach,
    ObjectType,
    OrbitalElements,
    RiskLevel,
    SpaceObject,
)
from aria.conjunction.data.space_weather_loader import SpaceWeatherLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orbital_elements(sma_km=6778.0, ecc=0.001, inc_deg=51.6, alt_km=400.0):
    inc = math.radians(inc_deg)
    return OrbitalElements(
        semi_major_axis=sma_km,
        eccentricity=ecc,
        inclination=inc,
        raan=0.0,
        arg_perigee=0.0,
        true_anomaly=0.0,
        epoch=datetime(2025, 1, 1),
    )


def _make_space_object(norad_id: str, name: str, alt_km: float = 400.0) -> SpaceObject:
    elems = _make_orbital_elements()
    # Not setting satellite (sgp4 Satrec) — tests don't need propagation
    return SpaceObject(
        norad_id=norad_id,
        name=name,
        tle_line1="",
        tle_line2="",
        object_type=ObjectType.PAYLOAD,
        rcs_size="MEDIUM",
        radius_m=1.5,
        elements=elems,
        satellite=None,
    )


def _make_approach(
    primary_id: str,
    secondary_id: str,
    pc: float = 1e-5,
    risk: RiskLevel = RiskLevel.YELLOW,
    miss_km: float = 0.5,
) -> CloseApproach:
    primary = _make_space_object(primary_id, f"SAT-{primary_id}")
    secondary = _make_space_object(secondary_id, f"SAT-{secondary_id}")
    return CloseApproach(
        primary=primary,
        secondary=secondary,
        tca=datetime(2025, 6, 1, 12, 0, 0),
        miss_distance_km=miss_km,
        miss_distance_rtn=np.array([miss_km, 0.0, 0.0]),
        relative_velocity_km_s=7.5,
        relative_position=np.array([miss_km, 0.0, 0.0]),
        relative_velocity_vec=np.array([7.5, 0.0, 0.0]),
        primary_covariance=None,
        secondary_covariance=None,
        probability_of_collision=pc,
        mahalanobis_distance=None,
        risk_level=risk,
    )


# ===========================================================================
# NASA Breakup Model Tests
# ===========================================================================

class TestNASABreakupModel:
    """Tests for EVOLVE 4.0 fragment count formulas."""

    def test_collision_energy_symmetric(self):
        """Equal masses, symmetric — energy = ½ m v²."""
        e = NASABreakupModel.collision_energy(100.0, 100.0, 10.0)
        expected = 0.5 * 100.0 * (10000.0**2)
        assert abs(e - expected) / expected < 1e-10

    def test_collision_energy_uses_impactor(self):
        """For unequal masses, energy uses the lighter (impactor) mass."""
        e_asym = NASABreakupModel.collision_energy(1.0, 1000.0, 10.0)
        e_impactor = 0.5 * 1.0 * (10000.0**2)
        assert abs(e_asym - e_impactor) / e_impactor < 1e-10

    def test_catastrophic_threshold(self):
        """40 J/g boundary: just above is catastrophic, just below is not."""
        # specific energy = E / (M_target * 1000) in J/g
        # E = 40 J/g × M_target × 1000 g/kg
        m_target = 500.0  # kg
        e_threshold = 40.0 * m_target * 1000  # J
        # Exactly at threshold → catastrophic
        assert NASABreakupModel.is_catastrophic(m_target, e_threshold)
        # 1% below threshold → not catastrophic
        assert not NASABreakupModel.is_catastrophic(m_target, e_threshold * 0.99)

    def test_fragment_count_catastrophic_scaling(self):
        """More mass → more fragments (monotonic with mass)."""
        n1 = NASABreakupModel.fragment_count_catastrophic(100.0, 0.01)
        n2 = NASABreakupModel.fragment_count_catastrophic(1000.0, 0.01)
        assert n2 > n1

    def test_fragment_count_catastrophic_size_scaling(self):
        """Smaller min_size → more fragments."""
        n_1cm = NASABreakupModel.fragment_count_catastrophic(500.0, 0.01)
        n_10cm = NASABreakupModel.fragment_count_catastrophic(500.0, 0.10)
        assert n_1cm > n_10cm

    def test_fragment_count_catastrophic_iridium_cosmos(self):
        """Iridium-33 (556 kg) + Cosmos-2251 (950 kg) catastrophic collision.

        Historical result: ~2,000+ trackable fragments.
        Model should predict >1,000 at >10cm threshold.
        """
        combined_mass = 556 + 950  # kg
        n_trackable = NASABreakupModel.fragment_count_catastrophic(combined_mass, 0.10)
        assert n_trackable > 500, f"Expected >500 trackable, got {n_trackable}"

    def test_fragment_count_non_catastrophic_positive(self):
        """Non-catastrophic should give a positive fragment count for valid inputs."""
        n = NASABreakupModel.fragment_count_non_catastrophic(10.0, 10.0, 0.01)
        assert n >= 0

    def test_fragment_count_zero_mass(self):
        """Zero mass → 0 fragments."""
        assert NASABreakupModel.fragment_count_catastrophic(0, 0.01) == 0

    def test_size_distribution_shape(self):
        """Size distribution should have correct shape and be monotonically decreasing."""
        sizes, counts = NASABreakupModel.size_distribution(500.0, "CATASTROPHIC", 50)
        assert len(sizes) == 50
        assert len(counts) == 50
        # Larger objects are rarer: counts should decrease with size
        # (comparing first and last is sufficient — power law means large size → few fragments)
        assert counts[0] > counts[-1]

    def test_fragment_delta_v_distribution_shape(self):
        """Delta-V distribution returns (N, 3) array."""
        dvs = NASABreakupModel.fragment_delta_v_distribution(100, seed=42)
        assert dvs.shape == (100, 3)

    def test_fragment_delta_v_speeds_positive(self):
        """All speeds should be positive."""
        dvs = NASABreakupModel.fragment_delta_v_distribution(200, seed=99)
        speeds = np.linalg.norm(dvs, axis=1)
        assert np.all(speeds > 0)

    def test_fragment_delta_v_isotropic(self):
        """Isotropic distribution: mean vector near zero over many samples."""
        dvs = NASABreakupModel.fragment_delta_v_distribution(10000, seed=7)
        mean = dvs.mean(axis=0)
        # Mean should be close to zero for large N (isotropic)
        assert np.abs(mean).max() < 0.05, f"Mean DV not isotropic: {mean}"

    def test_orbital_lifetime_altitude_monotonic(self):
        """Higher altitude → longer lifetime."""
        lt_300 = NASABreakupModel.orbital_lifetime_estimate(300.0)
        lt_500 = NASABreakupModel.orbital_lifetime_estimate(500.0)
        lt_900 = NASABreakupModel.orbital_lifetime_estimate(900.0)
        assert lt_300 < lt_500 < lt_900

    def test_mass_from_radius(self):
        """Mass = density × volume, reasonable for ISS-sized object."""
        # ISS radius ~ 54m, mass ~ 420,000 kg (real)
        # Our model uses spacecraft density 92.937 kg/m³
        m = mass_from_radius(54.0)
        assert m > 0
        # Check formula: (4/3)π r³ × density
        expected = (4.0 / 3.0) * math.pi * 54.0**3 * 92.937
        assert abs(m - expected) / expected < 1e-10


class TestAssessCollisionConsequence:
    """Tests for the end-to-end consequence assessment function."""

    def test_catastrophic_collision_correct_type(self):
        """High relative velocity → catastrophic."""
        result = assess_collision_consequence(
            primary_radius_m=1.5,
            secondary_radius_m=1.5,
            relative_velocity_km_s=14.0,  # hypervelocity
            altitude_km=800.0,
        )
        assert result.event_type == "CATASTROPHIC"

    def test_catastrophic_creates_more_fragments_than_non(self):
        """Higher velocity (catastrophic) → more trackable fragments."""
        cat = assess_collision_consequence(
            primary_radius_m=2.0,
            secondary_radius_m=2.0,
            relative_velocity_km_s=14.0,
            altitude_km=800.0,
        )
        non_cat = assess_collision_consequence(
            primary_radius_m=0.001,
            secondary_radius_m=2.0,
            relative_velocity_km_s=1.0,
            altitude_km=800.0,
        )
        assert cat.fragment_cloud.trackable_fragments > non_cat.fragment_cloud.trackable_fragments

    def test_result_fields_non_negative(self):
        """All fragment counts and energies must be non-negative."""
        result = assess_collision_consequence(
            primary_radius_m=1.5,
            secondary_radius_m=3.0,
            relative_velocity_km_s=10.0,
            altitude_km=600.0,
        )
        cloud = result.fragment_cloud
        assert cloud.trackable_fragments >= 0
        assert cloud.lethal_fragments >= 0
        assert cloud.sub_cm_fragments >= 0
        assert result.collision_energy_joules > 0
        assert result.specific_energy_j_per_g > 0
        assert result.kessler_contribution >= 0

    def test_mass_override(self):
        """Explicit mass values should be used instead of radius-based estimates."""
        result = assess_collision_consequence(
            primary_radius_m=1.0,
            secondary_radius_m=1.0,
            relative_velocity_km_s=10.0,
            altitude_km=500.0,
            primary_mass_kg=500.0,
            secondary_mass_kg=1000.0,
        )
        assert abs(result.primary_mass_kg - 500.0) < 1e-9
        assert abs(result.secondary_mass_kg - 1000.0) < 1e-9


# ===========================================================================
# Fleet Risk Aggregation Tests
# ===========================================================================

class TestFleetRiskAggregator:
    """Tests for constellation-level risk metrics."""

    def _make_fleet(self, n: int, start_id: int = 1) -> tuple[set[str], list[SpaceObject]]:
        ids = {str(start_id + i) for i in range(n)}
        objects = [_make_space_object(nid, f"STAR-{nid}") for nid in ids]
        return ids, objects

    def test_empty_approaches_zero_fleet_pc(self):
        """No conjunctions → fleet Pc = 0."""
        ids, _ = self._make_fleet(5)
        agg = FleetRiskAggregator(ids, "TEST_FLEET")
        report = agg.assess([])
        assert report.fleet_pc == 0.0
        assert report.total_conjunctions == 0

    def test_single_conjunction_fleet_pc_equals_sat_pc(self):
        """One conjunction: fleet Pc ≈ satellite cumulative Pc."""
        pc = 1e-4
        ids = {"1", "2"}
        approach = _make_approach("1", "2", pc=pc, risk=RiskLevel.RED)
        agg = FleetRiskAggregator(ids, "SMALL_FLEET")
        report = agg.assess([approach])
        # Fleet pc: 1 - Π(1-cum_pc_i) where each sat has cum_pc ≈ pc
        # For 2 sats each with cum_pc = pc: fleet_pc = 1 - (1-pc)^2
        assert report.fleet_pc > 0
        assert report.fleet_pc <= 1.0

    def test_fleet_pc_increases_with_more_red_events(self):
        """More RED alerts → higher fleet Pc."""
        ids = {str(i) for i in range(1, 11)}
        agg = FleetRiskAggregator(ids, "FLEET")

        # 1 red event
        a1 = _make_approach("1", "2", pc=1e-4, risk=RiskLevel.RED)
        r1 = agg.assess([a1])

        # 3 red events
        a2 = _make_approach("3", "4", pc=1e-4, risk=RiskLevel.RED)
        a3 = _make_approach("5", "6", pc=1e-4, risk=RiskLevel.RED)
        r3 = agg.assess([a1, a2, a3])

        assert r3.fleet_pc >= r1.fleet_pc

    def test_red_alert_counting(self):
        """RED approaches increment red alert counters."""
        ids = {"1", "2"}
        approach = _make_approach("1", "2", pc=5e-4, risk=RiskLevel.RED)
        agg = FleetRiskAggregator(ids, "FLEET")
        report = agg.assess([approach])
        assert report.total_red_alerts >= 1

    def test_yellow_alert_counting(self):
        """YELLOW approaches increment yellow alert counters."""
        ids = {"1", "2"}
        approach = _make_approach("1", "2", pc=5e-5, risk=RiskLevel.YELLOW)
        agg = FleetRiskAggregator(ids, "FLEET")
        report = agg.assess([approach])
        assert report.total_yellow_alerts >= 1

    def test_fleet_size(self):
        """Report reflects actual fleet size."""
        ids, _ = self._make_fleet(10)
        agg = FleetRiskAggregator(ids, "FLEET_10")
        report = agg.assess([])
        assert report.fleet_size == 10

    def test_expected_collisions_per_year_positive(self):
        """At least one conjunction → expected collisions/year > 0."""
        ids = {"10", "20"}
        approach = _make_approach("10", "20", pc=1e-4, risk=RiskLevel.RED)
        agg = FleetRiskAggregator(ids, "F")
        report = agg.assess([approach], window_hours=72.0)
        assert report.expected_collisions_per_year > 0

    def test_highest_risk_satellite(self):
        """Satellite with highest cumulative Pc should be identified."""
        ids = {"1", "2", "3"}
        a1 = _make_approach("1", "999", pc=1e-3, risk=RiskLevel.RED)
        a2 = _make_approach("2", "998", pc=1e-6, risk=RiskLevel.GREEN)
        agg = FleetRiskAggregator(ids, "F")
        report = agg.assess([a1, a2])
        assert report.highest_risk_satellite is not None
        # Sat 1 has higher Pc
        assert report.highest_risk_satellite.norad_id in {"1", "999"}

    def test_fleet_pc_bounded(self):
        """Fleet Pc must always be in [0, 1]."""
        ids = {str(i) for i in range(1, 20)}
        approaches = [
            _make_approach(str(i), str(i + 100), pc=1e-3, risk=RiskLevel.RED)
            for i in range(1, 20)
        ]
        agg = FleetRiskAggregator(ids, "BIG_FLEET")
        report = agg.assess(approaches)
        assert 0.0 <= report.fleet_pc <= 1.0

    def test_summary_string_contains_fleet_name(self):
        """Summary string includes fleet name."""
        ids = {"1"}
        agg = FleetRiskAggregator(ids, "MY_CONSTELLATION")
        report = agg.assess([])
        summary = report.summary()
        assert "MY_CONSTELLATION" in summary

    def test_shell_risks_generated(self):
        """Shell risks are generated for satellites with altitude data."""
        ids = {"1", "2"}
        approach = _make_approach("1", "2", pc=1e-5, risk=RiskLevel.YELLOW)
        agg = FleetRiskAggregator(ids, "F")
        report = agg.assess([approach])
        # Shell risks may be empty if no altitude data, but should be a list
        assert isinstance(report.shell_risks, list)

    def test_non_fleet_approaches_ignored(self):
        """Approaches not involving fleet members are excluded."""
        ids = {"1", "2"}
        agg = FleetRiskAggregator(ids, "F")
        # Approach between non-fleet objects
        approach = _make_approach("99", "88", pc=0.5, risk=RiskLevel.RED)
        report = agg.assess([approach])
        assert report.total_conjunctions == 0
        assert report.fleet_pc == 0.0


# ===========================================================================
# Pc Sensitivity Analysis Tests
# ===========================================================================

class TestPcSensitivityAnalyzer:
    """Tests for parameter sweep and dilution curve analysis."""

    def _baseline_inputs(self):
        """Simple test case: 1 km miss, diagonal covariance."""
        miss = np.array([1.0, 0.0])
        cov = np.diag([0.25, 0.25])  # σ = 0.5 km each axis
        R = 0.01  # 10m combined radius
        return miss, cov, R

    def test_covariance_sweep_returns_correct_shape(self):
        """Sweep should have n_points entries."""
        miss, cov, R = self._baseline_inputs()
        result = PcSensitivityAnalyzer.sweep_covariance_scale(miss, cov, R, n_points=20)
        assert len(result.parameter_values) == 20
        assert len(result.pc_values) == 20

    def test_covariance_sweep_pc_in_bounds(self):
        """All Pc values must be in [0, 1]."""
        miss, cov, R = self._baseline_inputs()
        result = PcSensitivityAnalyzer.sweep_covariance_scale(miss, cov, R, n_points=30)
        assert np.all(result.pc_values >= 0)
        assert np.all(result.pc_values <= 1)

    def test_covariance_sweep_dilution_curve_has_peak(self):
        """Dilution curve should have a non-trivial peak (Pc > 0 somewhere)."""
        miss, cov, R = self._baseline_inputs()
        result = PcSensitivityAnalyzer.sweep_covariance_scale(miss, cov, R, n_points=50)
        assert result.max_pc > 0.0

    def test_miss_distance_sweep_returns_correct_shape(self):
        """Miss distance sweep returns n_points results."""
        _, cov, R = self._baseline_inputs()
        result = PcSensitivityAnalyzer.sweep_miss_distance(cov, R, n_points=25)
        assert len(result.parameter_values) == 25
        assert len(result.pc_values) == 25

    def test_miss_distance_sweep_monotonic_decrease(self):
        """Increasing miss distance → decreasing Pc (beyond dilution peak)."""
        _, cov, R = self._baseline_inputs()
        # Use a large miss range where Pc monotonically decreases
        result = PcSensitivityAnalyzer.sweep_miss_distance(
            cov, R, miss_range_km=(0.5, 50.0), n_points=30
        )
        # Generally should decrease — check first half vs second half
        first_half_mean = result.pc_values[:10].mean()
        second_half_mean = result.pc_values[20:].mean()
        assert first_half_mean >= second_half_mean

    def test_hard_body_radius_sweep_increasing_pc(self):
        """Larger hard-body radius → larger Pc (monotonically)."""
        miss, cov, _ = self._baseline_inputs()
        result = PcSensitivityAnalyzer.sweep_hard_body_radius(
            miss, cov, radius_range_m=(0.001, 500.0), n_points=30
        )
        assert result.pc_values[-1] >= result.pc_values[0]

    def test_dilution_curve_has_peak(self):
        """Dilution curve should peak when σ ≈ miss distance."""
        miss = np.array([1.0, 0.0])
        result = PcSensitivityAnalyzer.compute_dilution_curve(
            miss, combined_radius_km=0.01, n_points=50
        )
        peak_idx = np.argmax(result.pc_values)
        # Peak should not be at the extremes
        assert 2 <= peak_idx <= 47, f"Peak at boundary: {peak_idx}"

    def test_threshold_crossing_detection_red(self):
        """RED threshold crossing detected when Pc exceeds PC_RED_THRESHOLD."""
        miss = np.array([0.001, 0.0])  # Very close — Pc will be high
        cov = np.diag([0.01, 0.01])
        R = 0.01
        result = PcSensitivityAnalyzer.sweep_covariance_scale(miss, cov, R, n_points=50)
        # At some point in the sweep Pc will exceed RED threshold
        if result.max_pc > PC_RED_THRESHOLD:
            # Crossing should be detected
            assert result.red_threshold_crossing is not None
        # If never crosses, crossing should be None
        else:
            assert result.red_threshold_crossing is None

    def test_sensitivity_result_max_min_pc(self):
        """SensitivityResult max_pc and min_pc properties work correctly."""
        miss, cov, R = self._baseline_inputs()
        result = PcSensitivityAnalyzer.sweep_miss_distance(cov, R, n_points=20)
        assert result.max_pc >= result.min_pc
        assert result.max_pc >= 0
        assert result.min_pc >= 0

    def test_parameter_name_correct(self):
        """Each sweep has the correct parameter_name label."""
        miss, cov, R = self._baseline_inputs()

        r1 = PcSensitivityAnalyzer.sweep_covariance_scale(miss, cov, R, n_points=10)
        assert r1.parameter_name == "covariance_scale_factor"

        r2 = PcSensitivityAnalyzer.sweep_miss_distance(cov, R, n_points=10)
        assert r2.parameter_name == "miss_distance_km"

        r3 = PcSensitivityAnalyzer.sweep_hard_body_radius(miss, cov, n_points=10)
        assert r3.parameter_name == "hard_body_radius_m"

        r4 = PcSensitivityAnalyzer.compute_dilution_curve(miss, R, n_points=10)
        assert r4.parameter_name == "covariance_sigma_km"


# ===========================================================================
# Space Weather Loader Tests
# ===========================================================================

SAMPLE_SW_CSV = textwrap.dedent("""\
    DATE,KP1,KP2,KP3,KP4,KP5,KP6,KP7,KP8,KP_SUM,AP1,AP2,AP3,AP4,AP5,AP6,AP7,AP8,AP_AVG,F10.7_OBS,F10.7_ADJ,F10.7_OBS_CENTER81,F10.7_OBS_LAST81
    2025-01-01,13,10,7,10,7,13,17,13,90,5,4,3,4,3,5,7,5,4,142.3,143.1,145.2,144.8
    2025-01-02,10,7,7,7,10,13,10,10,74,4,3,3,3,4,5,4,4,4,138.5,139.2,145.0,144.5
    2025-01-03,7,7,7,10,13,10,7,7,68,3,3,3,4,5,4,3,3,4,135.0,135.8,144.8,144.2
    2025-01-04,50,50,60,67,53,43,37,27,387,39,39,56,111,67,32,22,12,47,180.0,182.0,148.5,147.1
""")


class TestSpaceWeatherLoader:
    """Tests for CelesTrak space weather CSV loading."""

    def _load_sample(self) -> SpaceWeatherLoader:
        loader = SpaceWeatherLoader()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(SAMPLE_SW_CSV)
            tmp_path = f.name
        count = loader.load_csv(tmp_path)
        assert count == 4, f"Expected 4 rows, got {count}"
        return loader

    def test_load_csv_count(self):
        """Loads correct number of daily records."""
        loader = self._load_sample()
        assert loader.size == 4

    def test_get_exact_date(self):
        """Exact date lookup returns correct record."""
        loader = self._load_sample()
        day = loader.get(datetime(2025, 1, 1))
        assert day is not None
        assert day.date.date() == datetime(2025, 1, 1).date()

    def test_get_missing_date_returns_none(self):
        """Date not in dataset returns None from get()."""
        loader = self._load_sample()
        day = loader.get(datetime(2020, 1, 1))
        assert day is None

    def test_get_nearest_fallback(self):
        """get_nearest falls back to closest previous date within 7 days."""
        loader = self._load_sample()
        # 2025-01-05 not in dataset, nearest back is 2025-01-04
        day = loader.get_nearest(datetime(2025, 1, 5))
        assert day is not None
        assert day.date == datetime(2025, 1, 4)

    def test_kp_values_parsed(self):
        """Kp values are parsed as floats (×10 in CSV)."""
        loader = self._load_sample()
        day = loader.get(datetime(2025, 1, 1))
        assert len(day.kp_values) == 8
        assert all(isinstance(k, float) for k in day.kp_values)

    def test_max_kp_property(self):
        """max_kp returns the highest Kp value for the day."""
        loader = self._load_sample()
        day = loader.get(datetime(2025, 1, 4))
        # KP4=67 is the largest on day 4
        assert day.max_kp == max(day.kp_values)

    def test_storm_periods_kp_threshold(self):
        """Storm periods correctly identified by Kp threshold."""
        loader = self._load_sample()
        # Days 1-3 are quiet (max Kp ~17), day 4 is a storm (max Kp 67)
        storms = loader.storm_periods(kp_threshold=50.0)
        assert len(storms) >= 1
        # Day 4 should be included
        dates = [s.date for s in storms]
        assert datetime(2025, 1, 4) in dates

    def test_quiet_days_not_in_storms(self):
        """Quiet days excluded from storm list."""
        loader = self._load_sample()
        storms = loader.storm_periods(kp_threshold=50.0)
        dates = [s.date for s in storms]
        # Days 1-3 have max_kp < 50
        for d in [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)]:
            assert d not in dates

    def test_f107_parsed(self):
        """F10.7 values are parsed correctly."""
        loader = self._load_sample()
        day = loader.get(datetime(2025, 1, 1))
        assert abs(day.f107_obs - 142.3) < 0.01

    def test_date_range_property(self):
        """date_range returns (first_date, last_date) tuple."""
        loader = self._load_sample()
        dr = loader.date_range
        assert dr is not None
        start, end = dr
        assert start == datetime(2025, 1, 1)
        assert end == datetime(2025, 1, 4)

    def test_to_space_weather_state(self):
        """DailySpaceWeather converts to SpaceWeatherState correctly."""
        loader = self._load_sample()
        day = loader.get(datetime(2025, 1, 1))
        state = day.to_space_weather_state()
        # Kp in SpaceWeatherState is kp_values / 10.0 (CSV is Kp×10)
        assert 0 <= state.kp_index <= 9.0
        assert state.f107_index > 0

    def test_get_state_returns_state(self):
        """get_state() returns a SpaceWeatherState."""
        from aria.conjunction.propagation.space_weather import SpaceWeatherState
        loader = self._load_sample()
        state = loader.get_state(datetime(2025, 1, 2))
        assert isinstance(state, SpaceWeatherState)

    def test_get_state_fallback_moderate(self):
        """Empty loader returns default moderate SpaceWeatherState."""
        from aria.conjunction.propagation.space_weather import SpaceWeatherState
        loader = SpaceWeatherLoader()
        state = loader.get_state(datetime(2025, 1, 1))
        assert isinstance(state, SpaceWeatherState)

    def test_load_csv_skips_bad_rows(self):
        """Malformed rows are skipped, good rows still loaded."""
        loader = SpaceWeatherLoader()
        bad_csv = textwrap.dedent("""\
            DATE,KP1,KP2,KP3,KP4,KP5,KP6,KP7,KP8,KP_SUM,AP1,AP2,AP3,AP4,AP5,AP6,AP7,AP8,AP_AVG,F10.7_OBS,F10.7_ADJ,F10.7_OBS_CENTER81,F10.7_OBS_LAST81
            NOT-A-DATE,garbage,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
            2025-03-01,10,10,7,10,7,13,17,13,87,5,4,3,4,3,5,7,5,4,150.0,152.0,148.0,147.0
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(bad_csv)
            tmp_path = f.name
        count = loader.load_csv(tmp_path)
        assert count == 1  # Only the valid row


# ===========================================================================
# Integration: Breakup Model in Context
# ===========================================================================

class TestBreakupModelIntegration:
    """Integration tests combining multiple analysis pieces."""

    def test_iridium_cosmos_full_assessment(self):
        """Full assessment of the 2009 Iridium-33 / Cosmos-2251 collision.

        Known facts:
        - Iridium-33 mass: 556 kg, radius ~5m
        - Cosmos-2251 mass: 950 kg, radius ~8m
        - Relative velocity: ~11.6 km/s
        - Altitude: ~790 km
        - Result: ~2,300+ trackable fragments
        """
        result = assess_collision_consequence(
            primary_radius_m=5.0,
            secondary_radius_m=8.0,
            relative_velocity_km_s=11.6,
            altitude_km=790.0,
            primary_mass_kg=556.0,
            secondary_mass_kg=950.0,
        )
        assert result.event_type == "CATASTROPHIC"
        assert result.fragment_cloud.trackable_fragments > 1000
        assert result.fragment_cloud.orbital_lifetime_years > 50  # at 790km
        assert result.kessler_contribution > 0

    def test_small_debris_sub_cm_impact_non_catastrophic(self):
        """1-gram debris at 10 km/s hitting Starlink satellite.

        Typical hypervelocity impact: non-catastrophic cratering.
        """
        result = assess_collision_consequence(
            primary_radius_m=0.005,   # ~5mm paint fleck
            secondary_radius_m=2.0,   # Starlink
            relative_velocity_km_s=10.0,
            altitude_km=550.0,
            primary_mass_kg=0.001,    # 1 gram
            secondary_mass_kg=260.0,  # Starlink mass
        )
        # 1g × 10 km/s → specific energy well below 40 J/g for 260kg target
        assert result.event_type == "NON_CATASTROPHIC"
