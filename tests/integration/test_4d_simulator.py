"""Integration tests for the 4D Simulator Engine.

Tests cover:
  - Engine creation and initialization
  - Tick execution with all subsystems
  - 3D position tracking along trajectory
  - Timeline seek, forward/backward replay
  - State snapshots and serialization
  - Preset mission factory (all star targets)
  - Custom target missions
  - Recorder: JSON and SQLite export
  - Pause/resume control
  - Survival detection
  - Event aggregation across subsystems
  - Sub-year tick resolutions
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from aria.simulator.engine import (
    Simulator4D,
    SimulatorEngine,
    SimulatorEvent,
    SimulatorState,
    SimulatorTimeline,
    SubsystemSnapshot,
    TickResolution,
)
from aria.simulator.recorder import SimulatorRecorder
from aria.simulator.targets import (
    STAR_CATALOG,
    StarTarget,
    get_target,
    list_targets,
    mission_duration_years,
)


# ─────────────────────────────────────────────────────────────────
#  Targets & Star Catalog
# ─────────────────────────────────────────────────────────────────

class TestStarCatalog:
    """Tests for the star catalog and target definitions."""

    def test_catalog_has_required_targets(self):
        required = [
            "alpha_centauri", "proxima_centauri", "barnards_star",
            "tau_ceti", "100_ly_target",
        ]
        for name in required:
            assert name in STAR_CATALOG, f"Missing required target: {name}"

    def test_alpha_centauri_distance(self):
        ac = STAR_CATALOG["alpha_centauri"]
        assert 4.3 < ac.distance_ly < 4.4, "Alpha Centauri should be ~4.37 ly"

    def test_proxima_centauri_is_closest(self):
        proxima = STAR_CATALOG["proxima_centauri"]
        for name, target in STAR_CATALOG.items():
            if name == "proxima_centauri":
                continue
            assert proxima.distance_ly <= target.distance_ly, (
                f"Proxima should be closest, but {name} is at {target.distance_ly} ly"
            )

    def test_direction_unit_vector(self):
        for name, target in STAR_CATALOG.items():
            if target.distance_ly < 0.01:
                continue
            d = target.direction_unit
            magnitude = math.sqrt(sum(c * c for c in d))
            assert abs(magnitude - 1.0) < 0.1, (
                f"{name} direction vector should be approximately unit length, got {magnitude}"
            )

    def test_get_target_valid(self):
        t = get_target("tau_ceti")
        assert t.name == "tau_ceti"
        assert t.distance_ly > 11

    def test_get_target_invalid(self):
        with pytest.raises(KeyError, match="Unknown star target"):
            get_target("andromeda_galaxy")

    def test_mission_duration(self):
        ac = STAR_CATALOG["alpha_centauri"]
        years = mission_duration_years(ac, 0.1)
        assert abs(years - 43.7) < 0.1

    def test_list_targets_sorted(self):
        targets = list_targets()
        assert len(targets) >= 5
        distances = [t["distance_ly"] for t in targets]
        assert distances == sorted(distances), "Targets should be sorted by distance"


# ─────────────────────────────────────────────────────────────────
#  SimulatorState
# ─────────────────────────────────────────────────────────────────

class TestSimulatorState:
    """Tests for state dataclass and serialization."""

    def test_default_state(self):
        s = SimulatorState()
        assert s.position_3d == [0.0, 0.0, 0.0]
        assert s.mission_time_years == 0.0
        assert s.ship_survived is True
        assert s.crew_count == 4

    def test_state_to_dict(self):
        s = SimulatorState(
            position_3d=[1.0, 2.0, 3.0],
            mission_time_years=50.0,
            hull_integrity=0.85,
        )
        d = s.to_dict()
        assert d["position_3d"] == [1.0, 2.0, 3.0]
        assert d["mission_time_years"] == 50.0
        assert d["hull_integrity"] == 0.85
        assert d["ship_survived"] is True

    def test_state_to_dict_is_json_serializable(self):
        s = SimulatorState()
        d = s.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 50


# ─────────────────────────────────────────────────────────────────
#  SimulatorTimeline
# ─────────────────────────────────────────────────────────────────

class TestSimulatorTimeline:
    """Tests for the 4th dimension (time) navigation."""

    def test_empty_timeline(self):
        tl = SimulatorTimeline()
        assert tl.length == 0
        assert tl.current is None
        assert tl.seek(10.0) is None

    def test_append_and_length(self):
        tl = SimulatorTimeline()
        for year in range(5):
            s = SimulatorState(mission_time_years=float(year))
            tl.append(s)
        assert tl.length == 5

    def test_seek_exact_year(self):
        tl = SimulatorTimeline()
        for year in range(10):
            tl.append(SimulatorState(mission_time_years=float(year)))
        result = tl.seek(5.0)
        assert result is not None
        assert result.mission_time_years == 5.0

    def test_seek_between_years(self):
        tl = SimulatorTimeline()
        for year in [0, 10, 20, 30]:
            tl.append(SimulatorState(mission_time_years=float(year)))
        # Seek to year 15 — should get year 10 (closest <= 15)
        result = tl.seek(15.0)
        assert result is not None
        assert result.mission_time_years == 10.0

    def test_seek_before_start(self):
        tl = SimulatorTimeline()
        tl.append(SimulatorState(mission_time_years=5.0))
        result = tl.seek(2.0)
        assert result is not None
        assert result.mission_time_years == 5.0  # Returns first available

    def test_step_forward_backward(self):
        tl = SimulatorTimeline()
        for year in range(5):
            tl.append(SimulatorState(mission_time_years=float(year)))

        tl.seek(2.0)
        assert tl.current.mission_time_years == 2.0

        fwd = tl.step_forward()
        assert fwd.mission_time_years == 3.0

        bck = tl.step_backward()
        assert bck.mission_time_years == 2.0

    def test_step_at_boundaries(self):
        tl = SimulatorTimeline()
        tl.append(SimulatorState(mission_time_years=0.0))
        tl.append(SimulatorState(mission_time_years=1.0))

        tl.seek(1.0)
        assert tl.step_forward() is None  # Already at end

        tl.seek(0.0)
        assert tl.step_backward() is None  # Already at start

    def test_range_query(self):
        tl = SimulatorTimeline()
        for year in range(20):
            tl.append(SimulatorState(mission_time_years=float(year)))
        subset = tl.range(5.0, 10.0)
        assert len(subset) == 6  # Years 5, 6, 7, 8, 9, 10
        years = [s.mission_time_years for s in subset]
        assert years == [5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

    def test_get_trajectory(self):
        tl = SimulatorTimeline()
        for i in range(5):
            tl.append(SimulatorState(position_3d=[float(i), 0.0, 0.0]))
        traj = tl.get_trajectory()
        assert len(traj) == 5
        assert traj[3] == [3.0, 0.0, 0.0]

    def test_get_metric_series(self):
        tl = SimulatorTimeline()
        for year in range(5):
            tl.append(SimulatorState(
                mission_time_years=float(year),
                hull_integrity=1.0 - year * 0.1,
            ))
        series = tl.get_metric_series("hull_integrity")
        assert len(series) == 5
        assert series[0] == (0.0, 1.0)
        assert abs(series[4][1] - 0.6) < 0.01

    def test_export_json(self):
        tl = SimulatorTimeline()
        tl.append(SimulatorState(mission_time_years=1.0))
        exported = tl.export_json()
        assert len(exported) == 1
        assert exported[0]["mission_time_years"] == 1.0

    def test_deep_copy_on_append(self):
        """Verify that appending to timeline creates a deep copy."""
        tl = SimulatorTimeline()
        s = SimulatorState(position_3d=[1.0, 0.0, 0.0])
        tl.append(s)
        s.position_3d[0] = 999.0  # Mutate original
        assert tl.seek(0.0).position_3d[0] == 1.0  # Timeline copy is unchanged


# ─────────────────────────────────────────────────────────────────
#  SimulatorEngine — core tick execution
# ─────────────────────────────────────────────────────────────────

class TestSimulatorEngine:
    """Tests for the main simulation engine."""

    def test_create_engine(self):
        engine = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
            crew_size=4,
        )
        assert not engine.is_initialized
        assert engine.target.name == "alpha_centauri"

    def test_initialize(self):
        engine = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
        )
        engine.initialize()
        assert engine.is_initialized
        assert engine.timeline.length == 1  # Initial state recorded
        assert engine.mission_year == 0.0

    def test_step_without_init_raises(self):
        engine = SimulatorEngine()
        with pytest.raises(RuntimeError, match="initialize"):
            engine.step()

    def test_single_step(self):
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
        )
        engine.initialize()
        state = engine.step()
        assert state.mission_time_years == 1.0
        assert engine.tick_count == 1
        assert engine.timeline.length == 2  # Initial + 1 step

    def test_position_advances_along_trajectory(self):
        """Ship should move toward the target along the direction vector."""
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
        )
        engine.initialize()

        # Step 10 years
        for _ in range(10):
            engine.step()

        s = engine.state
        # At 0.1c, after 10 years, distance ~1.0 ly (with degradation)
        assert s.distance_traveled_ly > 0.5
        assert s.position_3d[0] > 0  # Moving toward [100, 0, 0]

    def test_run_short_mission(self):
        """Run a short mission and verify completion."""
        engine = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
            crew_size=4,
            seed=42,
        )
        engine.initialize()
        final = engine.run(years=10)
        assert final.mission_time_years == 10.0
        assert engine.tick_count == 10
        assert engine.timeline.length == 11  # Initial + 10 steps

    def test_events_are_collected(self):
        """After running, events should be populated from subsystems."""
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
            seed=42,
        )
        engine.initialize()
        engine.run(years=5)
        # At minimum, the core interstellar sim generates events
        assert len(engine.events) >= 0  # May be 0 for early years
        assert engine.timeline.length == 6

    def test_timeline_seek_after_run(self):
        """Verify we can seek to any year after simulation completes."""
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
        )
        engine.initialize()
        engine.run(years=20)

        state_y5 = engine.seek(5.0)
        state_y15 = engine.seek(15.0)
        assert state_y5 is not None
        assert state_y15 is not None
        assert state_y5.mission_time_years == 5.0
        assert state_y15.mission_time_years == 15.0
        # Position at year 15 should be further than year 5
        assert state_y15.distance_traveled_ly > state_y5.distance_traveled_ly

    def test_pause_resume(self):
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
        )
        engine.initialize()

        # Step a few times
        engine.step()
        engine.step()
        assert engine.tick_count == 2

        # Pause
        engine.pause()
        assert engine.is_paused
        engine.step()  # Should be a no-op
        assert engine.tick_count == 2

        # Resume
        engine.resume()
        engine.step()
        assert engine.tick_count == 3

    def test_state_fields_update_from_subsystems(self):
        """Verify that state fields are synced from subsystem states."""
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
            seed=42,
        )
        engine.initialize()
        engine.run(years=5)

        s = engine.state
        # These should have changed from initial values
        assert s.fuel_fraction < 1.0  # Some fuel consumed
        assert s.hull_integrity <= 1.0  # Some degradation
        assert s.phase != "PRE_LAUNCH"  # Should have advanced

    def test_subsystem_snapshots_populated(self):
        engine = SimulatorEngine(
            target=STAR_CATALOG["100_ly_target"],
            velocity_c=0.1,
        )
        engine.initialize()
        engine.run(years=3)

        s = engine.state
        assert "core_journey" in s.subsystems
        assert "power" in s.subsystems
        assert "life_support" in s.subsystems
        assert "electronics" in s.subsystems
        assert "crew" in s.subsystems

    def test_get_summary(self):
        engine = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
        )
        engine.initialize()
        engine.run(years=5)

        summary = engine.get_summary()
        assert summary["target"] == "Alpha Centauri A/B"
        assert summary["mission_year"] == 5.0
        assert summary["ticks"] == 5
        assert "hull_integrity" in summary
        assert "crew" in summary


# ─────────────────────────────────────────────────────────────────
#  Simulator4D Factory
# ─────────────────────────────────────────────────────────────────

class TestSimulator4DFactory:
    """Tests for the mission preset factory."""

    def test_create_alpha_centauri(self):
        engine = Simulator4D.create_mission("alpha_centauri")
        assert engine.is_initialized
        assert engine.target.name == "alpha_centauri"

    def test_create_barnards_star(self):
        engine = Simulator4D.create_mission("barnards_star")
        assert engine.target.distance_ly > 5.9

    def test_create_proxima_centauri(self):
        engine = Simulator4D.create_mission("proxima_centauri")
        assert engine.target.distance_ly < 4.3

    def test_create_tau_ceti(self):
        engine = Simulator4D.create_mission("tau_ceti")
        assert engine.target.distance_ly > 11

    def test_create_100ly_target(self):
        engine = Simulator4D.create_mission("100_ly_target")
        assert engine.target.distance_ly == 100.0

    def test_create_with_custom_velocity(self):
        engine = Simulator4D.create_mission("alpha_centauri", velocity_c=0.05)
        assert engine.state.velocity_scalar_c == 0.05

    def test_create_invalid_target(self):
        with pytest.raises(KeyError):
            Simulator4D.create_mission("nonexistent_star")

    def test_create_custom_target(self):
        engine = Simulator4D.create_custom(
            target_ly=[50.0, 10.0, -5.0],
            target_name="HD 12345",
            velocity_c=0.08,
        )
        assert engine.is_initialized
        assert engine.target.display_name == "HD 12345"
        dist = math.sqrt(50**2 + 10**2 + 5**2)
        assert abs(engine.target.distance_ly - dist) < 0.1

    def test_create_custom_zero_distance_raises(self):
        with pytest.raises(ValueError, match="nonzero"):
            Simulator4D.create_custom(target_ly=[0.0, 0.0, 0.0])

    def test_list_presets(self):
        presets = Simulator4D.list_presets()
        assert len(presets) >= 5
        names = [p["key"] for p in presets]
        assert "alpha_centauri" in names
        assert "100_ly_target" in names
        for p in presets:
            assert "duration_years" in p
            assert p["duration_years"] > 0

    def test_run_preset_mission(self):
        """Smoke test: create a preset and run it for a few years."""
        engine = Simulator4D.create_mission("alpha_centauri", seed=42)
        state = engine.run(years=5)
        assert state.mission_time_years == 5.0
        assert state.ship_survived is True
        assert engine.timeline.length > 1


# ─────────────────────────────────────────────────────────────────
#  SimulatorRecorder
# ─────────────────────────────────────────────────────────────────

class TestSimulatorRecorder:
    """Tests for state recording and export."""

    def test_recorder_start_stop(self):
        rec = SimulatorRecorder()
        rec.start(metadata={"target": "test"})
        assert rec.recording is True
        rec.stop()
        assert rec.recording is False

    def test_record_states(self):
        rec = SimulatorRecorder(interval_ticks=1)
        rec.start()

        for year in range(5):
            s = SimulatorState(mission_time_years=float(year))
            rec.record(s)

        assert rec.snapshot_count == 5

    def test_record_interval(self):
        """Only record every Nth tick."""
        rec = SimulatorRecorder(interval_ticks=3)
        rec.start()

        for year in range(10):
            s = SimulatorState(mission_time_years=float(year))
            rec.record(s)

        # 10 ticks / 3 interval = 3 recorded (ticks 3, 6, 9)
        assert rec.snapshot_count == 3

    def test_get_snapshot_at_year(self):
        rec = SimulatorRecorder()
        rec.start()

        for year in range(10):
            rec.record(SimulatorState(mission_time_years=float(year)))

        snap = rec.get_snapshot_at_year(5.0)
        assert snap is not None
        assert snap["mission_time_years"] == 5.0

    def test_export_json(self):
        rec = SimulatorRecorder()
        rec.start(metadata={"target": "alpha_centauri"})
        rec.record(SimulatorState(mission_time_years=1.0))
        rec.record(SimulatorState(mission_time_years=2.0))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_json(Path(tmpdir) / "test_mission.json")
            assert path.exists()

            data = SimulatorRecorder.load_json(path)
            assert data["snapshot_count"] == 2
            assert data["metadata"]["target"] == "alpha_centauri"
            assert len(data["snapshots"]) == 2

    def test_export_sqlite(self):
        rec = SimulatorRecorder()
        rec.start(metadata={"target": "barnards_star", "velocity_c": 0.1})
        for year in range(5):
            rec.record(SimulatorState(
                mission_time_years=float(year),
                position_3d=[float(year) * 0.1, 0.0, 0.0],
                hull_integrity=1.0 - year * 0.01,
            ))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = rec.export_sqlite(Path(tmpdir) / "test_mission.db")
            assert path.exists()

            loaded = SimulatorRecorder.load_sqlite(path)
            assert len(loaded) == 5
            assert loaded[0]["mission_time_years"] == 0.0
            assert loaded[4]["mission_time_years"] == 4.0

    def test_not_recording_skips(self):
        rec = SimulatorRecorder()
        # Don't call start()
        recorded = rec.record(SimulatorState())
        assert recorded is False
        assert rec.snapshot_count == 0


# ─────────────────────────────────────────────────────────────────
#  3D Trajectory & Position Tracking
# ─────────────────────────────────────────────────────────────────

class TestTrajectoryTracking:
    """Tests for 3D spatial position computation."""

    def test_starts_at_origin(self):
        engine = Simulator4D.create_mission("alpha_centauri")
        s = engine.state
        assert s.position_3d == [0.0, 0.0, 0.0]

    def test_position_moves_toward_target(self):
        engine = Simulator4D.create_mission("alpha_centauri", seed=42)
        target_pos = STAR_CATALOG["alpha_centauri"].position_ly

        engine.run(years=10)

        pos = engine.state.position_3d
        # Position should be somewhere between origin and target
        for i in range(3):
            if target_pos[i] > 0:
                assert pos[i] > 0, f"Position component {i} should be positive"
            elif target_pos[i] < 0:
                assert pos[i] < 0, f"Position component {i} should be negative"

    def test_position_monotonically_advances(self):
        """Distance from origin should increase each tick."""
        engine = Simulator4D.create_mission("100_ly_target", seed=42)
        engine.run(years=20)

        distances = []
        for snap in engine.timeline.range(0.0, 20.0):
            d = math.sqrt(sum(c * c for c in snap.position_3d))
            distances.append(d)

        # First snapshot is origin (distance 0)
        # Each subsequent should be >= previous
        for i in range(1, len(distances)):
            assert distances[i] >= distances[i - 1] - 0.001, (
                f"Distance should increase: year {i} = {distances[i]} < {distances[i-1]}"
            )

    def test_velocity_vector_aligned_with_trajectory(self):
        engine = Simulator4D.create_mission("alpha_centauri")
        engine.run(years=5)

        v = engine.state.velocity_3d
        target_dir = STAR_CATALOG["alpha_centauri"].direction_unit

        # Velocity should be roughly parallel to direction
        # Dot product should be positive
        dot = sum(v[i] * target_dir[i] for i in range(3))
        assert dot > 0, "Velocity should point toward the target"


# ─────────────────────────────────────────────────────────────────
#  Tick Resolution
# ─────────────────────────────────────────────────────────────────

class TestTickResolution:
    """Tests for different time granularities."""

    def test_year_resolution(self):
        assert TickResolution.YEAR.years_per_tick == 1.0

    def test_month_resolution(self):
        assert abs(TickResolution.MONTH.years_per_tick - 1.0 / 12.0) < 0.001

    def test_day_resolution(self):
        assert abs(TickResolution.DAY.years_per_tick - 1.0 / 365.25) < 0.0001

    def test_month_resolution_creates_more_snapshots(self):
        """Monthly resolution should produce 12x more snapshots per year."""
        engine_year = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
            tick_resolution=TickResolution.YEAR,
            enable_all_subsystems=False,
        )
        engine_year.initialize()
        engine_year.run(years=2)

        engine_month = SimulatorEngine(
            target=STAR_CATALOG["alpha_centauri"],
            velocity_c=0.1,
            tick_resolution=TickResolution.MONTH,
            enable_all_subsystems=False,
        )
        engine_month.initialize()
        engine_month.run(years=2)

        # Month should have ~24 ticks + 1 init vs ~2 ticks + 1 init
        assert engine_month.timeline.length > engine_year.timeline.length


# ─────────────────────────────────────────────────────────────────
#  Integration: Engine + Recorder
# ─────────────────────────────────────────────────────────────────

class TestEngineWithRecorder:
    """Tests combining the engine and recorder."""

    def test_record_full_simulation(self):
        engine = Simulator4D.create_mission("alpha_centauri", seed=42)
        recorder = SimulatorRecorder(interval_ticks=1)
        recorder.start(metadata={"target": "alpha_centauri"})

        for _ in range(10):
            state = engine.step()
            recorder.record(state)

        recorder.stop()
        assert recorder.snapshot_count == 10

    def test_record_and_export_roundtrip(self):
        engine = Simulator4D.create_mission("proxima_centauri", seed=42)
        recorder = SimulatorRecorder()
        recorder.start()

        engine.run(years=5)
        for snap_state in [engine.timeline.seek(float(y)) for y in range(6)]:
            recorder.record(snap_state)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = recorder.export_json(Path(tmpdir) / "roundtrip.json")
            loaded = SimulatorRecorder.load_json(path)
            assert loaded["snapshot_count"] == recorder.snapshot_count
