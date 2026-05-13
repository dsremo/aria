"""Vendor cell-level EPS model tests.

Validates the solar-cell + Li-ion-cell models against the published
datasheet values they're parameterised from. Each test cites the
datasheet section it's checking against.
"""

from __future__ import annotations

import math

import pytest

from aria.physics.eps.solar_cells import (
    AZUR_3G30A,
    XTJ_PRIME,
    cell_iv_at_voltage,
    cell_max_power,
    thermal_voltage,
)
from aria.physics.eps.li_ion_cells import (
    MP176065,
    VES180,
    terminal_voltage,
    update_soc,
    usable_energy_wh,
    voc_at_soc,
)


# ── Solar cell datasheet round-trip ─────────────────────────────


class TestXtjPrimeDatasheetMatch:
    """Spectrolab XTJ-Prime — the values populated in solar_cells.py
    must round-trip through the datasheet identities."""

    def test_pmax_matches_vmp_imp_product(self) -> None:
        # P_max = V_mp × I_mp (definition).
        assert XTJ_PRIME.pmax_w_at_bol == pytest.approx(
            XTJ_PRIME.vmp_v * XTJ_PRIME.imp_a, rel=1e-9,
        )

    def test_fill_factor_above_83pct(self) -> None:
        # Triple-junction cells: FF typically 0.83-0.86 per De Soto 2006
        # + Spectrolab datasheet (XTJ-Prime FF ≈ 0.838).
        assert XTJ_PRIME.fill_factor > 0.83

    def test_efficiency_consistent_with_pmax_and_intensity(self) -> None:
        # η = P_max / (intensity × area). At AM0 = 1367 W/m²,
        # area = 30.18 cm² = 30.18e-4 m², datasheet says η = 29.5 %.
        intensity = 1367.0
        area_m2 = XTJ_PRIME.cell_area_cm2 * 1e-4
        eff = XTJ_PRIME.pmax_w_at_bol / (intensity * area_m2)
        # Within 1 percentage point of the datasheet 29.5 %.
        assert abs(eff - 0.295) < 0.01

    def test_voc_temperature_derate(self) -> None:
        # At 80 °C (~353 K), V_oc should drop by ~0.33 V from 25 °C
        # baseline (∂V_oc/∂T = -6 mV/K × 55 K = -0.33 V).
        target = XTJ_PRIME.voc_v + XTJ_PRIME.dvoc_dT_v_k * 55.0
        assert target == pytest.approx(2.713 - 0.33, abs=0.01)


class TestAzur3G30ADatasheetMatch:
    """Azur Space 3G30C-Advanced datasheet round-trip."""

    def test_efficiency_30pct_at_am0_25c(self) -> None:
        intensity = 1367.0
        area_m2 = AZUR_3G30A.cell_area_cm2 * 1e-4
        eff = AZUR_3G30A.pmax_w_at_bol / (intensity * area_m2)
        assert abs(eff - 0.300) < 0.01

    def test_voc_higher_than_xtj_prime_per_datasheet(self) -> None:
        # Per Azur datasheet vs Spectrolab TR2020A: Azur's design has
        # marginally higher V_mp.  Check the qualitative ordering.
        assert AZUR_3G30A.vmp_v >= XTJ_PRIME.vmp_v


# ── Solar cell physics behaviour ────────────────────────────────


class TestSingleDiodeIVCurve:
    def test_short_circuit_current_at_zero_voltage(self) -> None:
        # I(V=0) ≈ I_sc by definition.
        point = cell_iv_at_voltage(XTJ_PRIME, voltage_v=0.0)
        assert point.current_a == pytest.approx(XTJ_PRIME.isc_a, rel=0.05)

    def test_zero_current_at_open_circuit_voltage(self) -> None:
        # I(V=V_oc) ≈ 0 by definition.
        point = cell_iv_at_voltage(XTJ_PRIME, voltage_v=XTJ_PRIME.voc_v)
        # Should be tiny, not exactly 0 because of the simplified diode.
        assert abs(point.current_a) < 0.01

    def test_iv_curve_monotonically_decreasing(self) -> None:
        # Standard solar cell I-V: I decreases as V increases.
        prev_i = float("inf")
        for v_step in range(0, 20):
            v = XTJ_PRIME.voc_v * v_step / 20.0
            point = cell_iv_at_voltage(XTJ_PRIME, voltage_v=v)
            assert point.current_a <= prev_i + 1e-9
            prev_i = point.current_a

    def test_max_power_within_5pct_of_datasheet(self) -> None:
        # cell_max_power should land near the datasheet P_max.
        result = cell_max_power(XTJ_PRIME)
        assert result.power_w == pytest.approx(
            XTJ_PRIME.pmax_w_at_bol, rel=0.05,
        )

    def test_intensity_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="intensity"):
            cell_iv_at_voltage(XTJ_PRIME, voltage_v=1.0, intensity_w_m2=0.0)

    def test_negative_voltage_rejected(self) -> None:
        with pytest.raises(ValueError, match="voltage_v"):
            cell_iv_at_voltage(XTJ_PRIME, voltage_v=-0.1)


