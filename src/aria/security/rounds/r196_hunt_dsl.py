"""R196 — Threat-hunt query DSL.

Threat: an analyst hunting in raw audit logs writes ad-hoc grep that
misses the events spread across multiple shapes (auth event, network
event, process event).  Hunt queries should be structured + repeatable.

Defence: a tiny DSL that compiles a hunt expression to a function
matching dict-shaped audit rows.  Operator can express e.g.
``actor=admin AND action=download AND bytes>1e6``.
"""

from __future__ import annotations

import operator
import re
from typing import Any, Callable, Dict, Iterable, List

from aria.security.plugins import DefencePlugin, register


_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    "=": lambda a, b: str(a) == str(b),
    "!=": lambda a, b: str(a) != str(b),
    ">": lambda a, b: float(a) > float(b),
    "<": lambda a, b: float(a) < float(b),
    ">=": lambda a, b: float(a) >= float(b),
    "<=": lambda a, b: float(a) <= float(b),
    "~": lambda a, b: re.search(b, str(a)) is not None,
}

_TOKEN_RE = re.compile(r"(\w+)\s*(=|!=|>=|<=|>|<|~)\s*([^\s)]+)")


def compile_hunt(expr: str) -> Callable[[Dict[str, Any]], bool]:
    expr = expr.strip()
    if not expr:
        return lambda _row: True
    parts = re.split(r"\s+(AND|OR)\s+", expr, flags=re.IGNORECASE)
    clauses: List[Callable[[Dict[str, Any]], bool]] = []
    ops: List[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            ops.append(part.upper())
            continue
        m = _TOKEN_RE.match(part.strip("()"))
        if not m:
            raise ValueError(f"R196: cannot parse '{part}'")
        field, op, val = m.group(1), m.group(2), m.group(3).strip('"\'')
        op_fn = _OPS[op]
        clauses.append(lambda row, f=field, v=val, o=op_fn: o(row.get(f, ""), v))

    def evaluate(row: Dict[str, Any]) -> bool:
        result = clauses[0](row)
        for i, op in enumerate(ops):
            nxt = clauses[i + 1](row)
            result = (result and nxt) if op == "AND" else (result or nxt)
        return result

    return evaluate


def run_hunt(expr: str, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pred = compile_hunt(expr)
    return [r for r in rows if pred(r)]


register(DefencePlugin(
    round_id="R196",
    name="hunt_dsl",
    description="Tiny query DSL for hunting across structured audit rows.",
))
