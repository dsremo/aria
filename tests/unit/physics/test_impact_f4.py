"""Verification tests for Pod F4 (hypervelocity impact + Whipple).

Covers the closed-form portions of the F4 scope §9 cases:

  9.1 Hertzian contact — Johnson 1985 closed-form for steel balls
  9.2 Rankine-Hugoniot peak pressure on Al 2024-T3 (Marsh 1980)
  9.3 Christiansen 1990 crater depth scaling on Al-on-Al at 6.8 km/s
  9.4 Christiansen NNO Whipple BLE for an Al 6061-T6 shield
  9.5 Relativistic dust impact KE vs classical (1/2)mv²
"""

from __future__ import annotations

import math

import pytest

from aria.physics.impact import (
    HUGONIOT_AL_2024_T3,
    HUGONIOT_TI_6AL_4V,
    ImpactRegime,
    ULTRA_RELATIVISTIC_THRESHOLD_FRACTION_C,
    classify_impact_regime,
    crater_depth_christiansen,
    ejecta_cone_half_angle_default,
    ejecta_mass_schonberg,
    hertzian_contact_force,
    hertzian_contact_radius,
    hertzian_max_pressure,
    hugoniot_peak_density,
    hugoniot_peak_pressure,
    hugoniot_shock_velocity,
    is_ultra_relativistic_regime,
    reduced_elastic_modulus,
    relativistic_impact_kinetic_energy,
    relativistic_impact_momentum,
    whipple_critical_diameter_nno,
    whipple_is_perforated,
)


SPEED_OF_LIGHT_M_S = 2.99792458e8


# ─────────────────────────────────────────────────────────────────────
# Test 9.1 — Hertzian steel-ball contact
# Source: Johnson 1985 Contact Mechanics §3 worked example
# ─────────────────────────────────────────────────────────────────────


class TestHertzian:
    """A 1 mm steel ball pressed with 1 N against a steel flat.

    E_steel ≈ 200 GPa, ν = 0.30 → E* ≈ 110 GPa.
    R = 0.5 mm (sphere; flat has R → ∞).

    From F = (4/3) E* √R δ^(3/2), inverting for δ:
        δ = (3 F / (4 E* √R))^(2/3)
          = (0.75 / (1.1e11 · 0.02236))^(2/3)
          = (3.05e-13)^(2/3)
          ≈ 4.5e-9 m  (note: this is ~5 nm — Johnson's "indentation
          of a 1 mm steel ball under 1 N" worked example)
    """

    E_STEEL = 200e9
    NU_STEEL = 0.30
    R_BALL = 0.5e-3  # 1 mm ball → radius 0.5 mm
    F_APPLIED = 1.0  # 1 N

    def test_reduced_modulus_two_steel(self) -> None:
        # Two identical steel bodies: 1/E* = 2(1-ν²)/E → E* = E/(2(1-ν²))
        e_star = reduced_elastic_modulus(
            self.E_STEEL, self.NU_STEEL, self.E_STEEL, self.NU_STEEL
        )
        expected = self.E_STEEL / (2.0 * (1.0 - self.NU_STEEL**2))
        assert e_star == pytest.approx(expected, rel=1e-12)

    def test_force_indentation_roundtrip(self) -> None:
        # Invert F = (4/3) E* √R δ^(3/2) to find δ, then feed back.
        e_star = reduced_elastic_modulus(
            self.E_STEEL, self.NU_STEEL, self.E_STEEL, self.NU_STEEL
        )
        delta = (
            3.0 * self.F_APPLIED / (4.0 * e_star * math.sqrt(self.R_BALL))
        ) ** (2.0 / 3.0)
        f_recovered = hertzian_contact_force(e_star, self.R_BALL, delta)
        assert f_recovered == pytest.approx(self.F_APPLIED, rel=1e-9)

    def test_contact_radius_scaling(self) -> None:
        # a = √(R δ) — scales as δ^(1/2).
        delta = 1.0e-8
        a = hertzian_contact_radius(self.R_BALL, delta)
        expected = math.sqrt(self.R_BALL * delta)
        assert a == pytest.approx(expected, rel=1e-12)

    def test_peak_pressure_steel_ball(self) -> None:
        e_star = reduced_elastic_modulus(
            self.E_STEEL, self.NU_STEEL, self.E_STEEL, self.NU_STEEL
        )
        p_0 = hertzian_max_pressure(self.F_APPLIED, e_star, self.R_BALL)
        # Hand calculation from Johnson 1985 eq. 3.41:
        #   p_0 = (1/π) · (6 F E*² / R²)^(1/3)
        #       = (1/π) · (6 · 1 · (110e9)² / (0.5e-3)²)^(1/3)
        #       = (1/π) · (2.904e29)^(1/3)
        #       = (1/π) · 6.622e9
        #       ≈ 2.11 GPa
        # Well above the ~1.6 σ_y yield threshold for most steels,
        # which means in practice a 1 N concentrated load on a 1 mm
        # steel ball initiates plastic deformation — consistent with
        # the "dimple" everyone sees after dropping a steel ball.
        assert 1.5e9 < p_0 < 3.0e9, p_0

    def test_zero_force_zero_pressure(self) -> None:
        assert hertzian_max_pressure(0.0, 200e9, 1e-3) == 0.0


