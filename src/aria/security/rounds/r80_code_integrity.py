"""R80 — Runtime code-integrity verification.

Threat: an attacker with disk write access edits ``aria/security/guard.py``
to delete the SSRF check, then waits for the next ``import`` to run.
ARIA already has the boot-time F-1 manifest (`docs/FAILSAFE_ARCHITECTURE.md`),
but only at boot.  This round adds **periodic re-verification** so an
attacker who wins write access during a long-running process is still
caught.

Defence: ``verify_module_tree(module_root)`` walks every ``.py`` in the
loaded ``sys.modules`` whose path is under ``module_root`` and recomputes
its SHA-256.  Compares to a baseline captured at boot via
``capture_baseline()``.  A scheduled task runs the verify every 60 s.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r80")

_BASELINE: Dict[str, str] = {}
_LOCK = threading.Lock()


def capture_baseline(module_root: str) -> int:
    """Hash every imported ``.py`` whose path starts with ``module_root``.
    Returns the count of files baselined.
    """
    root = Path(module_root).resolve()
    out: Dict[str, str] = {}
    for name, mod in list(sys.modules.items()):
        path_str = getattr(mod, "__file__", None)
        if not path_str:
            continue
        try:
            p = Path(path_str).resolve()
        except Exception:
            continue
        try:
            p.relative_to(root)
        except ValueError:
            continue
        try:
            out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            continue
    with _LOCK:
        _BASELINE.clear()
        _BASELINE.update(out)
    return len(out)


def verify_now() -> Tuple[bool, List[Tuple[str, str]]]:
    """Return ``(all_match, [(path, observed_hex), …diffs])``."""
    diffs: List[Tuple[str, str]] = []
    with _LOCK:
        baseline = dict(_BASELINE)
    for path_str, expected in baseline.items():
        try:
            actual = hashlib.sha256(Path(path_str).read_bytes()).hexdigest()
        except OSError:
            diffs.append((path_str, "<unreadable>"))
            continue
        if actual != expected:
            diffs.append((path_str, actual))
    return len(diffs) == 0, diffs


def start_periodic(*, interval_s: float = 60.0) -> threading.Thread:
    def _loop():
        while True:
            time.sleep(interval_s)
            ok, diffs = verify_now()
            if not ok:
                logger.critical(
                    "r80.code_integrity_changed count=%d sample=%s",
                    len(diffs), diffs[:3],
                )
    th = threading.Thread(target=_loop, daemon=True, name="aria-r80-integrity")
    th.start()
    return th


register(DefencePlugin(
    round_id="R80",
    name="code_integrity",
    description="Boot baseline + periodic SHA-256 re-verification of loaded modules.",
))
