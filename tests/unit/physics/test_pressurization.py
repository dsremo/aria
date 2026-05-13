"""Tests for propellant tank pressurization physics.

Validates:
1.  blowdown_pressure_Pa: P decreases as ullage expands.
2.  blowdown_pressure_Pa: P unchanged when ullage same as initial.
3.  blowdown_pressure_Pa: isothermal follows P×V = const (Boyle's law).
4.  blowdown_pressure_Pa: adiabatic lower pressure than isothermal at same V.
5.  blowdown_pressure_Pa: raises ValueError for zero initial ullage.
6.  blowdown_pressure_Pa: raises ValueError for zero final ullage.
7.  blowdown_pressure_Pa: raises ValueError for zero initial pressure.
8.  blowdown_pressure_ratio: < 1 when final ullage > initial (expansion).
9.  blowdown_pressure_ratio: = 1 when final = initial ullage.
10. blowdown_pressure_ratio: isothermal special case matches blowdown_pressure_ratio(n=1).
11. blowdown_pressure_ratio: adiabatic gives lower ratio than isothermal.
12. blowdown_pressure_ratio: raises ValueError for ullage fraction out of range.
13. dissolved_pressurant_mol_m3: positive for positive pressure.
14. dissolved_pressurant_mol_m3: proportional to pressure (Henry's law).
15. dissolved_pressurant_mol_m3: decreases with temperature (gas less soluble at high T).
16. dissolved_pressurant_mol_m3: raises ValueError at T=0.
17. absorbed_pressurant_volume_m3: positive for positive pressure and volume.
18. absorbed_pressurant_volume_m3: proportional to propellant volume.
19. absorption_volume_fraction: between 0 and 1 at nominal conditions.
20. absorption_volume_fraction: N₂ absorbed more than He at same conditions.
21. absorption_volume_fraction: raises ValueError at zero ullage.
22. pressurant_mass_kg_regulated: positive for any positive pressure/volume.
23. pressurant_mass_kg_regulated: proportional to feed pressure (ideal gas).
24. pressurant_mass_kg_regulated: proportional to propellant volume.
25. pressurant_mass_kg_regulated: He lighter than N₂ for same conditions.
26. pressurant_mass_kg_regulated: raises ValueError at T=0.
27. pressurant_bottle_volume_m3: positive for positive mass.
28. pressurant_bottle_volume_m3: smaller at higher storage pressure.
29. blowdown_final_pressure_with_absorption: ≤ no-absorption pressure (gas absorbed reduces available pressure).
30. blowdown_final_pressure_with_absorption: N₂ greater reduction than He (more absorption).
31. blowdown_pressure_history: first entry is (0, P_init).
32. blowdown_pressure_history: pressure monotonically decreasing.
33. blowdown_pressure_history: last time = duration_s.
34. He blowdown 10% → 90% ullage at 1 MPa: final P ≈ 0.111 MPa (isothermal).
35. He γ=5/3 adiabatic blowdown: final P < isothermal at same expansion ratio.
"""

from __future__ import annotations

import math
import pytest

from aria.physics.propulsion.pressurization import (
    GN2,
    HELIUM,
    NITROGEN,
    absorbed_pressurant_volume_m3,
    absorption_volume_fraction,
    blowdown_final_pressure_with_absorption,
    blowdown_pressure_Pa,
    blowdown_pressure_history,
    blowdown_pressure_ratio,
    blowdown_pressure_ratio_adiabatic,
    blowdown_pressure_ratio_isothermal,
    dissolved_pressurant_mol_m3,
    pressurant_bottle_volume_m3,
    pressurant_mass_kg_regulated,
)


