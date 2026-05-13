"""Tests for aria.simulator.engine — SimulatorState, SimulatorTimeline, SimulatorEngine.

Covers:
  - SimulatorState construction and serialization
  - SimulatorTimeline append/seek/step/range/trajectory
  - SimulatorEvent data class
  - TickResolution enum values
  - SimulatorEngine static helpers (health_to_status, food_status, compute_direction)
"""

from __future__ import annotations

import math

import pytest

from aria.simulator.engine import (
    SimulatorEngine,
    SimulatorEvent,
    SimulatorState,
    SimulatorTimeline,
    SubsystemSnapshot,
    TickResolution,
)
from aria.simulator.targets import STAR_CATALOG


# ── TickResolution ──────────────────────────────────────────────────


class TestTickResolution:

    def test_year_resolution(self):
        assert TickResolution.YEAR.years_per_tick == 1.0

    def test_month_resolution(self):
        assert abs(TickResolution.MONTH.years_per_tick - 1.0 / 12.0) < 1e-9

    def test_day_resolution(self):
        assert abs(TickResolution.DAY.years_per_tick - 1.0 / 365.25) < 1e-9


# ── SimulatorState ──────────────────────────────────────────────────


class TestSimulatorState:

    def test_default_construction(self):
        state = SimulatorState()
        assert state.position_3d == [0.0, 0.0, 0.0]
        assert state.crew_count == 4
        assert state.ship_survived is True
        assert state.phase == "PRE_LAUNCH"
        assert state.hull_integrity == 1.0

    def test_to_dict_returns_expected_keys(self):
        state = SimulatorState(
            mission_time_years=10.0,
            crew_count=50,
            hull_integrity=0.85,
        )
        d = state.to_dict()
        assert isinstance(d, dict)
        assert d["mission_time_years"] == 10.0
        assert d["crew_count"] == 50
        assert d["hull_integrity"] == 0.85
        assert "position_3d" in d
        assert "velocity_3d" in d
        assert "subsystems" in d

    def test_to_dict_subsystems_serialized(self):
        state = SimulatorState()
        state.subsystems["power"] = SubsystemSnapshot(
            name="power", health=0.9, status="NOMINAL",
        )
        d = state.to_dict()
        assert "power" in d["subsystems"]
        assert d["subsystems"]["power"]["health"] == 0.9


# ── SimulatorEvent ──────────────────────────────────────────────────


class TestSimulatorEvent:

    def test_event_to_dict(self):
        ev = SimulatorEvent(
            mission_year=25.0,
            category="HULL",
            severity="WARNING",
            description="Micrometeorite impact",
            subsystem="shield",
            source="defense",
            impact={"hull_loss": 0.01},
        )
        d = ev.to_dict()
        assert d["mission_year"] == 25.0
        assert d["severity"] == "WARNING"
        assert d["impact"]["hull_loss"] == 0.01


# ── SimulatorTimeline ───────────────────────────────────────────────


