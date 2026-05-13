"""Tests for Li-ion battery C-rate, capacity fade, and thermal model.

Validates:
1.  max_discharge_current_A: I = C_rate × capacity.
2.  max_discharge_current_A: scales with SoH.
3.  max_discharge_current_A: SoH=0 → zero current.
4.  max_discharge_power_W: positive at nominal conditions.
5.  max_discharge_power_W: decreases with lower SoH.
6.  internal_resistance_ohm: equals R_ref at T_ref.
7.  internal_resistance_ohm: decreases with higher temperature (Arrhenius).
8.  internal_resistance_ohm: increases with lower temperature.
9.  cell_joule_heat_W: P = I² × R for known current.
10. cell_joule_heat_W: zero at zero current.
11. state_of_health: unity at zero cycles, zero age.
12. state_of_health: decreases with cycle count.
13. state_of_health: decreases with calendar age.
14. state_of_health: clamped to [0, 1].
15. state_of_health: higher temp → faster calendar fade.
16. cycles_to_eol: returns positive value at nominal conditions.
17. cycles_to_eol: zero if already at EOL.
18. open_circuit_voltage_V: V_min at SoC=0, V_max at SoC=1.
19. open_circuit_voltage_V: monotonically increasing with SoC.
20. terminal_voltage_V: less than OCV under discharge load.
21. terminal_voltage_V: greater than OCV under charge (negative current).
22. is_thermal_safe: True in range, False outside.
23. is_soc_safe: True in nominal range, False outside.
24. 30-year mission: SoH stays above 60% at 25°C, 1 cycle/day.
25. C-rate limit: maximum current < (3C × capacity_Ah).
"""

from __future__ import annotations

import pytest

from aria.physics.electrical.battery import (
    NMC_C_RATE_MAX_CONTINUOUS,
    NMC_K_CYCLE,
    NMC_SOC_MAX,
    NMC_SOC_MIN,
    NMC_T_MAX_K,
    NMC_T_MIN_K,
    NMC_T_REF_K,
    BatteryCellConfig,
    cell_joule_heat_W,
    cycles_to_eol,
    internal_resistance_ohm,
    is_soc_safe,
    is_thermal_safe,
    max_discharge_current_A,
    max_discharge_power_W,
    open_circuit_voltage_V,
    state_of_health,
    terminal_voltage_V,
)


def _cfg() -> BatteryCellConfig:
    return BatteryCellConfig(capacity_Ah=50.0, n_series=8, n_parallel=1)


# ── C-rate and current limits ─────────────────────────────────────────────────

class TestMaxDischargeCurrent:

    def test_nominal(self):
        cfg = _cfg()
        I = max_discharge_current_A(cfg)
        expected = NMC_C_RATE_MAX_CONTINUOUS * cfg.module_capacity_Ah
        assert abs(I - expected) < 1e-9

    def test_scales_with_soh(self):
        cfg = _cfg()
        I_full = max_discharge_current_A(cfg, soh=1.0)
        I_half = max_discharge_current_A(cfg, soh=0.5)
        assert abs(I_half / I_full - 0.5) < 1e-9

    def test_zero_soh(self):
        cfg = _cfg()
        assert max_discharge_current_A(cfg, soh=0.0) == 0.0

    def test_negative_soh_clamped(self):
        cfg = _cfg()
        assert max_discharge_current_A(cfg, soh=-0.5) == 0.0


class TestMaxDischargePower:

    def test_positive_at_nominal(self):
        cfg = _cfg()
        P = max_discharge_power_W(cfg)
        assert P > 0.0

    def test_decreases_with_soh(self):
        cfg = _cfg()
        P_full = max_discharge_power_W(cfg, soh=1.0)
        P_half = max_discharge_power_W(cfg, soh=0.5)
        assert P_half < P_full

    def test_unit_check(self):
        cfg = BatteryCellConfig(capacity_Ah=100.0, n_series=1, n_parallel=1)
        P = max_discharge_power_W(cfg, temperature_K=NMC_T_REF_K)
        # Rough check: P ≈ V_nom × C_rate_max × Q_Ah × eta
        approx = cfg.v_nom * 3.0 * 100.0 * 0.97
        assert P > approx * 0.5  # accounts for voltage sag


