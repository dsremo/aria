"""Unit tests for the cruise-drag package (ISM ram pressure, Bondi,
Chandrasekhar dynamical friction).

Benchmarks:
  - Ferrière 2001 *Rev Mod Phys* 73 1031 — ISM phase densities.
  - Redfield & Linsky 2008 *ApJ* 673 283 — Local Interstellar Cloud.
  - Bondi 1952 *MNRAS* 112 195 — λ = 1/4 for γ = 5/3.
  - Chandrasekhar 1943 *ApJ* 97 255 — f(X) lineshape.
  - Binney & Tremaine 2008 *Galactic Dynamics* 2nd ed §8.1.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.cruise_drag import (
    COLD_NEUTRAL_MEDIUM,
    ISMPhase,
    LOCAL_BUBBLE,
    LOCAL_INTERSTELLAR_CLOUD,
    WARM_NEUTRAL_MEDIUM,
    bondi_accretion_rate_kg_s,
    bondi_hoyle_rate_kg_s,
    chandrasekhar_dynamical_friction_acceleration,
    coulomb_log_default,
    get_ism_phase,
    ram_pressure_drag_acceleration,
    ram_pressure_pa,
    stopping_length_m,
)
from aria.physics.cruise_drag.bondi_accretion import G_GRAV_M3_KG_S2


# ──────────────────────────────────────────────────────────────────────
#  ISM phase table
# ──────────────────────────────────────────────────────────────────────


def test_lic_density_redfield_linsky():
    """Redfield & Linsky 2008: n_H ≈ 0.22 cm⁻³ = 2.2e5 m⁻³."""
    assert LOCAL_INTERSTELLAR_CLOUD.number_density_m3 == 2.2e5


def test_local_bubble_low_density():
    """Ferrière 2001: Local Bubble n ≈ 0.005 /cm³ = 5e3 /m³."""
    assert LOCAL_BUBBLE.number_density_m3 == 5.0e3
    assert LOCAL_BUBBLE.temperature_k == 1.0e6


def test_cnm_denser_than_wnm_denser_than_lic():
    assert (
        COLD_NEUTRAL_MEDIUM.number_density_m3
        > WARM_NEUTRAL_MEDIUM.number_density_m3
        > LOCAL_INTERSTELLAR_CLOUD.number_density_m3
    )


def test_ism_phase_mass_density_matches_number_density_times_mu_mh():
    m_h = 1.6735575e-27
    mu_neutral = 1.4
    expected = 2.2e5 * mu_neutral * m_h
    assert LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3 == pytest.approx(expected)


def test_get_ism_phase_lookup_and_error():
    assert get_ism_phase("LIC") is LOCAL_INTERSTELLAR_CLOUD
    with pytest.raises(KeyError):
        get_ism_phase("NGC1024-reactor")


# ──────────────────────────────────────────────────────────────────────
#  Ram pressure
# ──────────────────────────────────────────────────────────────────────


def test_ram_pressure_scales_with_v_squared():
    p_1 = ram_pressure_pa(mass_density_kg_m3=1.0e-21, relative_velocity_m_s=1.0e5)
    p_2 = ram_pressure_pa(mass_density_kg_m3=1.0e-21, relative_velocity_m_s=2.0e5)
    assert p_2 / p_1 == pytest.approx(4.0)


def test_drag_acceleration_handbook_formula():
    """a = C_D · (1/2) · ρ v² · A / M with C_D = 2."""
    a = ram_pressure_drag_acceleration(
        mass_density_kg_m3=1.0e-21,
        relative_velocity_m_s=1.0e5,
        cross_section_m2=300.0,
        ship_mass_kg=1.0e6,
    )
    expected = 2.0 * 0.5 * 1.0e-21 * (1.0e5 ** 2) * 300.0 / 1.0e6
    assert a == pytest.approx(expected, rel=1.0e-12)


def test_drag_acceleration_in_lic_at_100_km_s():
    """A 1×10⁶ kg, 300 m² ship at 100 km/s through the LIC
    (ρ ≈ 5.15×10⁻²² kg/m³) sees a ≈ 1.5×10⁻¹⁵ m/s² — millions of
    times below any realistic mission threshold but non-zero."""
    rho = LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3
    a = ram_pressure_drag_acceleration(
        mass_density_kg_m3=rho,
        relative_velocity_m_s=1.0e5,
        cross_section_m2=300.0,
        ship_mass_kg=1.0e6,
    )
    assert 1.0e-16 < a < 1.0e-14, f"a_drag = {a:.3e}"


def test_stopping_length_ism_is_intergalactic_for_big_ships():
    """M = 10⁶ kg, A = 300 m², LIC ρ ≈ 5.15×10⁻²² → L_stop ≈ 3.2×10²⁴
    m ≈ 100 Mpc. Vastly larger than any realistic mission leg, which
    is the whole point of the stopping-length check — ISM drag is
    bookkeeping, not an operational hazard."""
    l = stopping_length_m(
        mass_density_kg_m3=LOCAL_INTERSTELLAR_CLOUD.mass_density_kg_m3,
        cross_section_m2=300.0,
        ship_mass_kg=1.0e6,
    )
    assert l > 1.0e23
    assert l < 1.0e26


# ──────────────────────────────────────────────────────────────────────
#  Bondi accretion
# ──────────────────────────────────────────────────────────────────────


def test_bondi_stationary_formula():
    """Ṁ = 4π λ G² M² ρ / c_s³ with λ = 1/4."""
    m = 1.0e6
    rho = 1.0e-21
    c_s = 1.0e4
    rate = bondi_accretion_rate_kg_s(
        ship_mass_kg=m, ambient_density_kg_m3=rho, ambient_sound_speed_m_s=c_s
    )
    expected = 4.0 * math.pi * 0.25 * (G_GRAV_M3_KG_S2 ** 2) * m * m * rho / (c_s ** 3)
    assert rate == pytest.approx(expected, rel=1.0e-12)


def test_bondi_scales_with_m_squared_and_rho():
    rate_1 = bondi_accretion_rate_kg_s(1.0e6, 1.0e-21, 1.0e4)
    rate_2 = bondi_accretion_rate_kg_s(2.0e6, 1.0e-21, 1.0e4)
    assert rate_2 / rate_1 == pytest.approx(4.0, rel=1.0e-9)
    rate_3 = bondi_accretion_rate_kg_s(1.0e6, 2.0e-21, 1.0e4)
    assert rate_3 / rate_1 == pytest.approx(2.0, rel=1.0e-9)


def test_bondi_hoyle_high_mach_v_minus_3_scaling():
    """For v ≫ c_s the Bondi-Hoyle rate scales as v⁻³."""
    common = dict(
        ship_mass_kg=1.0e6, ambient_density_kg_m3=1.0e-21, ambient_sound_speed_m_s=1.0
    )
    rate_low = bondi_hoyle_rate_kg_s(relative_velocity_m_s=1.0e5, **common)
    rate_hi = bondi_hoyle_rate_kg_s(relative_velocity_m_s=2.0e5, **common)
    assert rate_hi / rate_low == pytest.approx(0.125, rel=1.0e-6)  # (1/2)³


def test_bondi_hoyle_low_v_reduces_to_stationary_with_lambda_1():
    """At v → 0 the Bondi-Hoyle form uses v² + c_s² → c_s² and
    prefactor 4π (not 4π λ), so it equals 4 × the Bondi(λ=1/4) rate."""
    m, rho, cs = 1.0e6, 1.0e-21, 1.0e4
    rate_bh = bondi_hoyle_rate_kg_s(m, rho, cs, relative_velocity_m_s=0.0)
    rate_bondi = bondi_accretion_rate_kg_s(m, rho, cs, bondi_lambda=1.0)
    assert rate_bh == pytest.approx(rate_bondi, rel=1.0e-12)


# ──────────────────────────────────────────────────────────────────────
#  Chandrasekhar dynamical friction
# ──────────────────────────────────────────────────────────────────────


def test_dynamical_friction_zero_at_zero_velocity():
    a = chandrasekhar_dynamical_friction_acceleration(
        ship_mass_kg=1.0e6,
        velocity_m_s=0.0,
        background_density_kg_m3=1.0e-22,
        velocity_dispersion_m_s=1.0e5,
    )
    assert a == 0.0


def test_dynamical_friction_positive_and_bounded():
    a = chandrasekhar_dynamical_friction_acceleration(
        ship_mass_kg=1.0e6,
        velocity_m_s=1.0e5,
        background_density_kg_m3=1.0e-22,
        velocity_dispersion_m_s=2.0e5,
        coulomb_log=10.0,
    )
    # Ship scale × galactic background × ln Λ gives
    # ~ G² M ρ / v² × 4π · ln Λ × f(X) ≈ 4e-11²·1e6·1e-22/1e10·f ≈ 1e-40
    assert 0.0 < a < 1.0e-30


def test_dynamical_friction_monotone_in_ln_lambda():
    common = dict(
        ship_mass_kg=1.0e6,
        velocity_m_s=1.0e5,
        background_density_kg_m3=1.0e-22,
        velocity_dispersion_m_s=2.0e5,
    )
    a_low = chandrasekhar_dynamical_friction_acceleration(coulomb_log=3.0, **common)
    a_hi = chandrasekhar_dynamical_friction_acceleration(coulomb_log=30.0, **common)
    assert a_hi == pytest.approx(10.0 * a_low, rel=1.0e-9)


def test_coulomb_log_default_handbook_value():
    assert coulomb_log_default() == 10.0
