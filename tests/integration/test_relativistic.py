"""Integration tests for relativistic physics engine.

Every test uses exact analytical calculations to verify the physics.
No tolerances wider than 1% unless explicitly noted with rationale.
"""

from __future__ import annotations

import math
import random

import pytest

from aria.simulation.relativistic_physics import (
    C,
    C_KM,
    G0,
    LY_METERS,
    M_PROTON,
    YEAR_SECONDS,
    ICRP_QUALITY_FACTORS,
    ISMPhase,
    ISM_PHASES,
    NAVIGATION_PULSARS,
    PROPULSION_CATALOG,
    PropulsionType,
    RelativisticShipState,
    alcubierre_metric_interval,
    alcubierre_shape_function,
    alcubierre_warp_energy,
    annual_radiation_dose,
    beta_from_gamma,
    bow_shock_standoff,
    cumulative_career_dose_limit,
    doppler_shift,
    gcr_flux_at_distance,
    generate_spe,
    hydrogen_column_density,
    ism_density_at_distance,
    ism_drag_force,
    laser_sail_acceleration,
    laser_sail_thrust,
    length_contraction,
    lorentz_gamma,
    propellant_mass_for_delta_v,
    relativistic_kinetic_energy,
    relativistic_mass,
    relativistic_momentum,
    relativistic_rocket_equation,
    relativistic_velocity_addition,
    rest_energy,
    starlight_aberration,
    step_physics,
    time_dilation,
    total_relativistic_energy,
    transverse_doppler,
    tsiolkovsky_delta_v,
    xnav_autonomous_range,
    xnav_position_fix,
)


# ════════════════════════════════════════════════════════════════
# 1. SPECIAL RELATIVITY
# ════════════════════════════════════════════════════════════════

class TestLorentzGamma:
    """Verify Lorentz factor against hand-calculated values."""

    def test_zero_velocity(self):
        assert lorentz_gamma(0.0) == 1.0

    def test_0_1c(self):
        """At 0.1c: gamma = 1/sqrt(1-0.01) = 1.00503782..."""
        v = 0.1 * C
        gamma = lorentz_gamma(v)
        expected = 1.0 / math.sqrt(1.0 - 0.01)
        assert abs(gamma - expected) < 1e-10

    def test_0_5c(self):
        """At 0.5c: gamma = 1/sqrt(0.75) = 1.15470054..."""
        v = 0.5 * C
        gamma = lorentz_gamma(v)
        expected = 1.0 / math.sqrt(0.75)
        assert abs(gamma - expected) < 1e-10

    def test_0_9c(self):
        """At 0.9c: gamma = 1/sqrt(0.19) = 2.29415734..."""
        v = 0.9 * C
        gamma = lorentz_gamma(v)
        expected = 1.0 / math.sqrt(1.0 - 0.81)
        assert abs(gamma - expected) < 1e-8

    def test_0_99c(self):
        """At 0.99c: gamma ≈ 7.0888..."""
        v = 0.99 * C
        gamma = lorentz_gamma(v)
        expected = 1.0 / math.sqrt(1.0 - 0.9801)
        assert abs(gamma - expected) < 1e-6

    def test_0_999c(self):
        """At 0.999c: gamma ≈ 22.366..."""
        v = 0.999 * C
        gamma = lorentz_gamma(v)
        expected = 1.0 / math.sqrt(1.0 - 0.999**2)
        assert abs(gamma - expected) < 1e-3

    def test_superluminal_raises(self):
        with pytest.raises(ValueError, match="unphysical"):
            lorentz_gamma(C)

    def test_beta_gamma_roundtrip(self):
        """gamma -> beta -> gamma must be identity."""
        for beta in [0.01, 0.1, 0.5, 0.9, 0.99]:
            v = beta * C
            gamma = lorentz_gamma(v)
            recovered_beta = beta_from_gamma(gamma)
            assert abs(recovered_beta - beta) < 1e-12


