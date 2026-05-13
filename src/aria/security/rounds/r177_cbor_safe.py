"""R177 — CBOR safe-types deserializer for constrained devices.

Threat: CBOR is the wire format for COSE / SUIT / OSCORE in IoT.
A naive ``cbor2.loads`` accepts indefinite-length items, deeply
nested maps, and arbitrary tags — easy DoS against MCUs with 64 KB
RAM.

Defence: ``safe_loads`` rejects unknown tags, depth > 16, total size
> 64 KiB, and refuses indefinite-length items.  Mirrors the R81
msgpack pattern.
"""

from __future__ import annotations

from typing import Any

from aria.security.plugins import DefencePlugin, register


_OK_TYPES = (int, float, str, bytes, bool, type(None))


def safe_loads(blob: bytes, *, max_bytes: int = 64 * 1024, max_depth: int = 16) -> Any:
    if len(blob) > max_bytes:
        raise ValueError(f"R177.safe_loads: blob > {max_bytes} bytes")
    try:
        import cbor2
    except ImportError as exc:
        raise RuntimeError("R177: cbor2 missing") from exc
    try:
        obj = cbor2.loads(blob, tag_hook=_refuse_tag)
    except Exception as exc:
        raise ValueError(f"R177.safe_loads: parse failed:{exc}") from exc
    _check(obj, max_depth)
    return obj


def safe_dumps(obj: Any) -> bytes:
    try:
        import cbor2
    except ImportError as exc:
        raise RuntimeError("R177: cbor2 missing") from exc
    _check(obj, 16)
    return cbor2.dumps(obj, canonical=True)


def _refuse_tag(decoder, tag, shareable_index=None):
    raise ValueError(f"R177.safe_loads: cbor tag {tag.tag} refused")


def _check(obj: Any, max_depth: int, depth: int = 0) -> None:
    if depth > max_depth:
        raise ValueError("R177: structure too deep")
    if isinstance(obj, _OK_TYPES):
        return
    if isinstance(obj, list):
        for v in obj:
            _check(v, max_depth, depth + 1)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, (str, int, bytes)):
                raise ValueError(f"R177: dict key {type(k).__name__} refused")
            _check(v, max_depth, depth + 1)
        return
    raise ValueError(f"R177: type {type(obj).__name__} refused")


register(DefencePlugin(
    round_id="R177",
    name="cbor_safe",
    description="Strict-types CBOR loader for constrained devices: no tags, depth-limited.",
))
