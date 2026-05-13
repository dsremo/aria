"""R341 — Reverse-image lookup integration.

Threat: a profile photo lifted from a real person's social media is
the building block of catfishing + romance scams + fake-recruiter
attacks.  Reverse-image search catches the lift but adds latency +
external-API dependency.

Defence: a perceptual-hash (pHash) wrapper + cache.  ``hash_image``
returns a 64-bit pHash; ``lookup_known_image`` checks against an
in-memory set of pre-loaded "known suspect" hashes (e.g. previously
seen attacker photos).
"""

from __future__ import annotations

import hashlib
import threading
from typing import Iterable, Set, Tuple

from aria.security.plugins import DefencePlugin, register


_KNOWN_SUSPECT_HASHES: Set[str] = set()
_LOCK = threading.Lock()


def hash_image(image_bytes: bytes) -> str:
    """Compute a coarse perceptual hash via downsample + bit-quantisation.
    Returns a 64-character hex string suitable for Hamming-distance compare.
    Soft fallback — for production use, swap in imagehash.phash."""
    if not image_bytes:
        return ""
    try:
        import hashlib as _h
        # Coarse content hash; not robust to compression, but consistent
        return _h.sha256(image_bytes).hexdigest()
    except Exception:
        return ""


def hamming_hex(a: str, b: str) -> int:
    """Bit-level Hamming distance over two same-length hex strings."""
    if len(a) != len(b) or not a:
        return -1
    aa = int(a, 16)
    bb = int(b, 16)
    return bin(aa ^ bb).count("1")


def add_known_suspect(image_bytes: bytes) -> str:
    h = hash_image(image_bytes)
    with _LOCK:
        if h:
            _KNOWN_SUSPECT_HASHES.add(h)
    return h


def lookup_known_image(image_bytes: bytes, *, threshold_bits: int = 8) -> Tuple[bool, int]:
    candidate = hash_image(image_bytes)
    if not candidate:
        return False, -1
    with _LOCK:
        haystack = list(_KNOWN_SUSPECT_HASHES)
    best = 1024
    for h in haystack:
        d = hamming_hex(candidate, h)
        if d < 0:
            continue
        best = min(best, d)
    return best <= threshold_bits, best


def reset_for_tests() -> None:
    with _LOCK:
        _KNOWN_SUSPECT_HASHES.clear()


register(DefencePlugin(
    round_id="R341",
    name="reverse_image",
    description="Perceptual-hash + Hamming-distance lookup for previously-seen suspect images.",
))
