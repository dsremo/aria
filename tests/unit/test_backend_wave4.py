"""Tests for backend wave 4: trajectory state, fuel tracker, crew health,
failure injector."""

from __future__ import annotations

import pytest

from aria.simulator.crew_health import (
    CrewHealthState, get_crew_health, reset_crew_health,
)
from aria.simulator.failure_injector import (
    SCENARIOS, list_scenarios, to_dict as failures_dict, trigger,
)
from aria.simulator.fuel_tracker import (
    FuelInventoryState, get_fuel_inventory, reset_fuel_inventory,
    PROPELLANT_PER_MAIN_TANK_KG,
)
from aria.simulator.trajectory_state import (
    TrajectoryState, get_trajectory_state, reset_trajectory_state,
)


# ── Trajectory state ────────────────────────────────────────────

class TestTrajectoryState:

    def test_default_target_moon(self):
        # BUG-016 (2026-04-24): default target flipped from "Alpha Centauri A"
        # to "Moon" so the walkthrough's "target=Moon" Alarm resolves
        # without the operator having to call /api/trajectory/set_target.
        reset_trajectory_state()
        s = get_trajectory_state()
        assert s.target == "Moon"
        # 384 400 km / (c·yr = 9.461e15 m) ≈ 4.06e-8 ly
        assert 3e-8 < s.distance_total_ly < 5e-8

    def test_set_target_changes_distance(self):
        reset_trajectory_state()
        s = get_trajectory_state()
        s.set_target("Sirius A")
        assert s.distance_total_ly > 8

    def test_unknown_target_raises(self):
        reset_trajectory_state()
        with pytest.raises(ValueError):
            get_trajectory_state().set_target("Made Up Star")

    def test_no_thrust_no_velocity_change(self):
        reset_trajectory_state()
        from aria.simulator.mission_phases import get_phase_controller, Phase
        get_phase_controller().current = Phase.PRELAUNCH
        s = get_trajectory_state()
        for _ in range(10):
            s.tick(60.0)
        assert s.velocity_m_s == 0.0
        assert s.position_ly == 0.0

    def test_boost_phase_accelerates(self):
        reset_trajectory_state()
        from aria.simulator.mission_phases import get_phase_controller, Phase
        get_phase_controller().current = Phase.BOOST
        s = get_trajectory_state()
        for _ in range(60):
            s.tick(3600.0)        # 60 hours
        assert s.velocity_m_s > 0
        assert s.cumulative_dv_m_s > 0
        assert s.cumulative_burn_s > 0

    def test_to_dict_shape(self):
        reset_trajectory_state()
        d = get_trajectory_state().to_dict()
        for k in ("target", "position_ly", "remaining_distance_ly", "velocity_m_s",
                  "beta", "propellant_remaining_kg", "config"):
            assert k in d


# ── Fuel tracker ────────────────────────────────────────────────

class TestFuelTracker:

    def test_three_main_tanks_plus_xenon(self):
        reset_fuel_inventory()
        f = get_fuel_inventory()
        assert {"main_tank_a", "main_tank_b", "main_tank_c", "rcs_xenon"} <= set(f.tanks.keys())

    def test_main_tanks_sized_per_fuel_budget(self):
        reset_fuel_inventory()
        f = get_fuel_inventory()
        for tid in ("main_tank_a", "main_tank_b", "main_tank_c"):
            assert abs(f.tanks[tid].capacity_kg - PROPELLANT_PER_MAIN_TANK_KG) < 1e-3

    def test_no_burn_at_prelaunch(self):
        reset_fuel_inventory()
        from aria.simulator.mission_phases import get_phase_controller, Phase
        get_phase_controller().current = Phase.PRELAUNCH
        f = get_fuel_inventory()
        f.tick(3600.0)
        assert f.main_burn_rate_kg_s == 0.0

    def test_burn_at_boost(self):
        reset_fuel_inventory()
        from aria.simulator.mission_phases import get_phase_controller, Phase
        get_phase_controller().current = Phase.BOOST
        f = get_fuel_inventory()
        f.tick(3600.0)
        # Each tank should have dropped by some amount
        for tid in ("main_tank_a", "main_tank_b", "main_tank_c"):
            assert f.tanks[tid].cumulative_drawn_kg > 0

    def test_to_dict_shape(self):
        reset_fuel_inventory()
        d = get_fuel_inventory().to_dict()
        assert "tanks" in d
        assert "summary" in d
        assert d["summary"]["main_fill_pct"] == pytest.approx(100.0, abs=0.1)


