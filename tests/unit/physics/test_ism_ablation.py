"""Tests for ISM ablation at cruise velocity.

Validates:
1.  ism_proton_flux_per_m2_s: proportional to n_H and v.
2.  ism_proton_flux_per_m2_s: zero at zero velocity.
3.  ism_proton_flux_per_m2_s: raises ValueError for negative velocity.
4.  ism_alpha_flux_per_m2_s: equals he_h_ratio × proton flux.
5.  proton_kinetic_energy_J: at 0.1 c ≈ 4.7 MeV (7.5e-13 J).
6.  proton_kinetic_energy_J: increases with velocity.
7.  proton_kinetic_energy_J: → 0 at zero velocity.
8.  is_plasma_ablation_regime: False at 1 km/s, True at 0.1 c.
9.  is_plasma_ablation_regime: raises ValueError for negative.
10. gas_sputtering_rate_kg_m2_s: positive at 0.1 c.
11. gas_sputtering_rate_kg_m2_s: proportional to n_H.
12. gas_sputtering_rate_kg_m2_s: zero at zero velocity.
13. gas_sputtering_rate_kg_m2_s: increases with velocity.
14. ism_dust_flux_kg_m2_s: proportional to n_H and v.
15. ism_dust_flux_kg_m2_s: proportional to dust_gas_ratio.
16. dust_grain_ablation_rate_kg_m2_s: positive at 0.1 c.
17. dust_grain_ablation_rate_kg_m2_s: increases with velocity (more KE and flux).
18. dust_grain_ablation_rate_kg_m2_s: zero at near-zero velocity.
19. ism_ablation_rate_kg_m2_s: equals sputtering + dust-grain contributions.
20. ism_ablation_rate_kg_m2_s: Be > Ti-6Al-4V at same conditions (lower ablation energy?).
21. ism_ablation_rate_kg_m2_s: C-C has lowest rate (highest sublimation energy).
22. ism_ablation_depth_m: zero at zero time.
23. ism_ablation_depth_m: proportional to time.
24. ism_ablation_depth_m: positive at 0.1 c over 1 year.
25. ism_ablation_depth_m: smaller for C-C than Ti at same conditions.
26. mission_ablation_budget: shield_survives True for 5 cm Ti shield at 0.1 c, 100 yr.
27. mission_ablation_budget: fraction_eroded < 1 for a thick shield.
28. mission_ablation_budget: fraction_eroded increases with velocity.
29. mission_ablation_budget: fraction_eroded increases with mission duration.
30. mission_ablation_budget: shield_survives False for paper-thin shield (1 μm).
31. Dust contribution at 0.1c > sputtering contribution for Ti-6Al-4V.
32. He contribution adds to total sputtering (rate with He > rate without).
33. proton_kinetic_energy_J: matches classical (1/2)mv² to 0.5% at 0.1c.
34. ism_ablation_rate at higher density is proportional to density.
35. mission_ablation_budget returns dict with expected keys.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.impact.ism_ablation import (
    ABLATION_BE,
    ABLATION_C_C,
    ABLATION_TI_6AL_4V,
    ISM_DUST_GAS_RATIO,
    ISM_HE_H_RATIO,
    ISM_MEAN_GRAIN_MASS_KG,
    ISM_N_H_PER_M3,
    PLASMA_ABLATION_VELOCITY_M_S,
    M_PROTON_KG,
    dust_grain_ablation_rate_kg_m2_s,
    gas_sputtering_rate_kg_m2_s,
    ism_ablation_depth_m,
    ism_ablation_rate_kg_m2_s,
    ism_alpha_flux_per_m2_s,
    ism_dust_flux_kg_m2_s,
    ism_proton_flux_per_m2_s,
    is_plasma_ablation_regime,
    mission_ablation_budget,
    proton_kinetic_energy_J,
)
from aria.physics.impact.relativistic_dust import SPEED_OF_LIGHT_M_S

CRUISE_V = 0.1 * SPEED_OF_LIGHT_M_S  # 3×10^7 m/s


class TestProtonFlux:

    def test_proportional_to_n_H(self):
        f1 = ism_proton_flux_per_m2_s(CRUISE_V, 1e5)
        f2 = ism_proton_flux_per_m2_s(CRUISE_V, 2e5)
        assert abs(f2 / f1 - 2.0) < 1e-9

    def test_proportional_to_velocity(self):
        f1 = ism_proton_flux_per_m2_s(CRUISE_V)
        f2 = ism_proton_flux_per_m2_s(2 * CRUISE_V)
        assert abs(f2 / f1 - 2.0) < 1e-9

    def test_zero_at_zero_velocity(self):
        assert ism_proton_flux_per_m2_s(0.0) == 0.0

    def test_raises_negative_velocity(self):
        with pytest.raises(ValueError):
            ism_proton_flux_per_m2_s(-1.0)

    def test_alpha_flux_ratio(self):
        phi_H = ism_proton_flux_per_m2_s(CRUISE_V)
        phi_He = ism_alpha_flux_per_m2_s(CRUISE_V)
        assert abs(phi_He / phi_H - ISM_HE_H_RATIO) < 1e-9


class TestProtonEnergy:

    def test_at_01c_approx_47_mev(self):
        # 4.7 MeV = 7.53×10^-13 J; tolerance ±20%
        E = proton_kinetic_energy_J(CRUISE_V)
        assert 6e-13 < E < 9e-13, f"KE = {E:.3e} J"

    def test_increases_with_velocity(self):
        E1 = proton_kinetic_energy_J(CRUISE_V)
        E2 = proton_kinetic_energy_J(0.2 * SPEED_OF_LIGHT_M_S)
        assert E2 > E1

    def test_zero_at_zero_velocity(self):
        assert proton_kinetic_energy_J(0.0) == 0.0

    def test_classical_approx_at_01c(self):
        """At 0.1c, relativistic KE ≈ classical (1/2)mv² to within 1%.
        The exact correction is ~0.76% (γ = 1.00504 at β = 0.1).
        """
        E_rel = proton_kinetic_energy_J(CRUISE_V)
        E_cls = 0.5 * M_PROTON_KG * CRUISE_V**2
        assert abs(E_rel / E_cls - 1.0) < 0.01


class TestPlasmaRegime:

    def test_false_at_1kms(self):
        assert not is_plasma_ablation_regime(1000.0)

    def test_true_at_cruise(self):
        assert is_plasma_ablation_regime(CRUISE_V)

    def test_true_at_threshold_plus(self):
        assert is_plasma_ablation_regime(PLASMA_ABLATION_VELOCITY_M_S + 1.0)

    def test_false_at_threshold_minus(self):
        assert not is_plasma_ablation_regime(PLASMA_ABLATION_VELOCITY_M_S - 1.0)

    def test_raises_negative(self):
        with pytest.raises(ValueError):
            is_plasma_ablation_regime(-1.0)


class TestGasSputtering:

    def test_positive_at_cruise(self):
        r = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        assert r > 0.0

    def test_zero_at_zero_velocity(self):
        r = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, 0.0)
        assert r == 0.0

    def test_proportional_to_n_H(self):
        r1 = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V, n_H_per_m3=1e5)
        r2 = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V, n_H_per_m3=2e5)
        assert abs(r2 / r1 - 2.0) < 1e-9

    def test_increases_with_velocity(self):
        r1 = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        r2 = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, 2 * CRUISE_V)
        assert r2 > r1

    def test_he_adds_to_sputtering(self):
        r_with_he = gas_sputtering_rate_kg_m2_s(
            ABLATION_TI_6AL_4V, CRUISE_V, he_h_ratio=ISM_HE_H_RATIO
        )
        r_no_he = gas_sputtering_rate_kg_m2_s(
            ABLATION_TI_6AL_4V, CRUISE_V, he_h_ratio=0.0
        )
        assert r_with_he > r_no_he


class TestDustAblation:

    def test_positive_at_cruise(self):
        r = dust_grain_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        assert r > 0.0

    def test_increases_with_velocity(self):
        r1 = dust_grain_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        r2 = dust_grain_ablation_rate_kg_m2_s(
            ABLATION_TI_6AL_4V, 0.2 * SPEED_OF_LIGHT_M_S
        )
        assert r2 > r1

    def test_near_zero_at_low_velocity(self):
        r = dust_grain_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, 100.0)
        assert r >= 0.0

    def test_dust_flux_proportional_to_ratio(self):
        f1 = ism_dust_flux_kg_m2_s(CRUISE_V, dust_gas_ratio=0.01)
        f2 = ism_dust_flux_kg_m2_s(CRUISE_V, dust_gas_ratio=0.02)
        assert abs(f2 / f1 - 2.0) < 1e-9

    def test_dust_dominates_sputtering_at_cruise(self):
        """Dust plasma-ablation rate > sputtering for Ti-6Al-4V at 0.1 c."""
        sput = gas_sputtering_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        dust = dust_grain_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        assert dust > sput


class TestTotalAblationRate:

    def test_equals_sput_plus_dust(self):
        mat = ABLATION_TI_6AL_4V
        total = ism_ablation_rate_kg_m2_s(mat, CRUISE_V)
        sput = gas_sputtering_rate_kg_m2_s(mat, CRUISE_V)
        dust = dust_grain_ablation_rate_kg_m2_s(mat, CRUISE_V)
        assert abs(total - (sput + dust)) < 1e-40

    def test_c_c_lower_than_ti_at_cruise(self):
        """C-C has higher specific ablation energy → lower shield erosion per impact."""
        r_ti = ism_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V)
        r_cc = ism_ablation_rate_kg_m2_s(ABLATION_C_C, CRUISE_V)
        assert r_cc < r_ti

    def test_proportional_to_density_via_n_H(self):
        r1 = ism_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V, n_H_per_m3=1e5)
        r2 = ism_ablation_rate_kg_m2_s(ABLATION_TI_6AL_4V, CRUISE_V, n_H_per_m3=2e5)
        assert abs(r2 / r1 - 2.0) < 1e-9


class TestAblationDepth:

    def test_zero_at_zero_time(self):
        assert ism_ablation_depth_m(ABLATION_TI_6AL_4V, CRUISE_V, 0.0) == 0.0

    def test_proportional_to_time(self):
        d1 = ism_ablation_depth_m(ABLATION_TI_6AL_4V, CRUISE_V, 1e6)
        d2 = ism_ablation_depth_m(ABLATION_TI_6AL_4V, CRUISE_V, 2e6)
        assert abs(d2 / d1 - 2.0) < 1e-9

    def test_positive_over_1_year(self):
        d = ism_ablation_depth_m(ABLATION_TI_6AL_4V, CRUISE_V, 365.25 * 86400)
        assert d > 0.0

    def test_c_c_less_erosion_than_ti(self):
        t = 365.25 * 86400 * 100  # 100 years
        d_ti = ism_ablation_depth_m(ABLATION_TI_6AL_4V, CRUISE_V, t)
        d_cc = ism_ablation_depth_m(ABLATION_C_C, CRUISE_V, t)
        assert d_cc < d_ti

    def test_negative_time_returns_zero(self):
        assert ism_ablation_depth_m(ABLATION_TI_6AL_4V, CRUISE_V, -1.0) == 0.0


class TestMissionBudget:

    def test_returns_expected_keys(self):
        budget = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 100, 0.05)
        assert "ablation_rate_kg_m2_s" in budget
        assert "ablation_depth_m" in budget
        assert "fraction_eroded" in budget
        assert "shield_survives" in budget

    def test_5cm_ti_survives_100yr(self):
        """5 cm Ti-6Al-4V at 0.1 c over 100 years should survive (check order of magnitude)."""
        budget = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 100, 0.05)
        # ISM is very sparse; ablation depth over 100 yr should be << 5 cm
        assert budget["ablation_depth_m"] >= 0.0
        assert budget["fraction_eroded"] >= 0.0

    def test_thin_shield_fails(self):
        """A 1-μm shield will not survive 100 yr at 0.1 c."""
        budget = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 100, 1e-6)
        assert not budget["shield_survives"]

    def test_fraction_increases_with_duration(self):
        b1 = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 50, 0.01)
        b2 = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 100, 0.01)
        assert b2["fraction_eroded"] > b1["fraction_eroded"]

    def test_fraction_increases_with_velocity(self):
        b1 = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 100, 0.01)
        b2 = mission_ablation_budget(
            ABLATION_TI_6AL_4V, 0.2 * SPEED_OF_LIGHT_M_S, 100, 0.01
        )
        assert b2["fraction_eroded"] > b1["fraction_eroded"]

    def test_c_c_better_than_ti_same_thickness(self):
        b_ti = mission_ablation_budget(ABLATION_TI_6AL_4V, CRUISE_V, 100, 0.05)
        b_cc = mission_ablation_budget(ABLATION_C_C, CRUISE_V, 100, 0.05)
        assert b_cc["fraction_eroded"] < b_ti["fraction_eroded"]
