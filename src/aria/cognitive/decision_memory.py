"""Agent Decision Memory — learn from past anomalies and decisions.

For autonomous spacecraft operations, agents must learn from experience:
  - "Last time battery SoC dropped below 15% during eclipse, load shedding
    resolved the anomaly in 4 minutes."
  - "Bus undervoltage events combined with solar dropout have a 78% chance
    of cascading to ECLSS alarms within 10 minutes."

This module provides:
  - DecisionRecord: immutable record of a single decision + outcome
  - DecisionPattern: aggregated statistics from similar decisions
  - DecisionMemory: SQLite-backed storage, recording, and querying
  - DecisionRecommender: suggests actions based on historical patterns

Design principles:
  - Aging: recent decisions are weighted more than old ones (exponential decay)
  - Bounded: patterns and records are pruned to prevent unbounded growth
  - Durable: all data persists to SQLite via PersistenceManager's connection
  - Thread-safe: sync methods safe for run_in_executor; async wrappers provided
"""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from typing import Any, Dict, List, Optional, Sequence

import structlog

from aria.db.persistence import PersistenceManager

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DecisionType(Enum):
    """Categories of agent decisions."""
    ANOMALY_RESPONSE = "anomaly_response"
    LOAD_SHED = "load_shed"
    MODE_CHANGE = "mode_change"
    THRESHOLD_ADJUST = "threshold_adjust"
    ESCALATION = "escalation"
    SUPPRESSION = "suppression"
    RECONFIG = "reconfig"
    DIAGNOSTIC = "diagnostic"
    PREVENTIVE = "preventive"


class Outcome(Enum):
    """Result of a decision."""
    SUCCESS = "success"           # Action resolved the situation
    PARTIAL = "partial"           # Helped but didn't fully resolve
    FAILURE = "failure"           # Made things worse or didn't help
    NEUTRAL = "neutral"           # No measurable effect
    PENDING = "pending"           # Not yet determined


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DecisionRecord:
    """Immutable record of a single decision and its outcome.

    Fields:
        record_id: unique identifier
        timestamp: ISO-8601 when the decision was made
        mission_time_s: mission elapsed time in seconds (for aging)
        subsystem: which agent/subsystem made the decision
        decision_type: category of the decision
        trigger: what caused the decision (anomaly signature, sensor key, etc.)
        action: what was done
        context: snapshot of relevant state at decision time
        outcome: how it turned out
        resolution_time_s: seconds from decision to resolution (None if pending)
        severity: severity level that triggered the decision
        confidence: agent's confidence in the decision (0-1)
        notes: human or AI annotation
    """
    record_id: str
    timestamp: str
    mission_time_s: float
    subsystem: str
    decision_type: str
    trigger: str
    action: str
    context: dict[str, Any]
    outcome: str = Outcome.PENDING.value
    resolution_time_s: Optional[float] = None
    severity: str = "NOMINAL"
    confidence: float = 1.0
    notes: str = ""


@dataclass
class DecisionPattern:
    """Aggregated pattern from multiple similar decisions.

    Represents: "when trigger X occurs in subsystem Y, doing action A
    succeeds Z% of the time with median resolution of T seconds."
    """
    pattern_id: str
    subsystem: str
    trigger: str
    action: str
    decision_type: str
    total_count: int = 0
    success_count: int = 0
    partial_count: int = 0
    failure_count: int = 0
    neutral_count: int = 0
    avg_resolution_time_s: float = 0.0
    avg_confidence: float = 0.0
    last_used_timestamp: str = ""
    weighted_success_rate: float = 0.0  # Aging-adjusted

    @property
    def success_rate(self) -> float:
        """Raw success rate (successes / resolved decisions)."""
        resolved = self.success_count + self.partial_count + self.failure_count
        if resolved == 0:
            return 0.0
        return self.success_count / resolved

    @property
    def effectiveness_score(self) -> float:
        """Combined effectiveness: success contributes 1.0, partial 0.5, failure 0.0.

        Returns value in [0, 1].
        """
        resolved = self.success_count + self.partial_count + self.failure_count
        if resolved == 0:
            return 0.0
        return (self.success_count + 0.5 * self.partial_count) / resolved


