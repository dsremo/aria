"""R350 — Defence library API stability checker.

Threat: rounds whose public function names or signatures change
silently break downstream callers — operator scripts, partner
integrations, auditors' tooling.  A frozen public-surface contract
+ checker keeps the defence library trustworthy.

Defence: a manifest of (round_id, function_name, expected_arity).
``audit_api_surface`` introspects each round and flags missing
functions, renamed functions, or arity drift.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class APIContract:
    round_id: str
    module_path: str
    function_name: str
    min_arity: int
    max_arity: int


_CONTRACTS: List[APIContract] = [
    APIContract("R51", "aria.security.rounds.r51_adversarial_runner", "run", 0, 0),
    APIContract("R101", "aria.security.rounds.r101_adversarial_runner_v2", "run_v2", 0, 0),
    APIContract("R151", "aria.security.rounds.r151_adversarial_runner_v3", "run_v3", 0, 0),
    APIContract("R201", "aria.security.rounds.r201_adversarial_runner_v4", "run_v4", 0, 0),
    APIContract("R251", "aria.security.rounds.r251_adversarial_runner_v5", "run_v5", 0, 0),
    APIContract("R301", "aria.security.rounds.r301_adversarial_runner_v6", "run_v6", 0, 0),
    APIContract("R342", "aria.security.rounds.r342_runner_orchestrator", "run_all", 0, 0),
    APIContract("R349", "aria.security.rounds.r349_cvss", "base_score", 1, 1),
    APIContract("R349", "aria.security.rounds.r349_cvss", "severity_band", 1, 1),
]


def audit_api_surface() -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for c in _CONTRACTS:
        try:
            module = importlib.import_module(c.module_path)
        except Exception as exc:
            issues.append(f"api.import_failed:{c.round_id}:{c.module_path}:{exc}")
            continue
        fn = getattr(module, c.function_name, None)
        if fn is None:
            issues.append(f"api.function_missing:{c.round_id}:{c.function_name}")
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        required = sum(1 for p in sig.parameters.values()
                       if p.default is inspect.Parameter.empty
                       and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD))
        total = sum(1 for p in sig.parameters.values()
                    if p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD))
        if required > c.max_arity or total < c.min_arity:
            issues.append(
                f"api.arity_drift:{c.round_id}:{c.function_name} "
                f"required={required} total={total} expected=[{c.min_arity},{c.max_arity}]"
            )
    return not issues, issues


def register_contract(contract: APIContract) -> None:
    _CONTRACTS.append(contract)


register(DefencePlugin(
    round_id="R350",
    name="api_stability",
    description="Defence library API stability audit: per-round signature contract.",
))