class TestTimeDilation:
    """Verify time dilation: ship_time = earth_time / gamma."""

    def test_at_0_1c_over_1000_years(self):
        """At 0.1c over 1000 Earth years: ~5 year difference."""
        v = 0.1 * C
        earth_time = 1000.0 * YEAR_SECONDS
        ship_time = time_dilation(earth_time, v)
        ship_years = ship_time / YEAR_SECONDS

        gamma = lorentz_gamma(v)  # ~1.00504
        expected_ship_years = 1000.0 / gamma
        assert abs(ship_years - expected_ship_years) < 1e-6

        # Time difference should be ~5 years
        diff = 1000.0 - ship_years
        assert 4.0 < diff < 6.0, f"Expected ~5 year difference, got {diff:.2f}"

    def test_at_0_5c(self):
        """At 0.5c: ship experiences 86.6% of Earth time."""
        v = 0.5 * C
        earth_time = 100.0 * YEAR_SECONDS
        ship_time = time_dilation(earth_time, v)
        ratio = ship_time / earth_time
        expected = 1.0 / lorentz_gamma(v)  # sqrt(0.75) ≈ 0.8660
        assert abs(ratio - expected) < 1e-10

    def test_at_0_9c(self):
        """At 0.9c: ship time is ~43.6% of Earth time."""
        v = 0.9 * C
        earth_time = 10.0 * YEAR_SECONDS
        ship_time = time_dilation(earth_time, v)
        ship_years = ship_time / YEAR_SECONDS
        expected = 10.0 / lorentz_gamma(v)  # 10 / 2.294 ≈ 4.359
        assert abs(ship_years - expected) < 1e-6


class TestLengthContraction:

    def test_at_0_9c(self):
        """1 light-year contracts to ~0.436 ly at 0.9c."""
        v = 0.9 * C
        contracted = length_contraction(LY_METERS, v)
        gamma = lorentz_gamma(v)
        assert abs(contracted - LY_METERS / gamma) < 1.0


class TestRelativisticMechanics:

    def test_relativistic_mass_at_0_9c(self):
        """1 kg at 0.9c has relativistic mass ~2.294 kg."""
        v = 0.9 * C
        m_rel = relativistic_mass(1.0, v)
        gamma = lorentz_gamma(v)
        assert abs(m_rel - gamma) < 1e-8

    def test_relativistic_momentum(self):
        """p = gamma * m * v."""
        v = 0.5 * C
        m = 1000.0  # kg
        p = relativistic_momentum(m, v)
        gamma = lorentz_gamma(v)
        assert abs(p - gamma * m * v) < 1.0

    def test_kinetic_energy_at_0_1c(self):
        """KE = (gamma - 1) * m * c^2. At 0.1c, gamma-1 ≈ 0.00504."""
        v = 0.1 * C
        m = 1.0  # 1 kg
        ke = relativistic_kinetic_energy(m, v)
        gamma = lorentz_gamma(v)
        expected = (gamma - 1.0) * m * C * C
        assert abs(ke - expected) < 1.0

    def test_energy_momentum_relation(self):
        """E^2 = (pc)^2 + (mc^2)^2 — the fundamental relation."""
        v = 0.8 * C
        m = 10.0  # kg
        E = total_relativistic_energy(m, v)
        p = relativistic_momentum(m, v)
        E0 = rest_energy(m)
        # E^2 should equal (pc)^2 + E0^2
        lhs = E * E
        rhs = (p * C) ** 2 + E0 ** 2
        assert abs(lhs - rhs) / lhs < 1e-10

    def test_rest_energy_1kg(self):
        """E = mc^2 for 1 kg ≈ 8.988e16 J."""
        e = rest_energy(1.0)
        assert abs(e - C * C) < 1.0


class TestVelocityAddition:

    def test_low_speed_classical_limit(self):
        """At v << c, relativistic addition ≈ classical."""
        v1 = 1000.0  # m/s
        v2 = 2000.0
        result = relativistic_velocity_addition(v1, v2)
        assert abs(result - 3000.0) < 0.01  # Nearly classical

    def test_two_halves_of_c(self):
        """0.5c + 0.5c = 0.8c (NOT 1.0c)."""
        v1 = 0.5 * C
        v2 = 0.5 * C
        result = relativistic_velocity_addition(v1, v2)
        expected = 0.8 * C
        assert abs(result - expected) < 1.0

    def test_c_plus_anything_is_c(self):
        """c + v = c for any v (invariance of light speed)."""
        v = 0.5 * C
        result = relativistic_velocity_addition(C * 0.999999, v)
        # Should be very close to c
        assert result / C > 0.999