# ─────────────────────────────────────────────────────────────────────
# Test 9.2 — Rankine-Hugoniot peak pressure (Marsh 1980 Al 2024-T3)
# ─────────────────────────────────────────────────────────────────────


class TestHugoniot:
    """Marsh 1980 LASL Shock Hugoniot Data values for Al 2024-T3:
    c_0 = 5380 m/s, s = 1.338, ρ_0 = 2785 kg/m³.

    Symmetric Al-on-Al impact at 10 km/s has u_p = 5 km/s
    (impedance matching):

        U_s = 5380 + 1.338 · 5000 = 12 070 m/s
        p_H = 2785 · 12070 · 5000 = 1.68 × 10^11 Pa ≈ 168 GPa

    This is in the published Al-on-Al shock data (Marsh 1980 §II.A.4).
    """

    def test_linear_us_up_al_2024(self) -> None:
        u_s = hugoniot_shock_velocity(5_000.0, HUGONIOT_AL_2024_T3)
        expected = 5380.0 + 1.338 * 5000.0
        assert u_s == pytest.approx(expected, rel=1e-12)

    def test_peak_pressure_al_10_km_s_symmetric(self) -> None:
        # Symmetric 10 km/s Al-on-Al → u_p = 5 km/s in each body.
        p_h = hugoniot_peak_pressure(5_000.0, HUGONIOT_AL_2024_T3)
        expected = 2785.0 * (5380.0 + 1.338 * 5000.0) * 5000.0
        assert p_h == pytest.approx(expected, rel=1e-12)
        assert 150e9 < p_h < 200e9  # 150-200 GPa hypervelocity Al-on-Al

    def test_peak_density_strong_shock_compression(self) -> None:
        # Strong shock compression ρ_1/ρ_0 → (s+1)/s asymptotically.
        # For Al s = 1.338 → (2.338/1.338) ≈ 1.75, but real shocks
        # are nowhere near this asymptote at 5 km/s particle velocity.
        rho_1 = hugoniot_peak_density(5_000.0, HUGONIOT_AL_2024_T3)
        compression = rho_1 / HUGONIOT_AL_2024_T3.rho_0_kg_m3
        assert 1.3 < compression < 2.0, compression

    def test_zero_up_no_shock(self) -> None:
        u_s = hugoniot_shock_velocity(0.0, HUGONIOT_AL_2024_T3)
        assert u_s == HUGONIOT_AL_2024_T3.c_0_m_s
        p = hugoniot_peak_pressure(0.0, HUGONIOT_AL_2024_T3)
        assert p == 0.0

    def test_ti_hugoniot_slower_c0(self) -> None:
        # Ti-6Al-4V c_0 = 4780 m/s < Al 5380.
        assert HUGONIOT_TI_6AL_4V.c_0_m_s < HUGONIOT_AL_2024_T3.c_0_m_s


