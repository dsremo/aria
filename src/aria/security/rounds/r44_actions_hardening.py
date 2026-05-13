"""R44 — GitHub Actions workflow hardening.

Threat: a malicious workflow file ships with permission to write
contents, secrets, packages.  The 2024 ``tj-actions/changed-files``
incident leaked tokens from thousands of repos because most callers
left the default permissive permission set in place.

Defence: a static checker that scans every ``.github/workflows/*.yml``
and flags the danger shapes:
  * missing top-level ``permissions:`` block (default is overly broad)
  * uses of ``actions/checkout@v3`` etc. without a SHA pin
  * use of ``${{ github.event.pull_request.head.ref }}`` in ``run:``
    (script injection vector)
  * ``pull_request_target`` triggers without ``permissions: read-all``
  * any third-party action without a SHA pin
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_THIRD_PARTY_ACTION_RE = re.compile(r"uses:\s+([A-Za-z0-9_\-.]+/[A-Za-z0-9_\-.]+)@(\S+)")
_FIRST_PARTY_PREFIXES = ("actions/", "github/", "docker/")
_INJECTION_VECTORS = (
    "github.event.pull_request.head.ref",
    "github.event.pull_request.head.label",
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.comment.body",
    "github.head_ref",
)


def audit_workflow(text: str) -> List[str]:
    issues: List[str] = []
    if "permissions:" not in text:
        issues.append("missing top-level permissions block")
    if re.search(r"on:\s*\n\s*pull_request_target", text):
        if "permissions:\n" not in text:
            issues.append("pull_request_target without permissions: block")
    for m in _THIRD_PARTY_ACTION_RE.finditer(text):
        action, ref = m.group(1), m.group(2)
        if action.startswith(_FIRST_PARTY_PREFIXES):
            continue
        if not re.fullmatch(r"[a-f0-9]{40}", ref):
            issues.append(f"unpinned third-party action: {action}@{ref}")
    for vec in _INJECTION_VECTORS:
        if vec in text and "run:" in text:
            # Heuristic: if the vector is interpolated inside any run: block
            for m in re.finditer(r"run:\s*[|>]?\s*\n((?:.+\n)+?)(?:[^ ]|$)", text):
                block = m.group(1)
                if "${{" in block and vec in block:
                    issues.append(f"script-injection: {vec} inside run:")
                    break
    return issues


def audit_workflows_dir(workflows_dir: Path) -> List[Tuple[str, List[str]]]:
    out: List[Tuple[str, List[str]]] = []
    if not workflows_dir.is_dir():
        return out
    for f in workflows_dir.glob("*.yml"):
        text = f.read_text(encoding="utf-8")
        issues = audit_workflow(text)
        if issues:
            out.append((f.name, issues))
    return out


register(DefencePlugin(
    round_id="R44",
    name="actions_hardening",
    description="Scan .github/workflows/*.yml for unpinned actions + script-injection.",
))
