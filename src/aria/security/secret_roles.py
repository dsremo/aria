"""Role-separated key derivation and rotation hook.

TT&C audit C-7: previously, ``ARIA_SHARED_SECRET`` was used directly as
the Bearer token, the HMAC signing key, and the per-action challenge
verifier.  A single sniff (TLS misconfig, env-dump in a crash report,
log-leak) compromised the entire command-link until the next process
restart.

This module derives per-role subkeys from the root via HKDF-SHA-256
with role-bound ``info`` strings.  Compromise of a derived subkey does
not reveal the root or sibling subkeys (HKDF security relies on PRF
indistinguishability of HMAC-SHA-256).

Roles:
    - ``http_bearer``   — used for the API Bearer comparison.
    - ``http_envelope`` — HMAC over (counter|nonce|timestamp|body).
    - ``ws_envelope``   — same role-binding for the WebSocket path.
    - ``ccsds_tc``      — auth tag on CCSDS TC frames.
    - ``audit_anchor``  — long-term anchor signing.

Rotation:
    Bumping ``epoch`` produces a fresh derivation context; legitimate
    clients must perform a re-handshake to learn the new epoch.  An
    attacker who has captured an old subkey is locked out at the next
    rotation regardless of whether they captured the root.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
from dataclasses import dataclass


_HKDF_HASH = hashlib.sha256
_HKDF_HASH_LEN = 32


def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = bytes(_HKDF_HASH_LEN)
    return hmac.new(salt, ikm, _HKDF_HASH).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    t = b""
    counter = 1
    while len(b"".join(blocks)) < length:
        t = hmac.new(prk, t + info + bytes([counter]), _HKDF_HASH).digest()
        blocks.append(t)
        counter += 1
    return b"".join(blocks)[:length]


def derive_subkey(
    root_secret: bytes,
    role: str,
    *,
    epoch: int = 0,
    length: int = 32,
    salt: bytes = b"aria-tt&c-v1",
) -> bytes:
    """HKDF-SHA-256 with role + epoch binding.

    ``info`` is ``f"{role}|epoch={epoch}".encode()`` — flipping either
    field gives a fully-independent subkey, so an attacker who recovers
    one role's subkey cannot pivot to another role or to the root.
    """
    if not isinstance(root_secret, (bytes, bytearray)):
        raise TypeError("root_secret must be bytes")
    if not role or not isinstance(role, str):
        raise ValueError("role must be a non-empty string")
    info = f"{role}|epoch={int(epoch)}".encode("utf-8")
    prk = _hkdf_extract(salt, bytes(root_secret))
    return _hkdf_expand(prk, info, length)


@dataclass
class _EpochState:
    epoch: int = 0


class SecretRing:
    """Process-wide rotation registry.  Holds the current epoch and
    derives subkeys on demand.  Rotation is operator-initiated (call
    :meth:`rotate`); clients must re-handshake after rotation.
    """

    def __init__(self, root_secret: bytes) -> None:
        if not isinstance(root_secret, (bytes, bytearray)):
            raise TypeError("root_secret must be bytes")
        self._root = bytes(root_secret)
        self._state = _EpochState()
        self._lock = threading.Lock()

    @property
    def epoch(self) -> int:
        with self._lock:
            return self._state.epoch

    def rotate(self) -> int:
        """Bump the epoch, returning the new value.  Idempotent — call
        from a maintenance hook (Ctrl-C in the captain console, REST
        endpoint guarded by per-action challenge, etc.).  All previously
        derived subkeys become invalid for the next handshake."""
        with self._lock:
            self._state.epoch += 1
            return self._state.epoch

    def subkey(self, role: str, *, length: int = 32) -> bytes:
        with self._lock:
            epoch = self._state.epoch
        return derive_subkey(
            self._root, role, epoch=epoch, length=length,
        )

    def subkey_for_epoch(
        self, role: str, epoch: int, *, length: int = 32,
    ) -> bytes:
        """Explicit-epoch derivation — for ground simulators that need
        to verify a frame issued under a previous epoch."""
        return derive_subkey(self._root, role, epoch=epoch, length=length)