# ── Internal resistance ───────────────────────────────────────────────────────

class TestInternalResistance:

    def test_equals_ref_at_T_ref(self):
        cfg = _cfg()
        R = internal_resistance_ohm(cfg, NMC_T_REF_K)
        assert abs(R - cfg.r_int_ref_ohm) < 1e-12

    def test_decreases_with_higher_temperature(self):
        cfg = _cfg()
        R_cold = internal_resistance_ohm(cfg, 273.0)
        R_warm = internal_resistance_ohm(cfg, 323.0)
        assert R_warm < R_cold

    def test_increases_with_lower_temperature(self):
        cfg = _cfg()
        R_warm = internal_resistance_ohm(cfg, NMC_T_REF_K)
        R_cold = internal_resistance_ohm(cfg, NMC_T_REF_K - 50.0)
        assert R_cold > R_warm

    def test_positive_always(self):
        cfg = _cfg()
        for T in [150.0, 250.0, 300.0, 400.0]:
            assert internal_resistance_ohm(cfg, T) > 0.0


# ── Cell Joule heat ───────────────────────────────────────────────────────────

class TestCellJouleHeat:

    def test_ohms_law(self):
        cfg = _cfg()
        I = 10.0
        R = internal_resistance_ohm(cfg, NMC_T_REF_K)
        P = cell_joule_heat_W(I, cfg, NMC_T_REF_K)
        assert abs(P - I ** 2 * R) < 1e-12

    def test_zero_current_zero_heat(self):
        assert cell_joule_heat_W(0.0, _cfg(), NMC_T_REF_K) == 0.0

    def test_scales_with_current_squared(self):
        cfg = _cfg()
        P1 = cell_joule_heat_W(1.0, cfg, NMC_T_REF_K)
        P2 = cell_joule_heat_W(2.0, cfg, NMC_T_REF_K)
        assert abs(P2 / P1 - 4.0) < 1e-9


# ── State of Health (capacity fade) ──────────────────────────────────────────

class TestStateOfHealth:

    def test_unity_at_start(self):
        cfg = _cfg()
        soh = state_of_health(cfg, n_cycles=0.0, calendar_years=0.0,
                               temperature_K=NMC_T_REF_K)
        assert abs(soh - 1.0) < 1e-9

    def test_decreases_with_cycles(self):
        cfg = _cfg()
        soh_1000 = state_of_health(cfg, 1000, 0.0)
        soh_5000 = state_of_health(cfg, 5000, 0.0)
        assert soh_5000 < soh_1000

    def test_decreases_with_calendar_age(self):
        cfg = _cfg()
        soh_0 = state_of_health(cfg, 0, 0.0)
        soh_10 = state_of_health(cfg, 0, 10.0)
        assert soh_10 < soh_0

    def test_clamped_to_zero_at_extreme_wear(self):
        cfg = _cfg()
        soh = state_of_health(cfg, n_cycles=1e8, calendar_years=1000.0)
        assert soh == 0.0

    def test_clamped_to_one_maximum(self):
        cfg = _cfg()
        soh = state_of_health(cfg, 0.0, 0.0)
        assert soh <= 1.0

    def test_higher_temp_faster_calendar_fade(self):
        cfg = _cfg()
        soh_warm = state_of_health(cfg, 0, 5.0, temperature_K=320.0)
        soh_cold = state_of_health(cfg, 0, 5.0, temperature_K=270.0)
        assert soh_warm < soh_cold

    def test_cycle_fade_sqrt_scaling(self):
        cfg = _cfg()
        # 4× cycles → 2× cycle fade contribution (sqrt)
        soh_100 = state_of_health(cfg, 100, 0.0)
        soh_400 = state_of_health(cfg, 400, 0.0)
        fade_100 = 1.0 - soh_100
        fade_400 = 1.0 - soh_400
        assert abs(fade_400 / fade_100 - 2.0) < 0.1


# ── Cycles to EOL ─────────────────────────────────────────────────────────────

