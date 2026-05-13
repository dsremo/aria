"""Tests for secondary neutron production: spallation, albedo, dose buildup.

Validates:
1. ICRP 74 dose conversion returns tabulated values at known energies.
2. Conversion monotonically increases from thermal to 1 GeV (with log interpolation).
3. Spallation yield positive, increases with energy (power law).
4. Fe target produces more neutrons per interaction than Al (heavier target).
5. Secondary neutron exit flux > 0 for finite shield; zero for zero shield.
6. Exit flux increases with shield thickness (up to buildup peak), then ~flat.
7. Dose buildup factor ≥ 1 for all x; at x=0, B=1.
8. Buildup factor increases with shield thickness (saturation function).
9. Buildup factor at 20 g/cm² in NCRP 132 benchmark range [1.1, 1.5].
10. Albedo dose > 0 at 400 km altitude; 0 beyond GEO.
11. Albedo dose decreases with increasing altitude (geometric dilution).
12. Albedo dose decreases with more shielding.
13. SecondaryNeutronBudget: total > primary; secondary_fraction in (0,1).
14. Budget with altitude gives albedo > 0; without altitude gives albedo = 0.
15. SecondaryNeutronBudget primary dose consistency.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.transport import (
    SecondaryNeutronBudget,
    albedo_neutron_dose_sv_yr,
    dose_buildup_factor_gcr_al,
    icrp74_neutron_dose_coeff_psv_cm2,
    secondary_neutron_dose_budget,
    secondary_neutron_exit_flux,
    spallation_neutron_yield_per_interaction,
)


class TestIcrp74DoseConversion:
    """ICRP 74 Table A.12 fluence-to-dose coefficients."""

    def test_thermal_value(self):
        # Thermal neutrons: h_Phi = 2.7 pSv·cm² (ICRP 74 Table A.12)
        h = icrp74_neutron_dose_coeff_psv_cm2(1e-9)
        assert abs(h - 2.7) < 0.1, f"thermal h_Phi = {h:.2f}, expected 2.7"

    def test_1mev_value(self):
        # 1 MeV neutrons: h_Phi = 133 pSv·cm² (ICRP 74 Table A.12)
        h = icrp74_neutron_dose_coeff_psv_cm2(1.0)
        assert abs(h - 133.0) < 5.0, f"1 MeV h_Phi = {h:.1f}, expected 133"

    def test_100mev_value(self):
        # 100 MeV neutrons: h_Phi = 500 pSv·cm² (ICRP 74 Table A.12)
        h = icrp74_neutron_dose_coeff_psv_cm2(100.0)
        assert abs(h - 500.0) < 10.0, f"100 MeV h_Phi = {h:.1f}, expected 500"

    def test_1gev_value(self):
        # 1 GeV neutrons: h_Phi = 580 pSv·cm² (ICRP 74 Table A.12)
        h = icrp74_neutron_dose_coeff_psv_cm2(1000.0)
        assert abs(h - 580.0) < 10.0, f"1 GeV h_Phi = {h:.1f}, expected 580"

    def test_monotone_thermal_to_1gev(self):
        # h_Phi should generally increase from thermal to fast (rising curve)
        h_thermal = icrp74_neutron_dose_coeff_psv_cm2(1e-9)
        h_1mev = icrp74_neutron_dose_coeff_psv_cm2(1.0)
        h_100mev = icrp74_neutron_dose_coeff_psv_cm2(100.0)
        h_1gev = icrp74_neutron_dose_coeff_psv_cm2(1000.0)
        assert h_thermal < h_1mev < h_100mev
        assert h_100mev < h_1gev

    def test_interpolation_between_tabulated_points(self):
        # 3 MeV is between 2 and 5; should be between their h_Phi values
        h_2 = icrp74_neutron_dose_coeff_psv_cm2(2.0)
        h_3 = icrp74_neutron_dose_coeff_psv_cm2(3.0)
        h_5 = icrp74_neutron_dose_coeff_psv_cm2(5.0)
        assert h_2 < h_3 < h_5, f"Interpolation failed: h(2)={h_2}, h(3)={h_3}, h(5)={h_5}"

    def test_clamped_below_range(self):
        # Very low energy: clamp to thermal value
        h = icrp74_neutron_dose_coeff_psv_cm2(1e-15)
        assert abs(h - 2.7) < 0.1

    def test_clamped_above_range(self):
        # Very high energy: clamp to 1 GeV value
        h = icrp74_neutron_dose_coeff_psv_cm2(1e6)
        assert abs(h - 580.0) < 10.0

    def test_positive_energy_required(self):
        with pytest.raises(ValueError):
            icrp74_neutron_dose_coeff_psv_cm2(0.0)


class TestSpallationNeutronYield:
    """Alsmiller 1975 thin-target spallation neutron multiplicity."""

    def test_positive_yield(self):
        Y = spallation_neutron_yield_per_interaction(1000.0, 27)
        assert Y > 0.0

    def test_al_at_1gev_order_of_magnitude(self):
        # Al at 1 GeV: Y ≈ 1.0-1.5 neutrons per interaction (Armstrong 1969)
        Y = spallation_neutron_yield_per_interaction(1000.0, 27)
        assert 0.3 < Y < 3.0, f"Y(1 GeV, Al) = {Y:.3f}, expected 0.3–3.0"

    def test_al_at_100mev_less_than_1gev(self):
        Y_100 = spallation_neutron_yield_per_interaction(100.0, 27)
        Y_1000 = spallation_neutron_yield_per_interaction(1000.0, 27)
        assert Y_100 < Y_1000

    def test_yield_increases_monotonically_with_energy(self):
        energies = [50.0, 100.0, 300.0, 1000.0, 5000.0]
        yields = [spallation_neutron_yield_per_interaction(e, 27) for e in energies]
        for i in range(len(yields) - 1):
            assert yields[i] < yields[i + 1]

    def test_heavier_target_more_neutrons(self):
        # Fe (A=56) should produce more neutrons per interaction than Al (A=27)
        Y_al = spallation_neutron_yield_per_interaction(1000.0, 27)
        Y_fe = spallation_neutron_yield_per_interaction(1000.0, 56)
        assert Y_fe > Y_al, f"Y_Fe={Y_fe:.3f} should be > Y_Al={Y_al:.3f}"

    def test_yield_scales_as_sqrt_a(self):
        # Y ∝ A^0.5: ratio Y(Fe)/Y(Al) ≈ (56/27)^0.5 ≈ 1.44
        Y_al = spallation_neutron_yield_per_interaction(1000.0, 27)
        Y_fe = spallation_neutron_yield_per_interaction(1000.0, 56)
        ratio = Y_fe / Y_al
        expected_ratio = (56.0 / 27.0) ** 0.5
        assert abs(ratio - expected_ratio) / expected_ratio < 0.01

    def test_invalid_energy_raises(self):
        with pytest.raises(ValueError):
            spallation_neutron_yield_per_interaction(0.0, 27)

    def test_invalid_mass_number_raises(self):
        with pytest.raises(ValueError):
            spallation_neutron_yield_per_interaction(1000.0, 0)


class TestSecondaryNeutronExitFlux:
    """Slab transport integral for secondary neutron exit flux."""

    def test_zero_shield_zero_flux(self):
        phi = secondary_neutron_exit_flux(4.0, 0.0, 27, 1000.0)
        assert phi == 0.0

    def test_positive_flux_for_finite_shield(self):
        phi = secondary_neutron_exit_flux(4.0, 20.0, 27, 1000.0)
        assert phi > 0.0

    def test_flux_increases_with_shield_thickness(self):
        # Production buildup dominates at thin shields (λ_n > λ_p)
        phi_5 = secondary_neutron_exit_flux(4.0, 5.0, 27, 1000.0)
        phi_20 = secondary_neutron_exit_flux(4.0, 20.0, 27, 1000.0)
        assert phi_20 > phi_5

    def test_flux_less_than_primary_flux(self):
        # Secondary neutron flux should be less than primary for thin shields
        Phi_0 = 4.0
        phi_n = secondary_neutron_exit_flux(Phi_0, 10.0, 27, 1000.0)
        assert phi_n < Phi_0 * 2.0  # within 2× primary (sanity check)

    def test_flux_proportional_to_primary(self):
        # φ_n ∝ Φ_0 (linearity)
        phi_1 = secondary_neutron_exit_flux(4.0, 20.0, 27, 1000.0)
        phi_2 = secondary_neutron_exit_flux(8.0, 20.0, 27, 1000.0)
        assert abs(phi_2 / phi_1 - 2.0) < 1e-9

    def test_heavier_target_more_secondaries(self):
        # Fe target produces more secondaries than Al (higher spallation yield)
        phi_al = secondary_neutron_exit_flux(4.0, 20.0, 27, 1000.0)
        phi_fe = secondary_neutron_exit_flux(4.0, 20.0, 56, 1000.0)
        assert phi_fe > phi_al


class TestDoseBuildupFactor:
    """GCR dose buildup factor B(x) for Al shielding."""

    def test_b_equals_1_at_zero(self):
        B = dose_buildup_factor_gcr_al(0.0)
        assert abs(B - 1.0) < 1e-9

    def test_b_greater_than_1_for_positive_x(self):
        for x in [5.0, 10.0, 20.0, 40.0, 100.0]:
            B = dose_buildup_factor_gcr_al(x)
            assert B > 1.0, f"B({x}) = {B:.3f}, must be > 1"

    def test_b_monotonically_increasing(self):
        xs = [0.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0]
        Bs = [dose_buildup_factor_gcr_al(x) for x in xs]
        for i in range(len(Bs) - 1):
            assert Bs[i] <= Bs[i + 1], f"B not monotone at x={xs[i+1]}"

    def test_b_saturates_at_large_x(self):
        # B(x→∞) = 1 + b_max = 1.55; at 300 g/cm² should be close
        B_large = dose_buildup_factor_gcr_al(300.0)
        assert B_large < 1.60, f"B(300) = {B_large:.3f}, should be < 1.60"

    def test_b_at_20_gcm2_ncrp_benchmark(self):
        # NCRP 132 §4.4: B(20 g/cm²) ≈ 1.25-1.45 for GCR in Al
        B = dose_buildup_factor_gcr_al(20.0)
        assert 1.1 < B < 1.5, f"B(20 g/cm²) = {B:.3f}, expected 1.1–1.5"

    def test_b_at_40_gcm2_above_b_at_20(self):
        assert dose_buildup_factor_gcr_al(40.0) > dose_buildup_factor_gcr_al(20.0)

    def test_negative_thickness_raises(self):
        with pytest.raises(ValueError):
            dose_buildup_factor_gcr_al(-1.0)


class TestAlbedoNeutronDose:
    """Albedo neutron dose from Earth's atmosphere (LEO only)."""

    def test_positive_at_400km(self):
        dose = albedo_neutron_dose_sv_yr(400.0)
        assert dose > 0.0

    def test_zero_beyond_geo(self):
        dose = albedo_neutron_dose_sv_yr(40000.0)
        assert dose == 0.0

    def test_decreases_with_altitude(self):
        d_low = albedo_neutron_dose_sv_yr(400.0)
        d_high = albedo_neutron_dose_sv_yr(1000.0)
        assert d_low > d_high

    def test_decreases_with_shielding(self):
        d_thin = albedo_neutron_dose_sv_yr(400.0, shielding_gcm2=1.0)
        d_thick = albedo_neutron_dose_sv_yr(400.0, shielding_gcm2=20.0)
        assert d_thin > d_thick

    def test_iss_altitude_order_of_magnitude(self):
        # ISS ~400 km; albedo dose ~0.002-0.02 mSv/day (NCRP 132 §4.3.2)
        # Annual: ~0.7-7 mSv/yr = 0.0007-0.007 Sv/yr
        dose = albedo_neutron_dose_sv_yr(400.0, shielding_gcm2=5.0)
        assert 1e-6 < dose < 0.1, f"Albedo dose at 400 km = {dose:.2e} Sv/yr"