# ─────────────────────────────────────────────────────────────────────
# Test 9.3 — Christiansen 1990 crater depth
# Source: Christiansen 1990 NASA TM-105002 Fig. 4
# ─────────────────────────────────────────────────────────────────────


class TestChristiansenCrater:
    """Reproduces the worked example from Christiansen 1990 Fig. 4:

    d = 0.8 cm sphere, H_target = 120 (Al 2024-T3), ρ_p = ρ_t = 2700
    kg/m³ (Al on Al), v = 6.8 km/s, θ = 0.

    Christiansen's result: p ≈ 4.47 cm crater depth.
    """

    def test_christiansen_worked_example(self) -> None:
        p_m = crater_depth_christiansen(
            projectile_diameter_m=0.8e-2,  # 0.8 cm
            target_brinell_hardness=120.0,
            projectile_density_kg_m3=2700.0,
            target_density_kg_m3=2700.0,
            impact_velocity_m_s=6800.0,
            angle_from_normal_rad=0.0,
        )
        p_cm = p_m * 100.0
        # Christiansen 1990 Fig. 4 shows ~4.47 cm; allow 5% tolerance
        # for the analytic fit residual.
        assert p_cm == pytest.approx(4.47, rel=0.05), p_cm

    def test_harder_target_smaller_crater(self) -> None:
        p_al = crater_depth_christiansen(
            0.01, 120.0, 2700.0, 2700.0, 6000.0
        )
        p_ti = crater_depth_christiansen(
            0.01, 334.0, 2700.0, 4430.0, 6000.0
        )
        assert p_ti < p_al

    def test_oblique_angle_reduces_depth(self) -> None:
        p_normal = crater_depth_christiansen(
            0.01, 120.0, 2700.0, 2700.0, 6000.0, angle_from_normal_rad=0.0
        )
        p_45 = crater_depth_christiansen(
            0.01, 120.0, 2700.0, 2700.0, 6000.0,
            angle_from_normal_rad=math.radians(45.0),
        )
        assert p_45 < p_normal
        # cos 45 = 0.707, and p ∝ (v cos θ)^(2/3) = 0.707^(2/3) ≈ 0.794
        ratio = p_45 / p_normal
        assert ratio == pytest.approx(0.794, rel=0.01)

    def test_scaling_in_velocity(self) -> None:
        # Doubling v multiplies p by 2^(2/3) ≈ 1.587.
        p_low = crater_depth_christiansen(
            0.01, 120.0, 2700.0, 2700.0, 3000.0
        )
        p_high = crater_depth_christiansen(
            0.01, 120.0, 2700.0, 2700.0, 6000.0
        )
        assert p_high / p_low == pytest.approx(2.0 ** (2.0 / 3.0), rel=1e-6)


# ─────────────────────────────────────────────────────────────────────
# Test 9.4 — Christiansen NNO Whipple ballistic limit
# Source: Christiansen 1993 NASA TM-1993-107955, Ryan 2011 NASA/JSC 65282
# ─────────────────────────────────────────────────────────────────────


