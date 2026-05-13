"""Simulation state recorder — saves snapshots for playback and analysis.

Supports two backends:
  1. JSON: lightweight, human-readable, good for short simulations
  2. SQLite: compact, indexed, good for 1000-year missions with yearly snapshots

Each snapshot captures the complete SimulatorState at a given mission year,
enabling full time-travel through the simulation.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from aria.simulator.engine import SimulatorState

logger = structlog.get_logger()


class SimulatorRecorder:
    """Records simulation state snapshots at configurable intervals.

    Usage:
        recorder = SimulatorRecorder(interval_ticks=1)
        recorder.start(metadata={"target": "alpha_centauri"})

        for tick in range(1000):
            state = engine.step()
            recorder.record(state)

        recorder.export_json("/tmp/mission.json")
        recorder.export_sqlite("/tmp/mission.db")
    """

    def __init__(self, interval_ticks: int = 1) -> None:
        self._interval = max(1, interval_ticks)
        self._snapshots: list[dict[str, Any]] = []
        self._tick_count: int = 0
        self._metadata: dict[str, Any] = {}
        self._start_wall_time: float = 0.0
        self._recording: bool = False

    @property
    def snapshot_count(self) -> int:
        return len(self._snapshots)

    @property
    def snapshots(self) -> list[dict[str, Any]]:
        return list(self._snapshots)

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def start(self, metadata: dict[str, Any] | None = None) -> None:
        """Begin recording. Clears any previous data."""
        self._snapshots.clear()
        self._tick_count = 0
        self._metadata = metadata or {}
        self._start_wall_time = time.time()
        self._recording = True
        logger.info("recorder.started", interval=self._interval, metadata=self._metadata)

    def stop(self) -> None:
        """Stop recording."""
        self._recording = False
        wall_time = time.time() - self._start_wall_time
        logger.info(
            "recorder.stopped",
            snapshots=len(self._snapshots),
            wall_time_s=round(wall_time, 2),
        )

    def record(self, state: SimulatorState) -> bool:
        """Record a state snapshot if the interval has been reached.

        Returns True if a snapshot was recorded.
        """
        if not self._recording:
            return False

        self._tick_count += 1
        if self._tick_count % self._interval != 0:
            return False

        snapshot = self._state_to_dict(state)
        self._snapshots.append(snapshot)
        return True

    def get_snapshot(self, index: int) -> dict[str, Any] | None:
        """Get snapshot by index."""
        if 0 <= index < len(self._snapshots):
            return self._snapshots[index]
        return None

    def get_snapshot_at_year(self, year: float) -> dict[str, Any] | None:
        """Get the snapshot closest to the given mission year."""
        if not self._snapshots:
            return None

        best = min(
            self._snapshots,
            key=lambda s: abs(s["mission_time_years"] - year),
        )
        return best

    # ─── Export ──────────────────────────────────────────────────

    def export_json(self, path: str | Path) -> Path:
        """Export all snapshots to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "format_version": 1,
            "recorder": "aria.simulator.recorder.SimulatorRecorder",
            "metadata": self._metadata,
            "wall_time_s": time.time() - self._start_wall_time,
            "snapshot_count": len(self._snapshots),
            "snapshots": self._snapshots,
        }

        with open(path, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        logger.info("recorder.export_json", path=str(path), snapshots=len(self._snapshots))
        return path

    def export_sqlite(self, path: str | Path) -> Path:
        """Export all snapshots to a SQLite database for large simulations."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_year REAL NOT NULL,
                    position_x REAL,
                    position_y REAL,
                    position_z REAL,
                    velocity_x REAL,
                    velocity_y REAL,
                    velocity_z REAL,
                    hull_integrity REAL,
                    fuel_fraction REAL,
                    crew_count INTEGER,
                    crew_generation INTEGER,
                    power_watts REAL,
                    food_reserves_kg REAL,
                    water_liters REAL,
                    ship_survived INTEGER,
                    phase TEXT,
                    full_state TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_mission_year ON snapshots(mission_year)
            """)

            # Write metadata
            for key, value in self._metadata.items():
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    (key, json.dumps(value, default=str)),
                )

            # Write snapshots
            for snap in self._snapshots:
                pos = snap.get("position_3d", [0, 0, 0])
                vel = snap.get("velocity_3d", [0, 0, 0])
                conn.execute(
                    """INSERT INTO snapshots (
                        mission_year, position_x, position_y, position_z,
                        velocity_x, velocity_y, velocity_z,
                        hull_integrity, fuel_fraction, crew_count, crew_generation,
                        power_watts, food_reserves_kg, water_liters,
                        ship_survived, phase, full_state
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snap.get("mission_time_years", 0),
                        pos[0], pos[1], pos[2],
                        vel[0], vel[1], vel[2],
                        snap.get("hull_integrity", 0),
                        snap.get("fuel_fraction", 0),
                        snap.get("crew_count", 0),
                        snap.get("crew_generation", 0),
                        snap.get("power_watts", 0),
                        snap.get("food_reserves_kg", 0),
                        snap.get("water_liters", 0),
                        1 if snap.get("ship_survived", True) else 0,
                        snap.get("phase", ""),
                        json.dumps(snap, default=str),
                    ),
                )

            conn.commit()
        finally:
            conn.close()

        logger.info("recorder.export_sqlite", path=str(path), snapshots=len(self._snapshots))
        return path

    @staticmethod
    def load_json(path: str | Path) -> dict[str, Any]:
        """Load a previously exported JSON recording."""
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def load_sqlite(path: str | Path) -> list[dict[str, Any]]:
        """Load snapshots from a SQLite recording."""
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT full_state FROM snapshots ORDER BY mission_year"
            ).fetchall()
            return [json.loads(row["full_state"]) for row in rows]
        finally:
            conn.close()

    # ─── Internal ────────────────────────────────────────────────

    @staticmethod
    def _state_to_dict(state: SimulatorState) -> dict[str, Any]:
        """Convert a SimulatorState to a serializable dictionary."""
        return asdict(state)
