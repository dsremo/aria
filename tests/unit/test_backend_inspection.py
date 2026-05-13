"""Tests for the nut-and-bolt backend inspection layer.

Covers the four modules added to answer the user's asks:
  * dependency_graph   — "how parts interact"
  * mission_phases     — "how it travels"
  * startup_sequence   — "how it starts"
  * part_inspector     — "see individual parts to check"
"""

from __future__ import annotations

import pytest

from aria.digital_twin.dependency_graph import (
    DependencyGraph, get_dependency_graph,
)
from aria.simulator.mission_phases import (
    MissionPhaseController, Phase, PHASE_SPECS, get_phase_controller,
)
from aria.simulator.startup_sequence import (
    StartupController, StepStatus, default_startup_steps,
    get_startup_controller, reset_startup_controller,
)
from aria.simulator.part_inspector import (
    PartSnapshot, inspect_all, inspect_part, list_parts, snapshot_to_dict,
)


# ── Dependency graph ──────────────────────────────────────────────

class TestDependencyGraph:
    def test_graph_nonempty(self):
        g = get_dependency_graph()
        assert len(g.nodes()) > 20, f"Graph has only {len(g.nodes())} nodes"
        assert len(g.edges) > 40

    def test_reactor_has_dependents(self):
        g = get_dependency_graph()
        fed = g.feeds("reactor_engine")
        # power_distribution + magnetic_nozzle + possibly reactors need feed data
        fed_srcs = {e.src for e in fed}
        assert "power_distribution" in fed_srcs
        assert "magnetic_nozzle" in fed_srcs

    def test_reactor_failure_cascade_is_large(self):
        """Killing the reactor should take down power + most loads downstream."""
        g = get_dependency_graph()
        doomed = g.failure_cascade("reactor_engine", critical_only=True)
        # Should cascade through power_distribution to many parts
        assert "power_distribution" in doomed
        assert len(doomed) >= 8, f"Reactor loss only cascaded to {len(doomed)} parts"

    def test_hab_module_depends_on_ring_and_eclss(self):
        g = get_dependency_graph()
        deps = {e.dst for e in g.depends_on("hab_module_0")}
        assert "habitat_ring" in deps
        assert "eclss" in deps

    def test_all_upstream_of_avionics(self):
        """The set of things `avionics` (transitively) depends on."""
        g = get_dependency_graph()
        upstream = g.all_upstream("avionics")
        # avionics → power_distribution → reactor_engine → ...
        assert "power_distribution" in upstream
        assert "reactor_engine" in upstream

    def test_to_dict_structure(self):
        d = get_dependency_graph().to_dict()
        assert set(d.keys()) == {"nodes", "edges"}
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)
        assert {"src", "dst", "kind", "critical", "note"} <= set(d["edges"][0].keys())


# ── Mission phases ────────────────────────────────────────────────

class TestMissionPhases:
    def test_default_phase_is_prelaunch(self):
        ctl = MissionPhaseController()
        assert ctl.current == Phase.PRELAUNCH

    def test_legal_transition(self):
        ctl = MissionPhaseController()
        ctl.transition(Phase.BOOST)
        assert ctl.current == Phase.BOOST

    def test_illegal_transition_raises(self):
        ctl = MissionPhaseController()
        with pytest.raises(ValueError):
            ctl.transition(Phase.ARRIVAL)   # can't jump from PRELAUNCH→ARRIVAL

    def test_emergency_transition_from_any_phase(self):
        ctl = MissionPhaseController()
        ctl.transition(Phase.BOOST)
        ctl.transition(Phase.EMERGENCY)
        assert ctl.current == Phase.EMERGENCY

    def test_force_transition_bypasses_rules(self):
        ctl = MissionPhaseController()
        ctl.transition(Phase.ARRIVAL, force=True)
        assert ctl.current == Phase.ARRIVAL

    def test_tick_accumulates_time(self):
        # R7 refactor (2026-04-24): MissionPhaseController.tick() no longer
        # owns the elapsed-yr counter — it's a property over the process-wide
        # MissionClock, advanced by MissionClock.advance(). The phase
        # controller's tick() only checks for auto-transitions.
        from aria.core.mission_clock import get_mission_clock
        clock = get_mission_clock()
        clock.reset(to_yr=0.0)
        ctl = MissionPhaseController()
        clock.advance(2.0)
        ctl.tick(2.0)
        clock.advance(3.5)
        ctl.tick(3.5)
        assert abs(ctl.elapsed_yr - 5.5) < 1e-6

    def test_history_tracked(self):
        ctl = MissionPhaseController()
        ctl.tick(0.5)
        ctl.transition(Phase.BOOST)
        ctl.tick(5.0)
        ctl.transition(Phase.CRUISE)
        assert len(ctl.history) == 2
        assert ctl.history[0][1] == Phase.PRELAUNCH
        assert ctl.history[0][2] == Phase.BOOST

    def test_all_phases_have_specs(self):
        for phase in Phase:
            assert phase in PHASE_SPECS
            spec = PHASE_SPECS[phase]
            assert 0.0 <= spec.power_load_frac <= 1.0
            assert 0.0 <= spec.thermal_load_frac <= 1.0
            assert spec.nominal_duration_yr >= 0.0

    def test_to_dict_serialises(self):
        ctl = MissionPhaseController()
        d = ctl.to_dict()
        assert d["current_phase"] == "prelaunch"
        assert "spec" in d
        assert d["nominal_next"] == "boost"


