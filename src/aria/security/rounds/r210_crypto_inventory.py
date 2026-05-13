"""R210 — Cryptographic inventory + rotation schedule.

Threat: keys with no rotation schedule outlive the threat model
they were chosen for.  An audit team finds 6-year-old root keys
and the org can't tell who deployed them or what they sign.

Defence: a per-key inventory record (algorithm, role, install_ts,
last_rotated_ts, rotation_period) + ``due_for_rotation`` audit and
``register_rotation`` after rotation.  Pairs with R125 (KMS) and
R204 (manifest).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class KeyRecord:
    key_id: str
    algorithm: str
    role: str
    install_ts: float
    last_rotated_ts: float
    rotation_period_seconds: float
    custodian: str = ""


_INVENTORY: Dict[str, KeyRecord] = {}
_LOCK = threading.Lock()


def register_key(
    key_id: str, algorithm: str, role: str,
    *, rotation_period_days: float = 365.0, custodian: str = "",
) -> KeyRecord:
    rec = KeyRecord(
        key_id=key_id, algorithm=algorithm, role=role,
        install_ts=time.time(), last_rotated_ts=time.time(),
        rotation_period_seconds=rotation_period_days * 86_400,
        custodian=custodian,
    )
    with _LOCK:
        _INVENTORY[key_id] = rec
    return rec


def register_rotation(key_id: str, *, now: float = 0.0) -> bool:
    with _LOCK:
        rec = _INVENTORY.get(key_id)
        if rec is None:
            return False
        rec.last_rotated_ts = now or time.time()
    return True


def due_for_rotation(*, now: float = 0.0) -> List[Tuple[str, float]]:
    t = now or time.time()
    out: List[Tuple[str, float]] = []
    with _LOCK:
        for k, r in _INVENTORY.items():
            age = t - r.last_rotated_ts
            if age > r.rotation_period_seconds:
                out.append((k, age))
    return out


def render_inventory_md() -> str:
    lines = ["| Key ID | Algorithm | Role | Last rotated | Period (days) |",
             "|--------|-----------|------|--------------|---------------|"]
    with _LOCK:
        for r in _INVENTORY.values():
            lines.append(
                f"| {r.key_id} | {r.algorithm} | {r.role} | "
                f"{int(r.last_rotated_ts)} | {r.rotation_period_seconds / 86_400:.0f} |"
            )
    return "\n".join(lines)


register(DefencePlugin(
    round_id="R210",
    name="crypto_inventory",
    description="Per-key inventory + rotation overdue detector.",
))