class TestWhippleNNO:
    """Representative ISS Whipple shield: Al 6061-T6 bumper 0.127 cm
    + rear wall 0.32 cm + 10.16 cm standoff. Against a 7 km/s Al
    projectile, the NNO critical diameter is ~0.9 cm (Ryan 2011
    Fig. 4.2).

    ρ(Al 6061-T6) = 2710 kg/m³, σ_y = 276 MPa (MIL-HDBK-5).
    """

    RHO_AL = 2710.0
    SIGMA_AL_6061_T6 = 276e6
    T_BUMPER = 0.127e-2  # 0.127 cm
    T_WALL = 0.32e-2  # 0.32 cm
    STANDOFF = 10.16e-2  # 10.16 cm

    def test_iss_style_shield_at_7_km_s(self) -> None:
        d_c = whipple_critical_diameter_nno(
            bumper_thickness_m=self.T_BUMPER,
            bumper_density_kg_m3=self.RHO_AL,
            rear_wall_thickness_m=self.T_WALL,
            rear_wall_density_kg_m3=self.RHO_AL,
            rear_wall_yield_strength_pa=self.SIGMA_AL_6061_T6,
            standoff_m=self.STANDOFF,
            projectile_density_kg_m3=self.RHO_AL,
            impact_velocity_m_s=7000.0,
            angle_from_normal_rad=0.0,
        )
        # Ryan 2011 Fig 4.2: d_c ~ 0.5-1.0 cm band for this shield.
        assert 0.3e-2 < d_c < 1.5e-2, d_c

    def test_thicker_rear_wall_stops_bigger_projectile(self) -> None:
        d_c_thin = whipple_critical_diameter_nno(
            bumper_thickness_m=self.T_BUMPER,
            bumper_density_kg_m3=self.RHO_AL,
            rear_wall_thickness_m=self.T_WALL,
            rear_wall_density_kg_m3=self.RHO_AL,
            rear_wall_yield_strength_pa=self.SIGMA_AL_6061_T6,
            standoff_m=self.STANDOFF,
            projectile_density_kg_m3=self.RHO_AL,
            impact_velocity_m_s=7000.0,
        )
        d_c_thick = whipple_critical_diameter_nno(
            bumper_thickness_m=self.T_BUMPER,
            bumper_density_kg_m3=self.RHO_AL,
            rear_wall_thickness_m=self.T_WALL * 4.0,  # 4× thicker wall
            rear_wall_density_kg_m3=self.RHO_AL,
            rear_wall_yield_strength_pa=self.SIGMA_AL_6061_T6,
            standoff_m=self.STANDOFF,
            projectile_density_kg_m3=self.RHO_AL,
            impact_velocity_m_s=7000.0,
        )
        # d_c ∝ t_w^(2/3), so 4× thickness → 4^(2/3) ≈ 2.52× larger
        # critical diameter.
        assert d_c_thick == pytest.approx(
            d_c_thin * 4.0 ** (2.0 / 3.0), rel=1e-9
        )

    def test_larger_standoff_helps(self) -> None:
        base = whipple_critical_diameter_nno(
            self.T_BUMPER, self.RHO_AL, self.T_WALL, self.RHO_AL,
            self.SIGMA_AL_6061_T6, self.STANDOFF, self.RHO_AL, 7000.0
        )
        larger = whipple_critical_diameter_nno(
            self.T_BUMPER, self.RHO_AL, self.T_WALL, self.RHO_AL,
            self.SIGMA_AL_6061_T6, self.STANDOFF * 8.0, self.RHO_AL, 7000.0,
        )
        # d_c ∝ S^(1/3), so 8× standoff → 2× critical diameter.
        assert larger == pytest.approx(base * 2.0, rel=1e-9)

    def test_faster_impact_smaller_critical_diameter(self) -> None:
        # d_c ∝ v^(−2/3), so doubling v reduces d_c by 2^(2/3) ≈ 1.587.
        slow = whipple_critical_diameter_nno(
            self.T_BUMPER, self.RHO_AL, self.T_WALL, self.RHO_AL,
            self.SIGMA_AL_6061_T6, self.STANDOFF, self.RHO_AL, 7000.0,
        )
        fast = whipple_critical_diameter_nno(
            self.T_BUMPER, self.RHO_AL, self.T_WALL, self.RHO_AL,
            self.SIGMA_AL_6061_T6, self.STANDOFF, self.RHO_AL, 14_000.0,
        )
        assert slow / fast == pytest.approx(2.0 ** (2.0 / 3.0), rel=1e-9)

    def test_perforation_dispatcher(self) -> None:
        # Small projectile: shield stops it.
        safe = whipple_is_perforated(
            projectile_diameter_m=0.1e-2,  # 1 mm
            bumper_thickness_m=self.T_BUMPER,
            bumper_density_kg_m3=self.RHO_AL,
            rear_wall_thickness_m=self.T_WALL,
            rear_wall_density_kg_m3=self.RHO_AL,
            rear_wall_yield_strength_pa=self.SIGMA_AL_6061_T6,
            standoff_m=self.STANDOFF,
            projectile_density_kg_m3=self.RHO_AL,
            impact_velocity_m_s=7000.0,
        )
        assert not safe
        # Large projectile: shield is penetrated.
        unsafe = whipple_is_perforated(
            projectile_diameter_m=5.0e-2,  # 5 cm
            bumper_thickness_m=self.T_BUMPER,
            bumper_density_kg_m3=self.RHO_AL,
            rear_wall_thickness_m=self.T_WALL,
            rear_wall_density_kg_m3=self.RHO_AL,
            rear_wall_yield_strength_pa=self.SIGMA_AL_6061_T6,
            standoff_m=self.STANDOFF,
            projectile_density_kg_m3=self.RHO_AL,
            impact_velocity_m_s=7000.0,
        )
        assert unsafe


