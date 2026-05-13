"""Parse LLM recommendations into authorized simulator actions.

Closes the "LLM advice-only, no actual state change" gap. The executor
takes the CognitiveEngine's final text (expected JSON-ish) and:

  1. Parses out action keywords + target values
  2. Validates against authority level and guard rails
  3. Invokes the registered action callback (UI or simulator adapter)
  4. Records the outcome back into the DecisionLog

Supported action tokens (regex or JSON):
  - throttle_engine <fraction>      # 0..1
  - shed_load <subsystem>
  - safe_mode
  - schedule_maneuver <name> <dv_mps>
  - vent_tank <tank_id>
  - pressurize_cabin <kpa>

All actions are advisory: the default callback logs the attempted action
but does nothing to the simulator. Real deployments inject a callback
that mutates live state.

Standard LLM tool-use pattern: tool → verification → execution.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ActionIntent:
    """Parsed LLM recommendation."""
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    rationale: str = ""


_ACTION_PATTERNS = [
    (re.compile(r"\bthrottle[_\s]engine[^\w\d]*([\d.]+)", re.I),
     lambda m: ActionIntent("throttle_engine", {"fraction": float(m.group(1))})),
    (re.compile(r"\bshed[_\s]load\b[^\w]*(\w+)?", re.I),
     lambda m: ActionIntent("shed_load", {"subsystem": m.group(1) or "any"})),
    (re.compile(r"\bsafe[_\s]mode\b", re.I),
     lambda m: ActionIntent("safe_mode")),
    (re.compile(r"\bschedule[_\s]maneuver\b.*?([\d.]+)\s*m/s", re.I | re.S),
     lambda m: ActionIntent("schedule_maneuver", {"dv_mps": float(m.group(1))})),
    (re.compile(r"\bvent[_\s]tank\s+(\w+)", re.I),
     lambda m: ActionIntent("vent_tank", {"tank_id": m.group(1)})),
    (re.compile(r"\bpressurize[_\s]cabin\s+([\d.]+)\s*kpa", re.I),
     lambda m: ActionIntent("pressurize_cabin", {"kpa": float(m.group(1))})),
    # Track 3 P3 fan-out — domain-specific actions for thermal / comms / nav.
    (re.compile(r"\bset[_\s]setpoint\s+(\w+)\s+([-\d.]+)\s*c", re.I),
     lambda m: ActionIntent("set_setpoint", {"zone": m.group(1), "celsius": float(m.group(2))})),
    (re.compile(r"\bswitch[_\s]antenna\s+(hga|lga|mga)\b", re.I),
     lambda m: ActionIntent("switch_antenna", {"antenna": m.group(1).lower()})),
    (re.compile(r"\battitude[_\s]hold\b", re.I),
     lambda m: ActionIntent("attitude_hold")),
    (re.compile(r"\bboost[_\s]scrubber\b", re.I),
     lambda m: ActionIntent("boost_scrubber")),
]


def parse_recommendation(text: str) -> List[ActionIntent]:
    """Extract 0 or more actions from an LLM response."""
    if not text:
        return []
    intents: List[ActionIntent] = []
    for pat, maker in _ACTION_PATTERNS:
        for m in pat.finditer(text):
            intents.append(maker(m))
    return intents


# Wiring audit Pass 3 (F14.13) — `ExecutionReport` + `ActionExecutor`
# class deleted. They had zero production callers; every concrete
# agent uses ``parse_recommendation`` directly and routes intents
# through its own override of ``on_reasoning_response``. Test cases
# exercising the deleted class were also removed.
