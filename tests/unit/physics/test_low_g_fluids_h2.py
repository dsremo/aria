"""Unit tests for Pod H2 — low-gravity fluids (P1-6).

Benchmarks:
  - Myshkis et al. 1987 *Low-Gravity Fluid Mechanics* §1 (regime).
  - Adamson & Gast 1997 *Physical Chemistry of Surfaces* 6th ed §2.4
    (Jurin rise, capillary length).
  - Abramson (ed.) 1966 NASA SP-106 — cylindrical tank slosh.
  - Ibrahim 2005 *Liquid Sloshing Dynamics* §4.6 (rotating frame).
  - Yeleswarapu 1998 PhD thesis Univ Pittsburgh (blood Carreau).
"""

from __future__ import annotations

import math

import pytest

from aria.physics.low_g_fluids import (
    ABRAMSON_XI_11,
    BLOOD_CARREAU_YELESWARAPU,
    BOND_CAPILLARY_THRESHOLD,
    FLUID_H2_TABLE,
    bingham_apparent_viscosity,
    bond_number,
    capillary_length,
    capillary_number,
    capillary_pressure_spherical_cap,
    carreau_apparent_viscosity,
    centrifuged_ring_tank_frequency,
    cylindrical_tank_slosh_frequency,
    get_fluid_h2,
    is_capillary_regime,
    jurin_capillary_rise,
    marangoni_number,
    ohnesorge_number,
    power_law_apparent_viscosity,
    spring_mass_slosh_mass_ratio,
    weber_number,
    young_laplace_pressure_jump,
)


# ──────────────────────────────────────────────────────────────────────
#  Fluid DB
# ──────────────────────────────────────────────────────────────────────


def test_water_293k_surface_tension_crc():
    w = get_fluid_h2("Water")
    assert w.surface_tension_n_m == pytest.approx(0.0728, rel=1.0e-6)
    assert w.density_kg_m3 == pytest.approx(998.2, rel=1.0e-6)


def test_fluid_table_has_lh2_lox_blood():
    assert "LH2" in FLUID_H2_TABLE
    assert "LOX" in FLUID_H2_TABLE
    assert "Blood" in FLUID_H2_TABLE


def test_get_fluid_unknown_raises():
    with pytest.raises(KeyError):
        get_fluid_h2("Unobtainium")


# ──────────────────────────────────────────────────────────────────────
#  Dimensionless numbers
# ──────────────────────────────────────────────────────────────────────


def test_bond_number_water_1g_1m_tank():
    """Water, g=9.81, L=1 m, σ=0.0728 → Bo ≈ 134e3 ≫ 1 (gravity dominates)."""
    bo = bond_number(
        density_kg_m3=998.2, gravity_m_s2=9.81, length_m=1.0, surface_tension_n_m=0.0728
    )
    assert bo > 1.0e5


def test_bond_number_microgravity_capillary_regime():
    """Myshkis 1987: on-orbit residual 1e-6 g with a 1 m tank → Bo ≪ 1."""
    bo = bond_number(
        density_kg_m3=998.2, gravity_m_s2=1.0e-6, length_m=1.0, surface_tension_n_m=0.0728
    )
    assert bo < 1.0


def test_weber_and_capillary_and_ohnesorge_positive():
    we = weber_number(998.0, 1.0, 0.01, 0.072)
    ca = capillary_number(1.0e-3, 1.0, 0.072)
    oh = ohnesorge_number(1.0e-3, 998.0, 0.072, 0.01)
    assert we > 0 and ca > 0 and oh > 0


