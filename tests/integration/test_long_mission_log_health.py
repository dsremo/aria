"""Long-mission log-health regression test.

Unit tests exercise each subsystem for a handful of ticks, which means
spam bugs (publishing the same event every tick instead of once-per-edge)
routinely slip through. Operators only noticed `propulsion.thermal.hull_overtemp`
firing ~20 000 times during a live 5 sim-yr run.

This test autoruns a multi-year mission and asserts the bus stays quiet.
If any topic fires more than a threshold rate per sim-yr the test fails
and points at the offending topic — forcing the owning subsystem to add
a one-shot gate / hysteresis the way propulsion_thermal, agriculture_yield,
and fuel_tracker already do.

Threshold rationale:
  * Tick debug events ("tick.advanced") can fire every substep — excluded.
  * True semantic events (impacts, transitions, alarms) should fire on
    state-change edges, i.e. at most O(1) per mission-phase per year.
  * 10× per sim-yr is the pragmatic spam ceiling the BACKLOG calls out.
"""

from __future__ import annotations

import pytest

from aria.simulator.event_bus import get_event_bus
from aria.simulator.mission_phases import Phase, get_phase_controller
from aria.simulator.tick_engine import get_tick_engine, reset_tick_engine


# Topics that are legitimately high-volume and don't count against spam:
#   tick.advanced — per-substep bookkeeping, always one-per-tick by design
#   tick.subsystem_error — if this spams, the real bug is elsewhere
#   bus.subscriber_error — same: downstream subscriber failure
_HIGH_VOLUME_ALLOWLIST = {
    "tick.advanced",
    "tick.subsystem_error",
    "bus.subscriber_error",
}

# Per-severity spam ceilings (fires per sim-yr).
#   critical — should fire on a real edge; >5/yr means the gate is missing
#              (this is the class of bug hull_overtemp was — one per tick
#              while the condition held true).
#   warning  — stochastic hazards (SEU halts, throttle events) legitimately
#              fire per event, so the ceiling is looser.
#   info / debug — narrative fodder (harvests, phase changes) is naturally
#                  high volume; we don't assert on these counts.
_CEILING_PER_SIM_YR = {
    "critical": 5,
    "warning":  50,
}


def _register_all_subsystems() -> None:
    """Mirror web_dashboard._lazy_register_subsystems so the test runs
    the same tick graph an operator hits in production."""
    import importlib

    engine = get_tick_engine()
    modules = [
        ("computing_radiation", "aria.simulator.computing_radiation"),
        ("eclss_contaminants",  "aria.simulator.eclss_contaminants"),
        ("bearing_dynamics",    "aria.simulator.bearing_dynamics"),
        ("propulsion_thermal",  "aria.simulator.propulsion_thermal"),
        ("power_tracker",       "aria.simulator.power_tracker"),
        ("trajectory_state",    "aria.simulator.trajectory_state"),
        ("fuel_tracker",        "aria.simulator.fuel_tracker"),
        ("crew_health",         "aria.simulator.crew_health"),
        ("comms_budget",        "aria.simulator.comms_budget"),
        ("agriculture_yield",   "aria.simulator.agriculture_yield"),
        ("event_scheduler",     "aria.simulator.event_scheduler"),
        ("hull_damage",         "aria.simulator.hull_damage"),
        ("random_events",       "aria.simulator.random_events"),
        ("mission_objectives",  "aria.simulator.mission_objectives"),
        ("crew_schedule",       "aria.simulator.crew_schedule"),
        ("repair_queue",        "aria.simulator.repair_queue"),
    ]
    for name, modpath in modules:
        if name not in engine.registered_names():
            importlib.import_module(modpath).register_with_tick_engine()


@pytest.fixture
def fresh_sim():
    """Give each test a clean bus + phase + tick engine + subsystem singletons."""
    reset_tick_engine()

    # Reset module singletons so pre-existing state doesn't leak into the run.
    from aria.simulator import (
        trajectory_state,
        fuel_tracker,
        propulsion_thermal,
        agriculture_yield,
        crew_health,
        power_tracker,
        hull_damage,
    )
    for mod, fn in (
        (trajectory_state,    "reset_trajectory_state"),
        (fuel_tracker,        "reset_fuel_inventory"),
        (propulsion_thermal,  "reset_propulsion_thermal"),
    ):
        if hasattr(mod, fn):
            getattr(mod, fn)()

    phase = get_phase_controller()
    phase.current = Phase.PRELAUNCH
    phase.elapsed_yr = 0.0
    phase.history.clear()

    bus = get_event_bus()
    bus.clear_history()

    # Widen the ring buffer so a 5-yr run doesn't truncate — the ring
    # defaults to 512 events, but a mission in CRUISE can easily publish
    # more than that in milestone events + random events.
    bus._history = type(bus._history)(maxlen=10_000)

    yield

    reset_tick_engine()


