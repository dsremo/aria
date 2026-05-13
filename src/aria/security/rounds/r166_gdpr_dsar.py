"""R166 — GDPR data-subject-access-request handler.

Threat: under GDPR Art. 15 (access), Art. 17 (erasure), Art. 20
(portability), an EU resident can demand their data within 30 days.
A repo without first-class DSAR plumbing leaks PII through ad-hoc
SQL → CSV pipelines under deadline pressure.

Defence: a DSAR struct + handlers ``export_subject_data`` and
``erase_subject_data``.  Each takes a callback per data store; the
callback returns a dict, the handler bundles into one JSON archive.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class DSARequest:
    subject_id: str
    purpose: str        # "access" | "erasure" | "portability"
    received_at: float


def export_subject_data(
    req: DSARequest,
    sources: Dict[str, Callable[[str], Dict[str, Any]]],
) -> Tuple[str, Dict[str, Any]]:
    if req.purpose not in ("access", "portability"):
        raise ValueError(f"R166: purpose must be access|portability, got {req.purpose}")
    bundle: Dict[str, Any] = {
        "subject_id": req.subject_id,
        "exported_at": time.time(),
        "purpose": req.purpose,
        "sources": {},
    }
    for name, getter in sources.items():
        try:
            bundle["sources"][name] = getter(req.subject_id) or {}
        except Exception as exc:
            bundle["sources"][name] = {"_error": str(exc)}
    return json.dumps(bundle, sort_keys=True, default=str), bundle


def erase_subject_data(
    req: DSARequest,
    erasers: Dict[str, Callable[[str], int]],
) -> Tuple[bool, List[str]]:
    if req.purpose != "erasure":
        raise ValueError("R166: erasure required")
    log: List[str] = []
    failures = 0
    for name, eraser in erasers.items():
        try:
            n = eraser(req.subject_id)
            log.append(f"{name}:erased={n}")
        except Exception as exc:
            failures += 1
            log.append(f"{name}:error={exc}")
    return failures == 0, log


register(DefencePlugin(
    round_id="R166",
    name="gdpr_dsar",
    description="GDPR Art. 15/17/20 data-subject access + erasure dispatcher.",
))
