"""R92 — SIEM audit-log forwarder (Splunk HEC / Sentinel / Loki).

Threat: an attacker who reaches ARIA's host edits the local audit
trail to cover their tracks.  The R10 sealed-audit closes one axis;
the orthogonal axis is **off-host** — ship the events to a SIEM in
real time so the local host's tampering doesn't matter.

Defence: ``configure_forwarder(send_fn)`` accepts a callable that
takes a normalised audit event and ships it (Splunk HEC, Sentinel
Logs Ingestion, Loki, anything HTTP-based).  Falls back to a local
batched JSONL file when no forwarder is configured.  Wired into the
plugin ``on_audit`` hook so every audit-chain entry is sent.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from queue import Queue
from typing import Any, Callable, Dict, Optional

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r92")
_FORWARDER: Optional[Callable[[Dict[str, Any]], None]] = None
_QUEUE: Queue = Queue(maxsize=4096)
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def configure_forwarder(fn: Callable[[Dict[str, Any]], None]) -> None:
    global _FORWARDER
    _FORWARDER = fn


def _local_fallback_path() -> Path:
    return Path(os.environ.get(
        "ARIA_AUDIT_FORWARD_FALLBACK",
        str(Path(__file__).resolve().parents[4] / "data" / "audit_forwarded.jsonl"),
    ))


def _worker():
    while True:
        event = _QUEUE.get()
        if event is None:
            break
        try:
            if _FORWARDER is not None:
                _FORWARDER(event)
            else:
                _local_fallback_path().parent.mkdir(parents=True, exist_ok=True)
                with _local_fallback_path().open("a", encoding="utf-8") as f:
                    f.write(json.dumps(event) + "\n")
        except Exception as exc:
            logger.warning("r92.forward_failed %s", exc)


def _start_worker():
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        th = threading.Thread(target=_worker, daemon=True, name="aria-r92-forwarder")
        th.start()
        _WORKER_STARTED = True


def _on_audit(event: Dict[str, Any]) -> None:
    _start_worker()
    try:
        _QUEUE.put_nowait({"forwarded_at": time.time(), **event})
    except Exception:
        pass


register(DefencePlugin(
    round_id="R92",
    name="audit_forwarder",
    description="Async forward of every audit event to SIEM (Splunk/Sentinel/Loki).",
    on_audit=_on_audit,
))
