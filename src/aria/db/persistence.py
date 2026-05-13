"""SQLite persistence manager for ARIA core data."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import partial
from typing import Any, Dict, List, Optional


class PersistenceManager:
    """Synchronous SQLite persistence with async wrappers via run_in_executor."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS events (
        id              TEXT PRIMARY KEY,
        timestamp       TEXT NOT NULL,
        category        TEXT NOT NULL,
        severity        TEXT NOT NULL,
        source          TEXT NOT NULL,
        summary         TEXT NOT NULL,
        payload_json    TEXT
    );

    CREATE TABLE IF NOT EXISTS episodes (
        id              TEXT PRIMARY KEY,
        event_type      TEXT NOT NULL,
        severity        TEXT NOT NULL,
        summary         TEXT NOT NULL,
        details_json    TEXT,
        timestamp       TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS decisions (
        id              TEXT PRIMARY KEY,
        timestamp       TEXT NOT NULL,
        category        TEXT NOT NULL,
        severity        TEXT NOT NULL,
        outcome         TEXT NOT NULL,
        description     TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS state_snapshots (
        id              TEXT PRIMARY KEY,
        timestamp       TEXT NOT NULL,
        state_json      TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
    CREATE INDEX IF NOT EXISTS idx_events_category  ON events(category);
    CREATE INDEX IF NOT EXISTS idx_events_severity  ON events(severity);

    CREATE INDEX IF NOT EXISTS idx_episodes_event_type ON episodes(event_type);
    CREATE INDEX IF NOT EXISTS idx_episodes_severity   ON episodes(severity);
    CREATE INDEX IF NOT EXISTS idx_episodes_timestamp  ON episodes(timestamp);

    CREATE INDEX IF NOT EXISTS idx_decisions_timestamp ON decisions(timestamp);
    CREATE INDEX IF NOT EXISTS idx_decisions_category  ON decisions(category);
    CREATE INDEX IF NOT EXISTS idx_decisions_severity  ON decisions(severity);

    CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON state_snapshots(timestamp);
    """

    def init_db(self) -> None:
        """Create all tables and indexes (idempotent)."""
        conn = self._get_conn()
        conn.executescript(self._SCHEMA)
        conn.commit()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    # ------------------------------------------------------------------
    # Synchronous CRUD
    # ------------------------------------------------------------------

    def save_event(
        self,
        timestamp: str,
        category: str,
        severity: str,
        source: str,
        summary: str,
        payload: Any = None,
    ) -> str:
        """Insert an event row. Returns the generated id."""
        conn = self._get_conn()
        row_id = self._new_id()
        payload_json = json.dumps(payload) if payload is not None else None
        conn.execute(
            "INSERT INTO events (id, timestamp, category, severity, source, summary, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row_id, timestamp, category, severity, source, summary, payload_json),
        )
        conn.commit()
        return row_id

    def save_episode(
        self,
        event_type: str,
        severity: str,
        summary: str,
        details: Any = None,
    ) -> str:
        """Insert an episode row. Returns the generated id."""
        conn = self._get_conn()
        row_id = self._new_id()
        details_json = json.dumps(details) if details is not None else None
        timestamp = self._now_iso()
        conn.execute(
            "INSERT INTO episodes (id, event_type, severity, summary, details_json, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, event_type, severity, summary, details_json, timestamp),
        )
        conn.commit()
        return row_id

    def save_decision(
        self,
        timestamp: str,
        category: str,
        severity: str,
        outcome: str,
        description: str,
    ) -> str:
        """Insert a decision row. Returns the generated id."""
        conn = self._get_conn()
        row_id = self._new_id()
        conn.execute(
            "INSERT INTO decisions (id, timestamp, category, severity, outcome, description) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, timestamp, category, severity, outcome, description),
        )
        conn.commit()
        return row_id

    def save_state_snapshot(self, state: dict) -> str:
        """Insert a state snapshot. Returns the generated id."""
        conn = self._get_conn()
        row_id = self._new_id()
        timestamp = self._now_iso()
        conn.execute(
            "INSERT INTO state_snapshots (id, timestamp, state_json) VALUES (?, ?, ?)",
            (row_id, timestamp, json.dumps(state)),
        )
        conn.commit()
        return row_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def query_events(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return events as a list of dicts, newest first."""
        conn = self._get_conn()
        clauses: list[str] = []
        params: list[Any] = []
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM events{where} ORDER BY timestamp DESC LIMIT ?"  # nosec B608 (column names are literal; values bound via ?)
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_episodes(
        self,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return episodes as a list of dicts, newest first."""
        conn = self._get_conn()
        params: list[Any] = []
        where = ""
        if event_type is not None:
            where = " WHERE event_type = ?"
            params.append(event_type)
        sql = f"SELECT * FROM episodes{where} ORDER BY timestamp DESC LIMIT ?"  # nosec B608 (column names are literal; values bound via ?)
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_event_count(self) -> int:
        """Total number of events stored."""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Async wrappers (run_in_executor)
    # ------------------------------------------------------------------

    async def async_init_db(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.init_db)

    async def async_save_event(self, *args: Any, **kwargs: Any) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.save_event, *args, **kwargs))

    async def async_save_episode(self, *args: Any, **kwargs: Any) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.save_episode, *args, **kwargs))

    async def async_query_events(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.query_events, *args, **kwargs))

    async def async_query_episodes(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.query_episodes, *args, **kwargs))

    async def async_get_event_count(self) -> int:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_event_count)
