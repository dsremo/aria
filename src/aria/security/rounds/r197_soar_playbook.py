"""R197 — SOAR playbook trigger.

Threat: detection without response is detection-theatre — by the time
a human reads the alert the attacker has moved.  SOAR (Security
Orchestration, Automation, Response) wires an alert directly to a
named playbook.

Defence: a playbook registry + ``trigger`` dispatcher that maps a
named alert kind to a callable.  Records every dispatch into R171
incident ledger.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r197")


@dataclass
class _Playbook:
    name: str
    handler: Callable[[Dict[str, Any]], Tuple[bool, str]]
    severity: str = "SEV3"


_PLAYBOOKS: Dict[str, _Playbook] = {}
_LOCK = threading.Lock()


def register_playbook(alert_kind: str, handler: Callable[[Dict[str, Any]], Tuple[bool, str]], *, severity: str = "SEV3") -> None:
    with _LOCK:
        _PLAYBOOKS[alert_kind] = _Playbook(alert_kind, handler, severity)


def trigger(alert_kind: str, context: Dict[str, Any]) -> Tuple[bool, str]:
    with _LOCK:
        pb = _PLAYBOOKS.get(alert_kind)
    if pb is None:
        return False, f"no_playbook:{alert_kind}"
    started = time.monotonic()
    try:
        ok, why = pb.handler(context or {})
    except Exception as exc:
        logger.warning("r197.playbook_exc kind=%s exc=%s", alert_kind, exc)
        ok, why = False, f"exc:{type(exc).__name__}:{exc}"
    elapsed = time.monotonic() - started
    try:
        from aria.security.rounds.r171_incident_response import open_incident, add_artefact
        inc = open_incident(pb.severity, f"SOAR:{alert_kind}")
        add_artefact(inc.id, "playbook_result", f"ok={ok} elapsed={elapsed:.2f}s reason={why}")
    except Exception:
        pass
    return ok, why


def list_playbooks() -> List[str]:
    with _LOCK:
        return sorted(_PLAYBOOKS.keys())


register(DefencePlugin(
    round_id="R197",
    name="soar_playbook",
    description="Named-playbook dispatcher; records every trigger into the incident ledger.",
))
