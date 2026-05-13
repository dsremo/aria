"""R211 — Y2Q migration tracker.

Threat: the cryptographically-relevant quantum computer (CRQC)
arrival date is uncertain (NIST ~2030, Mosca harvest-now-decrypt-
later already underway).  Without a migration tracker, organisations
discover at audit time that 40% of TLS endpoints still serve
classical-only.

Defence: a migration record per role mapping classical alg →
PQ-hybrid alg → percent-rolled-out.  ``audit_migration_progress``
returns the laggard roles so leadership has a single number.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class MigrationRecord:
    role: str
    classical: str
    pq_target: str
    rolled_out_pct: float = 0.0     # 0..100
    target_pct: float = 100.0
    target_year: int = 2030


_TRACKER: Dict[str, MigrationRecord] = {
    "tls":         MigrationRecord("tls", "X25519", "X25519MLKEM768"),
    "ssh":         MigrationRecord("ssh", "curve25519-sha256", "sntrup761x25519-sha512"),
    "code_sign":   MigrationRecord("code_sign", "Ed25519", "Ed25519+SLH-DSA-128s"),
    "token_sign":  MigrationRecord("token_sign", "Ed25519", "Ed25519+ML-DSA-65"),
    "kex_at_rest": MigrationRecord("kex_at_rest", "RSA-OAEP-2048", "ML-KEM-768"),
}
_LOCK = threading.Lock()


def update_progress(role: str, *, rolled_out_pct: float) -> None:
    with _LOCK:
        rec = _TRACKER.get(role)
        if rec is None:
            return
        rec.rolled_out_pct = max(0.0, min(100.0, rolled_out_pct))


def audit_migration_progress() -> Tuple[float, List[str]]:
    laggards: List[str] = []
    with _LOCK:
        items = list(_TRACKER.values())
    if not items:
        return 0.0, []
    total = sum(r.rolled_out_pct for r in items) / len(items)
    for r in items:
        if r.rolled_out_pct < 50.0:
            laggards.append(f"{r.role}={r.rolled_out_pct:.0f}%->{r.pq_target}")
    return total, laggards


def render_tracker_md() -> str:
    lines = ["| Role | Classical | PQ target | Rolled-out % |",
             "|------|-----------|-----------|--------------|"]
    with _LOCK:
        for r in _TRACKER.values():
            lines.append(f"| {r.role} | {r.classical} | {r.pq_target} | {r.rolled_out_pct:.0f}% |")
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R211",
    name="y2q_tracker",
    description="Per-role classical→PQ migration progress tracker.",
))