# ─────────────────────────────────────────────────────────────────────
# Regime dispatcher
# ─────────────────────────────────────────────────────────────────────


class TestRegimeDispatcher:
    def test_hertzian_low_velocity_band(self) -> None:
        assert classify_impact_regime(10.0) == ImpactRegime.HERTZIAN
        assert classify_impact_regime(49.9) == ImpactRegime.HERTZIAN

    def test_low_velocity_band(self) -> None:
        assert classify_impact_regime(100.0) == ImpactRegime.LOW_VELOCITY
        assert classify_impact_regime(2_999.0) == ImpactRegime.LOW_VELOCITY

    def test_hypervelocity_tested_band(self) -> None:
        assert classify_impact_regime(3_000.0) == ImpactRegime.HYPERVELOCITY_BLE
        assert classify_impact_regime(15_000.0) == ImpactRegime.HYPERVELOCITY_BLE

    def test_extrapolated_band(self) -> None:
        assert classify_impact_regime(1e6) == ImpactRegime.EXTRAPOLATED_BLE

    def test_ultra_relativistic_above_0_01c(self) -> None:
        above = 0.02 * SPEED_OF_LIGHT_M_S
        assert classify_impact_regime(above) == ImpactRegime.ULTRA_RELATIVISTIC

    def test_negative_velocity_raises(self) -> None:
        with pytest.raises(ValueError):
            classify_impact_regime(-1.0)


# ─────────────────────────────────────────────────────────────────────
# Ejecta scaling
# ─────────────────────────────────────────────────────────────────────


class TestEjectaScaling:
    def test_schonberg_scaling_at_3_km_s(self) -> None:
        # At 3 km/s the Schonberg formula gives M_ej = 10 m_p.
        m_ej = ejecta_mass_schonberg(projectile_mass_kg=1e-6, impact_velocity_m_s=3_000.0)
        assert m_ej == pytest.approx(10.0 * 1e-6, rel=1e-12)

    def test_scales_linearly_with_velocity(self) -> None:
        low = ejecta_mass_schonberg(1e-6, 3_000.0)
        high = ejecta_mass_schonberg(1e-6, 6_000.0)
        assert high == pytest.approx(2.0 * low, rel=1e-12)

    def test_default_cone_angle(self) -> None:
        # 50° half-angle
        angle = ejecta_cone_half_angle_default()
        assert angle == pytest.approx(math.radians(50.0), rel=1e-12)


# ─────────────────────────────────────────────────────────────────────
# Test 9.5 — Relativistic dust impact
# Source: Einstein 1905 + Hoang 2017 ApJ 847 77
# ─────────────────────────────────────────────────────────────────────


