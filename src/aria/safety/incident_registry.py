"""IncidentRegistry — open / track / close incidents with correlation IDs.

R34 Phase 3. Closes the "trace this alert back to its root cause" gap
the user raised. Every detected event that warrants attention opens
an Incident; every related downstream event (operator approval, fix
applied, RCA finding) carries the same ``incident_id`` and can be
walked through the hash-chained audit log.

Lifecycle::

    Detected → OPEN → (mode-specific work) → RESOLVED | DEFERRED | ESCALATED

  open()       creates an Incident, decides response mode via the
               sealed policy, writes an audit "incident.opened" entry
               with the new incident_id, and publishes
               aria.incident.opened on the bus
  attach()     write any operator/agent-supplied note + audit entry
               with this incident_id
  apply_fix()  record a fix attempt + audit entry
  set_root_cause()  store the operator-confirmed RCA finding
  resolve()    close as resolved + audit entry
  escalate()   change mode → HUMAN_DECIDE + page operator

The incident_id is a short prefix-tagged UUID (``inc_xxxxxxxxxxxx``) so
it stands out in audit logs and is easy to grep.

The registry persists to ``data/runtime/incidents.jsonl`` so an active
incident survives a restart. The audit chain remains the source of
truth for *what happened* — this file is just an indexed view for the
operator UI.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


# ── Status ────────────────────────────────────────────────────────


class IncidentStatus(str, Enum):
    OPEN = "OPEN"           # detected + active
    RESOLVED = "RESOLVED"   # fix verified, normal ops resumed
    DEFERRED = "DEFERRED"   # logged for later (low priority / off-scope)
    ESCALATED = "ESCALATED" # escalated to a higher decision mode (rare)


# ── Records ──────────────────────────────────────────────────────


@dataclass
class FixAttempt:
    ts: float
    actor_principal_id: str
    summary: str
    success: bool


@dataclass
class Incident:
    incident_id: str
    incident_class: str       # IncidentClass.value
    controllability: str      # Controllability.value or ""
    severity: str             # info | warning | critical | emergency
    response_mode: str        # ResponseMode.value
    rule_name: str            # which sealed-policy rule matched
    title: str                # short human label
    detail: Dict[str, Any]    # opaque metadata from the source
    source: str               # subsystem that opened it
    opened_at: float
    status: str = IncidentStatus.OPEN.value
    root_cause: str = ""
    closed_at: float = 0.0
    notes: List[Dict[str, Any]] = field(default_factory=list)
    fixes: List[FixAttempt] = field(default_factory=list)
    # R35: trace_id at the moment the incident was opened — links the
    # incident to whatever flow was happening when it was detected
    # (HTTP request, scheduler tick, bus event chain).
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ── Locating the runtime store ────────────────────────────────────


def _default_runtime_dir() -> Path:
    env = os.environ.get("ARIA_RUNTIME_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    return (here.parents[3] / "data" / "runtime").resolve()


# ── Registry ─────────────────────────────────────────────────────


def _new_incident_id() -> str:
    """``inc_`` + 12 hex chars (48 bits). Short enough to read aloud,
    long enough to avoid collision in the lifetime of one mission."""
    return "inc_" + secrets.token_hex(6)


class IncidentRegistry:
    """In-memory map of open + recently-closed incidents, mirrored to
    a JSONL file for restart durability."""

    JSONL_FILENAME = "incidents.jsonl"
    KEEP_RECENT_CLOSED = 1000   # ring-buffer cap for closed incidents

    def __init__(
        self,
        runtime_dir: Optional[Path] = None,
        *,
        publish_fn: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self._runtime_dir = (runtime_dir or _default_runtime_dir()).resolve()
        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._runtime_dir / self.JSONL_FILENAME
        self._publish = publish_fn or (lambda topic, payload: None)
        self._lock = threading.RLock()
        self._open: Dict[str, Incident] = {}
        self._closed: List[Incident] = []
        if self._path.is_file():
            self._load()

    def set_publish_fn(
        self,
        publish_fn: Optional[Callable[[str, dict], None]],
    ) -> None:
        """Wiring audit Pass 1 (F6.2 + F10.4) — late-bind the publish
        callable on an existing singleton.  Used by main.py to swap
        the simulator-default publisher for the production
        MessageBus adapter without losing accumulated incident state.
        """
        with self._lock:
            self._publish = publish_fn or (lambda topic, payload: None)

    # ── Public lifecycle ────────────────────────────────────────

    def open(
        self,
        *,
        title: str,
        incident_class,            # IncidentClass enum
        controllability=None,      # Controllability enum or None
        severity: str = "warning",
        source: str = "",
        detail: Optional[Dict[str, Any]] = None,
    ) -> Incident:
        """Create a new incident. The sealed policy decides
        ``response_mode``; that decision is logged so the operator can
        audit *why* the runtime chose AUTO_STABILIZE vs HOLD_AND_RCA.
        """
        from aria.safety.incident_policy import (
            decide_response_mode, IncidentClass, Controllability,
        )
        from aria.security.audit import log_event

        ic = (incident_class if isinstance(incident_class, IncidentClass)
              else IncidentClass(str(incident_class)))
        ctl = None
        if controllability is not None:
            ctl = (controllability if isinstance(controllability, Controllability)
                   else Controllability(str(controllability)))
        decision = decide_response_mode(ic, ctl)
        incident_id = _new_incident_id()
        # R35: capture the active trace_id so the incident record
        # itself is reachable from the originating flow.
        try:
            from aria.security.trace_context import current_trace_id
            captured_trace = current_trace_id(mint_if_absent=False)
        except Exception:
            captured_trace = ""
        inc = Incident(
            incident_id=incident_id,
            incident_class=ic.value,
            controllability=ctl.value if ctl else "",
            severity=severity,
            response_mode=decision.mode.value,
            rule_name=decision.rule_name,
            title=title,
            detail=dict(detail or {}),
            source=source or "unknown",
            opened_at=time.time(),
            trace_id=captured_trace,
        )
        with self._lock:
            self._open[incident_id] = inc
            self._append_to_file(inc)
        # Audit + bus.
        log_event(
            event_type="incident",
            identity=source or "system",
            action="incident.opened",
            result=decision.mode.value,
            details={
                "title": title,
                "class": ic.value,
                "controllability": ctl.value if ctl else None,
                "rule_name": decision.rule_name,
                "rule_description": decision.description,
                **dict(detail or {}),
            },
            incident_id=incident_id,
            severity=severity,
            source=source,
        )
        try:
            self._publish("aria.incident.opened", {
                "incident_id": incident_id,
                "class": ic.value,
                "response_mode": decision.mode.value,
                "rule_name": decision.rule_name,
                "title": title,
                "severity": severity,
            })
        except Exception as exc:
            logger.warning("incident.publish_failed", error=str(exc))
        logger.info("incident.opened",
                    incident_id=incident_id,
                    class_=ic.value,
                    response_mode=decision.mode.value,
                    rule=decision.rule_name)
        return inc

    def attach_note(
        self,
        incident_id: str,
        *,
        actor_principal_id: str,
        text: str,
    ) -> bool:
        from aria.security.audit import log_event
        with self._lock:
            inc = self._open.get(incident_id)
            if inc is None:
                return False
            inc.notes.append({
                "ts": time.time(),
                "actor_principal_id": actor_principal_id,
                "text": text,
            })
            self._append_to_file(inc)
        log_event(
            event_type="incident",
            identity=actor_principal_id,
            action="incident.note",
            result="ok",
            details={"text": text},
            incident_id=incident_id,
            severity="info",
            source=actor_principal_id,
        )
        return True

    def apply_fix(
        self,
        incident_id: str,
        *,
        actor_principal_id: str,
        summary: str,
        success: bool,
    ) -> bool:
        from aria.security.audit import log_event
        with self._lock:
            inc = self._open.get(incident_id)
            if inc is None:
                return False
            inc.fixes.append(FixAttempt(
                ts=time.time(),
                actor_principal_id=actor_principal_id,
                summary=summary,
                success=success,
            ))
            self._append_to_file(inc)
        log_event(
            event_type="incident",
            identity=actor_principal_id,
            action="incident.fix_applied",
            result="success" if success else "failed",
            details={"summary": summary},
            incident_id=incident_id,
            severity="warning" if success else "critical",
            source=actor_principal_id,
        )
        return True

    def set_root_cause(
        self,
        incident_id: str,
        *,
        actor_principal_id: str,
        text: str,
    ) -> bool:
        from aria.security.audit import log_event
        with self._lock:
            inc = self._open.get(incident_id)
            if inc is None:
                return False
            inc.root_cause = text
            self._append_to_file(inc)
        log_event(
            event_type="incident",
            identity=actor_principal_id,
            action="incident.root_cause_set",
            result="ok",
            details={"root_cause": text},
            incident_id=incident_id,
            severity="warning",
            source=actor_principal_id,
        )
        return True

    def resolve(
        self,
        incident_id: str,
        *,
        actor_principal_id: str,
        resolution: str = "",
    ) -> bool:
        return self._close(
            incident_id, IncidentStatus.RESOLVED,
            actor_principal_id=actor_principal_id,
            resolution=resolution,
        )

    def defer(
        self,
        incident_id: str,
        *,
        actor_principal_id: str,
        reason: str = "",
    ) -> bool:
        return self._close(
            incident_id, IncidentStatus.DEFERRED,
            actor_principal_id=actor_principal_id,
            resolution=reason,
        )

    def _close(
        self,
        incident_id: str,
        status: IncidentStatus,
        *,
        actor_principal_id: str,
        resolution: str,
    ) -> bool:
        from aria.security.audit import log_event
        with self._lock:
            inc = self._open.pop(incident_id, None)
            if inc is None:
                return False
            inc.status = status.value
            inc.closed_at = time.time()
            self._closed.append(inc)
            if len(self._closed) > self.KEEP_RECENT_CLOSED:
                self._closed = self._closed[-self.KEEP_RECENT_CLOSED:]
            self._append_to_file(inc)
        log_event(
            event_type="incident",
            identity=actor_principal_id,
            action=f"incident.{status.value.lower()}",
            result=status.value,
            details={"resolution": resolution},
            incident_id=incident_id,
            severity="info",
            source=actor_principal_id,
        )
        try:
            self._publish("aria.incident.closed", {
                "incident_id": incident_id,
                "status": status.value,
                "actor_principal_id": actor_principal_id,
            })
        except Exception:
            pass
        return True

    # ── Read-only views ─────────────────────────────────────────

    def get(self, incident_id: str) -> Optional[Incident]:
        with self._lock:
            inc = self._open.get(incident_id)
            if inc is not None:
                return inc
            for c in reversed(self._closed):
                if c.incident_id == incident_id:
                    return c
            return None

    def list_open(self) -> List[Incident]:
        with self._lock:
            return list(self._open.values())

    def list_closed(self, limit: int = 100) -> List[Incident]:
        with self._lock:
            return list(self._closed[-limit:])

    def stats(self) -> Dict[str, int]:
        with self._lock:
            by_class: Dict[str, int] = {}
            by_mode: Dict[str, int] = {}
            for inc in self._open.values():
                by_class[inc.incident_class] = by_class.get(inc.incident_class, 0) + 1
                by_mode[inc.response_mode] = by_mode.get(inc.response_mode, 0) + 1
            return {
                "open": len(self._open),
                "closed_recent": len(self._closed),
                **{f"open.class.{k}": v for k, v in by_class.items()},
                **{f"open.mode.{k}": v for k, v in by_mode.items()},
            }

    # ── Persistence ─────────────────────────────────────────────

    def _append_to_file(self, inc: Incident) -> None:
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(inc.to_dict(),
                                   sort_keys=True, ensure_ascii=True) + "\n")
        except OSError as exc:
            logger.error("incident.persist_failed", error=str(exc))

    def _load(self) -> None:
        """Replay the JSONL into the in-memory state. Each incident
        appears multiple times (once per mutation); the LAST line wins.

        Wiring audit Pass 1 (F3.1) — bad lines no longer poison the
        whole load. A single corrupt or future-schema line is logged
        and skipped; valid records still hydrate. Previously a
        ``FixAttempt(**f)`` TypeError on one record dropped EVERY
        incident in the file via the broad ``except Exception``.
        """
        latest: Dict[str, Dict[str, Any]] = {}
        try:
            with open(self._path, "r", encoding="utf-8") as fp:
                for line_index, raw_line in enumerate(fp, start=1):
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning("incident.load_skip_bad_line",
                                       line=line_index, error=str(exc))
                        continue
                    incident_id = record.get("incident_id", "")
                    if incident_id:
                        latest[incident_id] = record
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.error("incident.load_io_failed", error=str(exc))
            return

        skipped = 0
        with self._lock:
            for record in latest.values():
                try:
                    fixes = [
                        FixAttempt(**fix_record)
                        for fix_record in record.get("fixes", [])
                    ]
                    inc = Incident(
                        incident_id=record["incident_id"],
                        incident_class=record.get("incident_class", ""),
                        controllability=record.get("controllability", ""),
                        severity=record.get("severity", "info"),
                        response_mode=record.get("response_mode", "OBSERVE_ONLY"),
                        rule_name=record.get("rule_name", ""),
                        title=record.get("title", ""),
                        detail=record.get("detail", {}),
                        source=record.get("source", ""),
                        opened_at=float(record.get("opened_at", 0.0)),
                        status=record.get("status", "OPEN"),
                        root_cause=record.get("root_cause", ""),
                        closed_at=float(record.get("closed_at", 0.0)),
                        notes=list(record.get("notes", [])),
                        fixes=fixes,
                        trace_id=record.get("trace_id", ""),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    skipped += 1
                    logger.warning(
                        "incident.load_skip_record",
                        incident_id=record.get("incident_id", "?"),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    continue

                if inc.status == "OPEN":
                    self._open[inc.incident_id] = inc
                else:
                    self._closed.append(inc)
        if skipped:
            logger.warning(
                "incident.load_partial",
                loaded=len(self._open) + len(self._closed),
                skipped=skipped,
            )


# ── Singleton ────────────────────────────────────────────────────


_INSTANCE: Optional[IncidentRegistry] = None
_LOCK = threading.RLock()


def configure_incident_registry(
    publish_fn: Optional[Callable[[str, dict], None]] = None,
) -> "IncidentRegistry":
    """Wiring audit Pass 1 (F6.2 + F10.4) — explicit constructor for
    the singleton.  Lets ``main.py`` inject a publish callable that
    targets the production ``MessageBus`` (via the ``publish_compat``
    adapter), instead of having ``get_incident_registry`` reach into
    the simulator-only event bus.

    Idempotent in the sense that the singleton identity is preserved
    across calls — but a second call WILL re-bind ``publish_fn`` on
    the existing instance.  This matters because the coordinator's
    construction path may trigger ``get_incident_registry()`` (which
    instantiates with the simulator-default publisher) before
    ``main.py`` gets a chance to call this; without the late-bind
    the production publisher would silently never replace the
    simulator one.
    """
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = IncidentRegistry(publish_fn=publish_fn)
        else:
            _INSTANCE.set_publish_fn(publish_fn)
    return _INSTANCE


def get_incident_registry() -> IncidentRegistry:
    """Return the configured singleton, or build a default one.

    The default-construction path tries to wire to the simulator's
    event bus for backward compat with tests / dev scripts that don't
    call ``configure_incident_registry``. Production code should call
    ``configure_incident_registry`` from ``main.py`` to ensure the
    registry publishes onto the real MessageBus.
    """
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                # Wiring audit Pass 1 (F6.2): if the simulator import
                # fails (missing in production), construct without a
                # publish_fn so events still log/persist locally —
                # better than silently dropping every incident.
                publish: Optional[Callable[[str, dict], None]] = None
                try:
                    from aria.simulator.event_bus import get_event_bus
                    bus = get_event_bus()

                    def publish(topic, payload):    # noqa: F811
                        bus.publish(
                            topic,
                            severity="warning",
                            payload=payload,
                            source="incident_registry",
                        )
                except (ImportError, OSError) as exc:
                    logger.warning(
                        "incident_registry.simulator_bus_unavailable",
                        error=str(exc),
                        note="constructing without publish_fn — call "
                             "configure_incident_registry(publish_fn=...) "
                             "from main.py to wire onto the production bus",
                    )
                _INSTANCE = IncidentRegistry(publish_fn=publish)
    return _INSTANCE


def reset_for_test(
    runtime_dir: Optional[Path] = None,
    *,
    publish_fn: Optional[Callable[[str, dict], None]] = None,
) -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = IncidentRegistry(
            runtime_dir=runtime_dir, publish_fn=publish_fn,
        )
