"""R222 — Solidity reentrancy lint (DAO-class).

Threat: a Solidity function that ``call``s an external address
*before* updating internal state lets the callee re-enter and drain
balances.  The DAO 2016 ($60M), Cream Finance 2021 ($130M), and
dozens since.

Defence: a static lint over Solidity source — flag ``.call{value:`` /
``.transfer(`` / ``.send(`` *before* any state-change in the same
function, and refuse functions missing ``nonReentrant`` modifier on
the whitelist.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_CALL_RE = re.compile(r"\.(call|delegatecall|staticcall|transfer|send)\s*[\{\(]")
_STATE_WRITE_RE = re.compile(r"\b\w+(?:\[[^\]]*\])?\s*[+\-*/]?=\s*[^=]")
_FN_HEAD_RE = re.compile(r"function\s+(\w+)\s*\([^)]*\)[^{]*\{")


def _extract_body(source: str, brace_start: int) -> Tuple[str, int]:
    depth = 1
    i = brace_start + 1
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[brace_start + 1:i - 1], i


def lint_solidity(source: str) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    src = source or ""
    for m in _FN_HEAD_RE.finditer(src):
        name = m.group(1)
        body, _ = _extract_body(src, m.end() - 1)
        call_match = _CALL_RE.search(body)
        if not call_match:
            continue
        call_pos = call_match.end()
        if _STATE_WRITE_RE.search(body[call_pos:]):
            issues.append(f"reentrancy_risk:{name}")
        if "nonReentrant" not in body:
            issues.append(f"missing_nonReentrant:{name}")
    return not issues, issues


def recommend_pattern() -> str:
    return ("Use OpenZeppelin ReentrancyGuard.nonReentrant + the "
            "Checks-Effects-Interactions pattern: validate, update "
            "state, then external call.")


register(DefencePlugin(
    round_id="R222",
    name="solidity_reentrancy",
    description="Solidity reentrancy lint: external call before state write or no nonReentrant.",
))
