"""R42 — Dependency confusion / typosquatting.

Threat: an attacker uploads ``aria-cor`` or ``aria_core_utils`` to
PyPI; a developer typo or a CI lookup picks the public package over
the operator's private mirror.  Microsoft / Apple / Tesla all hit by
this in the 2021 Birsan disclosure; still active in 2024 (npm wave
of typo-squat malware).

Defence: a small allow-list checker.  ``check_imports(modules)`` walks
the project's import set and refuses any package not on the allow-list.
The allow-list is generated at build time from ``requirements-lock.txt``
so an unfamiliar import can't sneak in via a transitive dep that wasn't
locked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_PKG_LINE_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==", re.MULTILINE)


def lockfile_packages(lockfile: Path) -> Set[str]:
    if not lockfile.is_file():
        return set()
    text = lockfile.read_text(encoding="utf-8")
    return {m.group(1).lower().replace("_", "-") for m in _PKG_LINE_RE.finditer(text)}


def normalise(name: str) -> str:
    return name.lower().replace("_", "-")


# Trojan-shape names that have been observed as typosquats.
_KNOWN_TYPOSQUATS = frozenset({
    "aria-cor", "aria-core-utils", "aria_core_utils",
    "araicore", "ariia-core",
    "request",                              # vs. requests
    "urllib",                               # not the stdlib
    "djnago",                               # vs. django
    "boto",                                 # legacy → suspicious on a fresh project
})


def is_typosquat(name: str) -> bool:
    n = normalise(name)
    return n in _KNOWN_TYPOSQUATS


def check_imports(
    modules: List[str],
    allowed_packages: Set[str],
) -> Tuple[bool, List[str]]:
    """Return ``(ok, suspicious)``.

    ``modules`` is the list of top-level Python imports actually used
    by ARIA (sniff with stdlib ``modulefinder`` or ``ast``).
    ``allowed_packages`` is the set produced by :func:`lockfile_packages`.

    A module is "suspicious" when its top-level name maps to a package
    that is neither stdlib nor in the allow-list, or matches a known
    typosquat shape.
    """
    import sys
    stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()
    suspicious: List[str] = []
    for m in modules:
        top = m.split(".", 1)[0]
        if not top:
            continue
        if top in stdlib:
            continue
        n = normalise(top)
        if is_typosquat(n):
            suspicious.append(f"{n} (typosquat shape)")
            continue
        if n not in allowed_packages and n.replace("-", "_") not in allowed_packages:
            suspicious.append(n)
    return len(suspicious) == 0, sorted(set(suspicious))


register(DefencePlugin(
    round_id="R42",
    name="dep_confusion",
    description="Refuse imports outside lockfile + flag known typosquat shapes.",
))
