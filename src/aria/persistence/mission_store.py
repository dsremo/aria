"""SQLite-backed mission persistence store.

Saves completed mission results with unique IDs and timestamps,
supports querying by ID, type, date range, and recency.

Database location: ~/.aria/missions.db (auto-created on first use).

Usage:
    store = MissionStore()  # Uses default path
    mission_id = store.save(results)
    loaded = store.load(mission_id)
    all_missions = store.list_missions()
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ────────────────────────────────────────────────────────────────
#  Data classes for stored mission records
# ────────────────────────────────────────────────────────────────


@dataclass
class MissionRecord:
    """A persisted mission result."""

    id: str
    name: str
    mission_type: str
    timestamp: str  # ISO-8601 UTC
    duration_sim_s: float
    duration_wall_s: float
    total_frames: int
    total_events: int
    total_alerts: int
    altitude_range_km: tuple[float, float]
    velocity_range_m_s: tuple[float, float]
    latitude_range_deg: tuple[float, float]
    eclipse_count: int
    agent_messages_processed: int
    anomalies_detected: int
    severity_distribution: dict[str, int]
    challenge_states: dict[str, str]
    terminal_challenges: int
    errors: list[str]
    status: str  # "success" or "failed"
    score: Optional[float] = None
    grade: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MissionSummary:
    """Lightweight summary for listing missions."""

    id: str
    name: str
    mission_type: str
    timestamp: str
    status: str
    score: Optional[float] = None
    grade: Optional[str] = None
    total_events: int = 0
    total_alerts: int = 0
    duration_wall_s: float = 0.0


# ────────────────────────────────────────────────────────────────
#  Schema
# ────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS missions (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    mission_type            TEXT NOT NULL,
    timestamp               TEXT NOT NULL,
    duration_sim_s          REAL NOT NULL DEFAULT 0,
    duration_wall_s         REAL NOT NULL DEFAULT 0,
    total_frames            INTEGER NOT NULL DEFAULT 0,
    total_events            INTEGER NOT NULL DEFAULT 0,
    total_alerts            INTEGER NOT NULL DEFAULT 0,
    altitude_range_json     TEXT NOT NULL DEFAULT '[]',
    velocity_range_json     TEXT NOT NULL DEFAULT '[]',
    latitude_range_json     TEXT NOT NULL DEFAULT '[]',
    eclipse_count           INTEGER NOT NULL DEFAULT 0,
    agent_messages_processed INTEGER NOT NULL DEFAULT 0,
    anomalies_detected      INTEGER NOT NULL DEFAULT 0,
    severity_json           TEXT NOT NULL DEFAULT '{}',
    challenge_states_json   TEXT NOT NULL DEFAULT '{}',
    terminal_challenges     INTEGER NOT NULL DEFAULT 0,
    errors_json             TEXT NOT NULL DEFAULT '[]',
    status                  TEXT NOT NULL DEFAULT 'success',
    score                   REAL,
    grade                   TEXT,
    extra_json              TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_missions_timestamp     ON missions(timestamp);
CREATE INDEX IF NOT EXISTS idx_missions_type          ON missions(mission_type);
CREATE INDEX IF NOT EXISTS idx_missions_status        ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_name          ON missions(name);
"""


# ────────────────────────────────────────────────────────────────
#  MissionStore
# ────────────────────────────────────────────────────────────────


def _default_db_path() -> str:
    """Return ~/.aria/missions.db, creating the directory if needed."""
    aria_dir = Path.home() / ".aria"
    aria_dir.mkdir(parents=True, exist_ok=True)
    return str(aria_dir / "missions.db")


