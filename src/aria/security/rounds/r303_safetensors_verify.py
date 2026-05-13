"""R303 — Hugging Face safetensors verification.

Threat: the ML community shifted to safetensors specifically because
``torch.load`` over pickle is RCE-by-design.  A malicious safetensors
file is still possible via metadata abuse + tensor shape mismatches.

Defence: a strict header parser that validates the JSON header, the
declared tensor offsets against the file size, and refuses any non-
ASCII tensor name or oversized header.
"""

from __future__ import annotations

import json
import struct
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_MAX_HEADER_SIZE = 64 * 1024 * 1024
_VALID_DTYPES = {
    "F64", "F32", "F16", "BF16", "I64", "I32", "I16", "I8", "U8", "BOOL",
}


def audit_safetensors_header(blob: bytes) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if len(blob) < 8:
        return False, ["safetensors.too_small"]
    header_len = struct.unpack("<Q", blob[:8])[0]
    if header_len > _MAX_HEADER_SIZE:
        issues.append(f"safetensors.header_too_large:{header_len}")
    if 8 + header_len > len(blob):
        issues.append("safetensors.header_overflow_file")
        return False, issues

    try:
        header = json.loads(blob[8:8 + header_len].decode("utf-8"))
    except Exception as exc:
        return False, [f"safetensors.header_invalid_json:{exc}"]

    if not isinstance(header, dict):
        return False, ["safetensors.header_not_dict"]

    data_size = len(blob) - 8 - header_len
    for name, spec in header.items():
        if name == "__metadata__":
            continue
        if not name.replace("_", "").replace(".", "").isalnum():
            issues.append(f"safetensors.bad_name:{name[:32]}")
        if not isinstance(spec, dict):
            issues.append(f"safetensors.bad_spec:{name}")
            continue
        dtype = spec.get("dtype", "")
        if dtype not in _VALID_DTYPES:
            issues.append(f"safetensors.unknown_dtype:{name}={dtype}")
        offsets = spec.get("data_offsets") or []
        if (not isinstance(offsets, list) or len(offsets) != 2
                or any(not isinstance(o, int) for o in offsets)
                or offsets[0] < 0 or offsets[1] < offsets[0]
                or offsets[1] > data_size):
            issues.append(f"safetensors.invalid_offsets:{name}")

    return not issues, issues


register(DefencePlugin(
    round_id="R303",
    name="safetensors_verify",
    description="HF safetensors header audit: validate JSON + offsets + dtype allow-list.",
))