def test_marangoni_number_pearson_critical():
    """Pearson 1958: Ma_c ≈ 80 for adiabatic upper boundary.

    Here we just check that the formula reproduces the correct
    numerical size for a 1 mm silicone-oil layer with ΔT = 1 K.
    Silicone oil: dσ/dT ≈ 6.4e-5 N/m/K, μ ≈ 1e-2 Pa·s, α ≈ 1e-7 m²/s.
    Ma ≈ 6.4e-5 · 1 · 1e-3 / (1e-2 · 1e-7) = 64. Order-of-magnitude
    match to Ma_c ≈ 80 for onset.
    """
    ma = marangoni_number(
        dsigma_dt_n_m_k=-6.4e-5,
        delta_t_k=1.0,
        length_m=1.0e-3,
        dynamic_viscosity_pa_s=1.0e-2,
        thermal_diffusivity_m2_s=1.0e-7,
    )
    assert 30.0 < ma < 200.0


# ──────────────────────────────────────────────────────────────────────
#  Young-Laplace + Jurin
# ──────────────────────────────────────────────────────────────────────


def test_young_laplace_spherical_cap():
    """Δp = 2σ/r for a 1 mm water droplet ≈ 145.6 Pa."""
    dp = capillary_pressure_spherical_cap(surface_tension_n_m=0.0728, radius_m=1.0e-3)
    assert dp == pytest.approx(2.0 * 0.0728 / 1.0e-3, rel=1.0e-9)


def test_young_laplace_two_radii():
    dp = young_laplace_pressure_jump(0.072, 1.0e-3, 2.0e-3)
    assert dp == pytest.approx(0.072 * (1.0 / 1.0e-3 + 1.0 / 2.0e-3), rel=1.0e-9)


def test_jurin_rise_matches_adamson_gast():
    """Adamson & Gast 1997 §2.4: 0.5 mm glass tube, water, θ=0 → h ≈ 29.7 mm."""
    h = jurin_capillary_rise(
        surface_tension_n_m=0.0728,
        contact_angle_rad=0.0,
        tube_radius_m=0.5e-3,
        density_kg_m3=998.2,
        gravity_m_s2=9.81,
    )
    assert 0.028 < h < 0.031, f"h = {h*1000:.2f} mm"


def test_jurin_rise_zero_at_zero_g():
    h = jurin_capillary_rise(0.0728, 0.0, 0.5e-3, 998.2, 0.0)
    assert h == 0.0


def test_capillary_length_water_1g():
    """ℓ_c = √(σ/ρg) water 1 g → 2.72 mm (Adamson 1997 handbook)."""
    lc = capillary_length(0.0728, 998.2, 9.81)
    assert 2.5e-3 < lc < 3.0e-3


def test_is_capillary_regime_threshold():
    assert is_capillary_regime(0.5) is True
    assert is_capillary_regime(2.0) is False
    assert BOND_CAPILLARY_THRESHOLD == 1.0


# ──────────────────────────────────────────────────────────────────────
#  Sloshing
# ──────────────────────────────────────────────────────────────────────


def test_abramson_xi_11_value():
    """First J'_1 root. Abramson 1966 Table 2.1: ξ_11 ≈ 1.8412."""
    assert abs(ABRAMSON_XI_11 - 1.8411838) < 1.0e-6


def test_cylindrical_slosh_frequency_1m_water():
    """Sanity: R = h = 1 m, g = 9.81 → f ≈ 0.66 Hz.

    Analytic: ω² = 9.81·1.8412·tanh(1.8412) = 9.81·1.8412·0.9504
         = 17.17  → ω ≈ 4.144 → f ≈ 0.659 Hz.
    """
    f = cylindrical_tank_slosh_frequency(
        gravity_m_s2=9.81, tank_radius_m=1.0, fill_depth_m=1.0
    )
    expected = math.sqrt(9.81 * 1.8411838 * math.tanh(1.8411838)) / (2.0 * math.pi)
    assert f == pytest.approx(expected, rel=1.0e-6)
    assert 0.64 < f < 0.68


def test_cylindrical_slosh_zero_g_returns_zero():
    f = cylindrical_tank_slosh_frequency(0.0, 1.0, 1.0)
    assert f == 0.0