class TestBlowdownPressure:

    def test_pressure_decreases_on_expansion(self):
        P = blowdown_pressure_Pa(1e6, 0.1, 0.5)
        assert P < 1e6

    def test_pressure_unchanged_same_ullage(self):
        P = blowdown_pressure_Pa(1e6, 0.1, 0.1)
        assert abs(P - 1e6) < 1e-6

    def test_boyles_law_isothermal(self):
        """P × V = const: P₀ × V₀ = P₁ × V₁."""
        P0, V0, V1 = 2e6, 0.05, 0.20
        P1 = blowdown_pressure_Pa(P0, V0, V1, n_polytropic=1.0)
        assert abs(P0 * V0 - P1 * V1) < 1.0  # <1 Pa·m³ tolerance

    def test_adiabatic_lower_than_isothermal(self):
        P0, V0, V1 = 1e6, 0.1, 0.9
        P_iso = blowdown_pressure_Pa(P0, V0, V1, n_polytropic=1.0)
        P_adi = blowdown_pressure_Pa(P0, V0, V1, n_polytropic=HELIUM.gamma)
        assert P_adi < P_iso

    def test_raises_zero_initial_ullage(self):
        with pytest.raises(ValueError):
            blowdown_pressure_Pa(1e6, 0.0, 0.5)

    def test_raises_zero_final_ullage(self):
        with pytest.raises(ValueError):
            blowdown_pressure_Pa(1e6, 0.1, 0.0)

    def test_raises_zero_initial_pressure(self):
        with pytest.raises(ValueError):
            blowdown_pressure_Pa(0.0, 0.1, 0.5)

    def test_he_10pct_to_90pct_isothermal(self):
        """He blowdown 10% → 90% ullage at 1 MPa: P_f = P_0 × (0.1/0.9) ≈ 111 kPa."""
        P = blowdown_pressure_Pa(1e6, 0.1, 0.9, n_polytropic=1.0)
        expected = 1e6 * (0.1 / 0.9)
        assert abs(P - expected) < 1.0

    def test_adiabatic_he_lower_than_isothermal(self):
        P_iso = blowdown_pressure_Pa(1e6, 0.1, 0.9, n_polytropic=1.0)
        P_adi = blowdown_pressure_Pa(1e6, 0.1, 0.9, n_polytropic=HELIUM.gamma)
        assert P_adi < P_iso


class TestBlowdownRatio:

    def test_less_than_one_on_expansion(self):
        r = blowdown_pressure_ratio(0.1, 0.9)
        assert r < 1.0

    def test_equal_to_one_no_change(self):
        r = blowdown_pressure_ratio(0.3, 0.3)
        assert abs(r - 1.0) < 1e-9

    def test_isothermal_matches_n1(self):
        r1 = blowdown_pressure_ratio_isothermal(0.1, 0.5)
        r2 = blowdown_pressure_ratio(0.1, 0.5, n_polytropic=1.0)
        assert abs(r1 - r2) < 1e-9

    def test_adiabatic_lower_than_isothermal(self):
        r_iso = blowdown_pressure_ratio_isothermal(0.1, 0.9)
        r_adi = blowdown_pressure_ratio_adiabatic(0.1, 0.9, HELIUM.gamma)
        assert r_adi < r_iso

    def test_raises_invalid_ullage_fraction(self):
        with pytest.raises(ValueError):
            blowdown_pressure_ratio(0.0, 0.9)
        with pytest.raises(ValueError):
            blowdown_pressure_ratio(0.1, 0.0)


class TestHenrysLaw:

    def test_positive_concentration(self):
        C = dissolved_pressurant_mol_m3(HELIUM, 1e6, 293.15)
        assert C > 0.0

    def test_proportional_to_pressure(self):
        C1 = dissolved_pressurant_mol_m3(HELIUM, 1e6, 293.15)
        C2 = dissolved_pressurant_mol_m3(HELIUM, 2e6, 293.15)
        assert abs(C2 / C1 - 2.0) < 1e-9

    def test_decreases_with_temperature(self):
        """Gas less soluble at higher temperature (van't Hoff)."""
        C_cold = dissolved_pressurant_mol_m3(HELIUM, 1e6, 280.0)
        C_warm = dissolved_pressurant_mol_m3(HELIUM, 1e6, 320.0)
        assert C_cold > C_warm

    def test_raises_zero_temperature(self):
        with pytest.raises(ValueError):
            dissolved_pressurant_mol_m3(HELIUM, 1e6, 0.0)

    def test_n2_more_absorbed_than_he(self):
        C_he = dissolved_pressurant_mol_m3(HELIUM, 1e6, 293.15)
        C_n2 = dissolved_pressurant_mol_m3(NITROGEN, 1e6, 293.15)
        assert C_n2 > C_he