@dataclass
class Recommendation:
    """A recommended action based on historical patterns."""
    action: str
    confidence: float          # 0-1, how confident we are in this recommendation
    success_rate: float        # historical success rate
    times_used: int            # how many times this action was taken for this trigger
    avg_resolution_time_s: float
    pattern: DecisionPattern
    similar_records: list[DecisionRecord] = field(default_factory=list)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Schema extension for decision memory tables
# ---------------------------------------------------------------------------

_DECISION_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_records (
    record_id           TEXT PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    mission_time_s      REAL NOT NULL,
    subsystem           TEXT NOT NULL,
    decision_type       TEXT NOT NULL,
    trigger             TEXT NOT NULL,
    action              TEXT NOT NULL,
    context_json        TEXT NOT NULL DEFAULT '{}',
    outcome             TEXT NOT NULL DEFAULT 'pending',
    resolution_time_s   REAL,
    severity            TEXT NOT NULL DEFAULT 'NOMINAL',
    confidence          REAL NOT NULL DEFAULT 1.0,
    notes               TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS decision_patterns (
    pattern_id              TEXT PRIMARY KEY,
    subsystem               TEXT NOT NULL,
    trigger                 TEXT NOT NULL,
    action                  TEXT NOT NULL,
    decision_type           TEXT NOT NULL,
    total_count             INTEGER NOT NULL DEFAULT 0,
    success_count           INTEGER NOT NULL DEFAULT 0,
    partial_count           INTEGER NOT NULL DEFAULT 0,
    failure_count           INTEGER NOT NULL DEFAULT 0,
    neutral_count           INTEGER NOT NULL DEFAULT 0,
    avg_resolution_time_s   REAL NOT NULL DEFAULT 0.0,
    avg_confidence          REAL NOT NULL DEFAULT 0.0,
    last_used_timestamp     TEXT NOT NULL DEFAULT '',
    weighted_success_rate   REAL NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_dr_subsystem ON decision_records(subsystem);
CREATE INDEX IF NOT EXISTS idx_dr_trigger ON decision_records(trigger);
CREATE INDEX IF NOT EXISTS idx_dr_decision_type ON decision_records(decision_type);
CREATE INDEX IF NOT EXISTS idx_dr_outcome ON decision_records(outcome);
CREATE INDEX IF NOT EXISTS idx_dr_timestamp ON decision_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_dr_mission_time ON decision_records(mission_time_s);

CREATE INDEX IF NOT EXISTS idx_dp_subsystem ON decision_patterns(subsystem);
CREATE INDEX IF NOT EXISTS idx_dp_trigger ON decision_patterns(trigger);
CREATE INDEX IF NOT EXISTS idx_dp_action ON decision_patterns(action);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dp_unique_pattern
    ON decision_patterns(subsystem, trigger, action, decision_type);
"""


# ---------------------------------------------------------------------------
# DecisionMemory — main interface
# ---------------------------------------------------------------------------

class DecisionMemory:
    """SQLite-backed decision memory with aging, pattern extraction, and querying.

    Usage:
        pm = PersistenceManager(":memory:")
        pm.init_db()
        dm = DecisionMemory(pm)
        dm.init_schema()

        # Record a decision
        record_id = dm.record_decision(
            subsystem="power", decision_type="load_shed",
            trigger="battery_low", action="shed_science_loads",
            mission_time_s=86400.0, severity="WARNING",
            context={"soc": 18.5, "in_eclipse": True},
        )

        # Later, update outcome
        dm.update_outcome(record_id, Outcome.SUCCESS, resolution_time_s=240.0)

        # Query recommendations
        recs = dm.get_recommendations("power", "battery_low")
    """

    # Aging half-life in mission-seconds (30 days).
    # A decision 30 days old has half the weight of a current one.
    AGING_HALF_LIFE_S: float = 30 * 24 * 3600.0

    # Maximum records to keep before pruning oldest
    MAX_RECORDS: int = 50_000

    # Minimum records needed to form a pattern
    MIN_PATTERN_SAMPLES: int = 2

    def __init__(self, persistence: PersistenceManager) -> None:
        self._pm = persistence
        self._conn_initialized = False

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_schema(self) -> None:
        """Create decision memory tables (idempotent)."""
        conn = self._pm._get_conn()
        conn.executescript(_DECISION_MEMORY_SCHEMA)
        conn.commit()
        self._conn_initialized = True

    async def async_init_schema(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.init_schema)

    # ------------------------------------------------------------------
    # Record decisions
    # ------------------------------------------------------------------

    def record_decision(
        self,
        subsystem: str,
        decision_type: str,
        trigger: str,
        action: str,
        mission_time_s: float,
        severity: str = "NOMINAL",
        context: Optional[dict[str, Any]] = None,
        confidence: float = 1.0,
        notes: str = "",
        timestamp: Optional[str] = None,
    ) -> str:
        """Record a new decision. Returns the record_id."""
        conn = self._pm._get_conn()
        record_id = uuid.uuid4().hex
        ts = timestamp or datetime.now(timezone.utc).isoformat()

        conn.execute(
            """INSERT INTO decision_records
               (record_id, timestamp, mission_time_s, subsystem, decision_type,
                trigger, action, context_json, outcome, severity, confidence, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id, ts, mission_time_s, subsystem, decision_type,
                trigger, action, json.dumps(context or {}),
                Outcome.PENDING.value, severity, confidence, notes,
            ),
        )
        conn.commit()

        logger.debug(
            "decision_memory.recorded",
            record_id=record_id, subsystem=subsystem,
            trigger=trigger, action=action,
        )
        return record_id

    async def async_record_decision(self, **kwargs: Any) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.record_decision, **kwargs))

    # ------------------------------------------------------------------
    # Update outcome
    # ------------------------------------------------------------------

    def update_outcome(
        self,
        record_id: str,
        outcome: Outcome,
        resolution_time_s: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """Update the outcome of a previously recorded decision.

        Returns True if the record was found and updated.
        """
        conn = self._pm._get_conn()

        # Build SET clause dynamically
        sets = ["outcome = ?"]
        params: list[Any] = [outcome.value]

        if resolution_time_s is not None:
            sets.append("resolution_time_s = ?")
            params.append(resolution_time_s)

        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)

        params.append(record_id)
        sql = f"UPDATE decision_records SET {', '.join(sets)} WHERE record_id = ?"  # nosec B608 (column names are literal; values bound via ?)
        cursor = conn.execute(sql, params)
        conn.commit()

        updated = cursor.rowcount > 0

        if updated:
            # Rebuild affected patterns
            row = conn.execute(
                "SELECT subsystem, trigger, action, decision_type FROM decision_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
            if row:
                self._rebuild_pattern(row["subsystem"], row["trigger"], row["action"], row["decision_type"])

        return updated

    async def async_update_outcome(self, record_id: str, outcome: Outcome, **kwargs: Any) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self.update_outcome, record_id, outcome, **kwargs),
        )

    # ------------------------------------------------------------------
    # Query records
    # ------------------------------------------------------------------

    def get_record(self, record_id: str) -> Optional[DecisionRecord]:
        """Fetch a single record by ID."""
        conn = self._pm._get_conn()
        row = conn.execute(
            "SELECT * FROM decision_records WHERE record_id = ?", (record_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def query_records(
        self,
        subsystem: Optional[str] = None,
        trigger: Optional[str] = None,
        decision_type: Optional[str] = None,
        outcome: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 100,
    ) -> list[DecisionRecord]:
        """Query records with optional filters, newest first."""
        conn = self._pm._get_conn()
        clauses: list[str] = []
        params: list[Any] = []

        if subsystem is not None:
            clauses.append("subsystem = ?")
            params.append(subsystem)
        if trigger is not None:
            clauses.append("trigger = ?")
            params.append(trigger)
        if decision_type is not None:
            clauses.append("decision_type = ?")
            params.append(decision_type)
        if outcome is not None:
            clauses.append("outcome = ?")
            params.append(outcome)
        if severity is not None:
            clauses.append("severity = ?")
            params.append(severity)

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM decision_records{where} ORDER BY mission_time_s DESC LIMIT ?"  # nosec B608 (column names are literal; values bound via ?)
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    async def async_query_records(self, **kwargs: Any) -> list[DecisionRecord]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.query_records, **kwargs))

    def find_similar(
        self,
        subsystem: str,
        trigger: str,
        limit: int = 10,
    ) -> list[DecisionRecord]:
        """Find records with the same subsystem and trigger, newest first."""
        return self.query_records(subsystem=subsystem, trigger=trigger, limit=limit)

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def get_pattern(
        self,
        subsystem: str,
        trigger: str,
        action: str,
        decision_type: str,
    ) -> Optional[DecisionPattern]:
        """Get the pattern for a specific (subsystem, trigger, action, type) tuple."""
        conn = self._pm._get_conn()
        row = conn.execute(
            """SELECT * FROM decision_patterns
               WHERE subsystem = ? AND trigger = ? AND action = ? AND decision_type = ?""",
            (subsystem, trigger, action, decision_type),
        ).fetchone()
        return self._row_to_pattern(row) if row else None

    def get_patterns_for_trigger(
        self,
        subsystem: str,
        trigger: str,
    ) -> list[DecisionPattern]:
        """Get all patterns for a given subsystem + trigger combination."""
        conn = self._pm._get_conn()
        rows = conn.execute(
            """SELECT * FROM decision_patterns
               WHERE subsystem = ? AND trigger = ?
               ORDER BY weighted_success_rate DESC""",
            (subsystem, trigger),
        ).fetchall()
        return [self._row_to_pattern(r) for r in rows]

    def get_all_patterns(self, subsystem: Optional[str] = None) -> list[DecisionPattern]:
        """Get all patterns, optionally filtered by subsystem."""
        conn = self._pm._get_conn()
        if subsystem:
            rows = conn.execute(
                "SELECT * FROM decision_patterns WHERE subsystem = ? ORDER BY total_count DESC",
                (subsystem,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM decision_patterns ORDER BY total_count DESC",
            ).fetchall()
        return [self._row_to_pattern(r) for r in rows]

    def rebuild_all_patterns(self, current_mission_time_s: Optional[float] = None) -> int:
        """Rebuild all patterns from raw records. Returns count of patterns rebuilt."""
        conn = self._pm._get_conn()
        # Get distinct (subsystem, trigger, action, decision_type) tuples
        rows = conn.execute(
            "SELECT DISTINCT subsystem, trigger, action, decision_type FROM decision_records",
        ).fetchall()

        count = 0
        for row in rows:
            self._rebuild_pattern(
                row["subsystem"], row["trigger"], row["action"], row["decision_type"],
                current_mission_time_s=current_mission_time_s,
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_statistics(
        self,
        subsystem: Optional[str] = None,
    ) -> dict[str, Any]:
        """Aggregate statistics: success rates per decision type, subsystem, severity."""
        conn = self._pm._get_conn()

        base_where = "WHERE outcome != 'pending'"
        params: list[Any] = []
        if subsystem:
            base_where += " AND subsystem = ?"
            params.append(subsystem)

        # Total resolved decisions
        total = conn.execute(
            f"SELECT COUNT(*) FROM decision_records {base_where}", params,  # nosec B608 (column names are literal; values bound via ?)
        ).fetchone()[0]

        # Per decision type — column names are literal; values bound via ?.
        sql_by_type = (
            "SELECT decision_type, COUNT(*) as total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes, "
            "SUM(CASE WHEN outcome = 'failure' THEN 1 ELSE 0 END) as failures, "
            "AVG(resolution_time_s) as avg_resolution "
            f"FROM decision_records {base_where} GROUP BY decision_type"  # nosec B608
        )
        by_type_rows = conn.execute(sql_by_type, params).fetchall()

        by_type = {}
        for r in by_type_rows:
            t = r["total"]
            by_type[r["decision_type"]] = {
                "total": t,
                "successes": r["successes"],
                "failures": r["failures"],
                "success_rate": r["successes"] / t if t > 0 else 0.0,
                "avg_resolution_time_s": r["avg_resolution"],
            }

        # Per subsystem — column names are literal; values bound via ?.
        sql_by_sub = (
            "SELECT subsystem, COUNT(*) as total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes "
            f"FROM decision_records {base_where} GROUP BY subsystem"  # nosec B608
        )
        by_sub_rows = conn.execute(sql_by_sub, params).fetchall()

        by_subsystem = {}
        for r in by_sub_rows:
            t = r["total"]
            by_subsystem[r["subsystem"]] = {
                "total": t,
                "successes": r["successes"],
                "success_rate": r["successes"] / t if t > 0 else 0.0,
            }

        # Per severity — column names are literal; values bound via ?.
        sql_by_sev = (
            "SELECT severity, COUNT(*) as total, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as successes "
            f"FROM decision_records {base_where} GROUP BY severity"  # nosec B608
        )
        by_sev_rows = conn.execute(sql_by_sev, params).fetchall()

        by_severity = {}
        for r in by_sev_rows:
            t = r["total"]
            by_severity[r["severity"]] = {
                "total": t,
                "successes": r["successes"],
                "success_rate": r["successes"] / t if t > 0 else 0.0,
            }

        return {
            "total_resolved": total,
            "by_decision_type": by_type,
            "by_subsystem": by_subsystem,
            "by_severity": by_severity,
        }

    async def async_get_statistics(self, **kwargs: Any) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.get_statistics, **kwargs))

    def get_record_count(self) -> int:
        """Total decision records stored."""
        conn = self._pm._get_conn()
        return conn.execute("SELECT COUNT(*) FROM decision_records").fetchone()[0]

    def get_pattern_count(self) -> int:
        """Total decision patterns stored."""
        conn = self._pm._get_conn()
        return conn.execute("SELECT COUNT(*) FROM decision_patterns").fetchone()[0]

    # ------------------------------------------------------------------
    # Pruning
    # ------------------------------------------------------------------

    def prune_old_records(self, keep_count: Optional[int] = None) -> int:
        """Delete oldest records beyond keep_count. Returns number deleted."""
        limit = keep_count or self.MAX_RECORDS
        conn = self._pm._get_conn()

        total = self.get_record_count()
        if total <= limit:
            return 0

        to_delete = total - limit
        conn.execute(
            """DELETE FROM decision_records WHERE record_id IN (
                 SELECT record_id FROM decision_records
                 ORDER BY mission_time_s ASC LIMIT ?
               )""",
            (to_delete,),
        )
        conn.commit()
        return to_delete

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_pattern(
        self,
        subsystem: str,
        trigger: str,
        action: str,
        decision_type: str,
        current_mission_time_s: Optional[float] = None,
    ) -> None:
        """Recompute a single pattern from its constituent records."""
        conn = self._pm._get_conn()

        rows = conn.execute(
            """SELECT * FROM decision_records
               WHERE subsystem = ? AND trigger = ? AND action = ? AND decision_type = ?
               ORDER BY mission_time_s DESC""",
            (subsystem, trigger, action, decision_type),
        ).fetchall()

        if not rows:
            # Delete the pattern if no records remain
            conn.execute(
                """DELETE FROM decision_patterns
                   WHERE subsystem = ? AND trigger = ? AND action = ? AND decision_type = ?""",
                (subsystem, trigger, action, decision_type),
            )
            conn.commit()
            return

        # Compute aggregate statistics
        total = len(rows)
        success = sum(1 for r in rows if r["outcome"] == Outcome.SUCCESS.value)
        partial_ = sum(1 for r in rows if r["outcome"] == Outcome.PARTIAL.value)
        failure = sum(1 for r in rows if r["outcome"] == Outcome.FAILURE.value)
        neutral = sum(1 for r in rows if r["outcome"] == Outcome.NEUTRAL.value)

        resolution_times = [r["resolution_time_s"] for r in rows if r["resolution_time_s"] is not None]
        avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0.0

        confidences = [r["confidence"] for r in rows]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        last_ts = rows[0]["timestamp"]  # newest first

        # Compute weighted success rate with aging
        if current_mission_time_s is not None:
            weighted_success_rate = self._compute_weighted_success_rate(
                rows, current_mission_time_s,
            )
        else:
            # Use raw success rate if no current time given
            resolved = success + partial_ + failure
            weighted_success_rate = success / resolved if resolved > 0 else 0.0

        pattern_id = f"{subsystem}:{trigger}:{action}:{decision_type}"

        conn.execute(
            """INSERT INTO decision_patterns
               (pattern_id, subsystem, trigger, action, decision_type,
                total_count, success_count, partial_count, failure_count, neutral_count,
                avg_resolution_time_s, avg_confidence, last_used_timestamp, weighted_success_rate)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(subsystem, trigger, action, decision_type) DO UPDATE SET
                total_count = excluded.total_count,
                success_count = excluded.success_count,
                partial_count = excluded.partial_count,
                failure_count = excluded.failure_count,
                neutral_count = excluded.neutral_count,
                avg_resolution_time_s = excluded.avg_resolution_time_s,
                avg_confidence = excluded.avg_confidence,
                last_used_timestamp = excluded.last_used_timestamp,
                weighted_success_rate = excluded.weighted_success_rate
            """,
            (
                pattern_id, subsystem, trigger, action, decision_type,
                total, success, partial_, failure, neutral,
                avg_resolution, avg_confidence, last_ts, weighted_success_rate,
            ),
        )
        conn.commit()

    def _compute_weighted_success_rate(
        self,
        rows: Sequence[sqlite3.Row],
        current_mission_time_s: float,
    ) -> float:
        """Compute age-weighted success rate using exponential decay.

        Weight = exp(-ln(2) * age / half_life)
        Recent decisions count more than old ones.
        """
        total_weight = 0.0
        success_weight = 0.0
        ln2 = math.log(2)

        for r in rows:
            outcome = r["outcome"]
            if outcome == Outcome.PENDING.value:
                continue

            age_s = max(0.0, current_mission_time_s - r["mission_time_s"])
            weight = math.exp(-ln2 * age_s / self.AGING_HALF_LIFE_S)

            if outcome == Outcome.SUCCESS.value:
                success_weight += weight
                total_weight += weight
            elif outcome == Outcome.PARTIAL.value:
                success_weight += 0.5 * weight
                total_weight += weight
            elif outcome in (Outcome.FAILURE.value, Outcome.NEUTRAL.value):
                total_weight += weight

        return success_weight / total_weight if total_weight > 0 else 0.0

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> DecisionRecord:
        return DecisionRecord(
            record_id=row["record_id"],
            timestamp=row["timestamp"],
            mission_time_s=row["mission_time_s"],
            subsystem=row["subsystem"],
            decision_type=row["decision_type"],
            trigger=row["trigger"],
            action=row["action"],
            context=json.loads(row["context_json"]) if row["context_json"] else {},
            outcome=row["outcome"],
            resolution_time_s=row["resolution_time_s"],
            severity=row["severity"],
            confidence=row["confidence"],
            notes=row["notes"],
        )

    @staticmethod
    def _row_to_pattern(row: sqlite3.Row) -> DecisionPattern:
        return DecisionPattern(
            pattern_id=row["pattern_id"],
            subsystem=row["subsystem"],
            trigger=row["trigger"],
            action=row["action"],
            decision_type=row["decision_type"],
            total_count=row["total_count"],
            success_count=row["success_count"],
            partial_count=row["partial_count"],
            failure_count=row["failure_count"],
            neutral_count=row["neutral_count"],
            avg_resolution_time_s=row["avg_resolution_time_s"],
            avg_confidence=row["avg_confidence"],
            last_used_timestamp=row["last_used_timestamp"],
            weighted_success_rate=row["weighted_success_rate"],
        )