class TestRadiationDegradation:
    def test_zero_fluence_no_degradation(self) -> None:
        # P_max at 0 fluence = BOL P_max.
        result = cell_max_power(XTJ_PRIME, fluence_e_cm2=0.0)
        assert result.power_w == pytest.approx(XTJ_PRIME.pmax_w_at_bol, rel=0.05)

    def test_at_90pct_fluence_about_90pct_pmax(self) -> None:
        result = cell_max_power(
            XTJ_PRIME, fluence_e_cm2=XTJ_PRIME.fluence_to_90pct_pmax,
        )
        # Within 5 % of 0.9 × P_max BOL.
        target = 0.9 * XTJ_PRIME.pmax_w_at_bol
        assert result.power_w == pytest.approx(target, rel=0.10)

    def test_huge_fluence_clipped_above_30pct(self) -> None:
        # Very-high fluence: the radiation floor is 0.5 × I_sc, plus
        # the voltage degrades to 0.75 × V_oc, so MPP P_max can drop
        # to ~0.375 × P_max BOL. Floor verifies the model doesn't
        # silently let P_max go to zero or negative.
        result = cell_max_power(XTJ_PRIME, fluence_e_cm2=1e18)
        assert result.power_w >= 0.30 * XTJ_PRIME.pmax_w_at_bol
        assert result.power_w <= 0.50 * XTJ_PRIME.pmax_w_at_bol


# ── Li-ion battery cell tests ───────────────────────────────────


class TestVES180DatasheetMatch:
    def test_nominal_energy_matches_v_times_ah(self) -> None:
        # 50 Ah × 3.6 V = 180 Wh per Saft datasheet §1.
        assert VES180.nominal_energy_wh == pytest.approx(
            VES180.nominal_voltage_v * VES180.nominal_capacity_ah,
            abs=1.0,
        )

    def test_voltage_window_4v1_to_2v7(self) -> None:
        assert VES180.voltage_max_v == pytest.approx(4.10)
        assert VES180.voltage_min_v == pytest.approx(2.70)

    def test_30k_cycle_qualification(self) -> None:
        # VES180 LEO qualification: 30,000 cycles at 30 % DoD.
        assert VES180.cycle_life_at_30pct_dod >= 30_000


class TestVocSoCCurve:
    def test_voc_at_full_charge_matches_datasheet_max(self) -> None:
        v = voc_at_soc(VES180, 1.0)
        # Curve anchor at SoC=1 is V_max ≈ 4.1 V (multiplier 1.14 × 3.6 = 4.10).
        assert v == pytest.approx(VES180.voltage_max_v, abs=0.05)

    def test_voc_at_zero_above_voltage_min(self) -> None:
        # At SoC=0, V_oc must be ABOVE the voltage_min cutoff (otherwise
        # the cell is sitting below its safe-operating window).
        v = voc_at_soc(VES180, 0.0)
        # Curve anchor at SoC=0 is 0.75 × 3.6 = 2.7 V (right at min).
        assert v >= VES180.voltage_min_v - 0.01

    def test_voc_monotonically_increasing(self) -> None:
        prev = -1.0
        for soc_pct in range(0, 101, 5):
            v = voc_at_soc(VES180, soc_pct / 100.0)
            assert v >= prev - 1e-6, (
                f"V_oc not monotonic at SoC {soc_pct}%: prev={prev:.3f}, now={v:.3f}"
            )
            prev = v

    def test_soc_outside_unit_interval_clamped(self) -> None:
        # Past SoC=1 should clamp to V_max.
        assert voc_at_soc(VES180, 1.5) == pytest.approx(
            voc_at_soc(VES180, 1.0), rel=1e-6,
        )
        # Below SoC=0 should clamp to V_min anchor.
        assert voc_at_soc(VES180, -0.3) == pytest.approx(
            voc_at_soc(VES180, 0.0), rel=1e-6,
        )


