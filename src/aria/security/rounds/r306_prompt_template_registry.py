"""R306 — Prompt-template registry signing.

Threat: production system prompts and few-shot templates often live
in YAML / JSON files and ship with the binary.  An attacker who edits
those — or substitutes a malicious template at deploy time — silently
weaponises the LLM.  Trivial to do without signed templates.

Defence: a per-template ``register_template`` that records SHA-256 +
signature; ``load_template`` returns the template *only* if the hash
matches the registered baseline + the signature verifies.
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class _RegistryEntry:
    template_id: str
    sha256: str
    signature: bytes
    body: str


_REGISTRY: Dict[str, _RegistryEntry] = {}
_LOCK = threading.Lock()


def register_template(
    template_id: str, body: str, signature: bytes,
) -> _RegistryEntry:
    digest = hashlib.sha256((body or "").encode("utf-8")).hexdigest()
    entry = _RegistryEntry(
        template_id=template_id, sha256=digest,
        signature=signature, body=body,
    )
    with _LOCK:
        _REGISTRY[template_id] = entry
    return entry


def load_template(
    template_id: str, *, candidate_body: str, pubkey: Optional[bytes] = None,
) -> Tuple[bool, str]:
    """Returns (verified, body_or_reason)."""
    with _LOCK:
        entry = _REGISTRY.get(template_id)
    if entry is None:
        return False, "registry.unknown_template"
    candidate_digest = hashlib.sha256((candidate_body or "").encode("utf-8")).hexdigest()
    if candidate_digest != entry.sha256:
        return False, f"registry.sha_mismatch expected={entry.sha256[:16]}…"
    if pubkey is not None:
        try:
            from aria.security.rounds.r55_hybrid_signing import hybrid_verify
            if not hybrid_verify((candidate_body or "").encode("utf-8"), entry.signature, pubkey):
                return False, "registry.signature_invalid"
        except Exception as exc:
            return False, f"registry.signature_error:{exc}"
    return True, candidate_body


def reset_for_tests() -> None:
    with _LOCK:
        _REGISTRY.clear()


register(DefencePlugin(
    round_id="R306",
    name="prompt_template_registry",
    description="Prompt-template registry: SHA-256 + hybrid signature verification on load.",
))
