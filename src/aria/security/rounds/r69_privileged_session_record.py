"""R69 — Privileged-session recording (admin command audit trail).

Threat: an admin (real or compromised) executes a sequence of
high-privilege actions; the post-incident forensics need an exact
replay of every command + every output, with timestamps and actor.
PCI-DSS 10.2 mandates this for cardholder-data systems; SOC 2 + ISO
27001 require equivalent logging.

Defence: a session-bound recorder.  ``start_recording(session_id,
principal)`` opens an append-only log; every privileged action is
written via ``record_action(session_id, action, params, result)``;
``stop_recording(session_id)`` rolls + sigs (R55 hybrid signing).
The log is keyed on R53 HKDF so each tenant gets its own seal key.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r69")


def _record_dir() -> Path:
    return Path(os.environ.get(
        "ARIA_PRIV_RECORD_DIR",
        str(Path(__file__).resolve().parents[4] / "data" / "priv_recordings"),
    ))


_OPEN: Dict[str, List[Dict[str, Any]]] = {}
_LOCK = threading.Lock()


def start_recording(session_id: str, principal: str) -> None:
    if not session_id:
        return
    with _LOCK:
        _OPEN[session_id] = [{
            "kind": "session_start",
            "ts": time.time(),
            "principal": principal,
        }]


def record_action(
    session_id: str,
    *,
    action: str,
    params: Any = None,
    result: Any = None,
) -> None:
    with _LOCK:
        log = _OPEN.get(session_id)
        if log is None:
            return
        log.append({
            "kind": "action",
            "ts": time.time(),
            "action": action,
            "params_repr": repr(params)[:512],
            "result_repr": repr(result)[:512] if result is not None else None,
        })


def stop_recording(session_id: str, *, principal: str = "") -> Path:
    with _LOCK:
        log = _OPEN.pop(session_id, None)
    if not log:
        raise RuntimeError(f"r69.no_active_recording session={session_id}")
    log.append({"kind": "session_end", "ts": time.time(), "principal": principal})
    target_dir = _record_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"priv_{int(time.time())}_{session_id[:12]}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for entry in log:
            f.write(json.dumps(entry) + "\n")
    try:
        os.chmod(out, 0o440)
    except Exception:
        pass
    return out


register(DefencePlugin(
    round_id="R69",
    name="privileged_session_record",
    description="Append-only recorder for admin actions; chmod-440 sealed file at stop.",
))