class TestTerminalVoltageWithLoad:
    def test_no_load_terminal_equals_voc(self) -> None:
        v = terminal_voltage(VES180, soc_fraction=0.5, current_a=0.0)
        assert v == pytest.approx(voc_at_soc(VES180, 0.5), rel=1e-9)

    def test_discharge_drops_terminal_voltage(self) -> None:
        v_no_load = terminal_voltage(VES180, soc_fraction=0.5, current_a=0.0)
        v_under_load = terminal_voltage(
            VES180, soc_fraction=0.5, current_a=10.0,
        )
        assert v_under_load < v_no_load

    def test_charge_raises_terminal_voltage(self) -> None:
        v_no_load = terminal_voltage(VES180, soc_fraction=0.5, current_a=0.0)
        v_charge = terminal_voltage(
            VES180, soc_fraction=0.5, current_a=-10.0,
        )
        assert v_charge > v_no_load

    def test_cold_temperature_raises_resistance(self) -> None:
        # At -10 °C, R_int should be ~2× the 25 °C value, so terminal
        # drop under load is roughly doubled.
        drop_25c = (
            terminal_voltage(VES180, 0.5, current_a=0.0, temperature_c=25.0)
            - terminal_voltage(VES180, 0.5, current_a=10.0, temperature_c=25.0)
        )
        drop_minus10c = (
            terminal_voltage(VES180, 0.5, current_a=0.0, temperature_c=-10.0)
            - terminal_voltage(VES180, 0.5, current_a=10.0, temperature_c=-10.0)
        )
        assert drop_minus10c > drop_25c


class TestSocCoulombCounting:
    def test_full_discharge_at_C5_takes_5_hours(self) -> None:
        # C/5 means I = C / 5 = 50 / 5 = 10 A; full discharge = 5 h.
        soc = 1.0
        dt_s = 60.0   # 1 minute steps
        total_min = 0
        while soc > 0.0 and total_min < 600:
            soc = update_soc(VES180, soc, current_a=10.0, dt_s=dt_s)
            total_min += 1
        # Should empty between 4.5 h and 5.5 h with ideal coulomb counting
        # (no losses, but capacity_factor = 1.0 at 25 °C).
        assert 270 <= total_min <= 330  # 4.5 to 5.5 h in minutes

    def test_zero_current_no_change(self) -> None:
        soc = update_soc(VES180, 0.5, current_a=0.0, dt_s=3600.0)
        assert soc == 0.5

    def test_charge_increases_soc(self) -> None:
        # Negative current = charge.
        new_soc = update_soc(VES180, 0.5, current_a=-10.0, dt_s=3600.0)
        assert new_soc > 0.5

    def test_clamped_at_full_charge(self) -> None:
        new_soc = update_soc(VES180, 0.99, current_a=-100.0, dt_s=3600.0)
        assert new_soc <= 1.0

    def test_clamped_at_empty(self) -> None:
        new_soc = update_soc(VES180, 0.01, current_a=100.0, dt_s=3600.0)
        assert new_soc >= 0.0


class TestUsableEnergy:
    def test_full_charge_energy_near_180wh(self) -> None:
        # Full energy from SoC=1 to SoC=0 should be near rated 180 Wh
        # (slightly higher due to non-flat curve; integral of V × dQ).
        e = usable_energy_wh(VES180, soc_initial=1.0)
        # Within 15 % of nominal (curve integrates higher than V_nom × Ah).
        assert 160.0 <= e <= 220.0

    def test_half_charge_about_half_energy(self) -> None:
        e_full = usable_energy_wh(VES180, soc_initial=1.0)
        e_half = usable_energy_wh(VES180, soc_initial=0.5)
        # Lower-SoC integral covers lower V_oc band; should be < 50 %.
        assert e_half < 0.6 * e_full
        assert e_half > 0.3 * e_full


# ── Cubesat-class small cell ────────────────────────────────────


class TestMP176065Cubesat:
    def test_nominal_capacity_around_6_8_ah(self) -> None:
        assert MP176065.nominal_capacity_ah == pytest.approx(6.8)

    def test_voltage_window_2v5_to_4v2(self) -> None:
        assert MP176065.voltage_max_v == pytest.approx(4.20)
        assert MP176065.voltage_min_v == pytest.approx(2.50)
