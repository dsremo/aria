"""Tests for backend wave 5: comms budget, agriculture, auto-tick, scheduler."""

from __future__ import annotations

import time

import pytest

from aria.simulator.agriculture_yield import (
    AgricultureYieldState, CROPS, get_agriculture, reset_agriculture,
)
from aria.simulator.auto_tick import AutoTickRunner
from aria.simulator.comms_budget import (
    CommsBudgetState, MODULATION_LADDER, get_comms_budget, reset_comms_budget,
)
from aria.simulator.event_scheduler import (
    EventScheduler, ScheduledEvent, get_scheduler, reset_scheduler,
)


# ── Comms budget ────────────────────────────────────────────────

class TestCommsBudget:

    def test_default_no_distance_no_delay(self):
        reset_comms_budget()
        # Reset trajectory state too — earlier tests may have left
        # position_ly populated, polluting this baseline assertion.
        from aria.simulator.trajectory_state import reset_trajectory_state
        reset_trajectory_state()
        c = get_comms_budget()
        c.tick(60.0)
        # BUG-034 fix (2026-04-24): zero distance now produces zero delay.
        # The 1 Gm floor was previously polluting the displayed delay
        # ("DISTANCE = 0.0 ly · LIGHT DELAY = 3.3 s" was contradictory).
        # The floor is still applied internally for the Friis path-loss
        # denominator (see comms_budget.py:116) but does NOT affect the
        # exposed one_way_delay_s.
        assert c.one_way_delay_s == 0.0

    def test_distance_increases_delay(self):
        from aria.simulator.trajectory_state import (
            get_trajectory_state, reset_trajectory_state,
        )
        reset_trajectory_state()
        reset_comms_budget()
        ts = get_trajectory_state()
        ts.position_ly = 1.0      # 1 ly out
        c = get_comms_budget()
        c.tick(60.0)
        # 1 ly delay = 1 yr light-time = ~3.16e7 s
        assert 3e7 < c.one_way_delay_s < 4e7

    def test_modulation_steps_down_with_distance(self):
        from aria.simulator.trajectory_state import (
            get_trajectory_state, reset_trajectory_state,
        )
        reset_trajectory_state()
        reset_comms_budget()
        ts = get_trajectory_state()
        c = get_comms_budget()
        ts.position_ly = 0.001
        c.tick(60.0)
        snr_close = c.snr_db
        ts.position_ly = 4.0
        c.tick(60.0)
        snr_far = c.snr_db
        assert snr_far < snr_close

    def test_queue_message_assigns_id(self):
        reset_comms_budget()
        m1 = get_comms_budget().queue_message("hello", 1024)
        m2 = get_comms_budget().queue_message("world", 2048)
        assert m1.msg_id != m2.msg_id

    def test_to_dict_shape(self):
        reset_comms_budget()
        d = get_comms_budget().to_dict()
        for k in ("link", "config", "queue", "stats"):
            assert k in d


# ── Agriculture yield ───────────────────────────────────────────

class TestAgriculture:

    def test_all_crops_initialised(self):
        reset_agriculture()
        a = get_agriculture()
        for cid in CROPS:
            assert cid in a.crops

    def test_lettuce_harvests_first(self):
        """Lettuce has 28-day cycle, fastest crop — should harvest before 30 days."""
        reset_agriculture()
        a = get_agriculture()
        for _ in range(30):
            a.tick(86400.0)        # 30 daily ticks
        assert a.crops["lettuce"].cumulative_yield_kg > 0
        assert a.crops["wheat"].cumulative_yield_kg == 0   # 80-day cycle, not yet

    def test_failure_drops_yield_modifier(self):
        reset_agriculture()
        a = get_agriculture()
        a.trigger_failure("lettuce", "led_outage")
        assert a.crops["lettuce"].yield_modifier == pytest.approx(0.1)
        a.restore_crop("lettuce")
        assert a.crops["lettuce"].yield_modifier == 1.0

    def test_food_store_balance_over_year(self):
        """1 year of nominal ops with crew metabolic frac = 1 → store should
        not run out (40 000 m² nominal yield easily covers 1000 crew)."""
        from aria.simulator.mission_phases import Phase, get_phase_controller
        get_phase_controller().current = Phase.CRUISE
        reset_agriculture()
        a = get_agriculture()
        for _ in range(365):
            a.tick(86400.0)
        # Some food consumed but not exhausted
        assert a.food_store_kg >= 0
        assert a.total_kcal_consumed > 0

    def test_to_dict_shape(self):
        reset_agriculture()
        d = get_agriculture().to_dict()
        for k in ("total_area_m2", "crew_size", "food_store_kg", "crops", "totals"):
            assert k in d
        assert len(d["crops"]) == len(CROPS)


