"""Unit tests for the thermal radiator bridge module."""

from __future__ import annotations

import math

import pytest

from aria.physics.thermal_radiator import (
    CMB_TEMPERATURE_K,
    STEFAN_BOLTZMANN_W_M2_K4,
    RadiatorPanelReport,
    carnot_ceiling_efficiency,
    fin_efficiency_gardner,
    radiator_net_rejection_w,
    sky_sink_temperature_k,
    solve_radiator_area_m2,
)


# ──────────────────────────────────────────────────────────────────────
#  Stefan-Boltzmann heat rejection
# ──────────────────────────────────────────────────────────────────────


def test_500k_panel_matches_scope_note_flux_density():
    """Scope note §14: ε=0.9 × σ × 500⁴ ≈ 3189 W/m² per panel."""
    q = radiator_net_rejection_w(
        area_m2=1.0,
        panel_temperature_k=500.0,
        sink_temperature_k=0.0,
        emissivity=0.9,
    )
    expected = 0.9 * STEFAN_BOLTZMANN_W_M2_K4 * (500.0 ** 4)
    assert q == pytest.approx(expected, rel=1.0e-12)
    assert 3100.0 < q < 3200.0


def test_cmb_sink_correction_is_ppm_level_at_500k():
    """T_sink⁴ correction at 500 K panel with 2.7 K CMB sink:
    (2.7/500)⁴ ≈ 8.5×10⁻¹⁰ — a ppb correction."""
    q_cmb = radiator_net_rejection_w(1.0, 500.0, CMB_TEMPERATURE_K, 0.9)
    q_zero = radiator_net_rejection_w(1.0, 500.0, 0.0, 0.9)
    rel = abs(q_cmb - q_zero) / q_zero
    assert rel < 1.0e-8


def test_cmb_sink_correction_dominant_for_cold_life_support_panel():
    """A 10 K panel in a 2.7 K sky cannot reject anything near the
    naïve T⁴ value — the T_sink⁴ term is 0.27⁴ ≈ 0.5 % of T_r⁴,
    so the net rejection is suppressed by that amount."""
    q_full = radiator_net_rejection_w(1.0, 10.0, CMB_TEMPERATURE_K, 0.9)
    q_naive = radiator_net_rejection_w(1.0, 10.0, 0.0, 0.9)
    assert q_full < q_naive
    assert (q_naive - q_full) / q_naive > 1.0e-3


def test_solve_area_round_trip_consistency():
    """solve_radiator_area_m2 should invert radiator_net_rejection_w."""
    area = solve_radiator_area_m2(
        heat_load_w=2.0e6, panel_temperature_k=500.0, emissivity=0.9
    )
    q_back = radiator_net_rejection_w(
        area_m2=area, panel_temperature_k=500.0, emissivity=0.9
    )
    assert q_back == pytest.approx(2.0e6, rel=1.0e-9)


def test_solve_area_2mw_at_500k_scope_note_example():
    """Scope note §18: 2 MW at 500 K ε=0.9 → A ≈ 627 m²."""
    area = solve_radiator_area_m2(2.0e6, 500.0, emissivity=0.9)
    assert 620.0 < area < 635.0


def test_solve_area_2mw_at_300k_scope_note_example():
    """Scope note §14: 2 MW at 300 K ε=0.9 → A ≈ 4843 m²."""
    area = solve_radiator_area_m2(2.0e6, 300.0, emissivity=0.9)
    assert 4700.0 < area < 4900.0


def test_solve_area_rejects_panel_at_or_below_sink():
    with pytest.raises(ValueError):
        solve_radiator_area_m2(1.0, panel_temperature_k=2.7, sink_temperature_k=2.72548)


# ──────────────────────────────────────────────────────────────────────
#  Sky sink temperature
# ──────────────────────────────────────────────────────────────────────


def test_sky_sink_infinite_distance_is_cmb():
    t = sky_sink_temperature_k(heliocentric_distance_au=float("inf"))
    assert t == pytest.approx(CMB_TEMPERATURE_K, rel=1.0e-12)


def test_sky_sink_at_1_au_is_order_250k():
    """At 1 AU a 0.10/0.85 α/ε panel sees an equivalent sink
    temperature around 250-260 K from solar albedo (Incropera 2011
    example 12.12)."""
    t = sky_sink_temperature_k(heliocentric_distance_au=1.0)
    assert 230.0 < t < 290.0


def test_sky_sink_monotone_in_distance():
    t_inner = sky_sink_temperature_k(heliocentric_distance_au=0.5)
    t_1_au = sky_sink_temperature_k(heliocentric_distance_au=1.0)
    t_outer = sky_sink_temperature_k(heliocentric_distance_au=5.0)
    assert t_inner > t_1_au > t_outer > CMB_TEMPERATURE_K


# ──────────────────────────────────────────────────────────────────────
#  Fin efficiency
# ──────────────────────────────────────────────────────────────────────


def test_fin_efficiency_approaches_unity_for_short_thick_high_k_fin():
    """A short thick aluminium fin (k = 237, t = 10 mm, L = 3 cm)
    at 500 K is nearly isothermal."""
    eta = fin_efficiency_gardner(
        fin_length_m=0.03,
        fin_thickness_m=1.0e-2,
        fin_thermal_conductivity_w_m_k=237.0,
        panel_temperature_k=500.0,
    )
    assert 0.99 < eta <= 1.0


def test_fin_efficiency_realistic_100mm_aluminium_in_80s():
    """A 0.1 m × 10 mm Al fin at 500 K lands in the realistic
    ~0.9 band — matching Incropera 2011 worked examples for
    practical radiator panels."""
    eta = fin_efficiency_gardner(
        fin_length_m=0.1,
        fin_thickness_m=1.0e-2,
        fin_thermal_conductivity_w_m_k=237.0,
        panel_temperature_k=500.0,
    )
    assert 0.85 < eta < 0.99


def test_fin_efficiency_decays_for_long_thin_fin():
    """A long thin low-k fin should drop well below unity."""
    eta = fin_efficiency_gardner(
        fin_length_m=2.0,
        fin_thickness_m=1.0e-4,
        fin_thermal_conductivity_w_m_k=0.5,
        panel_temperature_k=800.0,
    )
    assert 0.0 < eta < 0.3


def test_fin_efficiency_rejects_nonpositive():
    with pytest.raises(ValueError):
        fin_efficiency_gardner(0.0, 1.0e-3, 100.0, 300.0)


# ──────────────────────────────────────────────────────────────────────
#  Carnot ceiling
# ──────────────────────────────────────────────────────────────────────


def test_carnot_ceiling_standard_case():
    """T_h = 1000, T_c = 500 → η_C = 0.5."""
    assert carnot_ceiling_efficiency(1000.0, 500.0) == pytest.approx(0.5)


def test_carnot_ceiling_zero_when_cold_exceeds_hot():
    assert carnot_ceiling_efficiency(500.0, 700.0) == 0.0


# ──────────────────────────────────────────────────────────────────────
#  Report dataclass
# ──────────────────────────────────────────────────────────────────────


def test_report_build_aggregates_area_and_carnot():
    report = RadiatorPanelReport.build(
        heat_load_w=2.0e6,
        panel_temperature_k=500.0,
        fin_efficiency=0.95,
    )
    assert report.area_required_m2 > 0.0
    # η_C with T_hot = 2 T_r = 1000 K, T_cold = 500 K → 0.5.
    assert report.carnot_ceiling == pytest.approx(0.5, rel=1.0e-12)
    assert report.fin_efficiency == 0.95
