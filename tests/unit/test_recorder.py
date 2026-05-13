"""Tests for aria.simulator.recorder — SimulatorRecorder state capture and export.

Covers:
  - Clean import and construction
  - Start/stop/recording lifecycle
  - Snapshot capture at configured intervals
  - JSON round-trip export/load
  - SQLite round-trip export/load
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import pytest

from aria.simulator.recorder import SimulatorRecorder
from aria.simulator.engine import SimulatorState


@pytest.fixture
def recorder() -> SimulatorRecorder:
    return SimulatorRecorder(interval_ticks=1)


@pytest.fixture
def sample_state() -> SimulatorState:
    """A minimal SimulatorState for recording tests."""
    return SimulatorState(
        position_3d=[1.0, 2.0, 3.0],
        velocity_3d=[0.05, 0.0, 0.0],
        mission_time_years=10.0,
        hull_integrity=0.95,
        fuel_fraction=0.8,
        crew_count=40,
        crew_generation=2,
        power_watts=400000.0,
        food_reserves_kg=8000.0,
        water_liters=45000.0,
        ship_survived=True,
        phase="CRUISE",
    )


class TestRecorderLifecycle:
    """Start, record, stop lifecycle."""

    def test_initial_state(self, recorder: SimulatorRecorder):
        assert recorder.snapshot_count == 0
        assert recorder.recording is False
        assert recorder.metadata == {}

    def test_start_clears_and_activates(self, recorder: SimulatorRecorder):
        recorder.start(metadata={"target": "alpha_centauri"})
        assert recorder.recording is True
        assert recorder.metadata == {"target": "alpha_centauri"}
        assert recorder.snapshot_count == 0

    def test_stop_deactivates(self, recorder: SimulatorRecorder):
        recorder.start()
        recorder.stop()
        assert recorder.recording is False


class TestRecordSnapshots:
    """Recording state snapshots at the configured interval."""

    def test_record_when_not_recording_returns_false(
        self, recorder: SimulatorRecorder, sample_state: SimulatorState,
    ):
        assert recorder.record(sample_state) is False
        assert recorder.snapshot_count == 0

    def test_record_captures_snapshot(
        self, recorder: SimulatorRecorder, sample_state: SimulatorState,
    ):
        recorder.start()
        assert recorder.record(sample_state) is True
        assert recorder.snapshot_count == 1

        snap = recorder.get_snapshot(0)
        assert snap is not None
        assert snap["mission_time_years"] == 10.0
        assert snap["position_3d"] == [1.0, 2.0, 3.0]
        assert snap["hull_integrity"] == 0.95

    def test_interval_skips_intermediate_ticks(self, sample_state: SimulatorState):
        rec = SimulatorRecorder(interval_ticks=3)
        rec.start()
        results = [rec.record(sample_state) for _ in range(6)]
        # Should record on ticks 3 and 6 (every 3rd tick)
        assert results == [False, False, True, False, False, True]
        assert rec.snapshot_count == 2

    def test_get_snapshot_out_of_bounds_returns_none(
        self, recorder: SimulatorRecorder,
    ):
        assert recorder.get_snapshot(0) is None
        assert recorder.get_snapshot(-1) is None

    def test_get_snapshot_at_year(
        self, recorder: SimulatorRecorder,
    ):
        recorder.start()
        for yr in [5.0, 10.0, 15.0, 20.0]:
            state = SimulatorState(mission_time_years=yr)
            recorder.record(state)

        closest = recorder.get_snapshot_at_year(12.0)
        assert closest is not None
        assert closest["mission_time_years"] == 10.0

        exact = recorder.get_snapshot_at_year(15.0)
        assert exact is not None
        assert exact["mission_time_years"] == 15.0


class TestExportJSON:
    """JSON export and load round-trip."""

    def test_export_json_creates_file(
        self, recorder: SimulatorRecorder, sample_state: SimulatorState, tmp_path: Path,
    ):
        recorder.start(metadata={"mission": "test"})
        recorder.record(sample_state)
        out = recorder.export_json(tmp_path / "test_mission.json")

        assert out.exists()
        data = json.loads(out.read_text())
        assert data["format_version"] == 1
        assert data["snapshot_count"] == 1
        assert data["metadata"]["mission"] == "test"
        assert len(data["snapshots"]) == 1

    def test_load_json_round_trip(
        self, recorder: SimulatorRecorder, sample_state: SimulatorState, tmp_path: Path,
    ):
        recorder.start()
        recorder.record(sample_state)
        path = recorder.export_json(tmp_path / "rt.json")

        loaded = SimulatorRecorder.load_json(path)
        assert loaded["snapshot_count"] == 1
        assert loaded["snapshots"][0]["hull_integrity"] == 0.95


class TestExportSQLite:
    """SQLite export and load round-trip."""

    def test_export_sqlite_creates_db(
        self, recorder: SimulatorRecorder, sample_state: SimulatorState, tmp_path: Path,
    ):
        recorder.start(metadata={"target": "tau_ceti"})
        recorder.record(sample_state)
        db_path = recorder.export_sqlite(tmp_path / "test.db")

        assert db_path.exists()
        conn = sqlite3.connect(str(db_path))
        row_count = conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        conn.close()
        assert row_count == 1

    def test_load_sqlite_round_trip(
        self, recorder: SimulatorRecorder, sample_state: SimulatorState, tmp_path: Path,
    ):
        recorder.start()
        recorder.record(sample_state)
        db_path = recorder.export_sqlite(tmp_path / "rt.db")

        loaded = SimulatorRecorder.load_sqlite(db_path)
        assert len(loaded) == 1
        assert loaded[0]["mission_time_years"] == 10.0
        assert loaded[0]["hull_integrity"] == 0.95
