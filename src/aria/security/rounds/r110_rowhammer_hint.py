"""R110 — RowHammer / cosmic-ray bit-flip hardening hints.

Threat: an attacker who can run code on the same DRAM chip as our
process can flip bits in adjacent rows by repeated activation
(RowHammer, 2014; ECCploit 2024).  Bit-flips in security-critical
memory (key bytes, function pointers) become exploits.  Cloud
providers mitigate via target row refresh; cosmic-ray-induced flips
remain.

Defence: ``ecc_protect(blob)`` returns ``blob || crc32 || sha256_truncated``;
``ecc_verify`` re-computes both and refuses on mismatch.  Used to wrap
operationally-critical in-memory blobs — boot manifest, sealed keys,
audit-chain head — so a single-bit flip is detected and refused rather
than acted on.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_TAG_LEN = 16


def ecc_protect(blob: bytes) -> bytes:
    """Append a 4-byte CRC32 + 16-byte SHA-256 prefix.  Total overhead 20 B."""
    crc = zlib.crc32(blob) & 0xFFFFFFFF
    digest = hashlib.sha256(blob).digest()[:_TAG_LEN]
    return blob + struct.pack(">I", crc) + digest


def ecc_verify(protected: bytes) -> Tuple[bool, Optional[bytes]]:
    if len(protected) < 4 + _TAG_LEN:
        return False, None
    payload = protected[: -(4 + _TAG_LEN)]
    crc_packed = protected[-(4 + _TAG_LEN): -_TAG_LEN]
    digest = protected[-_TAG_LEN:]
    crc_expected = zlib.crc32(payload) & 0xFFFFFFFF
    crc_actual = struct.unpack(">I", crc_packed)[0]
    if crc_expected != crc_actual:
        return False, None
    if hashlib.sha256(payload).digest()[:_TAG_LEN] != digest:
        return False, None
    return True, payload


register(DefencePlugin(
    round_id="R110",
    name="rowhammer_hint",
    description="ECC-style CRC32 + SHA-256 wrap for in-memory critical blobs.",
))
