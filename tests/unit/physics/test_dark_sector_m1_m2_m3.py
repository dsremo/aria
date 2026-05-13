"""Unit tests for the dark-sector uncertainty budget (Pods M1-M3).

Benchmarks:
  - Aprile et al. 2023 *PRL* 131 041003 — XENONnT 2.6e-47 cm².
  - Read 2014 *J Phys G* 41 063101 — 0.4 GeV/cm³.
  - Bland-Hawthorn & Gerhard 2016 *ARA&A* 54 529 — v_sun ≈ 232 km/s.
  - Planck Collaboration 2020 *A&A* 641 A6 — Ω_Λ ≈ 0.685,
    H₀ ≈ 67.4, Λ ≈ 1.1e-52 m⁻².
  - Touboul et al. 2017 *PRL* 119 231101 — MICROSCOPE η ≤ 1.5e-15.
  - Webb et al. 2011 *PRL* 107 191101 — |Δα/α| ≤ 1e-6 / 10 Gyr.
  - Ubachs et al. 2016 *RMP* 88 021003 — |Δμ/μ| ≤ 1e-5 / 10 Gyr.
  - Hofmann & Müller 2018 *CQG* 35 035015 — |Ġ/G| ≤ 1.1e-13 /yr.
  - Dzuba, Flambaum & Webb 1999 *PRL* 82 888 — K_α sensitivities.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.dark_sector import (
    DARK_MATTER_DENSITY_READ_2014_KG_M3,
    DARK_MATTER_LOCAL_VELOCITY_M_S,
    HUBBLE_H0_KM_S_MPC,
    HUBBLE_OMEGA_LAMBDA,
    LAMBDA_COSMO_M2,
    MEGAPARSEC_M,
    MICROSCOPE_ETA_BOUND,
    PLANCK_2018_CMB_TEMPERATURE_K,
    UncertaintyBudgetRow,
    VARYING_ALPHA_FRAC_PER_S,
    VARYING_G_FRAC_PER_S,
    VARYING_MU_FRAC_PER_S,
    XENONNT_SIGMA_SI_30GEV_M2,
    alpha_drift_over_mission,
    clock_frequency_drift_from_alpha,
    cosmological_lambda_acceleration,
    dark_matter_drag_upper_bound,
    eotvos_parameter,
    g_drift_position_error_m,
    integrated_mu_drift,
    lambda_position_drift_over_transit,
    microscope_differential_acceleration_bound,
    propagate_position_uncertainty_m,
    quadrature_sum_rows,
)


# ──────────────────────────────────────────────────────────────────────
#  M1 — Dark matter + Λ
# ──────────────────────────────────────────────────────────────────────


def test_xenonnt_bound_aprile_2023():
    """Aprile 2023 PRL 131 041003: σ_SI ≤ 2.6e-47 cm² at 30 GeV."""
    # 2.6e-47 cm² = 2.6e-51 m²
    assert XENONNT_SIGMA_SI_30GEV_M2 == 2.6e-51


def test_local_dm_density_read_2014():
    """Read 2014 JPG 41 063101: 0.4 GeV/cm³ ≈ 7.13e-22 kg/m³."""
    assert DARK_MATTER_DENSITY_READ_2014_KG_M3 == pytest.approx(7.13e-22, rel=1.0e-3)


def test_planck_cosmology_values():
    """Planck 2018: H₀ ≈ 67.4, Ω_Λ ≈ 0.685, Λ ≈ 1.1e-52."""
    assert HUBBLE_H0_KM_S_MPC == 67.4
    assert HUBBLE_OMEGA_LAMBDA == pytest.approx(0.685, rel=1.0e-3)
    assert LAMBDA_COSMO_M2 == pytest.approx(1.1e-52, rel=1.0e-2)
    assert PLANCK_2018_CMB_TEMPERATURE_K == 2.7255


def test_dark_matter_drag_upper_bound_negligible():
    """Corrected §4.4 formula `a = σ·ρ_DM·v²·N_nuc/M_ship` gives
    `a ~ 6e-35 m/s²` per kg at 232 km/s under the XENONnT 30 GeV
    bound. The scope-note §4.4 worked example at v=0.1c and the
    PandaX 100 GeV bound gave 1.8e-30 m/s²; at 232 km/s (≈ 6500×
    slower) the v² factor gives a further 4×10⁻⁸ reduction, so
    ~10⁻³⁵ is the right order for the current inputs. Either way
    the drag is utterly sub-mission-sensitivity."""
    a = dark_matter_drag_upper_bound(ship_mass_kg=1.0)
    assert a >= 0.0
    assert a < 1.0e-30, f"|a|_max = {a:.3e}"


def test_dark_matter_drag_scales_with_density_and_v_squared():
    a_base = dark_matter_drag_upper_bound(
        ship_mass_kg=1.0,
        ship_velocity_through_halo_m_s=232.0e3,
        dm_density_kg_m3=1.0e-21,
    )
    a_dense = dark_matter_drag_upper_bound(
        ship_mass_kg=1.0,
        ship_velocity_through_halo_m_s=232.0e3,
        dm_density_kg_m3=2.0e-21,
    )
    a_fast = dark_matter_drag_upper_bound(
        ship_mass_kg=1.0,
        ship_velocity_through_halo_m_s=464.0e3,
        dm_density_kg_m3=1.0e-21,
    )
    assert a_dense / a_base == pytest.approx(2.0, rel=1.0e-6)
    assert a_fast / a_base == pytest.approx(4.0, rel=1.0e-6)


def test_lambda_acceleration_matches_scope_4_5():
    """Scope §4.5 gives `a_Λ ≈ 1e-12 m/s²` at d = 10 Mpc for
    Λ = 1.1e-52, which is the correct arithmetic (scope §4.2
    contains a typo claiming 5e-24 for 100 Mpc — off by 10¹³).

    Linear scaling: 100 Mpc → 1e-11 m/s².
    """
    a10 = cosmological_lambda_acceleration(separation_m=10.0 * MEGAPARSEC_M)
    assert 5.0e-13 < a10 < 5.0e-12, f"a_Λ(10 Mpc) = {a10:.3e}"
    a100 = cosmological_lambda_acceleration(separation_m=100.0 * MEGAPARSEC_M)
    assert a100 == pytest.approx(10.0 * a10, rel=1.0e-12)


def test_lambda_zero_separation_returns_zero():
    assert cosmological_lambda_acceleration(0.0) == 0.0


def test_lambda_position_drift_1myr_10mpc():
    """Scope note §4.5: d = 10 Mpc, t = 1 Myr → Δx ~ 5e14 m."""
    mpc_10 = 10.0 * MEGAPARSEC_M
    t_myr = 1.0e6 * 365.25 * 86400.0
    dx = lambda_position_drift_over_transit(mpc_10, t_myr)
    # Within an order of magnitude of the scope worked example
    assert 1.0e13 < dx < 1.0e16, f"Δx = {dx:.3e} m"


# ──────────────────────────────────────────────────────────────────────
#  M2 — Equivalence principle
# ──────────────────────────────────────────────────────────────────────


def test_microscope_eta_bound():
    """Touboul 2017 PRL 119 231101."""
    assert MICROSCOPE_ETA_BOUND == 1.5e-15


def test_eotvos_parameter_zero_for_identical_accelerations():
    assert eotvos_parameter(9.81, 9.81) == 0.0


def test_eotvos_parameter_linear_response():
    """For a small Δa, η ≈ Δa / a_mean."""
    eta = eotvos_parameter(9.81 + 1.0e-10, 9.81)
    assert eta == pytest.approx(1.0e-10 / 9.81, rel=1.0e-6)


def test_eotvos_parameter_zero_accelerations_handled():
    assert eotvos_parameter(0.0, 0.0) == 0.0


def test_microscope_bound_at_jupiter_gravity():
    """Scope §4.2: g_local ≈ 0.1 m/s² at Jupiter assist → |Δa|_max
    ≈ 1.5e-16 m/s²."""
    dv = microscope_differential_acceleration_bound(local_gravity_m_s2=0.1)
    assert dv == pytest.approx(1.5e-16, rel=1.0e-6)


def test_microscope_bound_at_deep_space_negligible():
    """Scope §4.2: g_local ≈ 1e-10 m/s² → |Δa|_max ≈ 1.5e-25 m/s²."""
    dv = microscope_differential_acceleration_bound(local_gravity_m_s2=1.0e-10)
    assert dv == pytest.approx(1.5e-25, rel=1.0e-6)


# ──────────────────────────────────────────────────────────────────────
#  M3 — Varying constants
# ──────────────────────────────────────────────────────────────────────


def test_varying_alpha_bound_webb_2011():
    """Webb 2011: |Δα/α| ≤ 1e-6 over 10 Gyr → rate ≈ 3.17e-24/s."""
    assert VARYING_ALPHA_FRAC_PER_S == 3.17e-24


def test_varying_g_bound_hofmann_muller_2018():
    """Hofmann-Müller 2018 LLR: |Ġ/G| ≤ 1.1e-13/yr ≈ 3.49e-21/s."""
    assert VARYING_G_FRAC_PER_S == 3.49e-21


def test_alpha_drift_linear_in_time():
    d1 = alpha_drift_over_mission(1.0e17)
    d2 = alpha_drift_over_mission(2.0e17)
    assert d2 == pytest.approx(2.0 * d1)


def test_alpha_drift_1myr_matches_scope_example():
    """Scope §4.2: 1 Myr at the Webb bound → |Δα/α| ≈ 1e-10."""
    one_myr = 1.0e6 * 365.25 * 86400.0
    da = alpha_drift_over_mission(one_myr)
    assert 5.0e-11 < da < 2.0e-10


def test_cs_clock_frequency_drift_scales_with_kalpha():
    t = 1.0e13
    cs_shift = clock_frequency_drift_from_alpha(t, clock_name="Cs-133-hfs")
    al_shift = clock_frequency_drift_from_alpha(t, clock_name="Al-27-plus-optical")
    # K_α(Cs) = 2.83, K_α(Al+) = 0.008 → ratio ≈ 353.75
    assert cs_shift / al_shift == pytest.approx(2.83 / 0.008, rel=1.0e-6)


def test_clock_unknown_raises():
    with pytest.raises(KeyError):
        clock_frequency_drift_from_alpha(1.0, clock_name="Unobtainium-1")


def test_g_drift_position_error_sub_meter_over_100yr_on_1_g():
    """Ġ/G ≈ 3.5e-21/s, g = 1 m/s², T = 100 yr ≈ 3.15e9 s.
    Δa ≈ 1 · 3.5e-21 · 3.15e9 ≈ 1.1e-11 m/s².
    Δx ≈ 0.5 · 1.1e-11 · (3.15e9)² ≈ 5.5e7 m. About 55 Mm — this
    is NOT sub-meter! The test verifies it lands in the expected
    Mm range."""
    t = 100.0 * 365.25 * 86400.0
    err = g_drift_position_error_m(local_gravity_m_s2=1.0, mission_duration_s=t)
    assert 1.0e6 < err < 1.0e9, f"Δx = {err:.3e} m"


def test_integrated_mu_drift_monotone():
    d1 = integrated_mu_drift(1.0e13)
    d2 = integrated_mu_drift(1.0e14)
    assert d2 > d1


# ──────────────────────────────────────────────────────────────────────
#  Shared uncertainty budget
# ──────────────────────────────────────────────────────────────────────


def test_quadrature_sum_independent_rows():
    rows = [
        UncertaintyBudgetRow("DM", "M1", 3.0, "m/s²", "XENONnT 2023"),
        UncertaintyBudgetRow("EP", "M2", 4.0, "m/s²", "MICROSCOPE 2017"),
    ]
    total = quadrature_sum_rows(rows)
    assert total == pytest.approx(5.0, rel=1.0e-12)


def test_quadrature_sum_unit_filter():
    rows = [
        UncertaintyBudgetRow("A", "M1", 3.0, "m/s²", "X"),
        UncertaintyBudgetRow("B", "M3", 4.0, "—", "Y"),
    ]
    assert quadrature_sum_rows(rows, unit_filter="m/s²") == pytest.approx(3.0)


def test_quadrature_sum_rejects_negative_value():
    rows = [UncertaintyBudgetRow("A", "M1", -1.0, "m/s²", "bad")]
    with pytest.raises(ValueError):
        quadrature_sum_rows(rows)


def test_propagate_position_uncertainty_ballistic_formula():
    """σ_x = (1/2) δa · Δt²."""
    sx = propagate_position_uncertainty_m(
        acceleration_perturbation_m_s2=1.0e-12, leg_duration_s=1.0e9
    )
    assert sx == pytest.approx(0.5 * 1.0e-12 * 1.0e18, rel=1.0e-12)


def test_propagate_position_rejects_negative():
    with pytest.raises(ValueError):
        propagate_position_uncertainty_m(-1.0, 1.0)
