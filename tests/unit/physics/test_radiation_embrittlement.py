"""Tests for radiation embrittlement physics: DBTT shift, yield strength
hardening, Master Curve fracture toughness, and GCR DPA conversion.

Validates:
1. DBTT shift is zero at DPA=0 and grows monotonically with DPA.
2. EUROFER97 DBTT shift is lower than ferritic steel at same DPA (better tolerance).
3. Yield strength shift saturates correctly at DPA >> DPA_sat.
4. Master Curve K_JC decreases after irradiation (DBTT shift → K drops).
5. GCR DPA annual rate: HZE species contribute disproportionately.
6. Reactor DPA is orders of magnitude higher than GCR DPA for same flux.
7. embrittlement_budget produces correct sign conventions and brittle_risk flag.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.solid_mechanics import (
    EMBRITTLEMENT_DB,
    GCR_DISPLACEMENT_XSEC_CM2,
    dbtt_shift_c,
    current_dbtt_c,
    embrittlement_budget,
    fracture_toughness_after_irradiation,
    gcr_dpa_annual,
    master_curve_k_jc,
    reactor_dpa_annual,
    yield_strength_shift_mpa,
)
from aria.physics.solid_mechanics.radiation_embrittlement import EmbrittlementParams


_EUROFER = EMBRITTLEMENT_DB["EUROFER97"]
_TI64   = EMBRITTLEMENT_DB["Ti-6Al-4V"]


class TestDBTTShift:
    """Odette-Lucas DBTT shift model."""

    def test_zero_dpa_gives_zero_shift(self):
        assert dbtt_shift_c(0.0, _EUROFER) == pytest.approx(0.0, abs=1e-10)

    def test_positive_dpa_positive_shift(self):
        assert dbtt_shift_c(1.0, _EUROFER) > 0.0

    def test_monotone_with_dpa(self):
        dpas = [0.0, 0.1, 1.0, 5.0, 20.0]
        shifts = [dbtt_shift_c(d, _EUROFER) for d in dpas]
        for i in range(len(shifts) - 1):
            assert shifts[i] <= shifts[i + 1]

    def test_eurofer97_shift_moderate_at_10dpa(self):
        # EUROFER97 at 10 DPA: A=30 × √10 ≈ 94.9°C; physically consistent with
        # Gaganidze 2006 (6.6 DPA → 70°C) extrapolated to 10 DPA
        shift = dbtt_shift_c(10.0, _EUROFER)
        assert 20.0 < shift < 150.0, f"EUROFER97 shift at 10 DPA = {shift:.1f}°C unexpected"

    def test_eurofer97_better_than_ferritic_steel(self):
        # EUROFER97 A_dbtt=30 < conventional ferritic (A≈50+); create synthetic worse material
        worse = EmbrittlementParams(
            name="worse-steel", A_dbtt=55.0, T_dbtt_ref_c=-80.0,
            delta_ys_sat_mpa=300.0, dpa_sat=0.5, T0_ref_c=-90.0,
            K_JC_upper_shelf_mpa_sqm=150.0,
        )
        shift_eurofer = dbtt_shift_c(5.0, _EUROFER)
        shift_worse = dbtt_shift_c(5.0, worse)
        assert shift_eurofer < shift_worse

    def test_current_dbtt_includes_reference(self):
        dbtt = current_dbtt_c(2.0, _EUROFER)
        assert dbtt == pytest.approx(_EUROFER.T_dbtt_ref_c + dbtt_shift_c(2.0, _EUROFER), rel=1e-9)

    def test_explicit_fluence_n19(self):
        # At fluence_n19 = 1 (10^19 n/cm²): ΔDBTT = A_dbtt × 1^exponent = A_dbtt × ~1
        shift = dbtt_shift_c(0.0, _EUROFER, fluence_n19=1.0)
        exponent = 0.28 - 0.10 * math.log10(1.0)  # 0.28
        expected = _EUROFER.A_dbtt * (1.0 ** exponent)
        assert shift == pytest.approx(expected, rel=1e-9)


class TestYieldStrengthShift:
    """Zinkle-Busby saturation model."""

    def test_zero_dpa_zero_shift(self):
        assert yield_strength_shift_mpa(0.0, _EUROFER) == pytest.approx(0.0, abs=1e-9)

    def test_saturation_approaches_limit(self):
        # At very high DPA, ΔYS → ΔYS_sat
        high_dpa_shift = yield_strength_shift_mpa(100.0, _EUROFER)
        assert high_dpa_shift == pytest.approx(_EUROFER.delta_ys_sat_mpa, rel=0.01)

    def test_63_percent_at_one_dpa_sat(self):
        # By definition: at DPA = DPA_sat, ΔYS = ΔYS_sat × (1 − e⁻¹) ≈ 63.2%
        shift = yield_strength_shift_mpa(_EUROFER.dpa_sat, _EUROFER)
        expected = _EUROFER.delta_ys_sat_mpa * (1 - math.exp(-1.0))
        assert shift == pytest.approx(expected, rel=1e-9)

    def test_monotone_with_dpa(self):
        dpas = [0.0, 0.5, 1.0, 5.0]
        shifts = [yield_strength_shift_mpa(d, _EUROFER) for d in dpas]
        for i in range(len(shifts) - 1):
            assert shifts[i] < shifts[i + 1]

    def test_positive_at_positive_dpa(self):
        assert yield_strength_shift_mpa(1.0, _TI64) > 0.0
        assert yield_strength_shift_mpa(1.0, _TI64) < _TI64.delta_ys_sat_mpa


class TestMasterCurve:
    """ASTM E1921 Master Curve K_JC."""

    def test_k_jc_formula_at_t0(self):
        # At T = T0: K_JC = 30 + 70 * exp(0) = 100 MPa√m
        k = master_curve_k_jc(0.0, T0_c=0.0)
        assert k == pytest.approx(100.0, rel=1e-9)

    def test_k_jc_increases_with_temperature(self):
        # Warmer → less brittle → higher K_JC
        k_cold = master_curve_k_jc(-100.0, T0_c=0.0)
        k_warm = master_curve_k_jc(50.0, T0_c=0.0)
        assert k_warm > k_cold

    def test_irradiation_reduces_toughness(self):
        # DBTT shift → T0 increases → K_JC at fixed T decreases
        # Use operating_temp well above T0 so we're off the upper-shelf cap
        k_fresh = fracture_toughness_after_irradiation(0.0, 0.0, _EUROFER)
        k_irr = fracture_toughness_after_irradiation(0.0, 10.0, _EUROFER)
        assert k_fresh > k_irr

    def test_k_jc_floored_at_30_mpa(self):
        # At very low temperature, K → 30 + small → must be ≥ 30
        k = master_curve_k_jc(-1000.0, T0_c=0.0)
        assert k >= 30.0

    def test_k_jc_capped_at_upper_shelf(self):
        # At very high temperature, capped at upper shelf
        k = fracture_toughness_after_irradiation(500.0, 0.0, _EUROFER)
        assert k <= _EUROFER.K_JC_upper_shelf_mpa_sqm


class TestGCRDPA:
    """GCR species → DPA conversion."""

    def test_fe_species_highest_dpa(self):
        # Per ion, Fe-56 has highest displacement cross-section
        assert GCR_DISPLACEMENT_XSEC_CM2["Fe"] > GCR_DISPLACEMENT_XSEC_CM2["Proton"]
        assert GCR_DISPLACEMENT_XSEC_CM2["Fe"] > GCR_DISPLACEMENT_XSEC_CM2["Helium-4"]

    def test_gcr_dpa_annual_positive(self):
        # Typical GCR free-space fluence: ~10^9 p/cm²/yr protons at 1 AU
        flux = {"Proton": 1e9, "Helium-4": 1e8, "CNO": 1e7, "Mg-Si": 3e6, "Fe": 2e6}
        dpa = gcr_dpa_annual(flux)
        assert dpa > 0.0

    def test_gcr_dpa_dominated_by_hze(self):
        # Low fluence of Fe contributes more DPA than 100× more protons
        p_only = gcr_dpa_annual({"Proton": 1e9})
        fe_only = gcr_dpa_annual({"Fe": 1e7})  # 100× fewer ions
        assert fe_only > p_only  # Fe has 5000× higher cross-section

    def test_gcr_dpa_zero_flux(self):
        assert gcr_dpa_annual({}) == pytest.approx(0.0)

    def test_gcr_annual_dpa_less_than_reactor(self):
        # GCR in free space: ~10^9 p/cm²/yr → DPA << reactor vessel level
        gcr_flux = {"Proton": 1e9, "Helium-4": 1e8}
        gcr_dpa = gcr_dpa_annual(gcr_flux)

        # Reactor vessel at 10^11 n/cm²/s (moderate power)
        reac_dpa = reactor_dpa_annual(1e11)

        assert reac_dpa > gcr_dpa * 1000  # reactor orders of magnitude higher


class TestReactorDPA:
    """Reactor fast-neutron DPA rate."""

    def test_reactor_dpa_positive(self):
        assert reactor_dpa_annual(1e10) > 0.0

    def test_reactor_dpa_linear_in_flux(self):
        d1 = reactor_dpa_annual(1e10)
        d2 = reactor_dpa_annual(2e10)
        assert d2 == pytest.approx(2 * d1, rel=1e-9)

    def test_fusion_first_wall_order_of_magnitude(self):
        # Fusion demo first wall: ~10^14 n/cm²/s; σ_d=1e-21 → ~3 DPA/yr
        # (Stoller 2013 NRT model; note ITER first wall is ~0.5 DPA/yr at lower flux)
        dpa = reactor_dpa_annual(1e14)
        assert 1.0 < dpa < 50.0, f"First wall DPA/yr = {dpa:.2f}, expected 1-50"


class TestEmbrittlementBudget:
    """Full embrittlement budget integration."""

    def test_fresh_material_no_brittle_risk_at_room_temp(self):
        # EUROFER97 unirradiated, DBTT ≈ -100°C → no brittle risk at 20°C
        budget = embrittlement_budget("EUROFER97", dpa=0.0, operating_temp_c=20.0)
        assert not budget.brittle_risk

    def test_high_dpa_shifts_dbtt_above_operating_temp(self):
        # After very high DPA, DBTT may exceed 20°C → brittle risk
        budget = embrittlement_budget("EUROFER97", dpa=200.0, operating_temp_c=20.0)
        if budget.dbtt_current_c >= 20.0:
            assert budget.brittle_risk
        else:
            assert not budget.brittle_risk

    def test_margin_fraction_bounded(self):
        budget = embrittlement_budget("EUROFER97", dpa=5.0, operating_temp_c=20.0)
        assert 0.0 < budget.margin_fraction <= 1.0

    def test_irradiation_reduces_margin(self):
        b0 = embrittlement_budget("EUROFER97", dpa=0.0)
        b10 = embrittlement_budget("EUROFER97", dpa=10.0)
        assert b10.margin_fraction <= b0.margin_fraction

    def test_all_materials_importable(self):
        for mat_name in EMBRITTLEMENT_DB:
            b = embrittlement_budget(mat_name, dpa=1.0)
            assert b.dpa == 1.0
            assert b.material == mat_name

    def test_dbtt_components_consistent(self):
        budget = embrittlement_budget("EUROFER97", dpa=5.0)
        assert budget.dbtt_current_c == pytest.approx(
            budget.dbtt_ref_c + budget.dbtt_shift_c, rel=1e-9
        )
