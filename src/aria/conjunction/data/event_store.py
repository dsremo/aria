"""SQLite-backed persistence for conjunction events.

P0 FIX (Panel 6 SRE): All conjunction events were previously in-memory only.
Process restart = complete history loss. For a safety-critical conjunction
assessment system, every event above the Pc threshold must be persisted with
a full audit trail: who was involved, what the Pc was at each update, and
when the event was first detected.

This module provides a lightweight SQLite store that requires no external
infrastructure — it works out of the box in any deployment environment.
For production scale (>10M events/year) migrate to PostgreSQL using the
same interface.

Schema:
  conjunction_events — one row per (primary_id, secondary_id, tca_date) event
  pc_snapshots       — one row per Pc assessment (many per event)
  alerts             — one row per threshold crossing or trend change
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Default DB path — can be overridden via EventStore(db_path=...)
DEFAULT_DB_PATH = Path.home() / ".conjunction" / "events.db"


class EventStoreError(Exception):
    """Raised for event store operation failures."""


class EventStore:
    """SQLite-backed conjunction event store.

    Thread-safe via SQLite WAL mode and per-connection context managers.

    Usage:
        store = EventStore()  # uses ~/.conjunction/events.db
        store.upsert_event(event_key, primary_id, secondary_id, ...)
        store.add_snapshot(event_key, timestamp, tca, miss_dist_km, pc, risk)
        events = store.get_active_events(min_pc=1e-4)
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info("event_store_initialized db=%s", self.db_path)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Open a connection with WAL mode and row_factory."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conjunction_events (
                    event_key       TEXT PRIMARY KEY,
                    primary_id      TEXT NOT NULL,
                    secondary_id    TEXT NOT NULL,
                    primary_name    TEXT NOT NULL DEFAULT '',
                    secondary_name  TEXT NOT NULL DEFAULT '',
                    tca_date        TEXT,           -- ISO date of approximate TCA (YYYY-MM-DD)
                    first_detected  TEXT NOT NULL,  -- ISO datetime
                    last_updated    TEXT NOT NULL,
                    peak_pc         REAL NOT NULL DEFAULT 0.0,
                    snapshot_count  INTEGER NOT NULL DEFAULT 0,
                    is_active       INTEGER NOT NULL DEFAULT 1,  -- 1=active, 0=past TCA
                    extra           TEXT DEFAULT '{}'            -- JSON metadata
                );

                CREATE INDEX IF NOT EXISTS idx_events_active
                    ON conjunction_events(is_active, peak_pc DESC);
                CREATE INDEX IF NOT EXISTS idx_events_objects
                    ON conjunction_events(primary_id, secondary_id);

                CREATE TABLE IF NOT EXISTS pc_snapshots (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key       TEXT NOT NULL REFERENCES conjunction_events(event_key),
                    assessed_at     TEXT NOT NULL,   -- ISO datetime when this Pc was computed
                    tca             TEXT NOT NULL,   -- ISO datetime of TCA
                    miss_distance_km REAL NOT NULL,
                    probability_of_collision REAL NOT NULL,
                    risk_level      TEXT NOT NULL,
                    hours_to_tca    REAL NOT NULL,
                    source          TEXT DEFAULT 'computed'  -- 'cdm', 'computed', 'maneuver'
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_event
                    ON pc_snapshots(event_key, assessed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_snapshots_pc
                    ON pc_snapshots(probability_of_collision DESC);

                CREATE TABLE IF NOT EXISTS alerts (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key       TEXT NOT NULL REFERENCES conjunction_events(event_key),
                    alert_type      TEXT NOT NULL,   -- 'threshold_crossed', 'trend_rising', 'storm'
                    severity        TEXT NOT NULL,   -- 'info', 'warning', 'critical'
                    message         TEXT NOT NULL,
                    pc_at_alert     REAL,
                    created_at      TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_event
                    ON alerts(event_key, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_alerts_severity
                    ON alerts(severity, created_at DESC);
            """)

    # ── Write operations ──────────────────────────────────────────────

    def upsert_event(
        self,
        event_key: str,
        primary_id: str,
        secondary_id: str,
        primary_name: str = "",
        secondary_name: str = "",
        tca_date: str | None = None,
    ) -> None:
        """Insert or update a conjunction event record."""
        now = datetime.now(timezone.utc).isoformat()  # R65: was utcnow() (deprecated/naive)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conjunction_events
                    (event_key, primary_id, secondary_id, primary_name, secondary_name,
                     tca_date, first_detected, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_key) DO UPDATE SET
                    last_updated = excluded.last_updated,
                    primary_name = COALESCE(excluded.primary_name, primary_name),
                    secondary_name = COALESCE(excluded.secondary_name, secondary_name),
                    tca_date = COALESCE(excluded.tca_date, tca_date)
                """,
                (event_key, primary_id, secondary_id, primary_name, secondary_name,
                 tca_date, now, now),
            )

    def add_snapshot(
        self,
        event_key: str,
        assessed_at: datetime,
        tca: datetime,
        miss_distance_km: float,
        probability_of_collision: float,
        risk_level: str,
        hours_to_tca: float,
        source: str = "computed",
    ) -> None:
        """Record a new Pc assessment snapshot for a conjunction event."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pc_snapshots
                    (event_key, assessed_at, tca, miss_distance_km,
                     probability_of_collision, risk_level, hours_to_tca, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_key,
                    assessed_at.isoformat(),
                    tca.isoformat(),
                    miss_distance_km,
                    probability_of_collision,
                    risk_level,
                    hours_to_tca,
                    source,
                ),
            )
            # Update peak_pc and snapshot count on the parent event
            conn.execute(
                """
                UPDATE conjunction_events SET
                    peak_pc = MAX(peak_pc, ?),
                    snapshot_count = snapshot_count + 1,
                    last_updated = ?
                WHERE event_key = ?
                """,
                (probability_of_collision, assessed_at.isoformat(), event_key),
            )

    def add_alert(
        self,
        event_key: str,
        alert_type: str,
        severity: str,
        message: str,
        pc_at_alert: float | None = None,
    ) -> None:
        """Record an alert (threshold crossing, rising trend, conjunction storm)."""
        now = datetime.now(timezone.utc).isoformat()  # R65: was utcnow() (deprecated/naive)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts
                    (event_key, alert_type, severity, message, pc_at_alert, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_key, alert_type, severity, message, pc_at_alert, now),
            )
        logger.warning(
            "conjunction_alert event_key=%s type=%s severity=%s pc=%.2e msg=%s",
            event_key, alert_type, severity, pc_at_alert or 0.0, message,
        )

    def mark_past_tca(self, event_key: str) -> None:
        """Mark an event as past TCA (no longer active)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE conjunction_events SET is_active = 0 WHERE event_key = ?",
                (event_key,),
            )

    # ── Read operations ───────────────────────────────────────────────

    def get_active_events(self, min_pc: float = 1e-6) -> list[dict]:
        """Return all active events above a Pc threshold, ordered by peak Pc."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM conjunction_events
                WHERE is_active = 1 AND peak_pc >= ?
                ORDER BY peak_pc DESC
                """,
                (min_pc,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_snapshots(self, event_key: str, limit: int = 50) -> list[dict]:
        """Return Pc history for a conjunction event, newest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pc_snapshots
                WHERE event_key = ?
                ORDER BY assessed_at DESC
                LIMIT ?
                """,
                (event_key, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_alerts(self, severity: str | None = None, limit: int = 100) -> list[dict]:
        """Return recent alerts, optionally filtered by severity."""
        with self._connect() as conn:
            if severity:
                rows = conn.execute(
                    """
                    SELECT a.*, e.primary_name, e.secondary_name
                    FROM alerts a JOIN conjunction_events e ON a.event_key = e.event_key
                    WHERE a.severity = ?
                    ORDER BY a.created_at DESC LIMIT ?
                    """,
                    (severity, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT a.*, e.primary_name, e.secondary_name
                    FROM alerts a JOIN conjunction_events e ON a.event_key = e.event_key
                    ORDER BY a.created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def event_summary(self) -> dict:
        """Return high-level statistics about the event store."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM conjunction_events").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM conjunction_events WHERE is_active = 1"
            ).fetchone()[0]
            critical = conn.execute(
                "SELECT COUNT(*) FROM conjunction_events WHERE is_active = 1 AND peak_pc >= 1e-4"
            ).fetchone()[0]
            snapshots = conn.execute("SELECT COUNT(*) FROM pc_snapshots").fetchone()[0]
        return {
            "total_events": total,
            "active_events": active,
            "critical_events_pc_1e4": critical,
            "total_snapshots": snapshots,
            "db_path": str(self.db_path),
        }