def _advance(years: float, substep_s: float = 3600.0 * 24.0 * 30.0) -> None:
    """Advance the tick engine by `years`, using a 30-day substep.
    Mirrors the production adaptive cap for long-coast missions."""
    dt_s = years * 365.25 * 24 * 3600
    engine = get_tick_engine()
    prev_cap = engine.MAX_SUBSTEP_S
    engine.MAX_SUBSTEP_S = substep_s
    try:
        engine.advance(dt_s)
    finally:
        engine.MAX_SUBSTEP_S = prev_cap


# ────────────────────────────────────────────────────────────────────

def test_bus_health_snapshot_shape(fresh_sim):
    """Sanity check the health() return shape before running the heavy sim."""
    bus = get_event_bus()
    bus.publish("unit.test", severity="info", source="test", sim_time_yr=0.0)
    snap = bus.health()
    assert snap["total_events"] >= 1
    assert "topics" in snap and "severity" in snap
    assert "top_topics" in snap and isinstance(snap["top_topics"], list)
    assert "spammed_topics" in snap and isinstance(snap["spammed_topics"], list)
    assert "history_size" in snap


def test_bus_health_windowed_filter(fresh_sim):
    """window_sim_yr should only count events within the trailing window."""
    bus = get_event_bus()
    bus.publish("old.event", sim_time_yr=0.0, source="test")
    bus.publish("recent.event", sim_time_yr=5.0, source="test")
    snap = bus.health(window_sim_yr=1.0)
    assert "recent.event" in snap["topics"]
    assert "old.event" not in snap["topics"]


def test_5yr_cruise_does_not_spam(fresh_sim):
    """Coast 5 sim-years in CRUISE and assert no critical topic fires
    more than 5×/yr and no warning topic more than 50×/yr. Catches the
    class of bug where a subsystem publishes on every tick while some
    condition holds instead of on the edge — e.g. the hull_overtemp
    spam that motivated this test."""
    _register_all_subsystems()

    phase = get_phase_controller()
    # Force straight into CRUISE so the 5-yr advance is a long coast.
    phase.transition(Phase.BOOST)
    phase.transition(Phase.CRUISE)

    _advance(years=5.0)

    bus = get_event_bus()
    with bus._lock:
        events = list(bus._history)
    window_yr = 5.0
    if events:
        max_t = max(e.sim_time_yr for e in events)
        events = [e for e in events if e.sim_time_yr >= max_t - window_yr]

    # Count (topic, severity) pairs so we can apply per-severity ceilings.
    from collections import Counter
    per_topic_sev: Counter = Counter((e.topic, e.severity) for e in events)

    offenders = {}
    for (topic, severity), count in per_topic_sev.items():
        if topic in _HIGH_VOLUME_ALLOWLIST:
            continue
        ceiling = _CEILING_PER_SIM_YR.get(severity)
        if ceiling is None:
            continue  # info / debug — unchecked
        if count > ceiling * window_yr:
            offenders[f"{topic}[{severity}]"] = count

    snap = bus.health(window_sim_yr=window_yr)
    assert not offenders, (
        f"Event spam detected over {window_yr:.1f} sim-yr "
        f"(critical >5/yr, warning >50/yr): {offenders}. "
        f"Top topics overall: {snap['top_topics'][:5]}"
    )


def test_5yr_cruise_history_not_saturated(fresh_sim):
    """A healthy ring buffer should still have some headroom after 5 yr.
    If it's 100% full of a single topic, an unbounded publisher is leaking."""
    _register_all_subsystems()
    phase = get_phase_controller()
    phase.transition(Phase.BOOST)
    phase.transition(Phase.CRUISE)

    _advance(years=5.0)

    snap = get_event_bus().health()
    if snap["total_events"] >= snap["history_size"]:
        # Ring is full — check that the dominant topic is a legitimate
        # high-volume one (tick.advanced) rather than a rogue semantic event.
        top_topic, top_count = snap["top_topics"][0]
        assert top_topic in _HIGH_VOLUME_ALLOWLIST, (
            f"Ring saturated by non-allowlisted topic {top_topic!r} "
            f"({top_count} events). Add a gate in the publishing subsystem."
        )
