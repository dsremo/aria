"""FDIR — Fault Detection, Isolation, and Recovery.

Per CENTRAL_AI_MASTER_PLAN Part 9:

FDIR Levels:
  Level 0: Hardware self-protection (analog circuits, < 1ms)
  Level 1: Unit-level FDIR (device firmware, < 10ms)
  Level 2: Subsystem-level FDIR (RTOS, < 100ms)
  Level 3: System-level FDIR (ARIA agents, < 1s)
  Level 4: Mission-level FDIR (ARIA Core, < 10s)
  Level 5: Ground-assisted FDIR (ground control, minutes-hours)

This module handles Levels 3-5 in software:
  - Maps Dsremo anomaly severity to FDIR level
  - Defines automated response actions per fault type
  - Tracks active faults and their recovery status
  - Provides FMEA-driven response recommendations
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from aria.bus.message_bus import Message, MessageBus
from aria.core.types import EventPriority, Severity

logger = structlog.get_logger()


# Autonomy audit F9 — a fault entry that has been "active" longer than
# this multiplier × the response timeout is considered stale and a new
# arrival of the same root_cause is treated as a re-fault (allowed
# through the gate).
_REFAULT_STALENESS_MULT = 10.0
# If response has no ``timeout_s``, fall back to this.
_REFAULT_DEFAULT_STALENESS_S = 600.0


class FDIRLevel(IntEnum):
    """FDIR response level — higher = more severe."""
    HARDWARE = 0       # Analog watchdog (not software)
    UNIT = 1           # Firmware (not software)
    SUBSYSTEM = 2      # RTOS partition (not ARIA)
    SYSTEM = 3         # ARIA agents
    MISSION = 4        # ARIA Core
    GROUND_ASSIST = 5  # Needs ground control


@dataclass
class FaultRecord:
    """Active or historical fault record."""
    fault_id: str
    fault_type: str
    subsystem: str
    fdir_level: FDIRLevel
    severity: str
    description: str
    detected_at: float = field(default_factory=time.time)
    response_actions: list[str] = field(default_factory=list)
    recovered: bool = False
    recovered_at: float | None = None
    recovery_method: str = ""


# Severity → FDIR level mapping (from master plan 9.2.3)
SEVERITY_TO_FDIR: dict[str, FDIRLevel] = {
    "NOMINAL": FDIRLevel.SYSTEM,
    "WATCH": FDIRLevel.SYSTEM,
    "WARNING": FDIRLevel.SYSTEM,
    "CRITICAL": FDIRLevel.MISSION,
    "EMERGENCY": FDIRLevel.MISSION,
}

# Fault type → automated response actions (from master plan FMEA)
FAULT_RESPONSES: dict[str, dict[str, Any]] = {
    "BATTERY_THERMAL_RUNAWAY": {
        "level": FDIRLevel.MISSION,
        "actions": ["disconnect_battery", "activate_backup_power", "alert_crew"],
        "timeout_s": 5,
        "auto_recovery": False,
    },
    "CO2_SCRUBBER_FAILURE": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["activate_backup_scrubber", "increase_ventilation", "alert_crew"],
        "timeout_s": 30,
        "auto_recovery": True,
    },
    "CABIN_DEPRESSURIZATION": {
        "level": FDIRLevel.MISSION,
        "actions": ["isolate_compartment", "emergency_suits", "seal_hatches"],
        "timeout_s": 2,
        "auto_recovery": False,
    },
    "ATTITUDE_CONTROL_FAILURE": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["switch_to_backup_adcs", "safe_point_mode"],
        "timeout_s": 10,
        "auto_recovery": True,
    },
    "POWER_GRID_FAILURE": {
        "level": FDIRLevel.MISSION,
        "actions": ["survival_mode", "emergency_power_bus", "shed_all_non_essential"],
        "timeout_s": 5,
        "auto_recovery": False,
    },
    "PROPULSION_LEAK": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["isolate_feed_lines", "close_valves", "assess_dv_budget"],
        "timeout_s": 15,
        "auto_recovery": False,
    },
    "SOLAR_PARTICLE_EVENT": {
        "level": FDIRLevel.MISSION,
        "actions": ["crew_to_shelter", "reduce_exposure", "switch_to_lga", "protect_electronics"],
        "timeout_s": 5,
        "auto_recovery": True,
    },
    "ECLIPSE_INDUCED_POWER_DROP": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["monitor_soc", "preheat_critical_zones"],
        "timeout_s": 60,
        "auto_recovery": True,
    },
    "THERMAL_RUNAWAY_MULTI_ZONE": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["reduce_power_load", "check_coolant_loop", "activate_radiators"],
        "timeout_s": 30,
        "auto_recovery": True,
    },
    "BEARING_DEGRADATION": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["schedule_wheel_replacement", "switch_backup_adcs"],
        "timeout_s": 300,
        "auto_recovery": True,
    },
    "COMMS_ANTENNA_MISPOINT": {
        "level": FDIRLevel.SYSTEM,
        "actions": ["repoint_antenna", "switch_to_lga"],
        "timeout_s": 60,
        "auto_recovery": True,
    },
}


class FDIRManager:
    """Manages fault detection, isolation, and recovery responses.

    Subscribes to anomaly correlation events and maps them to FDIR responses.
    Tracks active faults and coordinates recovery.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        # Autonomy audit F9 — maintain a list of FaultRecords per
        # root_cause so a re-fault doesn't get silently dropped.
        self._active_faults: dict[str, list[FaultRecord]] = {}
        self._fault_history: list[FaultRecord] = []
        # Autonomy audit F34 — persisted counter so fault IDs do not
        # collide across restarts.
        self._counter_lock = threading.Lock()
        self._counter_path = self._default_counter_path()
        self._fault_counter: int = self._load_counter()

        # Deterministic recovery plan library (PLEXIL/SMART-FAIL inspired).
        # Checked BEFORE LLM reasoning for known fault patterns.
        # Unknown faults still escalate to LLM via _on_correlation.
        # Recovery audit R-5: pass the running asyncio loop so the
        # dispatcher can ``run_coroutine_threadsafe`` onto MessageBus
        # from any thread (recovery plans run synchronously inside a
        # subscriber callback whose loop context can vary).
        try:
            from aria.safety.fdir_recovery_plans import build_standard_library
            try:
                import asyncio as _asyncio
                _loop = _asyncio.get_event_loop()
            except RuntimeError:
                _loop = None
            self.recovery_library = build_standard_library(
                event_bus=bus, asyncio_loop=_loop,
            )
        except Exception as exc:
            # R65 (2026-04-24): was silent — when the import / build
            # failed (typo, missing dep, config error) FDIR degraded
            # straight to LLM-only reasoning with zero deterministic
            # plans and no operator warning.  Now logged prominently.
            import structlog
            structlog.get_logger().error(
                "fdir.recovery_library_init_failed",
                error=f"{type(exc).__name__}: {exc}",
                impact="deterministic recovery plans unavailable; falling back to LLM-only",
            )
            self.recovery_library = None

    async def start(self) -> None:
        """Subscribe to anomaly correlation events."""
        self._bus.subscribe("aria.anomaly.correlation", self._on_correlation)
        logger.info("fdir.started")

    async def stop(self) -> None:
        pass

    async def _on_correlation(self, message: Message) -> None:
        """Handle a root-cause correlation — trigger FDIR response."""
        payload = message.payload
        root_cause = payload.get("root_cause", "UNKNOWN")
        severity = payload.get("severity", "WARNING")
        confidence = payload.get("confidence", 0.0)
        channels = payload.get("involved_channels", [])

        # Only respond to high-confidence correlations
        if confidence < 0.70:
            return

        response = FAULT_RESPONSES.get(root_cause, {})
        # Autonomy audit F9 — allow re-fault when the prior entry is
        # older than ``_REFAULT_STALENESS_MULT`` × its response timeout.
        # This catches the case where a recovery message was lost and
        # the fault recurs for real.
        prior = self._active_faults.get(root_cause, [])
        if prior:
            staleness_s = float(response.get(
                "timeout_s", _REFAULT_DEFAULT_STALENESS_S,
            )) * _REFAULT_STALENESS_MULT
            most_recent = max(p.detected_at for p in prior)
            if (time.time() - most_recent) < staleness_s:
                # Genuinely concurrent; the prior FDIR response is
                # still fresh.
                return
            logger.warning("fdir.refault_after_stale",
                           root_cause=root_cause,
                           staleness_s=round(time.time() - most_recent, 1))

        # Create fault record (autonomy F34 — persistent counter).
        with self._counter_lock:
            self._fault_counter += 1
            fault_id = f"FDIR-{self._fault_counter:06d}"
            self._persist_counter()

        fdir_level = response.get("level", SEVERITY_TO_FDIR.get(severity, FDIRLevel.SYSTEM))
        actions = response.get("actions", ["monitor", "alert_crew"])

        # Autonomy audit F34 — guard channel parsing.
        try:
            subsystem = channels[0].split(".")[0] if channels else "unknown"
        except (AttributeError, TypeError):
            subsystem = "unknown"
        fault = FaultRecord(
            fault_id=fault_id,
            fault_type=root_cause,
            subsystem=subsystem,
            fdir_level=fdir_level,
            severity=severity,
            description=payload.get("description", f"Root cause: {root_cause}"),
            response_actions=actions,
        )

        self._active_faults.setdefault(root_cause, []).append(fault)

        # Recovery audit R-23: skip recovery if the responsible
        # component is already in the dead-component registry and the
        # cooldown window has not yet elapsed — otherwise we would
        # repeatedly retry hardware that has been retired from
        # service, causing a recurring crash and audit-log spam.
        # Wiring audit Pass 1 (F6.1) — narrow the broad ``except``
        # that previously masked any error from the dead-component
        # registry. We now distinguish:
        #   * ImportError / OSError → registry not available;
        #     proceed with recovery (default-permissive).
        #   * Any other exception → fail-safe: do not retry.
        # Without this, a misbehaving registry that raised RuntimeError
        # would let FDIR continue retrying known-dead components.
        from aria.safety.dead_component_registry import (
            get_dead_component_registry,
        )
        try:
            _dead = get_dead_component_registry()
        except (ImportError, OSError) as exc:
            _dead = None
            logger.warning("fdir.dead_registry_unavailable", error=str(exc))

        if _dead is not None:
            try:
                _is_dead = _dead.is_dead(fault.subsystem)
                _can_retry = _dead.can_retry(fault.subsystem) if _is_dead else True
            except Exception as exc:    # noqa: BLE001
                # Fail-safe: treat registry errors as "do not retry"
                # rather than letting a recurring crash slip through.
                logger.error(
                    "fdir.dead_registry_error_fail_safe",
                    error=f"{type(exc).__name__}: {exc}",
                    component=fault.subsystem,
                )
                _is_dead = True
                _can_retry = False

            if _is_dead and not _can_retry:
                logger.warning("fdir.skipping_dead_component",
                               component=fault.subsystem,
                               root_cause=root_cause)
                # Wiring audit Pass 1 (F8.1) — failing silent for the
                # operator is wrong even when failing-silent for the
                # component is right. Publish a suppression event so
                # operators see that an active fault is being
                # intentionally not-recovered against retired hardware.
                await self._bus.publish(
                    Message(
                        topic="aria.fdir.suppressed_dead_component",
                        payload={
                            "fault_id": fault_id,
                            "fault_type": root_cause,
                            "component": fault.subsystem,
                            "severity": severity,
                            "reason": "component is in dead-component registry",
                        },
                        priority=EventPriority.P1_CRITICAL,
                        source_agent="fdir_manager",
                    )
                )
                return

        # Try deterministic recovery plan first (no LLM needed).
        # Only escalate to LLM reasoning if no plan matches.
        if self.recovery_library is not None:
            plan = self.recovery_library.find_matching_plan(
                fault_name=root_cause,
                severity=str(severity).lower(),
                subsystem=fault.subsystem,
            )
            if plan is not None:
                result = self.recovery_library.execute(plan)
                logger.info(
                    "fdir.recovery_executed",
                    plan=plan.name,
                    success=result.success,
                    steps=f"{result.steps_completed}/{result.total_steps}",
                )
                # Tag the fault with the plan that handled it
                fault.response_actions = fault.response_actions + [
                    f"recovery_plan:{plan.name}"
                ]
                # Wiring audit Pass 1 (F8.2) — when the deterministic
                # recovery plan FAILS, do not silently hand control
                # back to LLM reasoning. Publish an emergency event
                # and request a safe-mode demotion so a hardware fault
                # whose canned recovery did not work cannot continue
                # to be retried by autonomy at full authority.
                if not result.success:
                    logger.error(
                        "fdir.recovery_plan_failed",
                        plan=plan.name,
                        failed_step=result.failed_step,
                        error=result.error,
                        step_errors=result.step_errors,
                    )
                    await self._bus.publish(
                        Message(
                            topic="aria.emergency.fdir_recovery_failed",
                            payload={
                                "fault_id": fault_id,
                                "fault_type": root_cause,
                                "plan": plan.name,
                                "failed_step": result.failed_step,
                                "error": result.error,
                                "step_errors": result.step_errors,
                            },
                            priority=EventPriority.P0_EMERGENCY,
                            source_agent="fdir_manager",
                        )
                    )
                    await self._bus.publish(
                        Message(
                            topic="aria.safety.request_safe_mode",
                            payload={
                                "target_level": "REDUCED_AUTONOMY",
                                "reason": (
                                    f"fdir_recovery_failed:{plan.name}:"
                                    f"{result.failed_step or 'multiple_steps'}"
                                ),
                            },
                            priority=EventPriority.P0_EMERGENCY,
                            source_agent="fdir_manager",
                        )
                    )

        # Publish FDIR response
        await self._bus.publish(
            Message(
                topic="aria.fdir.response",
                payload={
                    "fault_id": fault_id,
                    "fault_type": root_cause,
                    "fdir_level": fdir_level,
                    "severity": severity,
                    "confidence": confidence,
                    "actions": actions,
                    "auto_recovery": response.get("auto_recovery", False),
                    "timeout_s": response.get("timeout_s", 30),
                    "channels": channels,
                },
                priority=EventPriority.P0_EMERGENCY if severity in ("CRITICAL", "EMERGENCY") else EventPriority.P1_CRITICAL,
                source_agent="fdir_manager",
            )
        )

        logger.warning(
            "fdir.response_triggered",
            fault_id=fault_id,
            fault_type=root_cause,
            level=fdir_level,
            actions=actions,
        )

    async def resolve_fault(self, fault_type: str, recovery_method: str = "auto") -> bool:
        """Mark a fault as resolved.

        Autonomy audit F9 — when multiple FaultRecords share a
        root_cause we resolve the OLDEST first so a re-fault stays
        observable until it is itself resolved.

        Recovery audit R-16: also append to the persistent JSONL
        history so a process restart does not lose the trace.
        """
        bucket = self._active_faults.get(fault_type)
        if not bucket:
            return False
        fault = bucket.pop(0)
        if not bucket:
            self._active_faults.pop(fault_type, None)

        fault.recovered = True
        fault.recovered_at = time.time()
        fault.recovery_method = recovery_method
        self._fault_history.append(fault)
        self._persist_history_record(fault)

        # Keep history bounded
        if len(self._fault_history) > 500:
            self._fault_history = self._fault_history[-500:]

        await self._bus.publish(
            Message(
                topic="aria.fdir.resolved",
                payload={
                    "fault_id": fault.fault_id,
                    "fault_type": fault_type,
                    "recovery_method": recovery_method,
                    "duration_s": round(fault.recovered_at - fault.detected_at, 1),
                },
                source_agent="fdir_manager",
            )
        )

        logger.info("fdir.fault_resolved", fault_id=fault.fault_id, fault_type=fault_type)
        return True

    @property
    def active_faults(self) -> list[FaultRecord]:
        out: list[FaultRecord] = []
        for bucket in self._active_faults.values():
            out.extend(bucket)
        return out

    @property
    def fault_history(self) -> list[FaultRecord]:
        return list(self._fault_history)

    # ── Persistent fault counter (autonomy audit F34) ──────────

    @staticmethod
    def _default_counter_path() -> Path:
        env = os.environ.get("ARIA_RUNTIME_DIR")
        base = Path(env) if env else Path(__file__).resolve().parents[3] / "data" / "runtime"
        return base / "fdir_counter.json"

    def _load_counter(self) -> int:
        path = self._counter_path
        if not path.is_file():
            return 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            return int(d.get("counter", 0))
        except Exception as exc:    # noqa: BLE001
            logger.warning("fdir.counter_load_failed", error=str(exc))
            return 0

    def _persist_counter(self) -> None:
        path = self._counter_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"counter": self._fault_counter}, f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("fdir.counter_persist_failed", error=str(exc))

    # ── Persistent fault history (Recovery audit R-16) ──────────

    def _history_path(self) -> Path:
        return self._counter_path.parent / "fdir_history.jsonl"

    def _persist_history_record(self, fault: FaultRecord) -> None:
        """Append-only JSONL persistence for resolved faults.

        Append-only is intentional: the file IS the audit trail.
        Rotation happens externally (logrotate-style) on operator
        request, not by truncating in place.
        """
        path = self._history_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "fault_id": fault.fault_id,
                "fault_type": fault.fault_type,
                "subsystem": fault.subsystem,
                "fdir_level": int(fault.fdir_level),
                "severity": fault.severity,
                "detected_at": fault.detected_at,
                "recovered_at": fault.recovered_at,
                "recovery_method": fault.recovery_method,
                "actions": list(fault.response_actions),
            }
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
        except OSError as exc:
            logger.warning("fdir.history_persist_failed", error=str(exc))