# ── Startup sequence ──────────────────────────────────────────────

class TestStartupSequence:
    def test_default_sequence_has_steps(self):
        steps = default_startup_steps()
        assert len(steps) > 10

    def test_sequence_covers_all_major_subsystems(self):
        subs = {s.subsystem for s in default_startup_steps()}
        for required in ("power", "avionics", "reactor", "thermal", "eclss", "habitat"):
            assert required in subs, f"Startup misses subsystem {required}"

    def test_deterministic_sequence_completes(self):
        """Force every step to always succeed → sequence must complete cleanly."""
        ctl = StartupController()
        for s in ctl.steps:
            s.success_prob = 1.0
        # 500 ticks of 1 day each — enough to cover the longest step (24 hr)
        for _ in range(500):
            ctl.tick(1000.0)
            if ctl.complete:
                break
        assert ctl.complete
        assert not ctl.aborted
        assert all(s.status == StepStatus.SUCCESS for s in ctl.steps)

    def test_dependency_chain_enforced(self):
        """reactor_plasma_ignition must happen after reactor_magnet_ramp."""
        steps = default_startup_steps()
        ids = [s.id for s in steps]
        assert ids.index("reactor_magnet_ramp") < ids.index("reactor_plasma_ignition")
        ignition = next(s for s in steps if s.id == "reactor_plasma_ignition")
        assert "reactor_magnet_ramp" in ignition.depends_on

    def test_abort_halts_sequence(self):
        ctl = StartupController()
        for s in ctl.steps:
            s.success_prob = 1.0
        ctl.tick(50.0)    # start first step
        ctl.abort("test")
        assert ctl.aborted

    def test_reset_returns_fresh_controller(self):
        reset_startup_controller()
        ctl1 = get_startup_controller()
        ctl1.tick(50.0)
        reset_startup_controller()
        ctl2 = get_startup_controller()
        assert ctl2 is not ctl1
        assert all(s.status == StepStatus.PENDING for s in ctl2.steps)

    def test_to_dict_shape(self):
        d = get_startup_controller().to_dict()
        assert "steps" in d
        assert "progress_pct" in d
        assert isinstance(d["steps"], list)
        assert {"id", "label", "status", "duration_s"} <= set(d["steps"][0].keys())


# ── Part inspector ────────────────────────────────────────────────

class TestPartInspector:
    def test_list_includes_all_known_part_types(self):
        parts = list_parts()
        # Expect at least: hull_main, habitat_ring, reactor_engine + all arrays
        for required in ("hull_main", "habitat_ring", "reactor_engine",
                         "shield_layer_0", "shield_layer_6",
                         "hab_module_0", "hab_module_23",
                         "comm_antenna_0", "docking_port_0",
                         "radiator_array_0", "engine_bell_0",
                         "magnetic_nozzle", "bow_sensor_ring"):
            assert required in parts, f"Registry missing {required}"

    def test_inspect_unknown_part_returns_none(self):
        assert inspect_part("not_a_real_part") is None

    def test_inspect_reactor_full_shape(self):
        s = inspect_part("reactor_engine")
        assert s is not None
        assert isinstance(s, PartSnapshot)
        assert s.subsystem == "reactor"
        assert s.mass_kg > 0
        assert s.dimensions_m.get("radius") == 3.0
        assert len(s.sources) > 0

    def test_inspect_hab_module_has_ring_dep(self):
        s = inspect_part("hab_module_0")
        assert s is not None
        assert "habitat_ring" in s.depends_on

    def test_inspect_ring_has_hab_modules_as_feeds(self):
        s = inspect_part("habitat_ring")
        assert s is not None
        hab_feeds = [f for f in s.feeds if f.startswith("hab_module_")]
        assert len(hab_feeds) == 24

    def test_health_degrades_with_mission_time(self):
        # R7 refactor (2026-04-24): elapsed_yr lives on MissionClock, not
        # on the phase controller. Advance the clock directly.
        from aria.core.mission_clock import get_mission_clock
        clock = get_mission_clock()
        before = clock.elapsed_yr
        h0 = inspect_part("reactor_engine").health_pct
        clock.advance(10.0)      # 10 years
        h1 = inspect_part("reactor_engine").health_pct
        assert h1 < h0
        # Rewind
        clock.reset(to_yr=before)

    def test_inspect_all_works_for_every_listed_part(self):
        parts = list_parts()
        snaps = inspect_all()
        assert len(snaps) == len(parts)

    def test_snapshot_to_dict_is_json_serialisable(self):
        import json
        s = inspect_part("magnetic_nozzle")
        d = snapshot_to_dict(s)
        serialised = json.dumps(d)
        assert len(serialised) > 50
