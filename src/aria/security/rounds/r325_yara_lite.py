"""R325 — YARA-style pattern engine (subset).

Threat: full YARA needs the libyara C runtime.  ARIA needs a Python-
only path that handles 80% of practical malware-pattern matching for
log-content scanning + IDS use cases.

Defence: a tiny YARA-shaped engine.  Rules are dicts with hex-byte
strings, ASCII strings, and a ``condition`` like ``$a and $b`` or
``2 of them``.  Matches a byte buffer in one pass.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def _compile_string(spec: str):
    spec = spec.strip()
    if spec.startswith("{") and spec.endswith("}"):
        hex_chars = re.sub(r"\s+", "", spec[1:-1])
        if len(hex_chars) % 2 != 0:
            raise ValueError("yara.bad_hex")
        try:
            return ("hex", bytes.fromhex(hex_chars))
        except ValueError as exc:
            raise ValueError(f"yara.bad_hex:{exc}")
    if spec.startswith("/") and spec.endswith("/"):
        return ("regex", re.compile(spec[1:-1].encode("utf-8")))
    if spec.startswith("\"") and spec.endswith("\""):
        return ("ascii", spec[1:-1].encode("utf-8"))
    return ("ascii", spec.encode("utf-8"))


def match_rule(buffer: bytes, rule: Dict[str, object]) -> Tuple[bool, List[str]]:
    strings = rule.get("strings") or {}
    matches: List[str] = []
    found_map: Dict[str, bool] = {}

    for name, spec in strings.items():
        kind, value = _compile_string(str(spec))
        hit = False
        if kind == "regex":
            if value.search(buffer):
                hit = True
        else:
            if value in buffer:
                hit = True
        found_map[name] = hit
        if hit:
            matches.append(name)

    cond = (rule.get("condition") or "").strip()
    if not cond:
        return all(found_map.values()), matches

    cond_low = cond.lower()
    if "of them" in cond_low:
        try:
            n = int(cond_low.split("of them")[0].strip())
        except Exception:
            n = 1
        return sum(found_map.values()) >= n, matches

    # Audit CRIT-6 — never use ``eval`` for the condition expression.
    # Parse with ``ast`` and walk an explicit allow-list of node types
    # (BoolOp, UnaryOp(Not), Name, Constant True/False, Call to ``any``
    # is intentionally excluded).  Anything else returns False so a
    # malicious rule cannot reach Python attribute walking.
    cond_for_ast = cond_low
    for name in found_map:
        cond_for_ast = re.sub(rf"\${re.escape(name)}\b", f"_var_{name}", cond_for_ast)
    if not re.fullmatch(r"[\s_a-zA-Z0-9andornot()]+", cond_for_ast):
        return False, matches
    try:
        return _safe_bool_eval(cond_for_ast, found_map), matches
    except Exception:
        return False, matches


def _safe_bool_eval(expr: str, env: dict) -> bool:
    """Evaluate a boolean expression over named flags using the AST.
    Allowed nodes: Module, Expression, BoolOp(And|Or), UnaryOp(Not),
    Name, Constant(True|False).  Refuses everything else."""
    import ast

    tree = ast.parse(expr, mode="eval")

    def _walk(node):
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name):
            key = node.id[5:] if node.id.startswith("_var_") else node.id
            return bool(env.get(key, False))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _walk(node.operand)
        if isinstance(node, ast.BoolOp):
            values = [_walk(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
        raise ValueError(f"yara.disallowed_node:{type(node).__name__}")

    return bool(_walk(tree))


register(DefencePlugin(
    round_id="R325",
    name="yara_lite",
    description="Tiny YARA-style pattern engine (hex / ASCII / regex strings + condition).",
))