# ── Auto-tick ───────────────────────────────────────────────────

class TestAutoTick:

    def test_starts_and_stops(self):
        runner = AutoTickRunner()
        runner.start(speed_factor=1000.0, wall_interval_s=0.1)
        time.sleep(0.4)
        st1 = runner.to_dict()
        assert st1["running"]
        assert st1["tick_count"] >= 1
        runner.stop()
        st2 = runner.to_dict()
        assert not st2["running"]

    def test_change_speed_idempotent(self):
        runner = AutoTickRunner()
        runner.start(speed_factor=10.0)
        runner.set_speed(100.0)
        st = runner.to_dict()
        assert st["speed_factor"] == 100.0
        runner.stop()

    def test_repeated_start_does_not_double(self):
        runner = AutoTickRunner()
        runner.start(speed_factor=10.0)
        runner.start(speed_factor=20.0)   # should just update speed, not spawn second thread
        st = runner.to_dict()
        assert st["running"]
        assert st["speed_factor"] == 20.0
        runner.stop()


# ── Event scheduler ─────────────────────────────────────────────

class TestEventScheduler:

    def test_schedule_returns_id(self):
        reset_scheduler()
        s = get_scheduler()
        evt = s.schedule(fire_at_yr=5.0, kind="note", label="halfway check")
        assert evt.event_id.startswith("evt_")
        assert not evt.fired

    def test_unknown_kind_raises(self):
        reset_scheduler()
        with pytest.raises(ValueError):
            get_scheduler().schedule(fire_at_yr=1.0, kind="bogus", label="x")

    def test_events_fire_at_or_after_target_time(self):
        from aria.simulator.mission_phases import get_phase_controller
        reset_scheduler()
        get_phase_controller().elapsed_yr = 0.0
        s = get_scheduler()
        s.schedule(fire_at_yr=0.5, kind="note", label="early")
        s.schedule(fire_at_yr=2.0, kind="note", label="late")
        # Advance the phase controller's clock
        get_phase_controller().elapsed_yr = 1.0
        s.tick(60.0)
        events = s.events
        assert events[0].fired and events[0].label == "early"
        assert not events[1].fired

    def test_cancel_pending(self):
        reset_scheduler()
        s = get_scheduler()
        e = s.schedule(fire_at_yr=10.0, kind="note", label="future")
        assert s.cancel(e.event_id)
        assert e not in s.events

    def test_failure_event_actually_triggers(self):
        from aria.simulator.bearing_dynamics import (
            BearingMode, get_bearing_state, reset_bearing_state,
        )
        from aria.simulator.mission_phases import get_phase_controller
        reset_bearing_state()
        reset_scheduler()
        get_phase_controller().elapsed_yr = 0.0
        s = get_scheduler()
        s.schedule(fire_at_yr=0.5, kind="failure", label="trip maglev",
                   payload={"scenario_id": "maglev_trip"})
        get_phase_controller().elapsed_yr = 1.0
        s.tick(60.0)
        # Bearing should now be in roller mode
        assert get_bearing_state().mode == BearingMode.ROLLER

    def test_to_dict_shape(self):
        reset_scheduler()
        d = get_scheduler().to_dict()
        for k in ("current_yr", "events", "stats"):
            assert k in d