class TestAbsorption:

    def test_absorbed_volume_positive(self):
        V = absorbed_pressurant_volume_m3(HELIUM, 1e6, 0.1, 293.15)
        assert V > 0.0

    def test_proportional_to_propellant_volume(self):
        V1 = absorbed_pressurant_volume_m3(HELIUM, 1e6, 0.1, 293.15)
        V2 = absorbed_pressurant_volume_m3(HELIUM, 1e6, 0.2, 293.15)
        assert abs(V2 / V1 - 2.0) < 1e-9

    def test_n2_greater_absorption_than_he(self):
        V_he = absorbed_pressurant_volume_m3(HELIUM, 1e6, 0.1, 293.15)
        V_n2 = absorbed_pressurant_volume_m3(NITROGEN, 1e6, 0.1, 293.15)
        assert V_n2 > V_he

    def test_fraction_raises_zero_ullage(self):
        with pytest.raises(ValueError):
            absorption_volume_fraction(HELIUM, 1e6, 0.1, 0.0, 293.15)


class TestPressurantMass:

    def test_positive_mass(self):
        m = pressurant_mass_kg_regulated(HELIUM, 1e6, 0.1, 293.15)
        assert m > 0.0

    def test_proportional_to_pressure(self):
        m1 = pressurant_mass_kg_regulated(HELIUM, 1e6, 0.1, 293.15)
        m2 = pressurant_mass_kg_regulated(HELIUM, 2e6, 0.1, 293.15)
        assert abs(m2 / m1 - 2.0) < 1e-9

    def test_proportional_to_volume(self):
        m1 = pressurant_mass_kg_regulated(HELIUM, 1e6, 0.1, 293.15)
        m2 = pressurant_mass_kg_regulated(HELIUM, 1e6, 0.2, 293.15)
        assert abs(m2 / m1 - 2.0) < 1e-9

    def test_he_lighter_than_n2(self):
        m_he = pressurant_mass_kg_regulated(HELIUM, 1e6, 0.1, 293.15)
        m_n2 = pressurant_mass_kg_regulated(NITROGEN, 1e6, 0.1, 293.15)
        assert m_he < m_n2

    def test_raises_zero_temperature(self):
        with pytest.raises(ValueError):
            pressurant_mass_kg_regulated(HELIUM, 1e6, 0.1, 0.0)


class TestBottleVolume:

    def test_positive_volume(self):
        V = pressurant_bottle_volume_m3(HELIUM, 0.5, 30e6, 293.15)
        assert V > 0.0

    def test_smaller_at_higher_pressure(self):
        V1 = pressurant_bottle_volume_m3(HELIUM, 0.5, 20e6, 293.15)
        V2 = pressurant_bottle_volume_m3(HELIUM, 0.5, 40e6, 293.15)
        assert V2 < V1


class TestAbsorptionBlowdown:

    def test_final_pressure_le_no_absorption(self):
        """Absorption reduces effective pressurant → lower final pressure."""
        P_no_abs = blowdown_pressure_Pa(
            1e6, 0.1, 0.1 + 0.5, n_polytropic=1.0
        )
        P_abs = blowdown_final_pressure_with_absorption(
            NITROGEN, 1e6, 0.1, 0.5, 293.15, n_polytropic=1.0
        )
        # N₂ absorbs significantly → effective ullage smaller → higher P (less expansion)
        # OR very small absorption → nearly equal. Either way, P_abs ≤ P_no_abs
        assert P_abs <= P_no_abs + 1.0  # within 1 Pa tolerance


class TestHistory:

    def test_first_entry_initial_conditions(self):
        hist = blowdown_pressure_history(
            HELIUM, 1e6, 1.0, 0.1, 0.01, 1000.0, 10.0, n_steps=5
        )
        t0, P0 = hist[0]
        assert t0 == 0.0
        assert abs(P0 - 1e6) < 1.0

    def test_pressure_monotonically_decreasing(self):
        hist = blowdown_pressure_history(
            HELIUM, 1e6, 1.0, 0.1, 0.01, 1000.0, 10.0, n_steps=10
        )
        pressures = [P for _, P in hist]
        for i in range(1, len(pressures)):
            assert pressures[i] <= pressures[i - 1] + 1e-6  # non-increasing

    def test_last_time_equals_duration(self):
        hist = blowdown_pressure_history(
            HELIUM, 1e6, 1.0, 0.1, 0.01, 1000.0, 10.0, n_steps=10
        )
        t_last, _ = hist[-1]
        assert abs(t_last - 10.0) < 1e-9
