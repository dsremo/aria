"""Tests for V3-G2: reaction-wheel life monitor (Miner's Rule).

Validates:
 1. First sample seeds state (no accumulation)
 2. Reversal count increments on sign change (positive → negative)
 3. Reversal count increments on negative → positive
 4. No reversal on same-sign samples
 5. Run seconds accumulate while RPM non-zero
 6. No run seconds when wheel idle (rpm=0 throughout interval)
 7. High-RPM seconds accumulate when previous sample above threshold
 8. damage_reversals = count / N_f
 9. damage_run_hours = hours / N_f_hours
10. damage_overall = max of the two damage terms
11. Tier classification: NOMINAL / WATCH / WARNING / CRITICAL
12. report pre-sample: all zeros, tier NOMINAL
13. reset() clears state
14. Custom RWWheelSpec honoured
"""

from __future__ import annotations

import pytest

from aria.dsremo.detection.rw_life_monitor import (
    D_CRITICAL_THRESHOLD,
    D_WARNING_THRESHOLD,
    D_WATCH_THRESHOLD,
    LifeTier,
    RWLifeMonitor,
    RWWheelSpec,
    _tier_for,
)


class TestReversalCount:

    def test_first_sample_does_not_count_reversal(self):
        mon = RWLifeMonitor()
        mon.update("W", rpm=1000.0, epoch=0.0)
        rep = mon.report("W")
        assert rep.cumulative_reversals == 0

    def test_positive_to_negative_is_reversal(self):
        mon = RWLifeMonitor()
        mon.update("W", rpm=1000.0, epoch=0.0)
        mon.update("W", rpm=-500.0, epoch=1.0)
        assert mon.report("W").cumulative_reversals == 1

    def test_negative_to_positive_is_reversal(self):
        mon = RWLifeMonitor()
        mon.update("W", rpm=-500.0, epoch=0.0)
        mon.update("W", rpm=1000.0, epoch=1.0)
        assert mon.report("W").cumulative_reversals == 1

    def test_same_sign_no_reversal(self):
        mon = RWLifeMonitor()
        mon.update("W", rpm=1000.0, epoch=0.0)
        mon.update("W", rpm=2000.0, epoch=1.0)
        mon.update("W", rpm=500.0,  epoch=2.0)
        assert mon.report("W").cumulative_reversals == 0


class TestRunTime:

    def test_run_seconds_accumulate_on_nonzero_rpm(self):
        mon = RWLifeMonitor()
        mon.update("W", rpm=1000.0, epoch=0.0)
        mon.update("W", rpm=1200.0, epoch=60.0)   # 60 s interval
        rep = mon.report("W")
        assert abs(rep.cumulative_run_hours - 60.0 / 3600.0) < 1e-12

    def test_no_run_seconds_when_idle(self):
        mon = RWLifeMonitor()
        mon.update("W", rpm=0.0, epoch=0.0)
        mon.update("W", rpm=0.0, epoch=100.0)
        assert mon.report("W").cumulative_run_hours == 0.0


class TestHighRpmHours:

    def test_high_rpm_hours_accumulate_above_threshold(self):
        spec = RWWheelSpec(max_rpm=1000.0, high_rpm_fraction=0.80)  # threshold = 800
        mon = RWLifeMonitor()
        mon.update("W", rpm=900.0, epoch=0.0,   spec=spec)
        mon.update("W", rpm=500.0, epoch=60.0,  spec=spec)  # prev was high → accumulate
        mon.update("W", rpm=500.0, epoch=120.0, spec=spec)  # prev was low  → skip
        rep = mon.report("W", spec=spec)
        assert abs(rep.cumulative_high_rpm_hrs - 60.0 / 3600.0) < 1e-12


class TestMinerDamage:

    def test_damage_reversals_fraction(self):
        spec = RWWheelSpec(n_f_reversals=10, n_f_run_hours=1e9)
        mon  = RWLifeMonitor()
        # 3 reversals against budget of 10 → D = 0.3
        rpm_seq = [100, -100, 100, -100]
        for i, r in enumerate(rpm_seq):
            mon.update("W", rpm=float(r), epoch=float(i), spec=spec)
        rep = mon.report("W", spec=spec)
        assert abs(rep.damage_reversals - 0.3) < 1e-12

    def test_damage_run_hours_fraction(self):
        spec = RWWheelSpec(n_f_reversals=1_000_000, n_f_run_hours=1.0)  # 1 hr budget
        mon  = RWLifeMonitor()
        mon.update("W", rpm=1.0, epoch=0.0,    spec=spec)
        mon.update("W", rpm=1.0, epoch=1800.0, spec=spec)  # 0.5 hr elapsed
        rep = mon.report("W", spec=spec)
        assert abs(rep.damage_run_hours - 0.5) < 1e-9

    def test_damage_overall_is_max(self):
        spec = RWWheelSpec(n_f_reversals=10, n_f_run_hours=0.5)
        mon  = RWLifeMonitor()
        mon.update("W", rpm=1.0, epoch=0.0,    spec=spec)
        mon.update("W", rpm=1.0, epoch=3600.0, spec=spec)  # 1 hr → D_hours = 2.0
        rep = mon.report("W", spec=spec)
        assert rep.damage_overall == pytest.approx(2.0, abs=1e-9)


class TestTiers:

    def test_nominal_tier_low_damage(self):
        assert _tier_for(0.1) == LifeTier.NOMINAL

    def test_watch_tier(self):
        assert _tier_for(D_WATCH_THRESHOLD) == LifeTier.WATCH

    def test_warning_tier(self):
        assert _tier_for(D_WARNING_THRESHOLD) == LifeTier.WARNING

    def test_critical_tier(self):
        assert _tier_for(D_CRITICAL_THRESHOLD) == LifeTier.CRITICAL


class TestLifecycle:

    def test_report_before_any_samples(self):
        mon = RWLifeMonitor()
        rep = mon.report("NEW")
        assert rep.cumulative_reversals == 0
        assert rep.tier == LifeTier.NOMINAL

    def test_reset_single_wheel(self):
        mon = RWLifeMonitor()
        mon.update("W1", rpm=100.0, epoch=0.0)
        mon.update("W1", rpm=-100.0, epoch=1.0)
        mon.update("W2", rpm=100.0, epoch=0.0)
        mon.reset("W1")
        assert mon.report("W1").cumulative_reversals == 0
        # W2 unaffected.
        assert "W2" in mon._states
