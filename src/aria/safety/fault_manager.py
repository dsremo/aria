"""Fault management with acknowledge/shelve workflow.

Implements the OpenMCT fault lifecycle: faults are detected, reported,
and then must be explicitly acknowledged by an operator. Faults can be
shelved (temporarily suppressed) for configurable durations. Unacknowledged
faults escalate after a deadline.

This replaces ad-hoc alarm handling with a structured workflow that
real mission control systems use.

Pattern studied from NASA OpenMCT faultManagement plugin (Apache 2.0).

Fault lifecycle:
    DETECTED → UNACKNOWLEDGED → ACKNOWLEDGED → RESOLVED
                      ↓
                   SHELVED (auto-unshelve after duration)
"""

from __future__ import annotations

import enum
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger()

# Wiring audit Pass 1 (F5.1) — schema version for the persisted fault
# state. Bump in lockstep with any change to the on-disk record shape.
_PERSIST_SCHEMA_VERSION = 1


class FaultState(enum.Enum):
    UNACKNOWLEDGED = "unacknowledged"
    ACKNOWLEDGED = "acknowledged"
    SHELVED = "shelved"
    RESOLVED = "resolved"


class FaultSeverity(enum.Enum):
    WATCH = "watch"        # informational, monitor
    WARNING = "warning"    # degraded, action needed
    CRITICAL = "critical"  # immediate action required


@dataclass
class Fault:
    """A tracked fault with lifecycle state."""
    id: str
    subsystem: str
    severity: FaultSeverity
    message: str
    state: FaultState = FaultState.UNACKNOWLEDGED
    detected_at: float = 0.0
    acknowledged_at: float = 0.0
    shelved_until: float = 0.0
    resolved_at: float = 0.0
    acknowledged_by: str = ""
    notes: str = ""
    sim_time_yr: float = 0.0


# Standard shelve durations (OpenMCT defaults)
SHELVE_DURATIONS = {
    "5min": 5 * 60,
    "10min": 10 * 60,
    "15min": 15 * 60,
    "1hr": 60 * 60,
    "unlimited": float('inf'),
}