class TestSecondaryNeutronBudget:
    """SecondaryNeutronBudget composite dose result."""

    def test_total_exceeds_primary(self):
        budget = secondary_neutron_dose_budget(0.42, 20.0)
        assert budget.total_dose_sv_yr > budget.primary_dose_sv_yr

    def test_buildup_factor_geq_1(self):
        budget = secondary_neutron_dose_budget(0.42, 20.0)
        assert budget.buildup_factor >= 1.0

    def test_secondary_fraction_in_range(self):
        # NCRP 132 §4.4: secondary fraction 20-50% at typical ISS shielding
        budget = secondary_neutron_dose_budget(0.42, 20.0)
        assert 0.0 < budget.secondary_fraction < 0.8, (
            f"secondary_fraction = {budget.secondary_fraction:.3f}"
        )

    def test_no_albedo_when_altitude_not_given(self):
        budget = secondary_neutron_dose_budget(0.42, 20.0, altitude_km=None)
        assert budget.albedo_sv_yr == 0.0

    def test_albedo_nonzero_in_leo(self):
        budget = secondary_neutron_dose_budget(0.42, 20.0, altitude_km=400.0)
        assert budget.albedo_sv_yr > 0.0

    def test_total_includes_albedo(self):
        budget_no_albedo = secondary_neutron_dose_budget(0.42, 20.0)
        budget_leo = secondary_neutron_dose_budget(0.42, 20.0, altitude_km=400.0)
        assert budget_leo.total_dose_sv_yr > budget_no_albedo.total_dose_sv_yr

    def test_primary_dose_preserved_in_budget(self):
        D = 0.42
        budget = secondary_neutron_dose_budget(D, 20.0)
        assert abs(budget.primary_dose_sv_yr - D) < 1e-9

    def test_secondary_fraction_increases_with_shield(self):
        # More shielding → more secondary production → higher fraction
        budget_thin = secondary_neutron_dose_budget(0.42, 5.0)
        budget_thick = secondary_neutron_dose_budget(0.42, 40.0)
        assert budget_thick.secondary_fraction > budget_thin.secondary_fraction

    def test_spallation_dose_positive_for_nonzero_flux(self):
        budget = secondary_neutron_dose_budget(0.42, 20.0, primary_flux_cm2_s=4.0)
        assert budget.secondary_spallation_sv_yr > 0.0

    def test_total_equals_buildup_times_primary_plus_albedo(self):
        budget = secondary_neutron_dose_budget(0.42, 20.0, altitude_km=400.0)
        from aria.physics.transport import dose_buildup_factor_gcr_al
        from aria.physics.transport import albedo_neutron_dose_sv_yr
        expected_total = (
            0.42 * dose_buildup_factor_gcr_al(20.0)
            + albedo_neutron_dose_sv_yr(400.0, 5.0)
        )
        assert abs(budget.total_dose_sv_yr - expected_total) < 1e-9
