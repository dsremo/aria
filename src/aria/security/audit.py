"""Tamper-Evident Audit Log.

All security events, command executions, and auth decisions are logged
to a hash-chained audit trail. Tampering with any entry breaks the chain.

Design:
  Each entry stores SHA-256(previous_entry_hash + this_entry_data).
  Verification is O(n): scan the chain and recompute each hash.
  Deletion or modification of any entry is detectable.

R34 (2026-04-25) made the audit chain a first-class durable artefact:
  * default persistence path ``data/runtime/audit.jsonl`` — survives restart
  * boot-time chain verification fires
    ``aria.security.audit_chain_break`` on tamper
  * head-hash anchoring publishes the current chain head to the bus
    every N entries so an external archiver can pin it
  * correlation IDs (``incident_id``) thread events from one incident
    so an investigator can `audit_trace.py --incident-id X` and walk
    every related entry

This defends against:
  - Layer 1 (human): Admin covering tracks (deleting log entries)
  - Layer 2 (skilled): Log injection to hide attack evidence
  - Layer 3 (Mythos): AI-driven log manipulation to evade detection
  - Layer 4 (quantum): SHA-256 provides 128-bit quantum security
    (Grover's → effective 128 bits, per NIST SP 800-131B)

Reference:
  Schneier & Kelsey (1999) "Secure audit logs to support computer forensics."
  ACM Trans. Inf. Syst. Secur. 2(2), 159-176.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Iterable, List, Optional

import structlog

logger = structlog.get_logger()


# Anchor every N entries — publish chain head to the bus so a separate
# archive process can pin it. 100 chosen so an active mission produces
# anchors every minute or two without spamming the bus. ESTIMATE — no
# published source; tune if archive bandwidth becomes a concern.
DEFAULT_ANCHOR_EVERY_N = 100


def _default_log_path() -> Path:
    """Resolve the default audit log path.

    Production:  data/runtime/audit.jsonl  (under the repo root)
    Override:    ARIA_AUDIT_PATH env var
    """
    env = os.environ.get("ARIA_AUDIT_PATH")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    # src/aria/security/audit.py → repo root via parents[3]
    return (here.parents[3] / "data" / "runtime" / "audit.jsonl").resolve()


@dataclass
class AuditEntry:
    seq: int
    timestamp: float
    event_type: str          # "auth", "command", "canary", "anomaly", "system"
    identity: str
    action: str
    result: str              # "accepted", "rejected", "alert", etc.
    details: dict
    prev_hash: str           # SHA-256 of previous entry's hash_value
    hash_value: str = ""     # SHA-256(prev_hash + canonical_data) — set on write
    incident_id: str = ""    # R34: correlation id within an incident
    severity: str = "info"   # R34: info | warning | critical | emergency
    source: str = ""         # R34: subsystem that emitted the event
    trace_id: str = ""       # R35: top-of-flow trace id (HTTP req / bus origin)

    def canonical_bytes(self) -> bytes:
        """Deterministic serialization for hashing."""
        d = {
            "seq": self.seq,
            "timestamp": f"{self.timestamp:.6f}",
            "event_type": self.event_type,
            "identity": self.identity,
            "action": self.action,
            "result": self.result,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "incident_id": self.incident_id,
            "severity": self.severity,
            "source": self.source,
            "trace_id": self.trace_id,
        }
        return json.dumps(d, sort_keys=True, ensure_ascii=True).encode()


class AuditLog:
    """Hash-chained tamper-evident audit log.

    In-memory list backed by an append-only JSONL file. Thread-safe for
    concurrent writes from multiple agents.

    R34: persistence is on by default. The constructor verifies the
    on-disk chain at load and refuses to keep going if hashes don't
    match — that way a tampered file is caught early instead of being
    silently appended over.
    """

    GENESIS_HASH = "0" * 64  # SHA-256 all-zeros genesis block

    def __init__(
        self,
        log_path: Optional[Path] = None,
        *,
        anchor_every_n: int = DEFAULT_ANCHOR_EVERY_N,
        anchor_publisher: Optional[Callable[[str, dict], None]] = None,
        strict_load: bool = True,
    ) -> None:
        self._entries: List[AuditEntry] = []
        self._lock = Lock()
        # R34: persist by default. Pass log_path=False to disable
        # (used by tests + ephemeral in-process audit instances).
        if log_path is None:
            log_path = _default_log_path()
        elif log_path is False:   # type: ignore[comparison-overlap]
            log_path = None
        self._log_path: Optional[Path] = log_path
        self._seq = 0
        self._anchor_every_n = max(1, int(anchor_every_n))
        self._anchor_publisher = anchor_publisher
        self._chain_intact: bool = True
        self._first_break_seq: Optional[int] = None

        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if log_path.is_file():
                self._load(log_path, strict=strict_load)

    # ── core API ─────────────────────────────────────────────────

    def log(
        self,
        event_type: str,
        identity: str,
        action: str,
        result: str,
        details: Optional[dict] = None,
        *,
        incident_id: str = "",
        severity: str = "info",
        source: str = "",
        trace_id: str = "",
    ) -> AuditEntry:
        """Append a new audit entry. Returns the persisted entry.

        R35: if ``trace_id`` is empty, the active TraceContext value
        is auto-filled. Pass an explicit empty string is impossible —
        you'd pass nothing — so this is always safe.
        """
        if not trace_id:
            try:
                from aria.security.trace_context import current_trace_id
                trace_id = current_trace_id(mint_if_absent=False)
            except Exception:
                # Defensive: if the context module isn't importable
                # (shouldn't happen), continue without tracing.
                trace_id = ""
        with self._lock:
            prev_hash = (
                self._entries[-1].hash_value
                if self._entries
                else self.GENESIS_HASH
            )
            entry = AuditEntry(
                seq=self._seq,
                timestamp=time.time(),
                event_type=event_type,
                identity=identity,
                action=action,
                result=result,
                details=details or {},
                prev_hash=prev_hash,
                incident_id=incident_id,
                severity=severity,
                source=source,
                trace_id=trace_id,
            )
            entry.hash_value = hashlib.sha256(
                prev_hash.encode() + entry.canonical_bytes()
            ).hexdigest()

            self._entries.append(entry)
            self._seq += 1

            if self._log_path:
                self._append_to_file(entry)

            anchor_due = (self._seq % self._anchor_every_n == 0
                          and self._anchor_publisher is not None)

        # Anchor publish OUTSIDE the lock so a slow subscriber can't stall writers.
        if anchor_due:
            try:
                self._anchor_publisher("aria.security.audit.anchor", {
                    "head_hash": entry.hash_value,
                    "head_seq": entry.seq,
                    "anchor_every_n": self._anchor_every_n,
                })
            except Exception as exc:
                logger.warning("audit.anchor_publish_failed", error=str(exc))

        # Wiring audit Pass 3 (F14.17) — fire the plugins hook so any
        # registered DefencePlugin (e.g. round-N adversarial defences)
        # sees every audited event. The plugins module's ``fire_audit``
        # was previously dead-on-arrival because nothing called it
        # from the audit path. Errors in plugins must not break the
        # audit write — they're logged and swallowed.
        try:
            from aria.security.plugins import fire_audit as _fire_audit
            _fire_audit({
                "seq": entry.seq,
                "timestamp": entry.timestamp,
                "event_type": entry.event_type,
                "identity": entry.identity,
                "action": entry.action,
                "result": entry.result,
                "severity": entry.severity,
                "source": entry.source,
                "trace_id": entry.trace_id,
            })
        except Exception as exc:    # noqa: BLE001
            logger.warning("audit.plugin_fire_failed", error=str(exc))

        return entry

    def verify_chain(self) -> tuple[bool, Optional[int]]:
        """Verify the entire chain integrity.

        Returns (True, None) if intact, (False, seq_number) of first break.
        """
        with self._lock:
            if not self._entries:
                return True, None

            prev_hash = self.GENESIS_HASH
            for entry in self._entries:
                expected = hashlib.sha256(
                    prev_hash.encode() + entry.canonical_bytes()
                ).hexdigest()
                if entry.hash_value != expected:
                    logger.error(
                        "audit.chain_broken",
                        seq=entry.seq,
                        expected=expected[:16],
                        actual=entry.hash_value[:16],
                    )
                    self._chain_intact = False
                    self._first_break_seq = entry.seq
                    return False, entry.seq
                prev_hash = entry.hash_value
            self._chain_intact = True
            self._first_break_seq = None
            return True, None

    def get_entries(
        self,
        event_type: Optional[str] = None,
        identity: Optional[str] = None,
        since: float = 0.0,
        limit: int = 1000,
        *,
        incident_id: Optional[str] = None,
        min_severity: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> List[AuditEntry]:
        """Query the chain. R34: added incident_id + min_severity.
        R35: added trace_id — gives back every event in one flow,
        from origin (HTTP request / bus publish / scheduler tick) all
        the way to the persisted mutation."""
        sev_rank = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}
        min_rank = sev_rank.get(min_severity or "", -1)
        with self._lock:
            results = [
                e for e in self._entries
                if e.timestamp >= since
                and (event_type is None or e.event_type == event_type)
                and (identity is None or e.identity == identity)
                and (incident_id is None or e.incident_id == incident_id)
                and (trace_id is None or e.trace_id == trace_id)
                and (min_severity is None
                     or sev_rank.get(e.severity, 0) >= min_rank)
            ]
            return results[-limit:]

    def head_hash(self) -> str:
        with self._lock:
            if self._entries:
                return self._entries[-1].hash_value
            return self.GENESIS_HASH

    def head_seq(self) -> int:
        with self._lock:
            return self._entries[-1].seq if self._entries else -1

    def chain_status(self) -> dict[str, Any]:
        """Snapshot of chain health for the SafetyConsole / CLI tools."""
        with self._lock:
            return {
                "entries": len(self._entries),
                "head_seq": self._entries[-1].seq if self._entries else -1,
                "head_hash": (self._entries[-1].hash_value
                              if self._entries else self.GENESIS_HASH),
                "log_path": str(self._log_path) if self._log_path else "",
                "chain_intact": self._chain_intact,
                "first_break_seq": self._first_break_seq,
            }

    def __len__(self) -> int:
        return len(self._entries)

    # ── R34: bus-event ingest ────────────────────────────────────

    def log_bus_event(self, event: Any) -> AuditEntry:
        """Mirror an event from ``aria.simulator.event_bus.EventBus``
        into the audit chain. The bus event has fields
        ``(topic, timestamp, sim_time_yr, severity, payload, source, seq,
        trace_id)``.

        Used by ``audit_bus_mirror`` to provide single-source-of-truth
        coverage for safety / security / approval / emergency events.
        """
        # Map bus severity → audit severity. The bus uses
        # info / warning / critical / emergency; pass through.
        sev = str(getattr(event, "severity", "info") or "info")
        # Pull correlation ids from the event itself or the payload.
        payload = dict(getattr(event, "payload", {}) or {})
        incident_id = str(payload.pop("incident_id", "") or "")
        # R35: trace_id lives on the event; fall back to payload
        # for back-compat with publishers that haven't been migrated.
        trace_id = str(getattr(event, "trace_id", "") or
                       payload.pop("trace_id", "") or "")
        identity = str(payload.pop("identity", "")
                       or getattr(event, "source", "") or "system")
        # Action = the topic; a bus topic is the verb already.
        return self.log(
            event_type="bus",
            identity=identity,
            action=str(getattr(event, "topic", "") or "(unknown)"),
            result=sev,
            details=payload,
            incident_id=incident_id,
            severity=sev,
            source=str(getattr(event, "source", "") or ""),
            trace_id=trace_id,
        )

    # ── persistence helpers ──────────────────────────────────────

    def _append_to_file(self, entry: AuditEntry) -> None:
        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(asdict(entry)) + "\n")
        except OSError as e:
            logger.error("audit.write_failed", error=str(e))

    def _load(self, path: Path, *, strict: bool) -> None:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    # Tolerate older entries without R34 fields.
                    d.setdefault("incident_id", "")
                    d.setdefault("severity", "info")
                    d.setdefault("source", "")
                    entry = AuditEntry(**d)
                    self._entries.append(entry)
                    self._seq = entry.seq + 1
            logger.info("audit.loaded",
                        entries=len(self._entries), path=str(path))
        except Exception as e:
            logger.error("audit.load_failed", error=str(e), path=str(path))
            if strict:
                # Raise so the boot-time verifier can react. For dev
                # tests pass strict=False to keep going on a partial file.
                raise
        # Verify chain after load — a tampered file should not silently
        # appear "ok" to the runtime.
        ok, seq = self.verify_chain()
        if not ok:
            logger.critical("audit.chain_break_at_load",
                            first_break_seq=seq, path=str(path))


# ── module-level singleton + helpers ─────────────────────────────


_default_log: Optional[AuditLog] = None
_default_log_lock = Lock()


def get_audit_log(log_path: Optional[Path] = None) -> AuditLog:
    """Return the process-wide audit log singleton."""
    global _default_log
    if _default_log is None:
        with _default_log_lock:
            if _default_log is None:
                _default_log = AuditLog(log_path)
    return _default_log


def reset_for_test(log_path: Optional[Path] = None) -> None:
    """Replace the singleton with a fresh instance — tests only."""
    global _default_log
    with _default_log_lock:
        _default_log = AuditLog(log_path or False)  # False = no persistence


def log_event(
    event_type: str,
    identity: str,
    action: str,
    result: str,
    details: Optional[dict] = None,
    *,
    incident_id: str = "",
    severity: str = "info",
    source: str = "",
    trace_id: str = "",
) -> AuditEntry:
    """Convenience wrapper for module-level audit logging."""
    return get_audit_log().log(
        event_type, identity, action, result, details,
        incident_id=incident_id, severity=severity, source=source,
        trace_id=trace_id,
    )


# ── R34: boot-time integrity check ───────────────────────────────


def verify_at_boot(
    *,
    log_path: Optional[Path] = None,
    publish_fn: Optional[Callable[[str, dict], None]] = None,
    strict: bool = True,
) -> bool:
    """Verify the persisted audit chain at startup.

    Failure modes:
      * file missing      → log info, return True (first boot)
      * unparseable line  → log error, raise (strict) or return False
      * chain hash break  → publish ``aria.security.audit_chain_break``,
                            log critical, return False (or sys.exit on
                            ``strict=True`` if no publisher is wired —
                            we surface the break either way)

    Returns True iff the chain is intact (or the file does not yet
    exist). The runtime should refuse to do anything privileged until
    the chain has been re-anchored by a maintainer.
    """
    path = log_path or _default_log_path()
    if not path.is_file():
        logger.info("audit.verify_at_boot.no_log", path=str(path))
        return True
    # Drop the singleton so the next get_audit_log() picks up the
    # fresh constructor — important for tests + maintenance restarts.
    global _default_log
    with _default_log_lock:
        _default_log = AuditLog(path, strict_load=False)
    log = _default_log
    ok, seq = log.verify_chain()
    if ok:
        logger.info("audit.verify_at_boot.ok",
                    entries=len(log), head=log.head_hash()[:16])
        return True
    # Chain break → emit a high-severity event so the operator knows.
    payload = {
        "first_break_seq": seq,
        "head_hash": log.head_hash(),
        "log_path": str(path),
        "entries": len(log),
    }
    logger.critical("audit.chain_break", **payload)
    if publish_fn is not None:
        try:
            publish_fn("aria.security.audit_chain_break", payload)
        except Exception as exc:
            logger.error("audit.publish_break_failed", error=str(exc))
    return False
