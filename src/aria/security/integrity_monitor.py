"""Continuous Integrity Monitor (CIM) — runtime version of F-18.

The boot-time check in ``aria.boot.verify`` runs once and exits.  An
attacker who can write to disk *after* boot — e.g. a hostile debugger
attaching to the live process and patching a ``.py`` file via
``/proc/<pid>/fd/`` — would slip past F-18 entirely.

This module closes that gap.  A daemon thread re-hashes every protected
file every ``period_s`` (default 60 s) and compares against the sealed
``BOOT_MANIFEST.toml``.  A single mismatch:

  1. publishes ``aria.security.cim_mismatch`` on the bus (severity =
     critical) with the offending path + computed-vs-expected digest
     prefixes,
  2. logs a critical entry to the hash-chained audit log,
  3. invokes the on-mismatch callback so the runtime can transition
     to safe-mode within the 5 s requirement of R38 acceptance 1.1.

Reference:
    NIST SP 800-193 §3.4 "Detection — runtime integrity verification";
    Anderson & Kuhn (1996) "Tamper Resistance — A Cautionary Note".

Implements §F-18 (continuous, runtime variant) per R38 acceptance 1.1.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

from aria.boot.verify import (
    _aria_pkg_root,
    _default_manifest_path,
    _enumerate_protected_files,
    _parse_boot_manifest,
)

logger = structlog.get_logger()


# Default re-hash period — 60 s satisfies R38 acceptance "every 60 s".
# Longer wastes detection latency, shorter starts to compete with the
# main loop on small CPU-only deployments.
DEFAULT_PERIOD_S = 60.0

# Maximum allowed time from mismatch detection to on_mismatch callback
# completion.  R38 acceptance: "triggers safe-mode within 5 s".  This
# value is what the watchdog enforces.
MISMATCH_REACTION_BUDGET_S = 5.0


class IntegrityMonitor:
    """Periodically re-hash protected files; alert on mismatch.

    Stateless w.r.t. expected hashes — re-reads the manifest each
    sweep so a release-engineer rotation is picked up without restart.
    Stateful w.r.t. mismatches — once a mismatch fires the callback,
    further sweeps continue to log but do not re-fire the callback
    until ``acknowledge()`` is called by an operator.  This prevents
    a single tampered file from spamming the bus every 60 s.
    """

    def __init__(
        self,
        on_mismatch: Callable[[Dict[str, Any]], None],
        publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        period_s: float = DEFAULT_PERIOD_S,
        manifest_path: Optional[Path] = None,
        pkg_root: Optional[Path] = None,
    ) -> None:
        self._on_mismatch = on_mismatch
        self._publish = publish_fn or (lambda topic, payload: None)
        self._period_s = max(5.0, float(period_s))
        self._manifest_path = manifest_path or _default_manifest_path()
        self._pkg_root = pkg_root or _aria_pkg_root()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._fired = False
        self._sweep_count = 0
        self._last_sweep_ts: float = 0.0
        self._last_mismatch: Optional[Dict[str, Any]] = None
        self._lock = threading.Lock()

    # ── Lifecycle ───────────────────────────────────────────────

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="aria-cim", daemon=True,
        )
        self._thread.start()
        logger.info("cim.started",
                    period_s=self._period_s,
                    manifest=str(self._manifest_path))

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.info("cim.stopped", sweeps=self._sweep_count)

    def acknowledge(self) -> None:
        """Re-arm the monitor after an operator has investigated a
        mismatch.  Subsequent mismatches will fire the callback again."""
        with self._lock:
            self._fired = False
            self._last_mismatch = None

    # ── Inspection ──────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sweeps": self._sweep_count,
                "last_sweep_ts": self._last_sweep_ts,
                "fired": self._fired,
                "period_s": self._period_s,
                "last_mismatch": self._last_mismatch,
            }

    # ── Core sweep ──────────────────────────────────────────────

    def sweep_once(self) -> Optional[Dict[str, Any]]:
        """Run one verification pass.  Returns a mismatch report dict
        (and fires the callback) on the first mismatch the monitor sees,
        otherwise returns None.  Test hook + worker body."""
        try:
            expected = self._read_manifest()
        except Exception as exc:
            logger.error("cim.manifest_read_failed", error=str(exc))
            return None

        if not expected:
            # Dev-tree without manifest.  Logged once per sweep at debug
            # level; not an integrity failure on its own.
            logger.debug("cim.no_manifest", path=str(self._manifest_path))
            with self._lock:
                self._sweep_count += 1
                self._last_sweep_ts = time.time()
            return None

        actual = self._compute_actual()
        missing = sorted(set(expected) - set(actual))
        mismatched = [
            rel for rel in expected
            if rel in actual and actual[rel] != expected[rel]
        ]

        with self._lock:
            self._sweep_count += 1
            self._last_sweep_ts = time.time()

        if not (missing or mismatched):
            return None

        # First mismatch sample (cheap to compute, useful for triage).
        sample_path = mismatched[0] if mismatched else missing[0]
        report: Dict[str, Any] = {
            "missing_count": len(missing),
            "mismatched_count": len(mismatched),
            "missing": missing[:5],
            "mismatched": mismatched[:5],
            "sample_path": sample_path,
            "expected_prefix": expected.get(sample_path, "")[:16],
            "actual_prefix": actual.get(sample_path, "")[:16],
            "manifest": str(self._manifest_path),
            "ts": time.time(),
        }

        with self._lock:
            self._last_mismatch = report
            already_fired = self._fired
            self._fired = True

        # Always log every sweep that sees a mismatch (operator visibility),
        # but only fire the bus event + callback once per arming cycle.
        logger.critical("cim.mismatch", **report)
        if already_fired:
            return report

        try:
            self._publish("aria.security.cim_mismatch", dict(report))
        except Exception as exc:
            logger.error("cim.publish_failed", error=str(exc))

        # Audit-log the mismatch.  Best-effort: if the audit chain itself
        # is broken, the cim event still gets out via the bus.
        try:
            from aria.security.audit import log_event
            log_event(
                event_type="security",
                identity="cim",
                action="integrity_mismatch",
                result="critical",
                details=report,
                severity="critical",
                source="cim",
            )
        except Exception as exc:
            logger.error("cim.audit_log_failed", error=str(exc))

        # Trigger reaction last so the bus + audit are already populated
        # by the time safe-mode publishes its own transition event.
        t0 = time.time()
        try:
            self._on_mismatch(report)
        except Exception as exc:
            logger.error("cim.on_mismatch_failed", error=str(exc))
        elapsed = time.time() - t0
        if elapsed > MISMATCH_REACTION_BUDGET_S:
            logger.warning("cim.reaction_overrun",
                           elapsed_s=round(elapsed, 2),
                           budget_s=MISMATCH_REACTION_BUDGET_S)

        return report

    # ── Internals ───────────────────────────────────────────────

    def _read_manifest(self) -> Dict[str, str]:
        if not self._manifest_path.is_file():
            return {}
        text = self._manifest_path.read_text()
        return _parse_boot_manifest(text)

    def _compute_actual(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for p in _enumerate_protected_files(self._pkg_root):
            try:
                rel = p.relative_to(self._pkg_root).as_posix()
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError as e:
                # File deleted mid-sweep — record as missing-by-omission.
                logger.warning("cim.read_failed", path=str(p), error=str(e))
        return out

    def _run(self) -> None:
        # Wiring audit Pass 3 (F4.5) — wrap sweep_once() in a worker
        # thread with a per-iteration timeout. A slow disk or a
        # million-file tree could otherwise wedge the daemon thread
        # for minutes; we'd rather publish ``aria.security.cim_wedged``
        # and skip the cycle.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cim-sweep",
        ) as pool:
            while not self._stop.is_set():
                future = pool.submit(self.sweep_once)
                try:
                    future.result(timeout=self._period_s)
                except concurrent.futures.TimeoutError:
                    logger.error(
                        "cim.sweep_wedged",
                        period_s=self._period_s,
                        impact="manifest sweep exceeded its window — "
                               "publishing wedge event and skipping cycle",
                    )
                    try:
                        self._publish(
                            "aria.security.cim_wedged",
                            {"period_s": self._period_s},
                        )
                    except Exception:    # noqa: BLE001
                        pass
                    # Don't cancel — let the slow sweep finish in
                    # background; the next cycle will start a fresh
                    # submission. The pool max_workers=1 means the
                    # next submit waits for the slow one — that's the
                    # safe default (better than racing two sweeps).
                except Exception as exc:
                    logger.error("cim.sweep_failed", error=str(exc))
                self._stop.wait(self._period_s)


# ── Module-level helpers ─────────────────────────────────────────


_INSTANCE: Optional[IntegrityMonitor] = None
_INSTANCE_LOCK = threading.Lock()


def get_integrity_monitor() -> Optional[IntegrityMonitor]:
    """Return the running CIM singleton, or None if not started."""
    with _INSTANCE_LOCK:
        return _INSTANCE


def start_integrity_monitor(
    on_mismatch: Callable[[Dict[str, Any]], None],
    publish_fn: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    period_s: float = DEFAULT_PERIOD_S,
) -> IntegrityMonitor:
    """Idempotent constructor + start.  Subsequent calls return the
    already-running monitor (the on_mismatch callback from the *first*
    call sticks)."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = IntegrityMonitor(
                on_mismatch=on_mismatch,
                publish_fn=publish_fn,
                period_s=period_s,
            )
            _INSTANCE.start()
        return _INSTANCE


def stop_integrity_monitor() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is not None:
            _INSTANCE.stop()
            _INSTANCE = None


def reset_for_test() -> None:
    """Tests only — drop the singleton without graceful shutdown."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is not None:
            _INSTANCE.stop()
        _INSTANCE = None