def test_centrifuged_ring_uses_omega_squared_r():
    """Tank at r = 100 m, Ω = 2 rad/s → g_eff = 400 m/s²."""
    f_ring = centrifuged_ring_tank_frequency(
        rotation_rate_rad_s=2.0,
        radial_distance_m=100.0,
        tank_radius_m=1.0,
        fill_depth_m=1.0,
    )
    f_static = cylindrical_tank_slosh_frequency(
        gravity_m_s2=400.0, tank_radius_m=1.0, fill_depth_m=1.0
    )
    assert f_ring == pytest.approx(f_static, rel=1.0e-12)


def test_centrifuged_ring_zero_omega_returns_zero():
    f = centrifuged_ring_tank_frequency(0.0, 100.0, 1.0, 1.0)
    assert f == 0.0


def test_spring_mass_ratio_positive_for_non_shallow_tanks():
    """m₁/m_tot is positive and (for h/R ≥ 1) bounded by 1.

    The Abramson 1966 eq. 2.34 linear-theory formula can exceed unity
    in the shallow-tank limit h/R ≪ 1, where linear sloshing theory
    itself breaks down (Ibrahim 2005 §4.2 warns that shallow-tank
    spring-mass abstractions need the first *two* modes to close).
    """
    for h in (1.0, 2.0, 5.0, 10.0):
        for r in (0.5, 1.0, 2.0):
            ratio = spring_mass_slosh_mass_ratio(h, r)
            assert 0.0 < ratio <= 1.0 + 1.0e-12


def test_spring_mass_ratio_deep_tank_small():
    """For h/R = 10 the mass fraction should be small (~0.046)."""
    ratio = spring_mass_slosh_mass_ratio(10.0, 1.0)
    assert 0.02 < ratio < 0.08


# ──────────────────────────────────────────────────────────────────────
#  Non-Newtonian
# ──────────────────────────────────────────────────────────────────────


def test_carreau_blood_zero_shear_limit():
    """At γ̇ = 0 the Carreau model returns μ_0 = 0.056 Pa·s."""
    mu = carreau_apparent_viscosity(shear_rate_1_s=0.0)
    assert mu == pytest.approx(BLOOD_CARREAU_YELESWARAPU.mu_0_pa_s, rel=1.0e-9)


def test_carreau_blood_high_shear_limit():
    """At γ̇ = 1e6 1/s the Carreau model approaches μ_∞ = 3.45e-3."""
    mu = carreau_apparent_viscosity(shear_rate_1_s=1.0e6)
    assert mu == pytest.approx(BLOOD_CARREAU_YELESWARAPU.mu_inf_pa_s, rel=1.0e-3)


def test_carreau_monotone_decreasing():
    mus = [carreau_apparent_viscosity(g) for g in (0.0, 1.0, 10.0, 100.0, 1000.0)]
    for i in range(len(mus) - 1):
        assert mus[i] > mus[i + 1]


def test_power_law_recovers_newtonian_at_n_1():
    mu = power_law_apparent_viscosity(10.0, consistency_index_pa_sn=1.5, power_law_exponent=1.0)
    assert mu == pytest.approx(1.5, rel=1.0e-12)


def test_power_law_shear_thinning_decreases():
    mu_1 = power_law_apparent_viscosity(1.0, 1.0, 0.5)
    mu_2 = power_law_apparent_viscosity(100.0, 1.0, 0.5)
    assert mu_2 < mu_1


def test_bingham_infinite_below_yield():
    mu = bingham_apparent_viscosity(0.0, 10.0, 1.0)
    assert math.isinf(mu)


def test_bingham_apparent_viscosity_formula():
    mu = bingham_apparent_viscosity(shear_rate_1_s=10.0, yield_stress_pa=1.0, plastic_viscosity_pa_s=2.0)
    assert mu == pytest.approx(1.0 / 10.0 + 2.0, rel=1.0e-12)