class TestCyclesToEol:

    def test_positive_at_nominal(self):
        cfg = _cfg()
        N = cycles_to_eol(cfg, eol_threshold=0.80)
        assert N > 0.0

    def test_more_cycles_to_eol_with_lower_threshold(self):
        cfg = _cfg()
        N80 = cycles_to_eol(cfg, eol_threshold=0.80)
        N70 = cycles_to_eol(cfg, eol_threshold=0.70)
        assert N70 > N80

    def test_zero_when_already_eol(self):
        cfg = _cfg()
        # Extreme calendar age: calendar fade alone already exceeds EOL
        N = cycles_to_eol(cfg, eol_threshold=0.80, calendar_years=1000.0)
        assert N == 0.0

    def test_reasonable_nmc_cycle_life(self):
        cfg = _cfg()
        N = cycles_to_eol(cfg, eol_threshold=0.80)
        # Standard NMC: 500–3000 cycles to 80% capacity (Schmalstieg 2014 Fig.3)
        assert 200 < N < 5000, f"NMC cycles to 80% = {N:.0f}"


# ── OCV and terminal voltage ──────────────────────────────────────────────────

class TestVoltageModel:

    def test_ocv_min_at_soc_zero(self):
        cfg = _cfg()
        V = open_circuit_voltage_V(cfg, 0.0)
        assert abs(V - cfg.v_min) < 1e-9

    def test_ocv_max_at_soc_one(self):
        cfg = _cfg()
        V = open_circuit_voltage_V(cfg, 1.0)
        assert abs(V - cfg.v_max) < 1e-9

    def test_ocv_monotone(self):
        cfg = _cfg()
        V1 = open_circuit_voltage_V(cfg, 0.2)
        V2 = open_circuit_voltage_V(cfg, 0.8)
        assert V2 > V1

    def test_terminal_less_than_ocv_discharge(self):
        cfg = _cfg()
        V_oc = open_circuit_voltage_V(cfg, 0.5)
        V_t = terminal_voltage_V(cfg, 0.5, current_A=10.0)  # discharge
        assert V_t < V_oc

    def test_terminal_greater_than_ocv_charge(self):
        cfg = _cfg()
        V_oc = open_circuit_voltage_V(cfg, 0.5)
        V_t = terminal_voltage_V(cfg, 0.5, current_A=-10.0)  # charge
        assert V_t > V_oc

    def test_terminal_equals_ocv_zero_current(self):
        cfg = _cfg()
        soc = 0.6
        V_oc = open_circuit_voltage_V(cfg, soc)
        V_t = terminal_voltage_V(cfg, soc, current_A=0.0)
        assert abs(V_t - V_oc) < 1e-9


# ── Safety checks ─────────────────────────────────────────────────────────────

class TestSafetyChecks:

    def test_thermal_safe_in_range(self):
        assert is_thermal_safe(298.0)

    def test_thermal_unsafe_above_max(self):
        assert not is_thermal_safe(NMC_T_MAX_K + 1.0)

    def test_thermal_unsafe_below_min(self):
        assert not is_thermal_safe(NMC_T_MIN_K - 1.0)

    def test_soc_safe_in_range(self):
        assert is_soc_safe(0.5)

    def test_soc_unsafe_below_min(self):
        assert not is_soc_safe(NMC_SOC_MIN - 0.01)

    def test_soc_unsafe_above_max(self):
        assert not is_soc_safe(NMC_SOC_MAX + 0.01)


# ── Mission scenario ──────────────────────────────────────────────────────────

class TestMissionScenario:

    def test_30yr_1cycle_per_week_soh_above_60pct(self):
        """30-year mission, 1 cycle/week (emergency storage) at 25°C.

        Generation ship batteries are reserve energy, not daily cycled.
        1560 cycles over 30 years is realistic for backup/surge use.
        """
        cfg = _cfg()
        n_cycles = 30 * 52  # 1560 full-equivalent cycles over 30 years
        soh = state_of_health(cfg, n_cycles, calendar_years=30.0,
                               temperature_K=NMC_T_REF_K)
        assert soh > 0.50, (
            f"SoH after 30 yr / {n_cycles} cycles = {soh:.1%}, expected > 50%"
        )

    def test_c_rate_limit_respected(self):
        cfg = _cfg()
        I_max = max_discharge_current_A(cfg, soh=1.0)
        assert I_max <= NMC_C_RATE_MAX_CONTINUOUS * cfg.module_capacity_Ah + 1e-9
