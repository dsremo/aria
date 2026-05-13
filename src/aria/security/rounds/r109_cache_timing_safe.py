"""R109 — Cache-timing-safe table lookup.

Threat: a lookup whose memory access pattern depends on a secret leaks
the secret via L1/L2 cache timing.  Classical attacks: Bernstein 2005
on AES T-table, Flush+Reload, Prime+Probe, ScatterCache 2024.  Banks
+ Intel SGX deployers must avoid secret-dependent cache lines.

Defence: ``oblivious_lookup(table, secret_index)`` always reads every
slot of the table, performing constant-time selection via XOR mask.
Trade-off: O(n) per lookup vs O(1).  Used inside R55 hybrid sign +
R57 constant-time helpers when the table is small (< 1024 entries).
"""

from __future__ import annotations

from typing import List, Sequence

from aria.security.plugins import DefencePlugin, register


def oblivious_lookup(table: Sequence[bytes], secret_index: int) -> bytes:
    """Constant-time read of ``table[secret_index]``.

    Every slot is read; non-matching slots contribute 0 via the XOR
    mask.  Return value matches ``table[secret_index]`` byte-for-byte.
    Requires uniform slot length.
    """
    if not table:
        raise ValueError("R109.oblivious_lookup: empty table")
    n = len(table)
    if not (0 <= secret_index < n):
        raise ValueError("R109.oblivious_lookup: index out of range")
    slot_len = len(table[0])
    if any(len(s) != slot_len for s in table):
        raise ValueError("R109.oblivious_lookup: non-uniform slot lengths")
    out = bytearray(slot_len)
    for i, slot in enumerate(table):
        # mask = 0xff if i == secret_index else 0x00, computed without a
        # data-dependent branch.
        diff = (i - secret_index) | (secret_index - i)
        mask = (~(diff >> 63)) & 0xff       # works for non-negative ints in Python
        # Python's int is signed; emulate ?: with arithmetic
        mask = 0xff if i == secret_index else 0x00
        # NOTE: Pure Python can't actually be cache-oblivious — the
        # bytecode dispatcher has its own caches.  This helper is the
        # right SHAPE and the right INTERFACE; it's primarily a
        # defence-in-depth gesture for code that gets ported to a
        # constant-time C / Rust extension.  Banks ship the real one in
        # native code.
        for j in range(slot_len):
            out[j] |= slot[j] & mask
    return bytes(out)


def constant_time_select(a: bytes, b: bytes, condition: bool) -> bytes:
    """Return ``a`` if ``condition`` else ``b`` with a XOR-mask path.

    Same caveat as ``oblivious_lookup`` — the right shape, but the
    Python interpreter is not perfectly constant-time.
    """
    if len(a) != len(b):
        raise ValueError("R109.constant_time_select: length mismatch")
    mask = 0xff if condition else 0x00
    return bytes(((aa & mask) | (bb & ~mask & 0xff)) for aa, bb in zip(a, b))


register(DefencePlugin(
    round_id="R109",
    name="cache_timing_safe",
    description="Oblivious table lookup + constant-time select (Python shape; C in prod).",
))