class TestSimulatorTimeline:

    @pytest.fixture
    def populated_timeline(self) -> SimulatorTimeline:
        tl = SimulatorTimeline()
        for yr in [0.0, 1.0, 2.0, 5.0, 10.0]:
            s = SimulatorState(
                mission_time_years=yr,
                position_3d=[yr * 0.1, 0.0, 0.0],
                hull_integrity=1.0 - yr * 0.01,
            )
            tl.append(s)
        return tl

    def test_empty_timeline_properties(self):
        tl = SimulatorTimeline()
        assert tl.length == 0
        assert tl.years == []
        assert tl.first_year == 0.0
        assert tl.last_year == 0.0
        assert tl.current is None

    def test_append_and_length(self, populated_timeline: SimulatorTimeline):
        assert populated_timeline.length == 5
        assert populated_timeline.years == [0.0, 1.0, 2.0, 5.0, 10.0]
        assert populated_timeline.first_year == 0.0
        assert populated_timeline.last_year == 10.0

    def test_seek_exact(self, populated_timeline: SimulatorTimeline):
        state = populated_timeline.seek_exact(5.0)
        assert state is not None
        assert state.mission_time_years == 5.0

    def test_seek_exact_missing_returns_none(self, populated_timeline: SimulatorTimeline):
        assert populated_timeline.seek_exact(3.0) is None

    def test_seek_interpolates_to_nearest_before(self, populated_timeline: SimulatorTimeline):
        state = populated_timeline.seek(3.0)
        assert state is not None
        # Should find year 2.0 (closest at-or-before 3.0)
        assert state.mission_time_years == 2.0

    def test_step_forward_backward(self, populated_timeline: SimulatorTimeline):
        populated_timeline.seek(0.0)
        assert populated_timeline.cursor == 0

        s1 = populated_timeline.step_forward()
        assert s1 is not None
        assert s1.mission_time_years == 1.0

        s0 = populated_timeline.step_backward()
        assert s0 is not None
        assert s0.mission_time_years == 0.0

        # Step backward at start returns None
        assert populated_timeline.step_backward() is None

    def test_range_filtering(self, populated_timeline: SimulatorTimeline):
        subset = populated_timeline.range(1.0, 5.0)
        assert len(subset) == 3
        years_in_range = [s.mission_time_years for s in subset]
        assert years_in_range == [1.0, 2.0, 5.0]

    def test_get_trajectory(self, populated_timeline: SimulatorTimeline):
        traj = populated_timeline.get_trajectory()
        assert len(traj) == 5
        assert traj[0] == [0.0, 0.0, 0.0]
        assert abs(traj[4][0] - 1.0) < 1e-6  # year 10 * 0.1

    def test_get_metric_series(self, populated_timeline: SimulatorTimeline):
        series = populated_timeline.get_metric_series("hull_integrity")
        assert len(series) == 5
        # year 0 -> 1.0, year 10 -> 0.9
        assert series[0] == (0.0, 1.0)
        assert abs(series[4][1] - 0.9) < 1e-6

    def test_export_json(self, populated_timeline: SimulatorTimeline):
        exported = populated_timeline.export_json()
        assert len(exported) == 5
        assert all(isinstance(d, dict) for d in exported)
        assert exported[0]["mission_time_years"] == 0.0

    def test_clear(self, populated_timeline: SimulatorTimeline):
        populated_timeline.clear()
        assert populated_timeline.length == 0
        assert populated_timeline.cursor == -1


# ── SimulatorEngine static helpers ──────────────────────────────────


class TestEngineStaticHelpers:

    def test_health_to_status_nominal(self):
        assert SimulatorEngine._health_to_status(0.9) == "NOMINAL"

    def test_health_to_status_warning(self):
        assert SimulatorEngine._health_to_status(0.5) == "WARNING"

    def test_health_to_status_critical(self):
        assert SimulatorEngine._health_to_status(0.2) == "CRITICAL"

    def test_health_to_status_offline(self):
        assert SimulatorEngine._health_to_status(0.05) == "OFFLINE"

    def test_food_status_nominal(self):
        s = SimulatorState(food_reserves_kg=8000.0, water_liters=30000.0)
        assert SimulatorEngine._food_status(s) == "NOMINAL"

    def test_food_status_warning(self):
        s = SimulatorState(food_reserves_kg=3000.0, water_liters=10000.0)
        assert SimulatorEngine._food_status(s) == "WARNING"

    def test_food_status_critical(self):
        s = SimulatorState(food_reserves_kg=500.0, water_liters=2000.0)
        assert SimulatorEngine._food_status(s) == "CRITICAL"


# ── SimulatorEngine construction (no subsystem init) ────────────────


class TestEngineConstruction:

    def test_engine_default_target(self):
        engine = SimulatorEngine()
        assert engine.target.name == "100_ly_target"
        assert engine.is_initialized is False
        assert engine.is_paused is False
        assert engine.tick_count == 0
        assert engine.mission_year == 0.0

    def test_engine_with_explicit_target(self):
        target = STAR_CATALOG["alpha_centauri"]
        engine = SimulatorEngine(target=target, velocity_c=0.1, crew_size=50)
        state = engine.state
        assert state.target_name == "alpha_centauri"
        assert state.crew_count == 50
        assert abs(state.velocity_scalar_c - 0.1) < 1e-9

    def test_engine_pause_resume(self):
        engine = SimulatorEngine()
        engine.pause()
        assert engine.is_paused is True
        engine.resume()
        assert engine.is_paused is False

    def test_step_without_init_raises(self):
        engine = SimulatorEngine()
        with pytest.raises(RuntimeError, match="initialize"):
            engine.step()

    def test_get_summary_returns_dict(self):
        engine = SimulatorEngine()
        summary = engine.get_summary()
        assert isinstance(summary, dict)
        assert "target" in summary
        assert "mission_year" in summary
        assert "ship_survived" in summary
        assert summary["ship_survived"] is True
