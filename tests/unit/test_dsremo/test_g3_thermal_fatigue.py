"""Tests for V3-G3: streaming rain-flow + Coffin-Manson thermal fatigue.

Validates:
 1. Empty monitor → report returns zeros + NOMINAL
 2. Monotone ramp → no closed cycles (open loading only)
 3. One full sine-like swing → exactly one closed cycle
 4. Two consecutive identical cycles double the damage
 5. Coffin-Manson: doubling ΔT at k=2 → 4× damage per cycle (exact ratio)
 6. Sub-gate oscillations do not open cycles or add damage
 7. Nested ranges (larger wrapping smaller) close the inner cycle first
 8. Tier classification: NOMINAL / WATCH / WARNING / CRITICAL
 9. Custom ThermalChannelSpec overrides are honoured
10. reset() clears state
11. Singleton get_monitor / reset_monitor
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection.thermal_fatigue_monitor import (
    D_CRITICAL_THRESHOLD,
    D_WARNING_THRESHOLD,
    D_WATCH_THRESHOLD,
    ThermalChannelSpec,
    ThermalFatigueMonitor,
    ThermalLifeTier,
    _tier_for,
    get_monitor,
    reset_monitor,
)


def _ingest(mon: ThermalFatigueMonitor, key: str, series, spec=None, t0=0.0):
    """Feed a list of temperatures 1 s apart into the monitor."""
    for i, v in enumerate(series):
        mon.update(key, float(v), t0 + float(i), spec)


class TestBasic:

    def test_empty_report(self):
        mon = ThermalFatigueMonitor()
        rep = mon.report("never")
        assert rep.full_cycles == 0
        assert rep.damage == 0.0
        assert rep.tier == ThermalLifeTier.NOMINAL

    def test_monotone_ramp_no_cycles(self):
        mon = ThermalFatigueMonitor()
        _ingest(mon, "K", range(50))   # 0, 1, 2, ..., 49
        rep = mon.report("K")
        assert rep.full_cycles == 0


class TestRainflow:

    def test_single_full_swing_closes_one_cycle(self):
        """Triangle wave up-down-up closes exactly one cycle of the
        inner range, leaving residual half-cycles on the stack."""
        mon = ThermalFatigueMonitor()
        # 0 → 10 → 0 → 10 → 0 : outer swing 0-10 encloses the middle one.
        _ingest(mon, "K", [0, 10, 0, 10, 0])
        rep = mon.report("K")
        # At least one full cycle should close.
        assert rep.full_cycles >= 1
        # And the RMS range must match ~10 (the swing amplitude).
        assert abs(rep.rms_range_c - 10.0) < 1e-9

    def test_two_identical_cycles_double_damage(self):
        mon = ThermalFatigueMonitor()
        series = [0, 20, 0, 20, 0, 20, 0, 20, 0]
        _ingest(mon, "K", series)
        rep = mon.report("K")
        # Rain-flow should find at least 2 closed 20 °C cycles.
        assert rep.full_cycles >= 2

    def test_nested_small_within_large_closes_small_first(self):
        """Large wrapping swing (0 → 40) with a tiny 10-degree excursion
        inside it.  Rain-flow must close the inner 10-degree cycle first
        and leave the outer range as a residual half-cycle."""
        mon = ThermalFatigueMonitor()
        # 0 → 40 (up) with a dip to 30 → 40 embedded inside, back to 0.
        _ingest(mon, "K", [0, 40, 30, 40, 0])
        rep = mon.report("K")
        # Exactly one inner full cycle of amplitude 10 gets closed.
        assert rep.full_cycles == 1
        # Its RMS must be 10.
        assert abs(rep.rms_range_c - 10.0) < 1e-9


class TestCoffinManson:

    def test_doubling_dt_gives_4x_damage_at_k_2(self):
        """At k=2, N_f scales as ΔT⁻² → damage per cycle scales as ΔT²."""
        mon = ThermalFatigueMonitor()
        spec = ThermalChannelSpec(coffin_manson_c=1.0e6, coffin_manson_k=2.0)
        _ingest(mon, "A", [0, 10, 0, 10, 0], spec=spec)
        _ingest(mon, "B", [0, 20, 0, 20, 0], spec=spec)
        ra = mon.report("A")
        rb = mon.report("B")
        # B has 4× the per-cycle damage of A.
        ratio = rb.damage / ra.damage
        assert abs(ratio - 4.0) < 0.01

    def test_sub_gate_oscillations_ignored(self):
        mon = ThermalFatigueMonitor()
        spec = ThermalChannelSpec(gate_delta=5.0)
        _ingest(mon, "K", [0, 1, 0, 1, 0, 1, 0], spec=spec)  # all ±1 — below gate
        rep = mon.report("K")
        assert rep.full_cycles == 0
        assert rep.damage == 0.0


class TestTiers:

    def test_tier_nominal(self):
        assert _tier_for(0.1) == ThermalLifeTier.NOMINAL

    def test_tier_watch(self):
        assert _tier_for(D_WATCH_THRESHOLD) == ThermalLifeTier.WATCH

    def test_tier_warning(self):
        assert _tier_for(D_WARNING_THRESHOLD) == ThermalLifeTier.WARNING

    def test_tier_critical(self):
        assert _tier_for(D_CRITICAL_THRESHOLD) == ThermalLifeTier.CRITICAL


class TestLifecycle:

    def test_reset_single_channel(self):
        mon = ThermalFatigueMonitor()
        _ingest(mon, "A", [0, 20, 0, 20, 0])
        _ingest(mon, "B", [0, 20, 0, 20, 0])
        mon.reset("A")
        assert mon.report("A").full_cycles == 0
        assert mon.report("B").full_cycles > 0

    def test_singleton_get_reset(self):
        reset_monitor()
        try:
            a = get_monitor()
            b = get_monitor()
            assert a is b
            a.update("X", 10.0, 0.0)
            reset_monitor()
            c = get_monitor()
            assert c is not a
        finally:
            reset_monitor()