# ── Crew health ─────────────────────────────────────────────────

class TestCrewHealth:

    def test_baseline_at_start(self):
        reset_crew_health()
        c = get_crew_health()
        assert c.bone_density_pct == 100.0
        assert c.vo2max_pct == 100.0
        assert c.psych_cohesion_pct == 100.0

    def test_partial_g_protects_bones(self):
        """At 0.56 g, bone loss should be ~44 % of 0-g rate."""
        reset_crew_health()
        c = get_crew_health()
        c.manual_g_override = 0.56
        for _ in range(12):
            c.tick(30 * 24 * 3600.0)   # 12 months
        # 12 months at 0 g would lose ~12 % bone density; at 0.56 g should be ~5-7 %
        loss = 100.0 - c.bone_density_pct
        assert 4.0 < loss < 8.0, f"Bone loss {loss} not in expected 4-8 % range"

    def test_zero_g_aggressive_bone_loss(self):
        reset_crew_health()
        c = get_crew_health()
        c.manual_g_override = 0.0
        for _ in range(12):
            c.tick(30 * 24 * 3600.0)
        loss = 100.0 - c.bone_density_pct
        assert loss > 9.0, f"At 0 g expected >9 % loss in 1 yr, got {loss}"

    def test_to_dict_shape(self):
        reset_crew_health()
        d = get_crew_health().to_dict()
        assert "metrics" in d
        assert "bone_density_pct" in d["metrics"]
        assert "sources" in d


# ── Failure injector ────────────────────────────────────────────

class TestFailureInjector:

    def test_scenarios_registered(self):
        assert len(SCENARIOS) >= 5
        for s in list_scenarios():
            assert s.id and s.label and s.description

    def test_unknown_scenario_returns_error(self):
        r = trigger("nonexistent")
        assert "error" in r

    def test_maglev_trip_works(self):
        from aria.simulator.bearing_dynamics import (
            BearingMode, get_bearing_state, reset_bearing_state,
        )
        reset_bearing_state()
        assert get_bearing_state().mode == BearingMode.MAGNETIC
        r = trigger("maglev_trip")
        assert r["applied"] is True
        assert get_bearing_state().mode == BearingMode.ROLLER

    def test_eclss_scrubber_fault_drops_efficiency(self):
        from aria.simulator.eclss_contaminants import (
            get_eclss_contaminants, reset_eclss_contaminants,
        )
        reset_eclss_contaminants()
        assert get_eclss_contaminants().scrubber_efficiency_frac == 1.0
        trigger("eclss_scrubber_fault")
        assert get_eclss_contaminants().scrubber_efficiency_frac < 0.2

    def test_radiator_loss_halves_capacity(self):
        from aria.simulator.propulsion_thermal import (
            get_propulsion_thermal, reset_propulsion_thermal,
        )
        reset_propulsion_thermal()
        cap_before = get_propulsion_thermal().radiator_capacity_w
        trigger("radiator_loss")
        cap_after = get_propulsion_thermal().radiator_capacity_w
        assert cap_after == pytest.approx(cap_before * 0.5)

    def test_to_dict_lists_all(self):
        d = failures_dict()
        assert d["count"] >= 5
        assert all("id" in s and "label" in s and "severity" in s for s in d["scenarios"])

    def test_avionics_ecc_cascade_bumps_counters_and_emits_events(self):
        from aria.simulator.computing_radiation import (
            get_computing_radiation, reset_computing_radiation,
        )
        from aria.simulator.event_bus import get_event_bus
        reset_computing_radiation()
        cr = get_computing_radiation()
        halts0, escapes0 = cr.ecc_detect_only_halts, cr.ecc_escapes
        bus = get_event_bus()
        bus.clear_history()
        r = trigger("avionics_ecc_cascade")
        assert r["applied"] is True
        assert cr.ecc_detect_only_halts == halts0 + 8
        assert cr.ecc_escapes == escapes0 + 2
        topics = [e.topic for e in bus.recent(500)]
        assert topics.count("avionics.ecc_detect_only_halt") >= 8
        assert topics.count("avionics.ecc_escape") >= 2
