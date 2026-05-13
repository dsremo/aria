"""Incident-response policy — class × controllability → response mode.

R34 Phase 2. Closes the design gap raised in the conversation: today's
runtime treats every event the same (constitution decides per-action,
kill switch is binary, safe-mode is monolithic). Real spacecraft ops
distinguishes situations where you ACT FIRST and diagnose later (life
critical, security breach) from situations where you DIAGNOSE FIRST
and act later (novel mission-critical anomaly, suspected cognitive
drift). This module encodes that distinction.

The decision matrix is sealed in
``data/sealed/incident_policy.v1.toml`` so a runtime mutation breaks
the F-1 boot manifest. Editing the policy requires a release re-bake.

Public surface:

    from aria.safety.incident_policy import (
        IncidentClass, Controllability, ResponseMode,
        decide_response_mode,
    )

    mode = decide_response_mode(
        incident_class=IncidentClass.MISSION_CRITICAL,
        controllability=Controllability.NOVEL_UNKNOWN,
    )
    # → ResponseMode.HOLD_AND_RCA

The evaluation walks the rules in file order and returns the FIRST
match. Rules with unspecified clauses are wildcards. A default catch-
all rule at the end of the file backstops anything no rule covered.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional

import structlog

# tomllib is stdlib on Py>=3.11; tomli is the backport for 3.10.
try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

logger = structlog.get_logger()


# ── Taxonomies ────────────────────────────────────────────────────


class IncidentClass(str, Enum):
    """Coarse classification of the *kind* of incident.

    Stable names — kept in sync with the sealed policy file. Adding a
    new class requires a release re-bake (the policy must reference it
    or the boot integrity check breaks).
    """

    # Crew safety. Pressure breach, life support failure, radiation
    # exposure, medical emergency.
    LIFE_CRITICAL = "LIFE_CRITICAL"

    # Mission objective threatened. Propulsion fault, navigation drift,
    # comms loss, science instrument failure.
    MISSION_CRITICAL = "MISSION_CRITICAL"

    # Adversarial — intrusion, tamper-evident chain break, capability
    # token forge attempt, F-19 replay defence trip, canary endpoint
    # touched.
    SECURITY = "SECURITY"

    # Cognitive / alignment — sandbagging detected, F-13 replay drift,
    # constitution check disagreeing with stated rationale, monitor
    # vetoes piling up, agent self-elevation attempt.
    COGNITIVE_DRIFT = "COGNITIVE_DRIFT"

    # Non-life-supporting equipment — pump degraded, sensor drift on a
    # diagnostic line, fan bearing wearing, redundant subsystem failing.
    SUBSYSTEM = "SUBSYSTEM"

    # Quality of life — cabin temp out of nominal, schedule slip,
    # noise above ambient comfort target.
    COMFORT = "COMFORT"

    # Curious telemetry that doesn't yet imply action. Useful for log +
    # forensics + future model training.
    INFORMATIONAL = "INFORMATIONAL"


class Controllability(str, Enum):
    """How well do we know what to do about this?"""

    # Documented playbook in the sealed constitution + runbook.
    KNOWN_PLAYBOOK = "KNOWN_PLAYBOOK"

    # Recognised pattern but each event needs a parameter tweak.
    RECURRING_TUNING = "RECURRING_TUNING"

    # Haven't seen this exact pattern before. Blind action could
    # compound the problem.
    NOVEL_UNKNOWN = "NOVEL_UNKNOWN"

    # Known issue but currently in a degraded state we have to operate
    # around (limited fuel, redundancy lost, etc.).
    DEGRADED_KNOWN = "DEGRADED_KNOWN"


class ResponseMode(str, Enum):
    """What the runtime should do *first* when the incident opens."""

    # Execute the pre-approved playbook NOW. RCA happens after the
    # system is stable. Examples: kill switch on intrusion, auto-
    # pressurise on cabin breach, shed_load on power dip.
    AUTO_STABILIZE = "AUTO_STABILIZE"

    # Pause non-essential autonomy, gather evidence, present root
    # cause + options to the operator before any fix is applied.
    HOLD_AND_RCA = "HOLD_AND_RCA"

    # Operator decides — surface the incident to the SafetyConsole /
    # bridge tablet immediately and require human input.
    HUMAN_DECIDE = "HUMAN_DECIDE"

    # Log + watch. No automatic action. Used for low-severity comfort
    # / informational anomalies where premature action causes more
    # noise than the original event.
    OBSERVE_ONLY = "OBSERVE_ONLY"


# ── Locating the sealed policy ────────────────────────────────────


def _default_sealed_dir() -> Path:
    env = os.environ.get("ARIA_SEALED_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    # src/aria/safety/incident_policy.py → repo root via parents[3]
    return (here.parents[3] / "data" / "sealed").resolve()


# ── Parsed policy ────────────────────────────────────────────────


@dataclass(frozen=True)
class _Rule:
    """One row of the decision matrix."""
    name: str
    incident_class: Optional[IncidentClass]
    controllability: Optional[Controllability]
    mode: ResponseMode
    description: str

    def matches(
        self,
        incident_class: IncidentClass,
        controllability: Optional[Controllability],
    ) -> bool:
        if self.incident_class is not None and self.incident_class != incident_class:
            return False
        if self.controllability is not None and self.controllability != controllability:
            return False
        return True


@dataclass(frozen=True)
class PolicyDecision:
    """Result of evaluating the policy. ``rule_name`` lets the
    operator audit *why* a particular mode was chosen."""
    mode: ResponseMode
    rule_name: str
    description: str


# ── Loader ───────────────────────────────────────────────────────


class _PolicyStore:
    """Loads + evaluates the sealed policy. Singleton."""

    SEALED_FILENAME = "incident_policy.v1.toml"

    def __init__(self, sealed_dir: Optional[Path] = None) -> None:
        self._sealed_dir = (sealed_dir or _default_sealed_dir()).resolve()
        self._rules: List[_Rule] = []
        self._default_mode: ResponseMode = ResponseMode.OBSERVE_ONLY
        self._default_description: str = "default catch-all"
        self._lock = threading.RLock()
        self._loaded = False

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            path = self._sealed_dir / self.SEALED_FILENAME
            if not path.is_file():
                raise FileNotFoundError(
                    f"sealed incident policy missing: {path}",
                )
            data = tomllib.loads(path.read_text())
            self._rules = self._parse_rules(data.get("rules") or [])
            default_block = data.get("default") or {}
            try:
                self._default_mode = ResponseMode(
                    default_block.get("mode", ResponseMode.OBSERVE_ONLY.value),
                )
            except ValueError as exc:
                raise ValueError(f"invalid default mode: {exc}") from exc
            self._default_description = str(
                default_block.get("description", "catch-all default"),
            )
            self._loaded = True
        logger.info("incident_policy.loaded",
                    rules=len(self._rules),
                    default_mode=self._default_mode.value)

    @staticmethod
    def _parse_rules(rules: Iterable[Mapping[str, Any]]) -> List[_Rule]:
        out: List[_Rule] = []
        for r in rules:
            try:
                cls_raw = r.get("incident_class")
                ctl_raw = r.get("controllability")
                rule = _Rule(
                    name=str(r.get("name", "(unnamed)")),
                    incident_class=(IncidentClass(cls_raw) if cls_raw else None),
                    controllability=(Controllability(ctl_raw)
                                     if ctl_raw else None),
                    mode=ResponseMode(r["mode"]),
                    description=str(r.get("description", "")),
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"invalid policy rule {r.get('name', '?')}: {exc}",
                ) from exc
            out.append(rule)
        return out

    def decide(
        self,
        incident_class: IncidentClass,
        controllability: Optional[Controllability] = None,
    ) -> PolicyDecision:
        self.load()
        with self._lock:
            for rule in self._rules:
                if rule.matches(incident_class, controllability):
                    return PolicyDecision(
                        mode=rule.mode,
                        rule_name=rule.name,
                        description=rule.description,
                    )
            return PolicyDecision(
                mode=self._default_mode,
                rule_name="(default)",
                description=self._default_description,
            )

    def all_rules(self) -> List[_Rule]:
        self.load()
        with self._lock:
            return list(self._rules)


# ── Singleton ────────────────────────────────────────────────────


_INSTANCE: Optional[_PolicyStore] = None
_LOCK = threading.RLock()


def get_policy_store() -> _PolicyStore:
    global _INSTANCE
    if _INSTANCE is None:
        with _LOCK:
            if _INSTANCE is None:
                _INSTANCE = _PolicyStore()
                _INSTANCE.load()
    return _INSTANCE


def reset_for_test(sealed_dir: Optional[Path] = None) -> None:
    global _INSTANCE
    with _LOCK:
        _INSTANCE = _PolicyStore(sealed_dir=sealed_dir)


# ── Public API ───────────────────────────────────────────────────


def decide_response_mode(
    incident_class: IncidentClass,
    controllability: Optional[Controllability] = None,
) -> PolicyDecision:
    """Return the policy decision for an incident at the moment it opens."""
    return get_policy_store().decide(incident_class, controllability)
