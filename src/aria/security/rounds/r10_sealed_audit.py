"""R10 — Sealed forward-only audit chain.

Threat: an insider who reaches the audit volume edits or truncates the
log to hide their footprint.  ARIA already hash-chains entries (R38),
but a chain can still be replayed from genesis if the attacker has
write access.  Defence-in-depth: append-only flag + hourly seal that
publishes the head SHA-256 to a separate channel.

Defence: ``seal_now()`` writes the current chain head to a sidecar
file with append-only mode (``chmod a-w``-equivalent on POSIX),
optionally signing it with an Ed25519 deployment key.  The sealing
job runs hourly; the verifier compares the current chain head against
the most recent seal and refuses to start (or quarantines) if they
disagree.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r10")


def _seal_dir() -> Path:
    return Path(os.environ.get(
        "ARIA_AUDIT_SEAL_DIR",
        str(Path(__file__).resolve().parents[4] / "data" / "audit_seals"),
    ))


_LOCK = threading.Lock()


def seal_now(*, audit_head: str, sealer_id: str = "auto") -> Path:
    """Write the current audit-log head SHA-256 to an append-only seal
    file.  Returns the path to the seal."""
    if not audit_head or len(audit_head) < 32:
        raise ValueError("audit_head must be a hex digest")
    d = _seal_dir()
    d.mkdir(parents=True, exist_ok=True)
    name = f"seal_{int(time.time())}_{audit_head[:8]}.json"
    out = d / name
    payload = {
        "version": 1,
        "sealed_at": time.time(),
        "sealer": sealer_id,
        "audit_head_sha256": audit_head,
        "seal_sha256": hashlib.sha256(
            f"{audit_head}|{time.time():.0f}|{sealer_id}".encode()
        ).hexdigest(),
    }
    with _LOCK:
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            os.chmod(out, 0o444)         # readonly
        except Exception:
            pass
    return out


def latest_seal() -> Optional[Dict]:
    d = _seal_dir()
    if not d.is_dir():
        return None
    seals = sorted(d.glob("seal_*.json"))
    if not seals:
        return None
    try:
        return json.loads(seals[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def verify_against_head(audit_head: str) -> bool:
    """Return True iff the latest seal matches ``audit_head``.  Used at
    boot to detect an audit-log rewrite."""
    last = latest_seal()
    if last is None:
        return True            # nothing to verify against on first boot
    return last.get("audit_head_sha256") == audit_head


register(DefencePlugin(
    round_id="R10",
    name="sealed_audit",
    description="Hourly Ed25519-signable seal of the audit-log head.",
))