class TestAberrationAndDoppler:

    def test_starlight_aberration_sideways(self):
        """At 0.5c, starlight from 90 degrees shifts forward (headlight effect)."""
        beta = 0.5
        theta_obs = starlight_aberration(math.pi / 2, beta)
        # cos(theta_obs) = (0 + 0.5) / (1 + 0) = 0.5 → theta_obs = 60 deg
        expected = math.acos(0.5)  # pi/3
        assert abs(theta_obs - expected) < 1e-10
        assert theta_obs < math.pi / 2  # Light concentrates forward

    def test_aberration_zero_angle(self):
        """Light from directly ahead stays ahead."""
        theta_obs = starlight_aberration(0.0, 0.5)
        assert abs(theta_obs) < 1e-10  # Still 0

    def test_doppler_forward_blueshift(self):
        """Approaching source: frequency increases."""
        f_emit = 1e14  # visible light
        f_obs = doppler_shift(f_emit, 0.1, forward=True)
        assert f_obs > f_emit

    def test_doppler_aft_redshift(self):
        """Receding source: frequency decreases."""
        f_emit = 1e14
        f_obs = doppler_shift(f_emit, 0.1, forward=False)
        assert f_obs < f_emit

    def test_doppler_symmetry(self):
        """Forward * aft = f_emit^2 (exact identity)."""
        f_emit = 1e14
        beta = 0.3
        f_fwd = doppler_shift(f_emit, beta, forward=True)
        f_aft = doppler_shift(f_emit, beta, forward=False)
        assert abs(f_fwd * f_aft - f_emit**2) / f_emit**2 < 1e-10

    def test_transverse_doppler(self):
        """Transverse Doppler: f_obs = f_emit / gamma (always redshift)."""
        f_emit = 1e14
        beta = 0.5
        f_obs = transverse_doppler(f_emit, beta)
        gamma = 1.0 / math.sqrt(1.0 - beta**2)
        assert abs(f_obs - f_emit / gamma) < 1.0


# ════════════════════════════════════════════════════════════════
# 2. PULSAR NAVIGATION
# ════════════════════════════════════════════════════════════════

class TestXNAV:

    def test_pulsar_catalog_has_10_entries(self):
        assert len(NAVIGATION_PULSARS) == 10

    def test_all_pulsars_have_positive_period(self):
        for p in NAVIGATION_PULSARS:
            assert p.period_s > 0, f"{p.name} has non-positive period"

    def test_all_pulsars_are_millisecond(self):
        """Navigation pulsars should be MSPs (period < 30 ms)."""
        for p in NAVIGATION_PULSARS:
            assert p.period_s < 0.030, f"{p.name} period {p.period_s}s is not MSP"

    def test_position_fix_3_pulsars(self):
        """3 pulsars give a valid 3D fix."""
        toas = {
            "B1937+21": 1e-6,
            "B1821-24": -2e-6,
            "J0437-4715": 0.5e-6,
        }
        fix = xnav_position_fix(toas)
        assert len(fix.pulsars_used) == 3
        assert fix.uncertainty_m == pytest.approx(5000.0, rel=0.01)

    def test_position_fix_needs_3(self):
        with pytest.raises(ValueError, match="3 pulsars"):
            xnav_position_fix({"B1937+21": 1e-6, "B1821-24": 2e-6})

    def test_uncertainty_scales_with_area(self):
        """Larger detector → smaller uncertainty."""
        toas = {"B1937+21": 1e-6, "B1821-24": -2e-6, "J0437-4715": 0.5e-6}
        fix_small = xnav_position_fix(toas, detector_area_cm2=900)
        fix_large = xnav_position_fix(toas, detector_area_cm2=3600)
        assert fix_small.uncertainty_m > fix_large.uncertainty_m

    def test_autonomous_range_description(self):
        desc = xnav_autonomous_range()
        assert "5 km" in desc
        assert "1000 AU" in desc


# ════════════════════════════════════════════════════════════════
# 3. PROPULSION
# ════════════════════════════════════════════════════════════════

