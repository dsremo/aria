"""R302 — Model lineage signed manifest.

Threat: a deployed ML model's provenance — training data, hyper-
parameters, base checkpoint, evaluation results — is rarely
verifiable post-hoc.  An attacker swapping the weights or training
on poisoned data produces an indistinguishable file.

Defence: a structured ``ModelManifest`` with SHA-256 of weights,
training-data manifest, base-model id, eval-metric snapshot, signed
via R67 hybrid Ed25519+ML-DSA.  Verification refuses unsigned or
hash-mismatched models.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class ModelManifest:
    model_id: str
    weights_sha256: str
    base_model_id: str = ""
    training_data_manifest_sha256: str = ""
    hyperparameters: Dict[str, object] = field(default_factory=dict)
    eval_metrics: Dict[str, float] = field(default_factory=dict)
    license: str = ""
    issued_at: float = 0.0


def serialise(m: ModelManifest) -> bytes:
    return json.dumps(asdict(m), sort_keys=True, default=str).encode("utf-8")


def sign_manifest(m: ModelManifest, sk: bytes) -> Optional[bytes]:
    try:
        from aria.security.rounds.r55_hybrid_signing import hybrid_sign
        return hybrid_sign(serialise(m), sk)
    except Exception:
        return None


def verify_manifest(m: ModelManifest, signature: bytes, pk: bytes) -> Tuple[bool, str]:
    try:
        from aria.security.rounds.r55_hybrid_signing import hybrid_verify
    except Exception:
        return False, "hybrid_signing_missing"
    if not signature:
        return False, "no_signature"
    try:
        ok = hybrid_verify(serialise(m), signature, pk)
    except Exception as exc:
        return False, f"verify_error:{exc}"
    if not ok:
        return False, "signature_mismatch"
    return True, "ok"


def verify_weights_match(weights_blob: bytes, manifest: ModelManifest) -> Tuple[bool, str]:
    actual = hashlib.sha256(weights_blob).hexdigest()
    if actual != manifest.weights_sha256:
        return False, f"weights_sha_mismatch actual={actual[:16]}…"
    return True, "ok"


register(DefencePlugin(
    round_id="R302",
    name="model_lineage",
    description="Model lineage manifest + hybrid signing + weights SHA-256 verification.",
))
