"""Unit tests for Pod D2 — Spacecraft charging (P1-4 + P1-8).

Canonical benchmarks:
  - Chen 2016 *Introduction to Plasma Physics* 3rd ed — Debye length.
  - Lai 2012 *Fundamentals of Spacecraft Charging* §4.1 — SCATHA eclipse.
  - Mullen et al. 1986 *J Spacecr Rockets* 23 593 — SCATHA 1979 event.
  - Redfield & Linsky 2008 *ApJ* 673 283 — local interstellar cloud.
  - NASA-HDBK-4002A 2011 §5 — dielectric properties, CSDA range,
    breakdown thresholds.
  - Frederickson et al. 1991 *IEEE Trans Nucl Sci* 38 1493 — deep
    dielectric charging steady state.
  - Koons et al. 2000 6th SCTC AFRL-VS-TR-20001578 — ESD rate vs field.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.mhd_plasma.constants import PLASMA_CONSTANTS
from aria.physics.sc_charging import (
    DIELECTRIC_TABLE,
    arc_energy_parallel_plate,
    ambient_electron_current_density,
    ambient_ion_current_density,
    child_langmuir_sheath_thickness,
    csda_range_kg_m2,
    csda_range_m,
    debye_length,
    equilibrium_surface_potential,
    esd_probability_per_hour,
    esd_triggered,
    get_dielectric,
    peak_internal_field_parallel_plate,
    photoemission_current_density,
    worst_case_eclipse_potential,
)
from aria.physics.sc_charging.deep_dielectric import charging_time_constant_s


# ──────────────────────────────────────────────────────────────────────
#  Debye length — canonical benchmarks
# ──────────────────────────────────────────────────────────────────────


def test_debye_length_geo_substorm_chen_2016():
    """Chen 2016 Table 1: GEO substorm λ_D ≈ 700 m.

    T_e = 10 keV, n_e = 1 cm⁻³ = 1e6 m⁻³. Analytic result ≈ 743 m.
    Lai 2012 §4.1 cites 'hundreds of meters'.
    """
    lam = debye_length(electron_density_m3=1.0e6, electron_temperature_ev=1.0e4)
    assert 700.0 < lam < 780.0, f"GEO substorm λ_D = {lam:.1f} m"


def test_debye_length_local_interstellar_cloud():
    """Redfield & Linsky 2008 ApJ 673 283.

    LIC: n_e ≈ 0.1 cm⁻³, T_e ≈ 8000 K = 0.689 eV. Analytic ≈ 19.6 m.
    """
    # 8000 K in eV
    t_e_ev = 8000.0 * PLASMA_CONSTANTS.k_b_j_k / PLASMA_CONSTANTS.e_c
    lam = debye_length(electron_density_m3=1.0e5, electron_temperature_ev=t_e_ev)
    assert 15.0 < lam < 25.0, f"LIC λ_D = {lam:.1f} m"


def test_debye_length_rejects_nonpositive():
    with pytest.raises(ValueError):
        debye_length(electron_density_m3=0.0, electron_temperature_ev=1.0)
    with pytest.raises(ValueError):
        debye_length(electron_density_m3=1.0, electron_temperature_ev=-1.0)


# ──────────────────────────────────────────────────────────────────────
#  Sheath thickness
# ──────────────────────────────────────────────────────────────────────


def test_child_langmuir_sheath_reduces_to_debye_for_weak_potential():
    s = child_langmuir_sheath_thickness(
        debye_length_m=10.0, surface_potential_v=-1.0, electron_temperature_ev=10.0
    )
    assert s == pytest.approx(10.0)


def test_child_langmuir_scales_with_phi_3_4():
    """s/λ_D = (eφ/kT)^{3/4}. For φ = 100·T, s/λ_D ≈ 100^{3/4} ≈ 31.62."""
    s = child_langmuir_sheath_thickness(
        debye_length_m=1.0, surface_potential_v=-1000.0, electron_temperature_ev=10.0
    )
    assert s == pytest.approx(100.0**0.75, rel=1e-6)


# ──────────────────────────────────────────────────────────────────────
#  Ambient current densities
# ──────────────────────────────────────────────────────────────────────


def test_electron_thermal_current_zero_potential():
    """At φ=0 the electron current is j = (1/4) e n_e v̄_e.

    For T_e = 1 eV, n_e = 1e6 m⁻³ the thermal current density is
    about 26.7 μA/m² (Chen 2016 §8.2).
    """
    j = ambient_electron_current_density(
        electron_density_m3=1.0e6,
        electron_temperature_ev=1.0,
        surface_potential_v=0.0,
    )
    # v̄ = √(8·1.6e-19 / (π·9.11e-31)) ≈ 6.69e5 m/s
    # j = 0.25·1.6e-19·1e6·6.69e5 ≈ 2.68e-8 A/m²
    assert j == pytest.approx(2.68e-8, rel=0.05)


def test_electron_current_boltzmann_suppressed_at_negative_phi():
    """φ = −5 T_e should suppress the electron current by exp(−5)."""
    j0 = ambient_electron_current_density(1e12, 1.0, 0.0)
    j1 = ambient_electron_current_density(1e12, 1.0, -5.0)
    assert j1 / j0 == pytest.approx(math.exp(-5.0), rel=1e-6)


def test_ion_current_oml_enhancement_negative_phi():
    """At strong negative φ, ion current is linearly enhanced."""
    j0 = ambient_ion_current_density(
        ion_density_m3=1e12,
        ion_temperature_ev=1.0,
        ion_mass_kg=PLASMA_CONSTANTS.m_p_kg,
        surface_potential_v=0.0,
    )
    j1 = ambient_ion_current_density(
        ion_density_m3=1e12,
        ion_temperature_ev=1.0,
        ion_mass_kg=PLASMA_CONSTANTS.m_p_kg,
        surface_potential_v=-100.0,
    )
    assert j1 / j0 == pytest.approx(101.0, rel=1e-6)


def test_current_density_rejects_nonpositive():
    with pytest.raises(ValueError):
        ambient_electron_current_density(-1.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        ambient_ion_current_density(1.0, 1.0, 0.0, 0.0)


# ──────────────────────────────────────────────────────────────────────
#  Photoemission
# ──────────────────────────────────────────────────────────────────────


def test_photoemission_zero_in_eclipse():
    assert photoemission_current_density(sunlit=False) == 0.0


def test_photoemission_inverse_square():
    """j_ph ∝ 1/r². At 10 AU should be 100× weaker than at 1 AU."""
    j_1 = photoemission_current_density(sunlit=True, solar_distance_au=1.0)
    j_10 = photoemission_current_density(sunlit=True, solar_distance_au=10.0)
    assert j_1 / j_10 == pytest.approx(100.0, rel=1e-6)


def test_photoemission_1au_value_lai_2012():
    """Lai 2012 Table 3.1: j_ph ≈ 2×10⁻⁵ A/m² at 1 AU."""
    j = photoemission_current_density(sunlit=True, solar_distance_au=1.0)
    assert j == pytest.approx(2.0e-5, rel=1e-12)


# ──────────────────────────────────────────────────────────────────────
#  Worst-case eclipse potential — SCATHA benchmark
# ──────────────────────────────────────────────────────────────────────


def test_eclipse_potential_order_kilovolts_at_scatha_conditions():
    """Mullen et al. 1986: SCATHA -8 to -14 kV in GEO substorm.

    With T_e = 10 keV, δ_eff = 0.3, proton-mass ions, the closed-form
    worst-case gives φ ≈ −24.8 kV — a conservative upper bound to the
    observed peak of −14 kV. This test verifies we land in the
    kilovolt range with the correct sign.
    """
    phi = worst_case_eclipse_potential(
        electron_temperature_ev=1.0e4, effective_se_yield=0.3
    )
    assert -5.0e4 < phi < -1.0e4, f"worst-case φ = {phi:.0f} V"


def test_eclipse_potential_rejects_yield_ge_one():
    with pytest.raises(ValueError):
        worst_case_eclipse_potential(electron_temperature_ev=1.0e4, effective_se_yield=1.2)


def test_eclipse_potential_zero_yield_is_most_negative():
    """Higher secondary yield → less negative potential."""
    phi_0 = worst_case_eclipse_potential(1.0e4, effective_se_yield=0.0)
    phi_1 = worst_case_eclipse_potential(1.0e4, effective_se_yield=0.5)
    assert phi_0 < phi_1 < 0.0


# ──────────────────────────────────────────────────────────────────────
#  Equilibrium surface potential — full current balance
# ──────────────────────────────────────────────────────────────────────


def test_sunlit_solar_wind_surface_is_mildly_positive():
    """Sunlit solar-wind plasma: photoemission dominates → φ ≳ 0 V.

    Lai 2012 §3.3 / Whipple 1981 Rep Prog Phys 44 1197: in the tenuous
    solar wind (n_e ~ 5 cm⁻³, T_e ~ 10 eV) the thermal electron
    current (~4×10⁻⁷ A/m²) is two orders of magnitude below the
    1 AU photoemission current (2×10⁻⁵ A/m²), so the frame charges
    *positive* until enough electrons are attracted to balance.
    """
    phi = equilibrium_surface_potential(
        electron_density_m3=5.0e6,
        electron_temperature_ev=10.0,
        ion_density_m3=5.0e6,
        ion_temperature_ev=10.0,
        ion_mass_kg=PLASMA_CONSTANTS.m_p_kg,
        sunlit=True,
        solar_distance_au=1.0,
    )
    assert 0.0 < phi < 1000.0, f"solar-wind sunlit φ = {phi:.2f} V"


def test_eclipse_geo_substorm_charges_kilovolts_negative():
    """GEO substorm eclipse: strongly negative frame."""
    phi = equilibrium_surface_potential(
        electron_density_m3=1.0e6,
        electron_temperature_ev=1.0e4,
        ion_density_m3=1.0e6,
        ion_temperature_ev=1.0e4,
        ion_mass_kg=PLASMA_CONSTANTS.m_p_kg,
        sunlit=False,
    )
    assert phi < -1.0e3, f"GEO eclipse φ = {phi:.0f} V"


# ──────────────────────────────────────────────────────────────────────
#  CSDA range
# ──────────────────────────────────────────────────────────────────────


def test_csda_range_1mev_handbook():
    """NASA-HDBK-4002A §5.3 example: 1 MeV electron ≈ 0.412 g/cm².

    At E = 1 MeV, ln E = 0, so R = 0.412 × 1 = 0.412 g/cm² = 4.12 kg/m².
    """
    r = csda_range_kg_m2(1.0)
    assert r == pytest.approx(4.12, rel=1e-3)


def test_csda_range_2mev_kapton_is_centimeter_scale():
    """NASA-HDBK-4002A §5.3: 2 MeV electrons in Kapton ≈ 1 cm."""
    r_m = csda_range_m(2.0, density_kg_m3=1420.0)
    assert 5.0e-3 < r_m < 2.0e-2, f"R_m(2 MeV, Kapton) = {r_m*1000:.2f} mm"


def test_csda_range_monotone_in_energy():
    r1 = csda_range_kg_m2(0.5)
    r2 = csda_range_kg_m2(1.0)
    r3 = csda_range_kg_m2(2.0)
    assert r1 < r2 < r3


# ──────────────────────────────────────────────────────────────────────
#  Deep-dielectric steady state
# ──────────────────────────────────────────────────────────────────────


def test_peak_field_linear_in_flux_frederickson():
    """E_peak = J_0 / σ (Frederickson 1991 eq. 5)."""
    e1 = peak_internal_field_parallel_plate(
        injected_current_density_a_m2=1.0e-10,
        dielectric_thickness_m=2.5e-4,
        bulk_conductivity_s_m=1.0e-18,
    )
    assert e1 == pytest.approx(1.0e8, rel=1e-6)
    e2 = peak_internal_field_parallel_plate(
        injected_current_density_a_m2=2.0e-10,
        dielectric_thickness_m=2.5e-4,
        bulk_conductivity_s_m=1.0e-18,
    )
    assert e2 == pytest.approx(2.0e8, rel=1e-6)


def test_peak_field_kapton_reaches_breakdown_at_modest_flux():
    """Frederickson et al. 1992 IEEE TNS 39 1773: 2 MeV e⁻ at
    10⁶ cm⁻²s⁻¹ (= 1e10 m⁻²s⁻¹, J ≈ 1.6e-9 A/m²) drives Kapton to
    breakdown once RIC σ ≈ 1e-17 (dark × 10): E ≈ 1.6e8 V/m.
    """
    e = peak_internal_field_parallel_plate(
        injected_current_density_a_m2=1.6e-9,
        dielectric_thickness_m=2.5e-4,
        bulk_conductivity_s_m=1.0e-17,
    )
    # 1.6e8 V/m is within a factor of 2 of the Kapton E_BD = 2.5e8.
    kapton = get_dielectric("Kapton-H")
    assert 0.5 * kapton.breakdown_field_v_m <= e <= 2.0 * kapton.breakdown_field_v_m


def test_charging_time_constant_kapton_is_weeks_to_months():
    """τ = ε_r ε_0 / σ. For Kapton dark: ~3.1e7 s ≈ 360 days."""
    kapton = get_dielectric("Kapton-H")
    tau = charging_time_constant_s(
        relative_permittivity=kapton.relative_permittivity,
        bulk_conductivity_s_m=kapton.dark_conductivity_s_m,
    )
    assert 1.0e7 < tau < 1.0e8


# ──────────────────────────────────────────────────────────────────────
#  ESD trigger
# ──────────────────────────────────────────────────────────────────────


def test_esd_triggered_at_breakdown():
    kapton = get_dielectric("Kapton-H")
    assert esd_triggered(kapton.breakdown_field_v_m, kapton.breakdown_field_v_m)
    assert esd_triggered(-kapton.breakdown_field_v_m, kapton.breakdown_field_v_m)


def test_esd_not_triggered_below_breakdown():
    kapton = get_dielectric("Kapton-H")
    assert not esd_triggered(0.9 * kapton.breakdown_field_v_m, kapton.breakdown_field_v_m)


def test_arc_energy_kapton_patch_milijoule_range():
    """Kapton 1 cm² × 250 µm at E_BD stores ~24 mJ.

    U = 0.5·ε_0·ε_r·E²·A·d
      = 0.5 · 8.854e-12 · 3.5 · (2.5e8)² · 1e-4 · 2.5e-4
      ≈ 2.42e-2 J ≈ 24 mJ
    — within the 1 mJ → 1 J on-orbit ESD range cataloged by
    Leach & Alexander 1995 NASA/TP-2003-212287 §3.4.
    """
    kapton = get_dielectric("Kapton-H")
    u = arc_energy_parallel_plate(
        internal_field_v_m=kapton.breakdown_field_v_m,
        area_m2=1.0e-4,
        thickness_m=2.5e-4,
        relative_permittivity=kapton.relative_permittivity,
    )
    assert 1.0e-2 < u < 5.0e-2, f"U_arc = {u*1000:.2f} mJ"


def test_esd_probability_piecewise_koons_2000():
    """Probability curve: 0 below 0.5·E_BD, linear to 1/h at E_BD,
    saturated above."""
    assert esd_probability_per_hour(internal_field_v_m=0.0, breakdown_field_v_m=1.0e8) == 0.0
    assert esd_probability_per_hour(
        internal_field_v_m=0.75e8, breakdown_field_v_m=1.0e8
    ) == pytest.approx(0.5, rel=1e-6)
    assert esd_probability_per_hour(
        internal_field_v_m=1.0e8, breakdown_field_v_m=1.0e8
    ) == pytest.approx(1.0, rel=1e-6)
    assert esd_probability_per_hour(
        internal_field_v_m=1.5e8, breakdown_field_v_m=1.0e8
    ) == pytest.approx(1.0, rel=1e-6)


# ──────────────────────────────────────────────────────────────────────
#  Materials DB
# ──────────────────────────────────────────────────────────────────────


def test_dielectric_table_has_canonical_kapton():
    d = get_dielectric("Kapton-H")
    assert d.breakdown_field_v_m == pytest.approx(2.5e8)
    assert d.relative_permittivity == pytest.approx(3.5)
    assert d.dark_conductivity_s_m == pytest.approx(1.0e-18)


def test_dielectric_table_has_teflon_and_hdpe():
    assert "Teflon-FEP" in DIELECTRIC_TABLE
    assert "HDPE" in DIELECTRIC_TABLE


def test_get_dielectric_unknown_raises():
    with pytest.raises(KeyError):
        get_dielectric("Unobtainium")