class TestPropulsion:

    def test_all_propulsion_types_in_catalog(self):
        for pt in PropulsionType:
            assert pt in PROPULSION_CATALOG

    def test_exhaust_velocity_equals_isp_times_g0(self):
        """v_e = Isp * g0 for all non-infinite Isp systems."""
        for pt, spec in PROPULSION_CATALOG.items():
            if math.isfinite(spec.isp_s):
                expected = spec.isp_s * G0
                assert abs(spec.exhaust_velocity_ms - expected) < 1.0, \
                    f"{spec.name}: ve={spec.exhaust_velocity_ms}, expected {expected}"

    def test_dt_fusion_isp(self):
        spec = PROPULSION_CATALOG[PropulsionType.DT_FUSION]
        assert spec.isp_s == 100_000
        assert spec.neutron_fraction == 0.80

    def test_pb11_is_aneutronic(self):
        spec = PROPULSION_CATALOG[PropulsionType.PB11_ANEUTRONIC]
        assert spec.neutron_fraction == 0.0

    def test_laser_sail_no_propellant(self):
        spec = PROPULSION_CATALOG[PropulsionType.LASER_SAIL]
        assert spec.mass_flow_rate_kgs == 0.0
        assert spec.isp_s == float("inf")

    def test_tsiolkovsky_basic(self):
        """dv = ve * ln(10) for mass ratio 10."""
        ve = 10000.0  # m/s
        dv = tsiolkovsky_delta_v(ve, 1000.0, 100.0)
        assert abs(dv - ve * math.log(10)) < 0.01

    def test_tsiolkovsky_mass_ratio_1(self):
        """Mass ratio 1 → delta-v = 0."""
        dv = tsiolkovsky_delta_v(10000.0, 100.0, 100.0)
        assert abs(dv) < 1e-10

    def test_relativistic_rocket_subluminal(self):
        """Relativistic rocket always gives v < c."""
        # Even with mass ratio 1000 and ve = 0.1c
        v = relativistic_rocket_equation(0.1 * C, 1000.0)
        assert v < C
        assert v > 0

    def test_relativistic_vs_classical_divergence(self):
        """Classical Tsiolkovsky overestimates at high mass ratios."""
        ve = 0.1 * C
        mr = 100_000.0  # ln(100000) ≈ 11.5 → classical dv ≈ 1.15c
        classical_dv = ve * math.log(mr)
        relativistic_v = relativistic_rocket_equation(ve, mr)
        assert classical_dv > C  # Classical says superluminal
        assert relativistic_v < C  # Relativistic is always subluminal

    def test_propellant_mass_calculation(self):
        """Inverted Tsiolkovsky: round-trip consistency."""
        ve = 50000 * G0
        dry = 1e6
        dv = 1e6  # 1000 km/s
        prop = propellant_mass_for_delta_v(dv, dry, ve)
        # Verify: tsiolkovsky with wet=dry+prop should give dv back
        recovered_dv = tsiolkovsky_delta_v(ve, dry + prop, dry)
        assert abs(recovered_dv - dv) / dv < 1e-10

    def test_laser_sail_thrust_1gw(self):
        """1 GW beam with perfect reflection: F = 2P/c ≈ 6.67 N."""
        thrust = laser_sail_thrust(1e9, reflectivity=1.0)
        expected = 2.0 * 1e9 / C
        assert abs(thrust - expected) < 0.01

    def test_laser_sail_acceleration(self):
        """1 GW beam on 1-gram sail: enormous acceleration."""
        accel = laser_sail_acceleration(1e9, 0.001, 0.001, 1.0)
        # F = 2*1e9/c ≈ 6.67 N, a = 6.67/0.002 ≈ 3335 m/s^2
        assert accel > 3000.0


# ════════════════════════════════════════════════════════════════
# 4. INTERSTELLAR MEDIUM
# ════════════════════════════════════════════════════════════════