class FaultManager:
    """Manages fault lifecycle with acknowledge/shelve/resolve workflow.

    Usage:
        mgr = FaultManager(bus=get_event_bus())
        fault_id = mgr.report("thermal", FaultSeverity.WARNING, "Zone 3 overtemp")
        mgr.acknowledge(fault_id, operator="flight_director")
        mgr.shelve(fault_id, duration="15min")
        mgr.resolve(fault_id)
    """

    def __init__(
        self,
        bus: Any = None,
        persist_path: Optional[str | os.PathLike] = None,
    ) -> None:
        self._faults: Dict[str, Fault] = {}
        self._lock = threading.Lock()
        self._bus = bus
        self._fault_counter: int = 0
        self._resolved_history: List[Fault] = []
        # Wiring audit Pass 1 (F5.1) — keep the active fault set on
        # disk so a process bounce does not silently clear an
        # operator-acknowledged set of faults.  Resolved history is NOT
        # persisted (it is bounded LRU).
        self._persist_path: Optional[Path] = (
            Path(persist_path) if persist_path else None
        )
        if self._persist_path is not None:
            self._load_persisted_state()

    def report(
        self,
        subsystem: str,
        severity: FaultSeverity,
        message: str,
        sim_time_yr: float = 0.0,
    ) -> str:
        """Report a new fault. Returns the fault ID."""
        with self._lock:
            self._fault_counter += 1
            fault_id = f"FAULT-{self._fault_counter:05d}"

        fault = Fault(
            id=fault_id,
            subsystem=subsystem,
            severity=severity,
            message=message,
            detected_at=time.monotonic(),
            sim_time_yr=sim_time_yr,
        )

        with self._lock:
            self._faults[fault_id] = fault
            self._persist_locked()    # F5.1

        if self._bus:
            # R7 (2026-04-24, sync refactor): map FaultSeverity → bus
            # severity explicitly.  Bus understands debug/info/warning/
            # critical (event_bus.py:65 _SEV_ORDER); FaultSeverity uses
            # watch/warning/critical.  Without the map, "watch" went
            # out as "watch" which the bus filter ranked at order=0
            # (same as debug), so spam-detection thresholds and the
            # /api/events/recent?min_severity=warning filter both
            # silently dropped it.
            _BUS_SEV = {
                FaultSeverity.WATCH:    "info",
                FaultSeverity.WARNING:  "warning",
                FaultSeverity.CRITICAL: "critical",
            }
            from aria.safety._bus_publish import publish_compat
            publish_compat(
                self._bus,
                f"fault.{subsystem}.{severity.value}",
                severity=_BUS_SEV.get(severity, "warning"),
                source="fault_manager",
                payload={"fault_id": fault_id, "message": message,
                         "fault_severity": severity.value},
                sim_time_yr=sim_time_yr,
            )

        return fault_id

    def acknowledge(self, fault_id: str, operator: str = "") -> bool:
        """Acknowledge a fault. Returns False if fault not found."""
        with self._lock:
            fault = self._faults.get(fault_id)
            if not fault or fault.state == FaultState.RESOLVED:
                return False
            fault.state = FaultState.ACKNOWLEDGED
            fault.acknowledged_at = time.monotonic()
            fault.acknowledged_by = operator
            self._persist_locked()    # F5.1
            return True

    def shelve(self, fault_id: str, duration: str = "15min") -> bool:
        """Shelve a fault for a duration. Auto-unshelves after expiry."""
        with self._lock:
            fault = self._faults.get(fault_id)
            if not fault or fault.state == FaultState.RESOLVED:
                return False
            duration_s = SHELVE_DURATIONS.get(duration, 15 * 60)
            fault.state = FaultState.SHELVED
            fault.shelved_until = time.monotonic() + duration_s
            self._persist_locked()    # F5.1
            return True

    def resolve(self, fault_id: str, notes: str = "") -> bool:
        """Mark a fault as resolved."""
        with self._lock:
            fault = self._faults.get(fault_id)
            if not fault:
                return False
            fault.state = FaultState.RESOLVED
            fault.resolved_at = time.monotonic()
            fault.notes = notes
            self._resolved_history.append(fault)
            del self._faults[fault_id]
            if len(self._resolved_history) > 10_000:
                self._resolved_history = self._resolved_history[-5_000:]
            self._persist_locked()    # F5.1
            return True

    def check_shelve_expiry(self) -> List[str]:
        """Check for shelved faults that have expired. Call periodically."""
        now = time.monotonic()
        unshelved: List[str] = []
        with self._lock:
            for fault in self._faults.values():
                if fault.state == FaultState.SHELVED and now >= fault.shelved_until:
                    fault.state = FaultState.UNACKNOWLEDGED
                    unshelved.append(fault.id)
            if unshelved:
                self._persist_locked()    # F5.1
        return unshelved

    def active_faults(self, severity: Optional[FaultSeverity] = None) -> List[Dict[str, Any]]:
        """List all active (non-resolved) faults."""
        with self._lock:
            faults = []
            for f in self._faults.values():
                if severity and f.severity != severity:
                    continue
                faults.append({
                    "id": f.id,
                    "subsystem": f.subsystem,
                    "severity": f.severity.value,
                    "state": f.state.value,
                    "message": f.message,
                    "age_s": time.monotonic() - f.detected_at,
                    "sim_time_yr": f.sim_time_yr,
                })
            return faults

    def stats(self) -> Dict[str, Any]:
        """Fault management statistics."""
        with self._lock:
            by_state: Dict[str, int] = {}
            by_severity: Dict[str, int] = {}
            for fault in self._faults.values():
                by_state[fault.state.value] = by_state.get(fault.state.value, 0) + 1
                by_severity[fault.severity.value] = by_severity.get(fault.severity.value, 0) + 1
            return {
                "active_faults": len(self._faults),
                "resolved_total": len(self._resolved_history),
                "by_state": by_state,
                "by_severity": by_severity,
            }

    # ── Persistence (F5.1) ──────────────────────────────────────────

    def _persist_locked(self) -> None:
        """Atomically write the active fault set to disk. Caller must
        hold ``self._lock``.  Wiring audit Pass 1 (F5.1).

        Active state is converted to monotonic-age offsets so a
        restart can re-anchor against the new monotonic clock without
        losing fault age.  Resolved history is not persisted — the
        operational requirement is "operator ack survives restart",
        not a complete archive (the audit JSONL covers archival).
        """
        if self._persist_path is None:
            return
        now_wall = time.time()
        now_mono = time.monotonic()
        records: List[Dict[str, Any]] = []
        for fault in self._faults.values():
            records.append({
                "id": fault.id,
                "subsystem": fault.subsystem,
                "severity": fault.severity.value,
                "message": fault.message,
                "state": fault.state.value,
                "detected_age_s": now_mono - fault.detected_at,
                "acknowledged_age_s": (
                    now_mono - fault.acknowledged_at
                    if fault.acknowledged_at
                    else 0.0
                ),
                "shelved_remaining_s": (
                    fault.shelved_until - now_mono
                    if fault.shelved_until and fault.shelved_until > now_mono
                    else 0.0
                ),
                "acknowledged_by": fault.acknowledged_by,
                "notes": fault.notes,
                "sim_time_yr": fault.sim_time_yr,
            })
        payload = {
            "schema_version": _PERSIST_SCHEMA_VERSION,
            "saved_at_wall": now_wall,
            "fault_counter": self._fault_counter,
            "faults": records,
        }
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._persist_path.with_suffix(
                self._persist_path.suffix + ".tmp"
            )
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(payload, fp)
                fp.flush()
                try:
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp_path, self._persist_path)
        except OSError as exc:
            logger.error("fault_manager.persist_failed", error=str(exc))

    def _load_persisted_state(self) -> None:
        """Hydrate the active fault set from disk on construction.

        Skips the load silently if the file does not exist (first boot).
        Logs a structured warning if the schema is unsupported or any
        single record fails to deserialise; valid records still load.
        """
        if self._persist_path is None or not self._persist_path.exists():
            return
        try:
            payload = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("fault_manager.load_failed", error=str(exc))
            return
        if payload.get("schema_version") != _PERSIST_SCHEMA_VERSION:
            logger.warning(
                "fault_manager.schema_version_unsupported",
                stored=payload.get("schema_version"),
                supported=_PERSIST_SCHEMA_VERSION,
            )
            return

        now_wall = time.time()
        now_mono = time.monotonic()
        saved_at_wall = float(payload.get("saved_at_wall", now_wall))
        elapsed_since_save = max(0.0, now_wall - saved_at_wall)

        loaded = 0
        skipped = 0
        for record in payload.get("faults", []):
            try:
                severity = FaultSeverity(record["severity"])
                state = FaultState(record["state"])
                detected_age_s = (
                    float(record.get("detected_age_s", 0.0))
                    + elapsed_since_save
                )
                ack_age_s = float(record.get("acknowledged_age_s", 0.0))
                shelve_remaining_s = (
                    float(record.get("shelved_remaining_s", 0.0))
                    - elapsed_since_save
                )
                fault = Fault(
                    id=record["id"],
                    subsystem=record.get("subsystem", ""),
                    severity=severity,
                    message=record.get("message", ""),
                    state=state,
                    detected_at=now_mono - detected_age_s,
                    acknowledged_at=(
                        now_mono - ack_age_s - elapsed_since_save
                        if ack_age_s > 0
                        else 0.0
                    ),
                    shelved_until=(
                        now_mono + shelve_remaining_s
                        if shelve_remaining_s > 0
                        else 0.0
                    ),
                    acknowledged_by=record.get("acknowledged_by", ""),
                    notes=record.get("notes", ""),
                    sim_time_yr=float(record.get("sim_time_yr", 0.0)),
                )
            except (KeyError, ValueError, TypeError) as exc:
                skipped += 1
                logger.warning(
                    "fault_manager.load_skip_record",
                    fault_id=record.get("id", "?"),
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue
            self._faults[fault.id] = fault
            loaded += 1

        try:
            self._fault_counter = max(
                int(payload.get("fault_counter", 0)),
                self._fault_counter,
            )
        except (TypeError, ValueError):
            pass

        if loaded or skipped:
            logger.info(
                "fault_manager.persisted_state_restored",
                loaded=loaded, skipped=skipped,
                elapsed_since_save_s=round(elapsed_since_save, 1),
            )
