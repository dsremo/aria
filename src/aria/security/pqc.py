"""Post-Quantum Cryptography layer for ARIA.

Provides hybrid classical/post-quantum encryption, signatures, and key exchange.
Hardened against Mythos-class adversaries (80% exploit success rate, autonomous
multi-step attack chaining, Anthropic internal red-team benchmark 2026-04).

Architecture:
  - KEM:       X25519 (classical) + MLKEM-768 when available (true PQC hybrid)
               If MLKEM not available: X25519 + SHA3-256 domain separation.
               A Mythos-class model cannot break X25519 without quantum hardware.
               The hybrid is quantum-safe under the assumption that breaking both
               X25519 and MLKEM simultaneously is required (OR-security).
  - Signature: Ed25519 (128-bit classical) — upgrade path to ML-DSA-65 noted.
  - Symmetric: AES-256-GCM (authenticated encryption, 256-bit key size).
               AES-256 is considered quantum-safe (Grover's reduces to 128-bit,
               still computationally infeasible). Ref: NIST SP 800-131B.
  - KDF:       HKDF-SHA3-256 for key derivation (SHA-3 = Keccak, no length
               extension, quantum-resistant hash output).

References:
  NIST FIPS 203 (ML-KEM, 2024)
  NIST FIPS 204 (ML-DSA, 2024)
  NIST SP 800-56C Rev. 2 (HKDF)
  NIST SP 800-131B (quantum-resistant key lengths)
  Bernstein & Lange (2017) "Post-quantum cryptography" Nature 549, 188-194.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import struct
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

import structlog
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization

logger = structlog.get_logger()

_PQC_AVAILABLE = False
_MLKEM_CLASS = None

try:
    from quantcrypt.kem import MLKEM_768
    # Probe it — binary might be missing
    _probe = MLKEM_768()
    _pk_probe, _sk_probe = _probe.keygen()
    _MLKEM_CLASS = MLKEM_768
    _PQC_AVAILABLE = True
    logger.info("pqc.mlkem_available", algo="MLKEM_768")
except Exception:
    logger.warning(
        "pqc.mlkem_unavailable",
        fallback="X25519+SHA3-256 hybrid (classical-only KEM)",
        note="Install quantcrypt with precompiled binaries for true PQC",
    )


@dataclass
class EncapsulationResult:
    ciphertext: bytes        # sent to recipient
    shared_secret: bytes     # 32-byte symmetric key (never transmitted)
    algorithm: str           # "MLKEM768+X25519" or "X25519+SHA3"


@dataclass
class KeyPair:
    public: bytes
    private: bytes
    algorithm: str


class HybridKEM:
    """Hybrid Key Encapsulation Mechanism.

    Uses MLKEM-768 + X25519 (when PQC binaries available) or
    X25519 + SHA3-256 domain separation (classical fallback).

    Security: both component keys must be broken simultaneously.
    Ref: Bindel et al. "Hybrid Key Encapsulation Mechanisms" NIST PQC workshop 2018.

    Wiring audit Pass 3 (F13.4) — production deploys must run with
    real PQ KEM available. The classical-only fallback violates
    NIST CNSA 2.0 (effective 2030); ARIA refuses to start in
    production rather than silently shipping classical-only.
    """

    def __init__(self) -> None:
        if (
            not _PQC_AVAILABLE
            and os.environ.get("ARIA_ENVIRONMENT", "development") == "production"
        ):
            logger.critical(
                "pqc.classical_only_in_production",
                impact="MLKEM unavailable; classical-only hybrid KEM is "
                       "below NIST CNSA 2.0 — refusing to start",
                fix="install quantcrypt with precompiled MLKEM binaries",
            )
            raise RuntimeError(
                "HybridKEM refuses classical-only KEM in production "
                "(install quantcrypt with MLKEM binaries)"
            )

    def keygen(self) -> Tuple[bytes, bytes]:
        """Generate (public_key, secret_key) pair. Returns raw bytes."""
        x_priv = X25519PrivateKey.generate()
        x_pub = x_priv.public_key()
        x_priv_bytes = x_priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        x_pub_bytes = x_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

        if _PQC_AVAILABLE and _MLKEM_CLASS is not None:
            mlkem = _MLKEM_CLASS()
            pq_pub, pq_priv = mlkem.keygen()
            pub_combined = _length_prefix(x_pub_bytes) + _length_prefix(pq_pub)
            priv_combined = _length_prefix(x_priv_bytes) + _length_prefix(pq_priv)
            return pub_combined, priv_combined

        return x_pub_bytes, x_priv_bytes

    def encaps(self, public_key: bytes) -> Tuple[bytes, bytes]:
        """Encapsulate: (ciphertext, shared_secret)."""
        if _PQC_AVAILABLE and _MLKEM_CLASS is not None:
            x_pub_bytes, pq_pub = _split_length_prefix(public_key)
            eph_priv = X25519PrivateKey.generate()
            eph_pub = eph_priv.public_key()
            eph_pub_bytes = eph_pub.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
            x_shared = eph_priv.exchange(
                X25519PublicKey_from_bytes(x_pub_bytes)
            )
            mlkem = _MLKEM_CLASS()
            pq_ct, pq_ss = mlkem.encaps(pq_pub)
            ct = _length_prefix(eph_pub_bytes) + _length_prefix(pq_ct)
            combined_ss = _hkdf_sha3(x_shared + pq_ss, info=b"ARIA-HYBRID-KEM-v1")
            return ct, combined_ss

        # Classical fallback
        eph_priv = X25519PrivateKey.generate()
        eph_pub_bytes = eph_priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        x_shared = eph_priv.exchange(X25519PublicKey_from_bytes(public_key))
        ss = _hkdf_sha3(x_shared, info=b"ARIA-X25519+SHA3-v1")
        return eph_pub_bytes, ss

    def decaps(self, secret_key: bytes, ciphertext: bytes) -> bytes:
        """Decapsulate ciphertext using secret key, return shared_secret."""
        if _PQC_AVAILABLE and _MLKEM_CLASS is not None:
            x_priv_bytes, pq_priv = _split_length_prefix(secret_key)
            eph_pub_bytes, pq_ct = _split_length_prefix(ciphertext)
            x_priv = X25519PrivateKey.from_private_bytes(x_priv_bytes)
            x_shared = x_priv.exchange(X25519PublicKey_from_bytes(eph_pub_bytes))
            mlkem = _MLKEM_CLASS()
            pq_ss = mlkem.decaps(pq_priv, pq_ct)
            return _hkdf_sha3(x_shared + pq_ss, info=b"ARIA-HYBRID-KEM-v1")

        x_priv = X25519PrivateKey.from_private_bytes(secret_key)
        x_shared = x_priv.exchange(X25519PublicKey_from_bytes(ciphertext))
        return _hkdf_sha3(x_shared, info=b"ARIA-X25519+SHA3-v1")

    @staticmethod
    def is_pqc() -> bool:
        return _PQC_AVAILABLE


class SignatureScheme:
    """Ed25519 digital signatures with PQC upgrade path.

    Ed25519 provides 128-bit classical security. While not quantum-resistant
    (Shor's algorithm breaks ECC), it is the current best practice for
    spacecraft command authentication. ML-DSA-65 upgrade is noted in code
    when quantcrypt MLDSA becomes available.

    Ref: Bernstein et al. (2012) "High-speed high-security signatures" J. Crypt. Eng.
    """

    def __init__(self) -> None:
        self._priv: Optional[Ed25519PrivateKey] = None

    def generate(self) -> Tuple[bytes, bytes]:
        """Generate (public_key_bytes, private_key_bytes)."""
        self._priv = Ed25519PrivateKey.generate()
        pub_bytes = self._priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        priv_bytes = self._priv.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        return pub_bytes, priv_bytes

    @staticmethod
    def sign(private_key_bytes: bytes, message: bytes) -> bytes:
        priv = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        return priv.sign(message)

    @staticmethod
    def verify(public_key_bytes: bytes, message: bytes, signature: bytes) -> bool:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            pub = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            pub.verify(signature, message)
            return True
        except Exception:
            return False


# ── ML-DSA dual-signature interface (TT&C audit H-4) ────────────────


@dataclass(frozen=True)
class DualSignature:
    """Composite Ed25519 + ML-DSA-65 signature.

    Both components must verify; either component failing rejects the
    whole signature.  When ML-DSA is unavailable (no ``quantcrypt``
    binary), the ``mldsa_*`` fields are empty and the dual-sign
    behaviour degrades to Ed25519 alone — production deploys MUST
    install quantcrypt to satisfy NIST CNSA 2.0 (effective 2030).
    """
    ed25519_sig: bytes
    mldsa_sig: bytes
    ed25519_pubkey: bytes
    mldsa_pubkey: bytes

    @property
    def is_pq_present(self) -> bool:
        return bool(self.mldsa_sig and self.mldsa_pubkey)


def dual_sign(
    ed25519_priv: bytes,
    message: bytes,
    *,
    mldsa_priv: bytes = b"",
    mldsa_pub: bytes = b"",
    ed25519_pub: bytes = b"",
) -> DualSignature:
    """Produce a dual signature.  ``mldsa_priv``/``mldsa_pub`` may be
    empty in dev environments without quantcrypt — callers can detect
    via :attr:`DualSignature.is_pq_present` and refuse non-PQ signatures
    in production mode.
    """
    ed_sig = SignatureScheme.sign(ed25519_priv, message)
    mldsa_sig = b""
    if mldsa_priv and _PQC_AVAILABLE:
        try:
            from quantcrypt.dss import MLDSA_65    # type: ignore[import-not-found]
            mldsa_sig = MLDSA_65().sign(message, mldsa_priv)
        except Exception as exc:    # noqa: BLE001
            logger.warning("pqc.mldsa_sign_failed", error=str(exc))
            mldsa_sig = b""
    return DualSignature(
        ed25519_sig=ed_sig,
        mldsa_sig=mldsa_sig,
        ed25519_pubkey=ed25519_pub,
        mldsa_pubkey=mldsa_pub,
    )


def dual_verify(
    signature: DualSignature,
    message: bytes,
    *,
    require_pq: bool = False,
) -> bool:
    """Verify a dual signature.  When ``require_pq`` is True and the
    ML-DSA component is absent, return False (production mode).  Both
    components must verify when both are present.
    """
    if require_pq and not signature.is_pq_present:
        return False
    if not SignatureScheme.verify(
        signature.ed25519_pubkey, message, signature.ed25519_sig,
    ):
        return False
    if signature.is_pq_present:
        try:
            from quantcrypt.dss import MLDSA_65    # type: ignore[import-not-found]
            MLDSA_65().verify(
                message, signature.mldsa_sig, signature.mldsa_pubkey,
            )
        except Exception:    # noqa: BLE001
            return False
    return True


class SymmetricEncryptor:
    """AES-256-GCM authenticated encryption.

    AES-256 with 256-bit keys is quantum-safe under Grover's algorithm (effective
    security reduced to 128-bit, still computationally infeasible for foreseeable
    quantum hardware). Ref: NIST SP 800-131B.

    Nonce: 96-bit random (NIST SP 800-38D recommendation).
    Tag: 128-bit authentication tag (GCM default).
    """

    def __init__(self, key: Optional[bytes] = None) -> None:
        self._key = key or secrets.token_bytes(32)  # 256-bit key
        if len(self._key) != 32:
            raise ValueError("AES-256 requires exactly 32-byte key")

    def encrypt(self, plaintext: bytes, associated_data: bytes = b"") -> bytes:
        """Encrypt and authenticate. Returns nonce + ciphertext + tag."""
        nonce = secrets.token_bytes(12)  # 96-bit nonce per NIST SP 800-38D
        aesgcm = AESGCM(self._key)
        ct = aesgcm.encrypt(nonce, plaintext, associated_data or None)
        return nonce + ct

    def decrypt(self, ciphertext: bytes, associated_data: bytes = b"") -> bytes:
        """Decrypt and verify authentication tag. Raises on tamper."""
        if len(ciphertext) < 12 + 16:
            raise ValueError("Ciphertext too short (min nonce + tag)")
        nonce, ct = ciphertext[:12], ciphertext[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ct, associated_data or None)

    @property
    def key(self) -> bytes:
        return self._key


class SecureChannel:
    """Full-duplex authenticated encrypted channel between two ARIA endpoints.

    Establishes a session using HybridKEM, then uses AES-256-GCM for
    message-level encryption. Each message includes a sequence number
    (replay protection) and timestamp.

    Designed to withstand Mythos-class MITM and replay attacks.
    """

    def __init__(self, identity: str) -> None:
        self._identity = identity
        self._kem = HybridKEM()
        self._sig = SignatureScheme()
        self._pub_key, self._priv_key = self._kem.keygen()
        self._sig_pub, self._sig_priv = self._sig.generate()
        self._session_key: Optional[bytes] = None
        self._enc: Optional[SymmetricEncryptor] = None
        self._seq: int = 0
        self._peer_seq: int = -1

    @property
    def public_key(self) -> bytes:
        return self._pub_key

    @property
    def signing_public_key(self) -> bytes:
        return self._sig_pub

    def initiate(self, peer_public_key: bytes) -> Tuple[bytes, bytes]:
        """Initiate channel as client. Returns (ciphertext, signature)."""
        ct, ss = self._kem.encaps(peer_public_key)
        self._session_key = ss
        self._enc = SymmetricEncryptor(ss[:32])
        sig = SignatureScheme.sign(self._sig_priv, ct)
        logger.info("secure_channel.initiated", identity=self._identity)
        return ct, sig

    def accept(self, ciphertext: bytes, peer_sig_pub: bytes, signature: bytes) -> bool:
        """Accept channel as server. Verifies signature, derives session key."""
        if not SignatureScheme.verify(peer_sig_pub, ciphertext, signature):
            logger.warning("secure_channel.signature_verify_failed", identity=self._identity)
            return False
        ss = self._kem.decaps(self._priv_key, ciphertext)
        self._session_key = ss
        self._enc = SymmetricEncryptor(ss[:32])
        logger.info("secure_channel.accepted", identity=self._identity)
        return True

    def send(self, plaintext: bytes) -> bytes:
        """Encrypt message with sequence number + timestamp."""
        if self._enc is None:
            raise RuntimeError("Channel not established")
        self._seq += 1
        header = struct.pack(">QQ", self._seq, int(time.time() * 1000))
        payload = header + plaintext
        return self._enc.encrypt(payload, b"aria-secure-channel-v1")

    def receive(self, ciphertext: bytes) -> bytes:
        """Decrypt and verify sequence number."""
        if self._enc is None:
            raise RuntimeError("Channel not established")
        payload = self._enc.decrypt(ciphertext, b"aria-secure-channel-v1")
        seq, ts_ms = struct.unpack(">QQ", payload[:16])
        age_s = abs(time.time() - ts_ms / 1000.0)
        if seq <= self._peer_seq:
            raise ValueError(f"Replay detected: seq {seq} <= last {self._peer_seq}")
        if age_s > 3600:
            raise ValueError(f"Stale message: age {age_s:.0f}s")
        self._peer_seq = seq
        return payload[16:]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hkdf_sha3(input_key_material: bytes, info: bytes, length: int = 32) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA3_256(),  # Keccak-based — quantum-resistant hash
        length=length,
        salt=None,
        info=info,
    )
    return hkdf.derive(input_key_material)


def _length_prefix(data: bytes) -> bytes:
    return struct.pack(">H", len(data)) + data


def _split_length_prefix(data: bytes) -> Tuple[bytes, bytes]:
    n1 = struct.unpack(">H", data[:2])[0]
    first = data[2 : 2 + n1]
    rest = data[2 + n1:]
    n2 = struct.unpack(">H", rest[:2])[0]
    second = rest[2 : 2 + n2]
    return first, second


def X25519PublicKey_from_bytes(pub_bytes: bytes):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    return X25519PublicKey.from_public_bytes(pub_bytes)


def generate_session_key(length: int = 32) -> bytes:
    """Generate a cryptographically secure random session key."""
    return secrets.token_bytes(length)


def constant_time_compare(a: bytes, b: bytes) -> bool:
    """Constant-time comparison — prevents timing attacks on auth tokens."""
    return hmac.compare_digest(a, b)
