"""R81 — Safe pickle alternative (msgpack) for ARIA's checkpoints.

Threat: the cFS bridge + the ML backbone (`masked_pretrain.py` etc.)
currently use ``torch.load`` / ``pickle`` on developer-trusted inputs.
R50 hardened those (``weights_only=True`` + env-gated pickle).  This
round provides a **drop-in safe alternative** so future code never has
to make the choice — it picks msgpack with a strict-types whitelist.

Defence: ``safe_dumps(obj)`` / ``safe_loads(blob)`` using ``msgpack``
in restricted mode — accepts only ``int / float / str / bytes / bool /
None / list / dict``.  Refuses ext-types, custom classes, anything else.
A thin shim over ``msgpack.packb / unpackb`` with strict_map_key=False
+ object_hook that refuses unknown ext codes.
"""

from __future__ import annotations

from typing import Any

from aria.security.plugins import DefencePlugin, register


def safe_dumps(obj: Any) -> bytes:
    """Serialise ``obj`` to msgpack bytes; raise if any value is not in
    the strict-type whitelist."""
    import msgpack
    _check_types(obj)
    return msgpack.packb(obj, use_bin_type=True)


def safe_loads(blob: bytes, *, max_bytes: int = 16 * 1024 * 1024) -> Any:
    """Parse ``blob`` back; raise if any value is outside the whitelist."""
    if len(blob) > max_bytes:
        raise ValueError(f"R81.safe_loads: blob > {max_bytes} bytes")
    import msgpack
    obj = msgpack.unpackb(
        blob,
        raw=False,
        ext_hook=_refuse_ext,
        strict_map_key=False,
    )
    _check_types(obj)
    return obj


def _refuse_ext(code: int, data: bytes) -> Any:
    raise ValueError(f"R81.safe_loads: msgpack ext code {code} refused")


_OK_TYPES = (int, float, str, bytes, bool, type(None))


def _check_types(obj: Any, depth: int = 0) -> None:
    if depth > 64:
        raise ValueError("R81.safe_dumps: structure too deep")
    if isinstance(obj, _OK_TYPES):
        return
    if isinstance(obj, list):
        for v in obj:
            _check_types(v, depth + 1)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, (str, int, bytes)):
                raise ValueError(f"R81.safe_dumps: dict key type {type(k).__name__} refused")
            _check_types(v, depth + 1)
        return
    raise ValueError(f"R81.safe_dumps: type {type(obj).__name__} refused")


register(DefencePlugin(
    round_id="R81",
    name="pickle_safe_alt",
    description="Strict-types msgpack serialisation: drop-in pickle replacement.",
))
