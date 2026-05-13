"""R283 — Workflow-step bypass detector.

Threat: a multi-step user flow (KYC → risk-check → fund) reachable
out of order via direct URL hits — attacker skips the KYC step,
funds the account anyway.  Found in fintech bug bounties; Plaid
2020-class.

Defence: a state-machine helper.  ``advance_state`` refuses to move
to step N+1 unless step N is verified-complete; every state
transition is recorded for audit.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class WorkflowState:
    flow: str
    user_id: str
    completed_steps: List[str] = field(default_factory=list)
    started_at: float = 0.0


_STATES: Dict[str, WorkflowState] = {}
_DEFINITIONS: Dict[str, List[str]] = {}
_LOCK = threading.Lock()


def define_flow(name: str, steps: List[str]) -> None:
    with _LOCK:
        _DEFINITIONS[name] = list(steps)


def advance_state(flow: str, user_id: str, target_step: str) -> Tuple[bool, str]:
    with _LOCK:
        steps = _DEFINITIONS.get(flow)
        if not steps:
            return False, f"workflow.unknown_flow:{flow}"
        if target_step not in steps:
            return False, f"workflow.unknown_step:{target_step}"

        key = f"{flow}|{user_id}"
        st = _STATES.get(key)
        if st is None:
            st = WorkflowState(flow=flow, user_id=user_id, started_at=time.time())
            _STATES[key] = st

        target_idx = steps.index(target_step)
        for prior in steps[:target_idx]:
            if prior not in st.completed_steps:
                return False, f"workflow.bypass missing_prior={prior}"

        if target_step in st.completed_steps:
            return False, "workflow.repeat"

        st.completed_steps.append(target_step)
    return True, "ok"


def reset_for_tests() -> None:
    with _LOCK:
        _STATES.clear()
        _DEFINITIONS.clear()


register(DefencePlugin(
    round_id="R283",
    name="workflow_bypass",
    description="Multi-step workflow state-machine; refuse out-of-order step advance.",
))
