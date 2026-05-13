"""R204 — Crypto-agility manifest.

Threat: when a primitive breaks (RC4, SHA-1, DES, RSA-1024) most
codebases discover the dependency by grepping — and miss half the
sites.  Y2Q migration will be the largest single break since SHA-1.

Defence: a per-purpose ``CryptoSpec`` manifest enumerating which
algorithm + key-size + provenance ARIA uses for each role
(``audit_seal``, ``token_sign``, ``transport``, ``code_sign``).
``audit_manifest`` flags any role still bound to a deprecated alg.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_DEPRECATED = {
    "MD5", "SHA1", "RC4", "DES", "3DES", "RSA-1024", "DSA-1024",
    "ECDSA-P224",
}

_QUANTUM_VULNERABLE = {
    "ECDSA-P256", "ECDSA-P384", "ECDSA-P521",
    "RSA-2048", "RSA-3072", "RSA-4096",
    "Ed25519", "X25519",
}


@dataclass
class CryptoSpec:
    role: str
    algorithm: str
    key_size_bits: int = 0
    provenance: str = ""
    not_before: float = 0.0
    not_after: float = 0.0


_MANIFEST: Dict[str, CryptoSpec] = {
    "audit_seal":  CryptoSpec("audit_seal", "HMAC-SHA-256", 256, "RFC 2104"),
    "token_sign":  CryptoSpec("token_sign", "Ed25519+ML-DSA-65", 0, "R67 hybrid"),
    "transport":   CryptoSpec("transport", "TLS 1.3 + X25519+ML-KEM-768", 0, "R68 hybrid"),
    "code_sign":   CryptoSpec("code_sign", "Ed25519+SLH-DSA-128s", 0, "R203 + R7"),
    "key_wrap":    CryptoSpec("key_wrap", "AES-KWP", 256, "RFC 5649"),
    "kdf":         CryptoSpec("kdf", "HKDF-SHA-256", 0, "RFC 5869"),
    "password_kdf": CryptoSpec("password_kdf", "Argon2id", 0, "R65"),
    "at_rest":     CryptoSpec("at_rest", "AES-GCM-SIV", 256, "RFC 8452"),
    "request_id":  CryptoSpec("request_id", "SHA-256 truncated", 128, "R150"),
}


def audit_manifest() -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for role, spec in _MANIFEST.items():
        if any(d in spec.algorithm for d in _DEPRECATED):
            issues.append(f"deprecated:{role}={spec.algorithm}")
        if any(q == spec.algorithm.split("+")[0] for q in _QUANTUM_VULNERABLE):
            if "+" not in spec.algorithm:
                issues.append(f"quantum_only:{role}={spec.algorithm}")
    return not issues, issues


def render_manifest_md() -> str:
    lines = ["| Role | Algorithm | Key (bits) | Provenance |",
             "|------|-----------|------------|------------|"]
    for spec in _MANIFEST.values():
        lines.append(f"| {spec.role} | {spec.algorithm} | {spec.key_size_bits or '—'} | {spec.provenance} |")
    return "\n".join(lines)


def update_role(role: str, algorithm: str, *, key_size_bits: int = 0, provenance: str = "") -> None:
    _MANIFEST[role] = CryptoSpec(role, algorithm, key_size_bits, provenance, time.time(), 0.0)


register(DefencePlugin(
    round_id="R204",
    name="crypto_agility",
    description="Per-role crypto manifest; deprecated + quantum-only algorithm audit.",
))