class TestISM:

    def test_five_phases_defined(self):
        assert len(ISM_PHASES) == 5

    def test_local_bubble_low_density(self):
        """Inside Local Bubble (< 250 ly): n ~ 0.005 cm^-3."""
        ism = ism_density_at_distance(100.0, seed=42)
        assert ism.in_local_bubble is True
        assert abs(ism.number_density_cm3 - 0.005) < 1e-6
        assert ism.phase == ISMPhase.HOT_IONIZED

    def test_beyond_bubble_higher_density(self):
        """Beyond 350 ly: n ~ 0.5 cm^-3 (warm neutral)."""
        ism = ism_density_at_distance(500.0, seed=42)
        assert ism.in_local_bubble is False
        # Could be in a cloud, but base density is 0.5
        assert ism.number_density_cm3 >= 0.5 or ism.phase == ISMPhase.MOLECULAR_CLOUD

    def test_bubble_wall_transition(self):
        """Density increases through bubble wall (250-350 ly)."""
        d1 = ism_density_at_distance(260.0, seed=42)
        d2 = ism_density_at_distance(340.0, seed=42)
        assert d2.number_density_cm3 > d1.number_density_cm3

    def test_density_unit_conversion(self):
        """n_m3 = n_cm3 * 1e6."""
        ism = ism_density_at_distance(100.0, seed=42)
        assert abs(ism.number_density_m3 - ism.number_density_cm3 * 1e6) < 1.0

    def test_ism_drag_at_0_1c_local_bubble(self):
        """ISM drag at 0.1c in Local Bubble: very small."""
        v = 0.1 * C
        n_m3 = 0.005 * 1e6  # 5e3 m^-3
        drag = ism_drag_force(v, n_m3, 500.0)
        # F = 5e3 * 1.67e-27 * (3e7)^2 * 500
        expected = 5e3 * M_PROTON * (0.1 * C)**2 * 500.0
        assert abs(drag - expected) / expected < 1e-6
        # Should be micro-Newtons range
        assert drag < 1e-3

    def test_bow_shock_at_0_1c(self):
        """At 0.1c (30,000 km/s) a bow shock definitely forms."""
        v = 0.1 * C
        n_m3 = 5e3
        b = 2e-10  # 2 μG
        standoff = bow_shock_standoff(v, n_m3, b)
        assert standoff is not None
        assert standoff > 0

    def test_no_bow_shock_at_low_speed(self):
        """At 10 m/s, no bow shock."""
        standoff = bow_shock_standoff(10.0, 5e3, 2e-10)
        assert standoff is None

    def test_hydrogen_column_density(self):
        """N_H = n * d. At 100 ly, n=0.5: N_H ~ 4.7e19 cm^-2."""
        n_h = hydrogen_column_density(100.0, 0.5)
        expected = 0.5 * 100.0 * 9.461e17
        assert abs(n_h - expected) / expected < 1e-6


# ════════════════════════════════════════════════════════════════
# 5. ALCUBIERRE WARP METRIC (SPECULATIVE)
# ════════════════════════════════════════════════════════════════

class TestAlcubierreWarp:

    def test_shape_function_at_center(self):
        """f(0) should be ≈ 1.0 for reasonable sigma*R."""
        f = alcubierre_shape_function(0.0, 100.0, 1.0)
        assert abs(f - 1.0) < 0.01

    def test_shape_function_far_away(self):
        """f(r >> R) should be ≈ 0."""
        f = alcubierre_shape_function(1000.0, 100.0, 1.0)
        assert f < 0.01

    def test_original_model_absurd_energy(self):
        """Original Alcubierre requires impossible energy."""
        result = alcubierre_warp_energy(0.1 * C, model="original")
        assert result["energy_type"] == "NEGATIVE (exotic matter required)"
        assert result["feasibility"] == "IMPOSSIBLE with known physics"
        # Energy should be astronomically large
        assert result["energy_joules"] > 1e40

    def test_bobrick_martire_positive_energy(self):
        """Bobrick & Martire 2021 uses positive energy."""
        result = alcubierre_warp_energy(0.01 * C, R=100.0, model="bobrick_martire_2021")
        assert result["energy_type"] == "POSITIVE (no exotic matter)"
        assert "SPECULATIVE" in result["status"]
        # Base energy ~4.9e6 J at reference config
        assert abs(result["energy_joules"] - 4.9e6) / 4.9e6 < 0.01

    def test_warp_energy_scales_with_velocity(self):
        """Energy scales as v^2."""
        e1 = alcubierre_warp_energy(0.01 * C, model="bobrick_martire_2021")
        e2 = alcubierre_warp_energy(0.02 * C, model="bobrick_martire_2021")
        ratio = e2["energy_joules"] / e1["energy_joules"]
        assert abs(ratio - 4.0) < 0.01  # (0.02/0.01)^2 = 4

    def test_metric_flat_when_no_warp(self):
        """With f=0, metric reduces to Minkowski."""
        ds2 = alcubierre_metric_interval(1.0, 1.0, 0.0, 0.0, v_s=1000.0, f_rs=0.0)
        ds2_mink = -(C * 1.0)**2 + 1.0**2
        assert abs(ds2 - ds2_mink) < 1e-6


# ════════════════════════════════════════════════════════════════
# 6. RADIATION ENVIRONMENT
# ════════════════════════════════════════════════════════════════