class TestRelativisticDust:
    """At cruise velocity β = 0.1, γ = 1.00504 and KE = (γ−1) m c²
    differs from the classical (1/2) m v² by only ~0.5 %. At higher
    β the departure grows rapidly."""

    # 1 femtogram = 1e-18 kg. A 1 pg grain (1e-15 kg, ~10 μm radius
    # for ρ = 2500 kg/m³) is a more representative interstellar
    # dust-grain mass and the one used in Hoang 2017 §3.
    M_DUST_KG = 1.0e-15  # 1 picogram; a typical interstellar grain

    def test_classical_limit_at_low_v(self) -> None:
        v = 1000.0  # 1 km/s — fully non-relativistic
        ke_rel = relativistic_impact_kinetic_energy(self.M_DUST_KG, v)
        ke_classical = 0.5 * self.M_DUST_KG * v * v
        assert ke_rel == pytest.approx(ke_classical, rel=1e-10)

    def test_cruise_velocity_0_1c(self) -> None:
        # β = 0.1 → γ = 1/√0.99 ≈ 1.00504
        v = 0.1 * SPEED_OF_LIGHT_M_S
        ke = relativistic_impact_kinetic_energy(self.M_DUST_KG, v)
        expected = (1.0 / math.sqrt(1.0 - 0.01) - 1.0) * self.M_DUST_KG * SPEED_OF_LIGHT_M_S**2
        assert ke == pytest.approx(expected, rel=1e-12)
        # Hand calculation:
        #   (γ − 1) · 1e-15 · 9e16
        # = 0.00504 · 9e1
        # = 0.453 J  (≈ half a joule per picogram grain at 10% c)
        # This is the Hoang 2017 ApJ 847 77 §3 ballpark and explains
        # why interstellar dust is a first-order threat for relativistic
        # probes — every grain carries the energy of a bullet.
        assert 0.4 < ke < 0.5, ke

    def test_relativistic_exceeds_classical_at_high_gamma(self) -> None:
        # At β = 0.9, γ ≈ 2.294, so KE = 1.294 m c² whereas classical
        # is 0.5 · 0.81 · m c² = 0.405 m c² — a factor of ~3.2 difference.
        v = 0.9 * SPEED_OF_LIGHT_M_S
        ke_rel = relativistic_impact_kinetic_energy(self.M_DUST_KG, v)
        ke_classical = 0.5 * self.M_DUST_KG * v * v
        assert ke_rel / ke_classical == pytest.approx(3.197, rel=0.01)

    def test_momentum_exceeds_classical_at_high_gamma(self) -> None:
        v = 0.9 * SPEED_OF_LIGHT_M_S
        p_rel = relativistic_impact_momentum(self.M_DUST_KG, v)
        p_classical = self.M_DUST_KG * v
        # p = γ m v, so ratio = γ ≈ 2.294
        assert p_rel / p_classical == pytest.approx(1.0 / math.sqrt(0.19), rel=1e-9)

    def test_cannot_exceed_c(self) -> None:
        with pytest.raises(ValueError, match="cannot reach or exceed"):
            relativistic_impact_kinetic_energy(self.M_DUST_KG, SPEED_OF_LIGHT_M_S)
        with pytest.raises(ValueError, match="cannot reach or exceed"):
            relativistic_impact_momentum(self.M_DUST_KG, SPEED_OF_LIGHT_M_S * 1.1)

    def test_ultra_relativistic_regime_gate(self) -> None:
        assert not is_ultra_relativistic_regime(100.0)
        assert not is_ultra_relativistic_regime(15_000.0)
        assert not is_ultra_relativistic_regime(2.9e6)  # just below 0.01c
        assert is_ultra_relativistic_regime(3.1e6)  # above 0.01c
        assert is_ultra_relativistic_regime(0.1 * SPEED_OF_LIGHT_M_S)

    def test_regime_threshold_constant(self) -> None:
        assert ULTRA_RELATIVISTIC_THRESHOLD_FRACTION_C == 0.01
