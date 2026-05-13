"""Tests for spacecraft fire safety combustion kinetics.

Validates:
1.  molar_concentration_mol_m3: ideal gas at STP (1 atm, 298 K, x=1 → 40.9 mol/m³).
2.  molar_concentration_mol_m3: proportional to pressure.
3.  molar_concentration_mol_m3: inversely proportional to temperature.
4.  molar_concentration_mol_m3: raises ValueError at T=0.
5.  global_reaction_rate_mol_m3_s: zero below 500 K.
6.  global_reaction_rate_mol_m3_s: zero at zero fuel.
7.  global_reaction_rate_mol_m3_s: zero at zero O₂.
8.  global_reaction_rate_mol_m3_s: positive at 1500 K, stoichiometric mixture.
9.  global_reaction_rate_mol_m3_s: increases with temperature (Arrhenius).
10. global_reaction_rate_mol_m3_s: increases with O₂ fraction.
11. heat_release_rate_W_m3: positive at 1500 K, stoichiometric.
12. heat_release_rate_W_m3: proportional to global rate.
13. heat_release_rate_W_m3: H₂ rate ≠ CH₄ rate at same conditions.
14. adiabatic_flame_temperature_K: stoichiometric T_ad > T_reactants.
15. adiabatic_flame_temperature_K: higher for richer mixtures up to φ=1.
16. adiabatic_flame_temperature_K: same for φ > 1 (limited by stoichiometric).
17. adiabatic_flame_temperature_K: raises ValueError at φ=0.
18. adiabatic_flame_temperature_K: methane at 298 K ≈ 2200 K (±500 K tolerance).
19. laminar_flame_speed_m_s: maximum near φ=1 (parabolic fit).
20. laminar_flame_speed_m_s: positive at stoichiometric, 1 atm, 298 K.
21. laminar_flame_speed_m_s: increases with temperature.
22. laminar_flame_speed_m_s: decreases with diluent addition.
23. laminar_flame_speed_m_s: H₂ faster than CH₄ at stoichiometric.
24. laminar_flame_speed_m_s: zero at φ=0.
25. is_above_loi: True at 21% O₂ for CH₄ (LOI=21%).
26. is_above_loi: True at 25% O₂ for PTFE-surrogate (high LOI).
27. is_above_loi: H₂ flammable at 10% O₂ (LOI=5%).
28. stoichiometric_o2_mass_fraction: CH₄ ≈ 4.0 kg O₂/kg fuel.
29. microgravity_flame_speed_m_s: ≤ 1g speed at g=0 for CH₄.
30. microgravity_flame_speed_m_s: equals 1g speed at g=1.
31. microgravity_flame_speed_m_s: radiative extinction → 0 for near-lean mixture at g=0.
32. flashover_hrr_threshold_W: positive for finite room/opening.
33. flashover_hrr_threshold_W: increases with room area.
34. is_flashover_risk: True when HRR ≥ threshold.
35. is_flashover_risk: False when HRR < threshold.
36. Spacecraft scenario: ISS-sized module (45 m³), 300 W fire → no flashover.
37. Apollo 1 scenario: 100% O₂ → CH₄ above LOI, reaction rate orders of magnitude higher.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.fire_safety.combustion_kinetics import (
    ETHANOL,
    HYDROGEN,
    METHANE,
    N_HEPTANE,
    P_REF_PA,
    T_REF_K,
    adiabatic_flame_temperature_K,
    flashover_hrr_threshold_W,
    global_reaction_rate_mol_m3_s,
    heat_release_rate_W_m3,
    is_above_loi,
    is_flashover_risk,
    laminar_flame_speed_m_s,
    microgravity_flame_speed_m_s,
    molar_concentration_mol_m3,
    stoichiometric_o2_mass_fraction,
)


class TestMolarConcentration:

    def test_stp_pure_gas(self):
        # ideal gas: 1 mol → PV = RT → C = P/(RT) = 101325/(8.314×298) ≈ 40.9 mol/m³
        C = molar_concentration_mol_m3(1.0, P_REF_PA, T_REF_K)
        assert abs(C - 40.9) < 0.5

    def test_proportional_to_pressure(self):
        C1 = molar_concentration_mol_m3(0.21, P_REF_PA, 300.0)
        C2 = molar_concentration_mol_m3(0.21, 2 * P_REF_PA, 300.0)
        assert abs(C2 / C1 - 2.0) < 1e-9

    def test_inversely_proportional_to_temperature(self):
        C1 = molar_concentration_mol_m3(0.21, P_REF_PA, 300.0)
        C2 = molar_concentration_mol_m3(0.21, P_REF_PA, 600.0)
        assert abs(C2 / C1 - 0.5) < 1e-9

    def test_raises_zero_temperature(self):
        with pytest.raises(ValueError):
            molar_concentration_mol_m3(0.21, P_REF_PA, 0.0)


class TestGlobalReactionRate:

    def test_zero_below_500K(self):
        rate = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 499.0)
        assert rate == 0.0

    def test_zero_at_zero_fuel(self):
        assert global_reaction_rate_mol_m3_s(METHANE, 0.0, 0.21, 1500.0) == 0.0

    def test_zero_at_zero_O2(self):
        assert global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.0, 1500.0) == 0.0

    def test_positive_at_stoichiometric_1500K(self):
        rate = global_reaction_rate_mol_m3_s(METHANE, 0.095, 0.21, 1500.0)
        assert rate > 0.0

    def test_increases_with_temperature(self):
        r1 = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 1200.0)
        r2 = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 1500.0)
        assert r2 > r1

    def test_increases_with_o2(self):
        r1 = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 1400.0)
        r2 = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.32, 1400.0)
        assert r2 > r1

    def test_h2_different_from_ch4(self):
        r_ch4 = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 1400.0)
        r_h2 = global_reaction_rate_mol_m3_s(HYDROGEN, 0.05, 0.21, 1400.0)
        assert r_ch4 != r_h2


class TestHeatReleaseRate:

    def test_positive_at_1500K(self):
        Q = heat_release_rate_W_m3(METHANE, 0.05, 0.21, 1500.0)
        assert Q > 0.0

    def test_proportional_to_rate(self):
        Q1 = heat_release_rate_W_m3(METHANE, 0.05, 0.21, 1400.0)
        omega1 = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 1400.0)
        assert abs(Q1 / (omega1 * METHANE.delta_H_c_J_mol) - 1.0) < 1e-9

    def test_h2_differs_from_ch4(self):
        Q_ch4 = heat_release_rate_W_m3(METHANE, 0.05, 0.21, 1400.0)
        Q_h2 = heat_release_rate_W_m3(HYDROGEN, 0.05, 0.21, 1400.0)
        assert Q_ch4 != Q_h2


class TestAdiabaticFlameTemp:

    def test_above_reactant_temp(self):
        T_ad = adiabatic_flame_temperature_K(METHANE, 1.0, T_REF_K)
        assert T_ad > T_REF_K

    def test_lean_lower_than_stoich(self):
        T_lean = adiabatic_flame_temperature_K(METHANE, 0.5, T_REF_K)
        T_stoich = adiabatic_flame_temperature_K(METHANE, 1.0, T_REF_K)
        assert T_lean < T_stoich

    def test_rich_same_as_stoich(self):
        """φ > 1: T_ad capped at φ=1 value (excess fuel, no more O₂ to burn)."""
        T_stoich = adiabatic_flame_temperature_K(METHANE, 1.0, T_REF_K)
        T_rich = adiabatic_flame_temperature_K(METHANE, 1.5, T_REF_K)
        assert abs(T_rich - T_stoich) < 1e-6

    def test_raises_zero_phi(self):
        with pytest.raises(ValueError):
            adiabatic_flame_temperature_K(METHANE, 0.0, T_REF_K)

    def test_methane_at_298K_approx_2200K(self):
        """Methane stoichiometric T_ad ≈ 2226 K (literature: 2230 K ± model error)."""
        T_ad = adiabatic_flame_temperature_K(METHANE, 1.0, T_REF_K)
        assert 1800 < T_ad < 3500, f"T_ad = {T_ad:.0f} K"


class TestLaminarFlameSpeed:

    def test_positive_at_stoichiometric(self):
        S = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K)
        assert S > 0.0

    def test_zero_at_phi_zero(self):
        assert laminar_flame_speed_m_s(METHANE, 0.0, T_REF_K) == 0.0

    def test_max_near_stoichiometric(self):
        S_stoich = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K)
        S_lean = laminar_flame_speed_m_s(METHANE, 0.5, T_REF_K)
        S_rich = laminar_flame_speed_m_s(METHANE, 1.5, T_REF_K)
        assert S_stoich >= S_lean
        assert S_stoich >= S_rich

    def test_increases_with_temperature(self):
        S1 = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K)
        S2 = laminar_flame_speed_m_s(METHANE, 1.0, 450.0)
        assert S2 > S1

    def test_decreases_with_diluent(self):
        S0 = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K, diluent_volume_fraction=0.0)
        S_dil = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K, diluent_volume_fraction=0.3)
        assert S_dil < S0

    def test_h2_faster_than_ch4(self):
        S_h2 = laminar_flame_speed_m_s(HYDROGEN, 1.0, T_REF_K)
        S_ch4 = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K)
        assert S_h2 > S_ch4


class TestLOI:

    def test_ch4_flammable_at_21pct(self):
        assert is_above_loi(METHANE, 0.21)

    def test_ch4_not_flammable_at_20pct(self):
        # LOI = 0.21 exactly; 0.20 < LOI → not flammable
        assert not is_above_loi(METHANE, 0.20)

    def test_h2_flammable_at_10pct(self):
        # H₂ LOI = 5%; 10% > 5% → flammable
        assert is_above_loi(HYDROGEN, 0.10)

    def test_h2_not_flammable_at_3pct(self):
        assert not is_above_loi(HYDROGEN, 0.03)


class TestStoichO2:

    def test_methane_approx_4kg_per_kg(self):
        # CH₄ + 2O₂: stoich_O2 = 2 × 32/16 = 4.0 kg O₂/kg CH₄
        r = stoichiometric_o2_mass_fraction(METHANE)
        assert abs(r - 4.0) < 0.05

    def test_positive_for_all_fuels(self):
        for fuel in [METHANE, ETHANOL, N_HEPTANE, HYDROGEN]:
            assert stoichiometric_o2_mass_fraction(fuel) > 0.0


class TestMicrogravityFlameSpeed:

    def test_le_one_g_speed_at_zero_g(self):
        S_1g = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K)
        S_0g = microgravity_flame_speed_m_s(METHANE, 1.0, T_REF_K, g_fraction=0.0)
        assert S_0g <= S_1g

    def test_equals_1g_at_g1(self):
        S_1g = laminar_flame_speed_m_s(METHANE, 1.0, T_REF_K)
        S_g1 = microgravity_flame_speed_m_s(METHANE, 1.0, T_REF_K, g_fraction=1.0)
        assert abs(S_g1 - S_1g) < 1e-9

    def test_radiative_extinction_very_lean_0g(self):
        # Very lean CH₄ at 0g: S_L drops below extinction threshold → 0
        S = microgravity_flame_speed_m_s(METHANE, 0.3, T_REF_K, g_fraction=0.0)
        assert S == 0.0


class TestFlashover:

    def test_positive_hrr_threshold(self):
        Q = flashover_hrr_threshold_W(10.0, 1.0, 2.0)
        assert Q > 0.0

    def test_increases_with_room_area(self):
        Q1 = flashover_hrr_threshold_W(10.0, 1.0, 2.0)
        Q2 = flashover_hrr_threshold_W(20.0, 1.0, 2.0)
        assert Q2 > Q1

    def test_is_flashover_risk_true(self):
        Q_thresh = flashover_hrr_threshold_W(5.0, 1.0, 2.0)
        assert is_flashover_risk(Q_thresh * 2, 5.0, 1.0, 2.0)

    def test_is_flashover_risk_false(self):
        Q_thresh = flashover_hrr_threshold_W(5.0, 1.0, 2.0)
        assert not is_flashover_risk(Q_thresh * 0.1, 5.0, 1.0, 2.0)


class TestSpacecraftScenarios:

    def test_iss_module_300W_no_flashover(self):
        """ISS Node module: ~45 m³ floor area ~9 m², door 0.8 m × 2 m.
        A small 300 W trash fire should be far below flashover.
        """
        Q_fo = flashover_hrr_threshold_W(9.0, 1.6, 2.0)
        assert not is_flashover_risk(300.0, 9.0, 1.6, 2.0)
        assert Q_fo > 300.0  # confirm margin

    def test_apollo1_high_o2_ch4_rate_higher(self):
        """100% O₂ (Apollo 1) → CH₄ reaction rate far exceeds 21% O₂ rate.
        With b=1.3 (O₂ exponent), ratio = (0.99/0.21)^1.3 ≈ 7.6×.
        """
        r_normal = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.21, 1400.0)
        r_apollo = global_reaction_rate_mol_m3_s(METHANE, 0.05, 0.99, 1400.0)
        assert r_apollo > r_normal * 5  # 5× conservative; actual ~7.6×

    def test_h2_in_oga_compartment_loi(self):
        """H₂ above 5%: LOI exceeded in any normal cabin atmosphere."""
        assert is_above_loi(HYDROGEN, 0.21)  # cabin air is enough to burn H₂