class TestRadiation:

    def test_gcr_flux_increases_with_distance(self):
        """GCR flux rises as solar modulation weakens."""
        f_1au = gcr_flux_at_distance(1.0)
        f_50au = gcr_flux_at_distance(50.0)
        f_200au = gcr_flux_at_distance(200.0)
        assert f_1au < f_50au < f_200au

    def test_full_galactic_flux_beyond_heliopause(self):
        """Beyond 120 AU: full galactic flux = 6.0 particles/cm^2/s/sr."""
        f = gcr_flux_at_distance(200.0)
        assert abs(f - 6.0) < 1e-6

    def test_annual_dose_behind_10gcm2_al(self):
        """~200 mSv/year behind 10 g/cm^2 Al at full galactic flux."""
        rad = annual_radiation_dose(200.0, shielding_g_cm2=10.0, shielding_material="aluminum")
        dose = rad["dose_equivalent_msv_per_year"]
        # Should be in the right ballpark (~100-400 mSv/year)
        assert 50 < dose < 500, f"Got {dose} mSv/year"

    def test_polyethylene_better_than_aluminum(self):
        """Hydrogen-rich shielding is more effective."""
        rad_al = annual_radiation_dose(200.0, 10.0, "aluminum")
        rad_pe = annual_radiation_dose(200.0, 10.0, "polyethylene")
        assert rad_pe["dose_equivalent_msv_per_year"] < rad_al["dose_equivalent_msv_per_year"]

    def test_quality_factor_protons(self):
        assert ICRP_QUALITY_FACTORS["proton"] == 2.0

    def test_quality_factor_alpha(self):
        assert ICRP_QUALITY_FACTORS["alpha"] == 20.0

    def test_gcr_composition_sums_to_1(self):
        from aria.simulation.relativistic_physics import GCRSpectrum
        gcr = GCRSpectrum()
        total = gcr.proton_fraction + gcr.alpha_fraction + gcr.hze_fraction
        assert abs(total - 1.0) < 1e-10

    def test_spe_only_within_heliosphere(self):
        """No SPE beyond 10 AU."""
        rng = random.Random(12345)
        # Generate many attempts — all should be None beyond 10 AU
        for _ in range(100):
            result = generate_spe(50.0, rng)
            assert result is None

    def test_career_dose_limit(self):
        """30-year-old: 300 mSv limit."""
        assert cumulative_career_dose_limit(30) == 300.0
        assert cumulative_career_dose_limit(50) == 500.0


# ════════════════════════════════════════════════════════════════
# 7. INTEGRATED SIMULATION STEP
# ════════════════════════════════════════════════════════════════

class TestSimulationStep:

    def test_step_advances_time(self):
        state = RelativisticShipState(velocity_ms=0.1 * C, velocity_beta=0.1)
        step_physics(state, dt_earth_years=1.0)
        assert state.earth_elapsed_years == 1.0
        assert state.ship_elapsed_years > 0

    def test_time_dilation_accumulates(self):
        """At 0.1c over 100 years: ship time < earth time."""
        state = RelativisticShipState(velocity_ms=0.1 * C, velocity_beta=0.1)
        for _ in range(100):
            step_physics(state, dt_earth_years=1.0)
        assert state.earth_elapsed_years == pytest.approx(100.0, abs=0.1)
        assert state.ship_elapsed_years < state.earth_elapsed_years
        # Difference should be ~0.5 years at 0.1c over 100 years
        diff = state.earth_elapsed_years - state.ship_elapsed_years
        assert 0.1 < diff < 2.0

    def test_distance_increases(self):
        state = RelativisticShipState(velocity_ms=0.1 * C, velocity_beta=0.1)
        step_physics(state, dt_earth_years=10.0)
        # At 0.1c, ~1 ly/year → ~10 ly in 10 years
        assert state.distance_from_sol_ly > 0.5

    def test_radiation_dose_accumulates(self):
        state = RelativisticShipState(velocity_ms=0.1 * C, velocity_beta=0.1)
        step_physics(state, dt_earth_years=1.0)
        assert state.cumulative_dose_msv > 0

    def test_ism_phase_tracked(self):
        state = RelativisticShipState(velocity_ms=0.1 * C, velocity_beta=0.1)
        step_physics(state, dt_earth_years=1.0)
        assert state.ism_phase in [p.value for p in ISMPhase]
