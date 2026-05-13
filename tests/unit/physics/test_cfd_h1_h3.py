"""Unit tests for Pod H1 + H3 — habitat CFD primitives (P1-5).

Canonical benchmarks:
  - NIST WebBook — dry-air composition, γ, c_p, μ, c_sound.
  - White 2006 *Viscous Fluid Flow* 3rd ed §1.4 — Sutherland air.
  - Incropera et al. 2011 *Fundamentals of Heat and Mass Transfer*
    7th ed Table A.4 — dry-air Pr.
  - Schlichting & Gersten 2017 *Boundary-Layer Theory* 9th ed §6.2 —
    Blasius flat plate.
  - Pope 2000 *Turbulent Flows* §7.1 eq. 7.43 — log-law of the wall.
  - Toro 2009 *Riemann Solvers and Numerical Methods for Fluid
    Dynamics* 3rd ed Table 4.1 — Sod shock tube star state.
  - Son, Zhang, Lu 2015 SAE 2015-01-2443 — ISS US-Lab turnover time.
  - Churchill & Chu 1975 *Int J Heat Mass Transfer* 18 1323 — vertical
    plate Nusselt.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.cfd import (
    AIR_STANDARD,
    AIR_SUTHERLAND,
    CFL_EXPLICIT_LIMIT,
    FlowRegime,
    K_EPSILON_STANDARD,
    SodExactSolution,
    blasius_displacement_thickness_over_x,
    blasius_skin_friction_coefficient,
    cfl_time_step_bound,
    classify_pipe_flow,
    classify_plate_flow,
    friction_velocity,
    grashof_number,
    ideal_gas_density,
    ideal_gas_pressure,
    iss_cabin_turnover_time_s,
    law_of_the_wall_u_plus,
    mach_number,
    nusselt_churchill_chu_vertical_plate,
    prandtl_number,
    rayleigh_number,
    reynolds_number,
    sod_exact_post_shock_state,
    specific_gas_constant,
    speed_of_sound,
    sutherland_viscosity,
    turbulent_viscosity_k_epsilon,
)
from aria.physics.cfd.equation_of_state import GasMixture


# ──────────────────────────────────────────────────────────────────────
#  Equation of state
# ──────────────────────────────────────────────────────────────────────


def test_specific_gas_constant_dry_air_287():
    """R_specific = R_u/M should reproduce the NIST ≈ 287.05 J/(kg·K)."""
    r = specific_gas_constant(AIR_STANDARD)
    assert 285.0 < r < 289.0, f"R_specific = {r:.2f}"


def test_ideal_gas_density_standard_atmosphere():
    """1 atm, 288.15 K → ρ ≈ 1.225 kg/m³ (ISA)."""
    rho = ideal_gas_density(pressure_pa=101325.0, temperature_k=288.15)
    assert 1.21 < rho < 1.24, f"ρ = {rho:.3f}"


def test_ideal_gas_pressure_roundtrip():
    rho = 1.225
    p = ideal_gas_pressure(density_kg_m3=rho, temperature_k=288.15)
    assert p == pytest.approx(101325.0, rel=5.0e-3)


def test_speed_of_sound_dry_air_293k():
    """Canonical c ≈ 343 m/s at 293.15 K."""
    c = speed_of_sound(temperature_k=293.15)
    assert 340.0 < c < 345.0, f"c = {c:.2f}"


def test_gas_mixture_rejects_unnormalized():
    with pytest.raises(ValueError):
        GasMixture(mass_fractions={"N2": 0.5, "O2": 0.3})


def test_gas_mixture_rejects_unknown_species():
    with pytest.raises(KeyError):
        GasMixture(mass_fractions={"Xe": 1.0})


# ──────────────────────────────────────────────────────────────────────
#  Sutherland viscosity
# ──────────────────────────────────────────────────────────────────────


def test_sutherland_air_293k_matches_nist():
    """NIST/Incropera: μ_air(293.15 K) ≈ 1.82×10⁻⁵ Pa·s."""
    mu = sutherland_viscosity(temperature_k=293.15)
    assert 1.79e-5 < mu < 1.84e-5, f"μ = {mu:.3e}"


def test_sutherland_air_500k_monotone():
    """Viscosity of an ideal gas increases with T."""
    mu_low = sutherland_viscosity(temperature_k=300.0)
    mu_hi = sutherland_viscosity(temperature_k=500.0)
    assert mu_hi > mu_low


def test_sutherland_rejects_nonpositive_t():
    with pytest.raises(ValueError):
        sutherland_viscosity(temperature_k=0.0)


# ──────────────────────────────────────────────────────────────────────
#  Dimensionless numbers
# ──────────────────────────────────────────────────────────────────────


def test_reynolds_number_pipe():
    """Pipe flow Re = ρUD/μ for water-like values."""
    re = reynolds_number(
        density_kg_m3=1000.0, velocity_m_s=1.0, length_m=0.05, dynamic_viscosity_pa_s=1.0e-3
    )
    assert re == pytest.approx(50000.0)


def test_mach_number_low():
    """ISS cabin velocities are deeply subsonic."""
    m = mach_number(velocity_m_s=0.1, speed_of_sound_m_s=343.0)
    assert m < 1.0e-3


def test_prandtl_number_dry_air_near_071():
    """Incropera Table A.4 at 293 K: Pr ≈ 0.707."""
    pr = prandtl_number(
        specific_heat_j_kg_k=1007.0,
        dynamic_viscosity_pa_s=1.82e-5,
        thermal_conductivity_w_m_k=0.0257,
    )
    assert 0.69 < pr < 0.73, f"Pr = {pr:.3f}"


def test_grashof_and_rayleigh_scale_with_length_cubed():
    gr_1 = grashof_number(
        gravity_m_s2=9.81,
        thermal_expansion_1_k=3.4e-3,
        delta_t_k=20.0,
        length_m=0.5,
        kinematic_viscosity_m2_s=1.5e-5,
    )
    gr_2 = grashof_number(
        gravity_m_s2=9.81,
        thermal_expansion_1_k=3.4e-3,
        delta_t_k=20.0,
        length_m=1.0,
        kinematic_viscosity_m2_s=1.5e-5,
    )
    assert gr_2 / gr_1 == pytest.approx(8.0, rel=1.0e-6)
    ra = rayleigh_number(gr_1, 0.71)
    assert ra == pytest.approx(gr_1 * 0.71)


def test_churchill_chu_canonical_ra_1e9_pr_07():
    """Incropera 2011 Example 9.2: Ra=10⁹, Pr=0.7 → Nu ≈ 127."""
    nu = nusselt_churchill_chu_vertical_plate(rayleigh=1.0e9, prandtl=0.7)
    assert 120.0 < nu < 140.0, f"Nu = {nu:.1f}"


# ──────────────────────────────────────────────────────────────────────
#  Flow regime classification
# ──────────────────────────────────────────────────────────────────────


def test_pipe_flow_regimes_kundu_thresholds():
    assert classify_pipe_flow(500.0) == FlowRegime.LAMINAR
    assert classify_pipe_flow(3000.0) == FlowRegime.TRANSITIONAL
    assert classify_pipe_flow(10000.0) == FlowRegime.TURBULENT


def test_plate_flow_regime_schlichting_threshold():
    assert classify_plate_flow(1.0e5) == FlowRegime.LAMINAR
    assert classify_plate_flow(1.0e6) == FlowRegime.TURBULENT


# ──────────────────────────────────────────────────────────────────────
#  Turbulence closure
# ──────────────────────────────────────────────────────────────────────


def test_k_epsilon_constants_launder_spalding_1974():
    c = K_EPSILON_STANDARD
    assert c.c_mu == pytest.approx(0.09)
    assert c.c_1_eps == pytest.approx(1.44)
    assert c.c_2_eps == pytest.approx(1.92)


def test_turbulent_viscosity_scales_with_k_squared():
    mut_1 = turbulent_viscosity_k_epsilon(1.2, 0.1, 0.01)
    mut_2 = turbulent_viscosity_k_epsilon(1.2, 0.2, 0.01)
    assert mut_2 / mut_1 == pytest.approx(4.0, rel=1.0e-6)


# ──────────────────────────────────────────────────────────────────────
#  Wall functions / Blasius / CFL / turnover
# ──────────────────────────────────────────────────────────────────────


def test_law_of_wall_viscous_sublayer():
    assert law_of_the_wall_u_plus(1.0) == 1.0
    assert law_of_the_wall_u_plus(4.0) == 4.0


def test_law_of_wall_log_layer_pope_eq_7_43():
    """u⁺(y⁺=100) = ln 100 / 0.41 + 5.2 ≈ 16.43 (Pope 2000 eq. 7.43)."""
    u = law_of_the_wall_u_plus(100.0)
    expected = math.log(100.0) / 0.41 + 5.2
    assert u == pytest.approx(expected, rel=1.0e-6)


def test_friction_velocity_rejects_nonpositive_density():
    with pytest.raises(ValueError):
        friction_velocity(1.0, 0.0)


def test_blasius_cf_schlichting():
    """C_f(Re_x = 10⁶) = 0.664 / 1000 = 6.64×10⁻⁴."""
    cf = blasius_skin_friction_coefficient(reynolds_x=1.0e6)
    assert cf == pytest.approx(6.64e-4, rel=1.0e-6)


def test_blasius_displacement_thickness_schlichting():
    """δ*/x (Re_x = 10⁶) = 1.7208 / 1000 = 1.721×10⁻³."""
    d_over_x = blasius_displacement_thickness_over_x(reynolds_x=1.0e6)
    assert d_over_x == pytest.approx(1.7208e-3, rel=1.0e-6)


def test_cfl_time_step_bound_hirsch():
    """Δt ≤ CFL · Δx / (|u| + c)."""
    dt = cfl_time_step_bound(
        cell_size_m=0.01, velocity_m_s=10.0, speed_of_sound_m_s=340.0, cfl=0.5
    )
    assert dt == pytest.approx(0.5 * 0.01 / 350.0, rel=1.0e-6)


def test_cfl_explicit_limit_is_unity_hirsch():
    assert CFL_EXPLICIT_LIMIT == 1.0


def test_iss_cabin_turnover_son_2015():
    """Son et al. 2015 CFD: V = 76 m³, Q̇ = 4.5 m³/min → ~1013 s."""
    tau = iss_cabin_turnover_time_s(volume_m3=76.0, volumetric_flow_m3_s=4.5 / 60.0)
    assert 900.0 < tau < 1100.0, f"τ = {tau:.0f} s"


def test_iss_cabin_turnover_rejects_zero_flow():
    with pytest.raises(ValueError):
        iss_cabin_turnover_time_s(volume_m3=76.0, volumetric_flow_m3_s=0.0)


# ──────────────────────────────────────────────────────────────────────
#  Sod shock tube — exact Riemann star state
# ──────────────────────────────────────────────────────────────────────


def test_sod_exact_star_state_matches_toro_table_4_1():
    """Toro 2009 Table 4.1: p★ = 0.30313, u★ = 0.92745,
    ρ★_L = 0.42632, ρ★_R = 0.26557."""
    sol = sod_exact_post_shock_state()
    assert isinstance(sol, SodExactSolution)
    assert sol.p_star == pytest.approx(0.30313, abs=5.0e-5)
    assert sol.u_star == pytest.approx(0.92745, abs=5.0e-5)
    assert sol.rho_star_left == pytest.approx(0.42632, abs=5.0e-5)
    assert sol.rho_star_right == pytest.approx(0.26557, abs=5.0e-5)


def test_sod_rejects_nonpositive_density():
    with pytest.raises(ValueError):
        sod_exact_post_shock_state(rho_left=0.0)


def test_sod_rejects_gamma_unity():
    with pytest.raises(ValueError):
        sod_exact_post_shock_state(gamma=1.0)
