"""R323 — Sigma rule engine (subset).

Threat: detection rules in vendor-specific languages can't migrate
between SIEMs.  Sigma is the cross-SIEM detection-as-code format.
Without an in-process engine, ARIA can't consume community Sigma
feeds (SOCPrime, Sigma HQ).

Defence: a tiny subset Sigma matcher — supports `selection`/
`condition`, `contains`/`startswith`/`endswith`, AND/OR composition.
Enough to validate community rules against ARIA audit events.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def _value_matches(field_value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_value_matches(field_value, e) for e in expected)
    fv = "" if field_value is None else str(field_value)
    if isinstance(expected, str):
        if expected.startswith("re:"):
            return re.search(expected[3:], fv) is not None
        return fv == expected
    return False


def _check_clause(event: Dict[str, Any], clause: Dict[str, Any]) -> bool:
    for raw_field, expected in clause.items():
        op = "eq"
        field = raw_field
        if "|" in raw_field:
            field, op = raw_field.split("|", 1)
        fv = "" if event.get(field) is None else str(event.get(field))
        if op == "contains":
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(p in fv for p in patterns):
                return False
        elif op == "startswith":
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(fv.startswith(p) for p in patterns):
                return False
        elif op == "endswith":
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(fv.endswith(p) for p in patterns):
                return False
        else:
            if not _value_matches(event.get(field), expected):
                return False
    return True


def evaluate_rule(rule: Dict[str, Any], event: Dict[str, Any]) -> bool:
    """Evaluate a Sigma-shaped rule (dict) against a single event dict.
    Supports {detection: {selection: {...}, selection_b: {...},
    condition: 'selection and selection_b'}}."""
    detection = rule.get("detection") or {}
    condition = (detection.get("condition") or "").strip()
    selections = {k: v for k, v in detection.items() if k != "condition" and isinstance(v, dict)}
    if not selections:
        return False
    clause_results = {name: _check_clause(event, body) for name, body in selections.items()}
    if not condition:
        return all(clause_results.values())

    # Tiny boolean expression evaluator
    cond = condition.lower().replace("(", " ( ").replace(")", " ) ")
    tokens = cond.split()

    def _val(token: str) -> bool:
        return clause_results.get(token, False)

    def _eval(toks: List[str]) -> bool:
        # naive shunt: handle 'not', 'and', 'or' in precedence order
        # 1. resolve identifiers + 'not'
        out: List = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "not":
                out.append(not _val(toks[i + 1]))
                i += 2
            else:
                out.append(t if t in ("and", "or", "(", ")") else _val(t))
                i += 1
        # 2. handle 'and'
        i = 0
        while i < len(out):
            if out[i] == "and":
                out = out[:i - 1] + [bool(out[i - 1] and out[i + 1])] + out[i + 2:]
                i = 0
                continue
            i += 1
        # 3. handle 'or'
        i = 0
        while i < len(out):
            if out[i] == "or":
                out = out[:i - 1] + [bool(out[i - 1] or out[i + 1])] + out[i + 2:]
                i = 0
                continue
            i += 1
        return bool(out[0]) if out else False

    return _eval(tokens)


def evaluate_corpus(rule: Dict[str, Any], events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in events if evaluate_rule(rule, e)]


register(DefencePlugin(
    round_id="R323",
    name="sigma_engine",
    description="Tiny Sigma-rule subset engine: selections + AND/OR/NOT condition.",
))
