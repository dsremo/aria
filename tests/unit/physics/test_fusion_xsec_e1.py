"""Unit tests for Pod E1 — fusion xsec + breeding (P1-11).

Benchmarks:
  - Bosch & Hale 1992 *Nucl Fusion* 32 611 Table VII — D-T reactivity
    at 10, 15, 20 keV.
  - Bosch & Hale 1992 Table I — Q_DT = 17.589 MeV, E_n = 14.028 MeV.
  - Brown et al. 2018 *Nucl Data Sheets* 148 1 — ENDF/B-VIII.0
    ⁶Li(n,α)T thermal 940 barn.
  - Meija et al. 2016 *Pure Appl Chem* 88 293 — ⁶Li 7.59 %.
  - Abdou et al. 2015 *Fusion Eng Des* 100 2 — TBR ≥ 1.10.
  - Bell & Glasstone 1970 *Nuclear Reactor Theory* eq. 2-127 —
    Breit-Wigner lineshape.
"""

from __future__ import annotations

import pytest

from aria.physics.fusion_xsec import (
    LI6_NALPHA_THERMAL_BARN,
    LI6_NATURAL_ABUNDANCE,
    LI7_NALPHA_THRESHOLD_MEV,
    Q_DT_MEV,
    Q_NEUTRON_DT_MEV,
    REQUIRED_TBR_ABDOU_2015,
    bosch_hale_dt_reactivity_m3_s,
    breit_wigner_capture_cross_section_barn,
    fusion_power_density_w_m3,
    fusion_power_volumetric,
    meets_tbr_requirement,
)


# ──────────────────────────────────────────────────────────────────────
#  Bosch-Hale constants and Q value
# ──────────────────────────────────────────────────────────────────────


def test_q_dt_bosch_hale_table_1():
    """Bosch & Hale 1992 Table I: Q_DT = 17.589 MeV, E_n = 14.028."""
    assert Q_DT_MEV == 17.589
    assert Q_NEUTRON_DT_MEV == 14.028


def test_bosch_hale_reactivity_rejects_nonpositive_t():
    with pytest.raises(ValueError):
        bosch_hale_dt_reactivity_m3_s(0.0)


def test_bosch_hale_reactivity_at_10_kev():
    """Bosch & Hale 1992 Table VII reference value.

    Published: ⟨σv⟩(10 keV) ≈ 1.13×10⁻²² m³/s for D-T.
    """
    sv = bosch_hale_dt_reactivity_m3_s(10.0)
    assert 1.0e-22 < sv < 1.3e-22, f"<σv>(10 keV) = {sv:.3e}"


def test_bosch_hale_reactivity_at_15_kev():
    """Bosch & Hale 1992 Table VII: ⟨σv⟩(15 keV) ≈ 2.65×10⁻²² m³/s."""
    sv = bosch_hale_dt_reactivity_m3_s(15.0)
    assert 2.3e-22 < sv < 3.0e-22, f"<σv>(15 keV) = {sv:.3e}"


def test_bosch_hale_reactivity_at_20_kev():
    """Bosch & Hale 1992 Table VII: ⟨σv⟩(20 keV) ≈ 4.24×10⁻²² m³/s."""
    sv = bosch_hale_dt_reactivity_m3_s(20.0)
    assert 3.8e-22 < sv < 4.7e-22, f"<σv>(20 keV) = {sv:.3e}"


def test_bosch_hale_reactivity_monotone_in_temperature():
    """Up to the peak around 60-70 keV <σv> is strictly increasing."""
    vals = [bosch_hale_dt_reactivity_m3_s(t) for t in (5.0, 10.0, 20.0, 40.0)]
    for i in range(len(vals) - 1):
        assert vals[i + 1] > vals[i]


# ──────────────────────────────────────────────────────────────────────
#  Fusion power
# ──────────────────────────────────────────────────────────────────────


def test_fusion_power_density_scales_with_n2():
    p1 = fusion_power_density_w_m3(
        deuterium_density_m3=1.0e19,
        tritium_density_m3=1.0e19,
        ion_temperature_kev=10.0,
    )
    p2 = fusion_power_density_w_m3(
        deuterium_density_m3=2.0e19,
        tritium_density_m3=2.0e19,
        ion_temperature_kev=10.0,
    )
    # P ∝ n_D · n_T → P2 / P1 = 4
    assert p2 / p1 == pytest.approx(4.0, rel=1.0e-6)


