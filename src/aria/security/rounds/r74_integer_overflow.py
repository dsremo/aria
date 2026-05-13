"""R74 — Integer-overflow guard for sensitive arithmetic.

Threat: a length × stride multiplication wraps around 2³² and the
caller allocates a tiny buffer for what the attacker expects to be
huge data; the subsequent write smashes the heap.  CVE-2024-XXX class;
common in image / video / packet decoders.  Python's int is arbitrary-
precision so the language itself is safe — but ARIA bridges to C
sometimes, and length fields in inbound bytes are adversarial inputs.

Defence: ``checked_mul(a, b, max_value)`` / ``checked_add(...)`` /
``size_for(count, stride, max_bytes)`` — explicit-bounds helpers.
The signature returns ``(value, overflow_bool)`` so consumers don't
silently pass bad values through.
"""

from __future__ import annotations

from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_DEFAULT_MAX = 2 ** 31 - 1


def checked_add(a: int, b: int, *, max_value: int = _DEFAULT_MAX) -> Tuple[int, bool]:
    if a < 0 or b < 0:
        return 0, True
    s = a + b
    if s > max_value:
        return 0, True
    return s, False


def checked_mul(a: int, b: int, *, max_value: int = _DEFAULT_MAX) -> Tuple[int, bool]:
    if a < 0 or b < 0:
        return 0, True
    if a == 0 or b == 0:
        return 0, False
    if a > max_value // b:
        return 0, True
    return a * b, False


def size_for(count: int, stride: int, *, max_bytes: int = 64 * 1024 * 1024) -> int:
    """Allocate-size helper.  Raises ``OverflowError`` if the product
    would exceed ``max_bytes`` or wrap.  Use inside parsers that allocate
    one buffer per ``count`` items."""
    n, overflow = checked_mul(int(count), int(stride), max_value=max_bytes)
    if overflow:
        raise OverflowError(
            f"R74.size_for: count={count} * stride={stride} > {max_bytes}"
        )
    return n


register(DefencePlugin(
    round_id="R74",
    name="integer_overflow",
    description="Bounded checked_add / checked_mul / size_for helpers.",
))