# ---------------------------------------------------------------------------
# DecisionRecommender — suggests actions based on patterns
# ---------------------------------------------------------------------------

class DecisionRecommender:
    """Suggests actions based on historical decision patterns.

    Usage:
        recommender = DecisionRecommender(decision_memory)
        recs = recommender.recommend("power", "battery_low")
        # Returns list of Recommendation, best first
    """

    # Minimum samples to even consider recommending
    MIN_SAMPLES: int = 1

    # Below this success rate, we actively warn against the action
    WARN_THRESHOLD: float = 0.3

    def __init__(self, memory: DecisionMemory) -> None:
        self._memory = memory

    def recommend(
        self,
        subsystem: str,
        trigger: str,
        current_mission_time_s: Optional[float] = None,
        top_k: int = 5,
    ) -> list[Recommendation]:
        """Get top-K recommended actions for a given trigger.

        Actions are ranked by weighted success rate (aging-adjusted if
        current_mission_time_s is provided), then by total usage count.
        """
        patterns = self._memory.get_patterns_for_trigger(subsystem, trigger)

        if not patterns:
            return []

        # Optionally refresh weighted rates with current time
        if current_mission_time_s is not None:
            self._memory.rebuild_all_patterns(current_mission_time_s)
            patterns = self._memory.get_patterns_for_trigger(subsystem, trigger)

        recommendations: list[Recommendation] = []

        for pattern in patterns:
            if pattern.total_count < self.MIN_SAMPLES:
                continue

            # Fetch a few recent similar records for context
            similar = self._memory.query_records(
                subsystem=subsystem, trigger=trigger, limit=3,
            )

            confidence = self._compute_confidence(pattern)
            reasoning = self._build_reasoning(pattern)

            recommendations.append(Recommendation(
                action=pattern.action,
                confidence=confidence,
                success_rate=pattern.success_rate,
                times_used=pattern.total_count,
                avg_resolution_time_s=pattern.avg_resolution_time_s,
                pattern=pattern,
                similar_records=similar,
                reasoning=reasoning,
            ))

        # Sort by confidence (descending), then success rate, then usage count
        recommendations.sort(
            key=lambda r: (r.confidence, r.success_rate, r.times_used),
            reverse=True,
        )

        return recommendations[:top_k]

    async def async_recommend(self, **kwargs: Any) -> list[Recommendation]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(self.recommend, **kwargs))

    def get_best_action(
        self,
        subsystem: str,
        trigger: str,
        current_mission_time_s: Optional[float] = None,
    ) -> Optional[Recommendation]:
        """Get the single best recommended action, or None if no data."""
        recs = self.recommend(
            subsystem, trigger,
            current_mission_time_s=current_mission_time_s,
            top_k=1,
        )
        return recs[0] if recs else None

    def get_actions_to_avoid(
        self,
        subsystem: str,
        trigger: str,
    ) -> list[DecisionPattern]:
        """Return patterns with success rate below WARN_THRESHOLD — actions to avoid."""
        patterns = self._memory.get_patterns_for_trigger(subsystem, trigger)
        return [
            p for p in patterns
            if p.total_count >= self.MIN_SAMPLES
            and (p.success_count + p.partial_count + p.failure_count) > 0
            and p.success_rate < self.WARN_THRESHOLD
        ]

    def _compute_confidence(self, pattern: DecisionPattern) -> float:
        """Confidence in recommending this action.

        Factors:
          - Sample size (more data = more confident, capped at 1.0)
          - Success rate
          - Recency (via weighted success rate)
        """
        # Sample size factor: log scale, reaches 0.9 at ~20 samples
        sample_factor = min(1.0, math.log(1 + pattern.total_count) / math.log(21))

        # Success factor: direct from effectiveness
        effectiveness = pattern.effectiveness_score

        # Weighted blend: 40% sample, 60% effectiveness
        return 0.4 * sample_factor + 0.6 * effectiveness

    def _build_reasoning(self, pattern: DecisionPattern) -> str:
        """Build a human-readable reasoning string for the recommendation."""
        parts: list[str] = []

        resolved = pattern.success_count + pattern.partial_count + pattern.failure_count
        if resolved > 0:
            parts.append(
                f"Action '{pattern.action}' used {pattern.total_count} time(s) "
                f"for trigger '{pattern.trigger}' in subsystem '{pattern.subsystem}'."
            )
            parts.append(
                f"Success rate: {pattern.success_rate:.0%} "
                f"({pattern.success_count}/{resolved} resolved successfully)."
            )
        else:
            parts.append(
                f"Action '{pattern.action}' recorded {pattern.total_count} time(s) "
                f"but no outcomes resolved yet."
            )

        if pattern.avg_resolution_time_s > 0:
            parts.append(f"Average resolution time: {pattern.avg_resolution_time_s:.0f}s.")

        return " ".join(parts)