def test_fusion_power_volumetric_jet_dte1_ballpark():
    """Keilhacker 1999 JET DTE1 #42976: T_i ≈ 13 keV, n_D ≈ n_T ≈
    2.5e19 m⁻³, V ≈ 80 m³, peak fusion power ~16 MW. Pure Maxwellian
    Bosch-Hale should agree to within a factor of ~2 (JET was not
    fully thermal at peak).
    """
    p = fusion_power_volumetric(
        deuterium_density_m3=2.5e19,
        tritium_density_m3=2.5e19,
        ion_temperature_kev=13.0,
        volume_m3=80.0,
    )
    assert 5.0e6 < p < 5.0e7, f"P_fus = {p/1e6:.1f} MW"


def test_fusion_power_rejects_zero_volume():
    with pytest.raises(ValueError):
        fusion_power_volumetric(1e19, 1e19, 10.0, 0.0)


# ──────────────────────────────────────────────────────────────────────
#  Breit-Wigner
# ──────────────────────────────────────────────────────────────────────


def test_breit_wigner_peak_at_resonance():
    """σ_γ(E=E₀) = σ_0 · Γ_γ Γ_n / Γ²."""
    sigma_peak = breit_wigner_capture_cross_section_barn(
        energy_ev=6.67,
        resonance_energy_ev=6.67,
        total_width_ev=0.027,
        neutron_width_ev=0.0015,
        gamma_width_ev=0.023,
        peak_sigma_0_barn=2.1e5,  # textbook ²³⁸U 6.67 eV (elastic + capture)
    )
    expected = 2.1e5 * (0.023 * 0.0015) / (0.027 * 0.027)
    assert sigma_peak == pytest.approx(expected, rel=1.0e-9)


def test_breit_wigner_half_width_half_maximum():
    """At E = E₀ + Γ/2 the cross section drops to half of the peak."""
    common = dict(
        resonance_energy_ev=6.67,
        total_width_ev=0.027,
        neutron_width_ev=0.0015,
        gamma_width_ev=0.023,
        peak_sigma_0_barn=2.1e5,
    )
    peak = breit_wigner_capture_cross_section_barn(energy_ev=6.67, **common)
    half = breit_wigner_capture_cross_section_barn(
        energy_ev=6.67 + 0.027 / 2.0, **common
    )
    assert half == pytest.approx(0.5 * peak, rel=1.0e-9)


def test_breit_wigner_symmetric_about_resonance():
    common = dict(
        resonance_energy_ev=100.0,
        total_width_ev=1.0,
        neutron_width_ev=0.5,
        gamma_width_ev=0.5,
        peak_sigma_0_barn=1000.0,
    )
    s_lo = breit_wigner_capture_cross_section_barn(energy_ev=99.0, **common)
    s_hi = breit_wigner_capture_cross_section_barn(energy_ev=101.0, **common)
    assert s_lo == pytest.approx(s_hi, rel=1.0e-9)


def test_breit_wigner_rejects_nonpositive_width():
    with pytest.raises(ValueError):
        breit_wigner_capture_cross_section_barn(
            energy_ev=1.0,
            resonance_energy_ev=1.0,
            total_width_ev=0.0,
            neutron_width_ev=0.1,
            gamma_width_ev=0.1,
            peak_sigma_0_barn=1.0,
        )


# ──────────────────────────────────────────────────────────────────────
#  ENDF anchors and TBR gate
# ──────────────────────────────────────────────────────────────────────


def test_li6_thermal_brown_2018():
    """ENDF/B-VIII.0 MT=105 at 0.0253 eV: 940 barn."""
    assert LI6_NALPHA_THERMAL_BARN == 940.0


def test_li6_natural_abundance_iupac_2021():
    assert LI6_NATURAL_ABUNDANCE == pytest.approx(0.0759)


def test_li7_threshold_endf():
    assert LI7_NALPHA_THRESHOLD_MEV == 2.467


def test_tbr_gate_abdou_2015():
    assert REQUIRED_TBR_ABDOU_2015 == 1.10
    assert meets_tbr_requirement(1.15)
    assert not meets_tbr_requirement(1.00)
    assert meets_tbr_requirement(1.10)


def test_tbr_rejects_negative():
    with pytest.raises(ValueError):
        meets_tbr_requirement(-0.1)
