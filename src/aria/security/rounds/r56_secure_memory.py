"""R56 — Secure memory wiping + mlock for short-lived secrets.

Threat: a freed-but-not-zeroed buffer holding a key fragment can be
recovered from a process core dump, swap file, or container snapshot.
Heartbleed (CVE-2014-0160) was a stark case — buffers in OpenSSL leaked
recent heap content over the wire.  Banking + classified guidance: zero
sensitive memory immediately + mlock pages to disable swap.

Defence: a ``with secure_buffer(size) as buf:`` context manager that
allocates a fixed-size mutable buffer, mlocks the page on POSIX, and
overwrites with zeros + random + zeros at exit.  Best-effort — Python's
GC may copy bytes in the meantime, but the canonical scratch lands
inside this region and the wipe is the right last-line guarantee.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import secrets
from typing import Iterator

from aria.security.plugins import DefencePlugin, register


def _mlock(addr: int, length: int) -> bool:
    if os.name != "posix":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        return libc.mlock(ctypes.c_void_p(addr), ctypes.c_size_t(length)) == 0
    except Exception:
        return False


def _munlock(addr: int, length: int) -> None:
    if os.name != "posix":
        return
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.munlock(ctypes.c_void_p(addr), ctypes.c_size_t(length))
    except Exception:
        pass


@contextlib.contextmanager
def secure_buffer(size: int) -> Iterator[bytearray]:
    """Mutable byte buffer with best-effort mlock + 3-pass wipe at exit."""
    if size < 1 or size > 64 * 1024:
        raise ValueError("R56.secure_buffer: size out of range")
    buf = bytearray(size)
    addr = ctypes.addressof((ctypes.c_char * size).from_buffer(buf))
    locked = _mlock(addr, size)
    try:
        yield buf
    finally:
        try:
            for fill in (b"\x00", os.urandom(1), b"\x00"):
                ctypes.memset(addr, fill[0], size)
        except Exception:
            pass
        if locked:
            _munlock(addr, size)


def secure_compare_and_wipe(a: bytes, b: bytearray) -> bool:
    """Constant-time compare ``a`` against the bytes in mutable ``b``;
    wipe ``b`` regardless of result."""
    import hmac as _hmac
    try:
        return _hmac.compare_digest(a, bytes(b))
    finally:
        for i in range(len(b)):
            b[i] = 0


register(DefencePlugin(
    round_id="R56",
    name="secure_memory",
    description="secure_buffer context manager: mlock + 3-pass wipe.",
))
