"""R248 — Counter-intel decoy / canary pattern.

Threat: an attacker who has *already* breached studies infrastructure
to plan exfil.  If decoy assets are obvious or static, the attacker
recognises and avoids them.  Decoy refresh + variability is the
counter — make the trap indistinguishable from a real artefact.

Defence: a decoy generator that produces realistic-looking
credentials, document paths, DB rows, with embedded canary tokens
that R195 scan_for_decoys recognises.  ``rotate`` re-generates so
attackers can't memorise the trap surface.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


@dataclass
class DecoyArtefact:
    kind: str        # "aws_credential" | "github_token" | "db_row"
    path: str
    canary: str
    created_at: float = field(default_factory=time.time)


_ACTIVE_DECOYS: Dict[str, DecoyArtefact] = {}
_LOCK = threading.Lock()


def generate_decoy(kind: str = "aws_credential") -> DecoyArtefact:
    canary = f"ARIA_CANARY_{secrets.token_hex(8)}"
    if kind == "aws_credential":
        path = f"/var/secrets/aws_{secrets.token_hex(4)}.creds"
    elif kind == "github_token":
        path = f"/var/secrets/github_pat_{secrets.token_hex(4)}.txt"
    else:
        path = f"/var/decoys/row_{secrets.token_hex(4)}.json"
    artefact = DecoyArtefact(kind=kind, path=path, canary=canary)
    with _LOCK:
        _ACTIVE_DECOYS[canary] = artefact
    return artefact


def rotate(*, max_age_seconds: float = 86_400) -> List[str]:
    """Discard decoys older than ``max_age_seconds``; caller regenerates."""
    t = time.time()
    rotated: List[str] = []
    with _LOCK:
        for canary in list(_ACTIVE_DECOYS):
            if t - _ACTIVE_DECOYS[canary].created_at > max_age_seconds:
                del _ACTIVE_DECOYS[canary]
                rotated.append(canary)
    return rotated


def is_canary(token: str) -> bool:
    with _LOCK:
        return token in _ACTIVE_DECOYS


def reset_for_tests() -> None:
    with _LOCK:
        _ACTIVE_DECOYS.clear()


register(DefencePlugin(
    round_id="R248",
    name="counterintel_decoy",
    description="Counter-intel decoy generator + rotator; integrates with R195 honeytokens.",
))