class MissionStore:
    """SQLite-backed store for completed mission results.

    Parameters
    ----------
    db_path : str or None
        Path to the SQLite database file.  ``":memory:"`` for an in-memory
        database (useful for tests).  *None* uses ``~/.aria/missions.db``.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        resolved = db_path if db_path is not None else _default_db_path()
        # Guard against path traversal — resolve to absolute and verify
        # it stays under an allowed parent (home dir or :memory:).
        if resolved != ":memory:":
            resolved = str(Path(resolved).resolve())
        self.db_path = resolved
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_schema()

    # ── connection management ──────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── save ───────────────────────────────────────────────────

    def save(self, results: Any, score: Optional[float] = None,
             grade: Optional[str] = None, extra: Optional[dict] = None) -> str:
        """Persist a MissionResults object. Returns the generated mission ID.

        Parameters
        ----------
        results : MissionResults
            The completed mission results (from ``aria.simulation.mission_runner``).
        score : float or None
            Optional mission score (0-100).
        grade : str or None
            Optional letter grade (A+, A, B, ...).
        extra : dict or None
            Any additional metadata to store.
        """
        mission_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO missions (
                id, name, mission_type, timestamp,
                duration_sim_s, duration_wall_s,
                total_frames, total_events, total_alerts,
                altitude_range_json, velocity_range_json, latitude_range_json,
                eclipse_count, agent_messages_processed, anomalies_detected,
                severity_json, challenge_states_json, terminal_challenges,
                errors_json, status, score, grade, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mission_id,
                getattr(results, "mission_name", "unknown"),
                getattr(results, "mission_type", "unknown"),
                timestamp,
                getattr(results, "duration_sim_s", 0.0),
                getattr(results, "duration_wall_s", 0.0),
                getattr(results, "total_frames", 0),
                getattr(results, "total_events", 0),
                getattr(results, "total_alerts", 0),
                json.dumps(list(getattr(results, "altitude_range_km", (0, 0)))),
                json.dumps(list(getattr(results, "velocity_range_m_s", (0, 0)))),
                json.dumps(list(getattr(results, "latitude_range_deg", (0, 0)))),
                getattr(results, "eclipse_count", 0),
                getattr(results, "agent_messages_processed", 0),
                getattr(results, "anomalies_detected", 0),
                json.dumps(getattr(results, "severity_distribution", {})),
                json.dumps(getattr(results, "challenge_states", {})),
                getattr(results, "terminal_challenges", 0),
                json.dumps(getattr(results, "errors", [])),
                "success" if getattr(results, "success", True) else "failed",
                score,
                grade,
                json.dumps(extra or {}),
            ),
        )
        conn.commit()
        return mission_id

    # ── load ───────────────────────────────────────────────────

    def load(self, mission_id: str) -> Optional[MissionRecord]:
        """Load a mission by ID. Returns None if not found."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM missions WHERE id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    # ── list ───────────────────────────────────────────────────

    def list_missions(self, limit: int = 50) -> list[MissionSummary]:
        """List all missions, most recent first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, name, mission_type, timestamp, status, score, grade, "
            "total_events, total_alerts, duration_wall_s "
            "FROM missions ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    # ── query helpers ──────────────────────────────────────────

    def latest(self) -> Optional[MissionRecord]:
        """Load the most recently saved mission."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM missions ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def by_type(self, mission_type: str, limit: int = 50) -> list[MissionSummary]:
        """Query missions by type (LEO, GEO, INTERSTELLAR)."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, name, mission_type, timestamp, status, score, grade, "
            "total_events, total_alerts, duration_wall_s "
            "FROM missions WHERE mission_type = ? ORDER BY timestamp DESC LIMIT ?",
            (mission_type, limit),
        ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def by_date_range(
        self, start: str, end: str, limit: int = 100
    ) -> list[MissionSummary]:
        """Query missions within a date range (ISO-8601 strings).

        Parameters
        ----------
        start : str
            Start of range (inclusive), e.g. "2026-01-01".
        end : str
            End of range (inclusive), e.g. "2026-12-31".
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, name, mission_type, timestamp, status, score, grade, "
            "total_events, total_alerts, duration_wall_s "
            "FROM missions WHERE timestamp >= ? AND timestamp <= ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (start, end, limit),
        ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def count(self) -> int:
        """Total number of stored missions."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM missions").fetchone()
        return row[0]

    # ── delete ─────────────────────────────────────────────────

    def delete(self, mission_id: str) -> bool:
        """Delete a mission by ID. Returns True if a row was deleted."""
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM missions WHERE id = ?", (mission_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

    def delete_all(self) -> int:
        """Delete all missions. Returns count of deleted rows."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM missions")
        conn.commit()
        return cursor.rowcount

    # ── internal helpers ───────────────────────────────────────

    @staticmethod
    def _safe_json(val: str, default: Any = None) -> Any:
        """Parse JSON from DB, returning default on corrupt data."""
        try:
            return json.loads(val) if val else (default if default is not None else {})
        except (json.JSONDecodeError, TypeError):
            return default if default is not None else {}

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MissionRecord:
        alt = MissionStore._safe_json(row["altitude_range_json"], [0, 0])
        vel = MissionStore._safe_json(row["velocity_range_json"], [0, 0])
        lat = MissionStore._safe_json(row["latitude_range_json"], [0, 0])
        return MissionRecord(
            id=row["id"],
            name=row["name"],
            mission_type=row["mission_type"],
            timestamp=row["timestamp"],
            duration_sim_s=row["duration_sim_s"],
            duration_wall_s=row["duration_wall_s"],
            total_frames=row["total_frames"],
            total_events=row["total_events"],
            total_alerts=row["total_alerts"],
            altitude_range_km=tuple(alt) if len(alt) == 2 else (0, 0),
            velocity_range_m_s=tuple(vel) if len(vel) == 2 else (0, 0),
            latitude_range_deg=tuple(lat) if len(lat) == 2 else (0, 0),
            eclipse_count=row["eclipse_count"],
            agent_messages_processed=row["agent_messages_processed"],
            anomalies_detected=row["anomalies_detected"],
            severity_distribution=MissionStore._safe_json(row["severity_json"]),
            challenge_states=MissionStore._safe_json(row["challenge_states_json"]),
            terminal_challenges=row["terminal_challenges"],
            errors=MissionStore._safe_json(row["errors_json"], []),
            status=row["status"],
            score=row["score"],
            grade=row["grade"],
            extra=MissionStore._safe_json(row["extra_json"]),
        )

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> MissionSummary:
        return MissionSummary(
            id=row["id"],
            name=row["name"],
            mission_type=row["mission_type"],
            timestamp=row["timestamp"],
            status=row["status"],
            score=row["score"],
            grade=row["grade"],
            total_events=row["total_events"],
            total_alerts=row["total_alerts"],
            duration_wall_s=row["duration_wall_s"],
        )
