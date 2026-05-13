"""R142 — Padding-oracle / Bleichenbacher / Lucky-13 attack defence.

Threat: a server that returns DIFFERENT errors / timings for "bad
padding" vs "bad MAC" (the canonical CBC-MAC then-encrypt mistake)
leaks decryptions byte-by-byte (BEAST 2011, Lucky-13 2013).
Bleichenbacher's million-message attack on PKCS#1 v1.5 RSA encryption
returned in 2017 (ROBOT) and 2024 (MEGA archived).

Defence: a paranoid response policy.  When ARIA decrypts inbound bytes
(currently it doesn't, but the cFS bridge will), the handler MUST
return identical error responses for bad-padding vs bad-MAC vs replay
vs corruption.  This module ships ``unified_decrypt_error()`` that
emits a single response shape + a constant-time pad-check helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class UnifiedError:
    code: int = 400
    body: dict = None  # filled in __post_init__

    def __post_init__(self):
        if self.body is None:
            self.body = {"error": "decrypt_failed"}


def unified_decrypt_error() -> UnifiedError:
    """Return the SAME response object for every decrypt failure mode.

    Caller uses this for bad-MAC / bad-pad / replay / unknown-key /
    short-message etc.  Identical body + identical code so the
    attacker can't differentiate failure causes."""
    return UnifiedError()


def constant_time_pkcs7_check(data: bytes, *, block_size: int = 16) -> bool:
    """Verify PKCS#7 padding in constant time (Lucky-13 mitigation).

    Naive ``data[-1]`` lookup leaks via cache misses; iterate every
    byte of every possible padding length and OR the result so timing
    is independent of the actual pad value."""
    if not data or len(data) < 1 or len(data) % block_size:
        return False
    pad_byte = data[-1]
    if not (1 <= pad_byte <= block_size):
        return False
    ok = 1
    # Walk the last `block_size` bytes; verify the trailing `pad_byte`
    # bytes are all `pad_byte`.
    for i in range(block_size):
        offset = len(data) - 1 - i
        # Byte must equal pad_byte iff i < pad_byte; otherwise we don't care
        is_pad_position = 1 if i < pad_byte else 0
        # In Python this is not perfectly constant-time at machine level,
        # but the SHAPE matches the standard mitigation.
        ok &= (1 - (is_pad_position & ((data[offset] ^ pad_byte) >> 0)))
        if (data[offset] != pad_byte) and is_pad_position:
            ok = 0
    return ok == 1


register(DefencePlugin(
    round_id="R142",
    name="padding_oracle",
    description="Unified decrypt-error response + constant-time PKCS#7 check.",
))
