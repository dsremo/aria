"""R43 — Lockfile-diff CI gate.

Threat: a maintainer (you / future you) adds ``foo>=1.2`` to
``pyproject.toml`` and merges.  The next CI run quietly resolves to
``foo-1.9.7`` which has the XZ-style backdoor.  Without a lockfile diff
in CI, no human ever reads which transitive deps changed.

Defence: a one-shot ``diff_lockfiles(old, new)`` that produces a
human-readable summary suitable for a PR comment.  CI invokes it on
every change to ``requirements-lock.txt``; the operator must ack added
or upgraded direct dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_PKG_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+]+)", re.MULTILINE)


def parse_lockfile(text: str) -> Dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in _PKG_RE.finditer(text)}


def diff_lockfiles(old_text: str, new_text: str) -> Dict[str, List[str]]:
    """Return ``{added, removed, upgraded}`` keyed lists of package strings.

    ``added``    — package present in ``new_text`` only, with version.
    ``removed``  — present in ``old_text`` only.
    ``upgraded`` — version differs.
    """
    old_map = parse_lockfile(old_text)
    new_map = parse_lockfile(new_text)
    added, removed, upgraded = [], [], []
    for name, ver in new_map.items():
        if name not in old_map:
            added.append(f"{name}=={ver}")
        elif old_map[name] != ver:
            upgraded.append(f"{name}: {old_map[name]} -> {ver}")
    for name in old_map:
        if name not in new_map:
            removed.append(f"{name}=={old_map[name]}")
    return {"added": sorted(added), "removed": sorted(removed),
            "upgraded": sorted(upgraded)}


def render_pr_comment(diff: Dict[str, List[str]]) -> str:
    out = ["## R43 — lockfile diff"]
    for k in ("added", "upgraded", "removed"):
        items = diff.get(k, [])
        out.append(f"\n**{k.title()} ({len(items)})**")
        if items:
            for it in items[:50]:
                out.append(f"  - {it}")
            if len(items) > 50:
                out.append(f"  - … {len(items) - 50} more")
        else:
            out.append("  (none)")
    return "\n".join(out)


register(DefencePlugin(
    round_id="R43",
    name="lockfile_diff",
    description="Diff two requirements-lock.txt versions; render PR comment.",
))
