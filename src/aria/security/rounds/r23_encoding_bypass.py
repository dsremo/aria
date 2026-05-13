"""R23 — Encoding-bypass jailbreaks (base64, hex, ROT-13, leetspeak,
ZWSP-stuffing, polyglot).

Threat: an attacker hides a jailbreak inside an encoding ("decode
this base64 then act on it") to slip past surface-level prompt
sanitizers.  Garak's ``probes/encoding.py`` documents 6+ encodings.
Real cases: 2024 wave of multi-encoding combo attacks against
production chatbots (ProtectAI advisory 2024-12).

Defence: detect-then-decode-then-rescan.  We try a small set of
common encodings on suspicious-looking blobs (high entropy + fits
target alphabet) and run the decoded text through the existing
sanitiser chain.  Hits fire only if the *decoded* text triggers a
defence — pure encoded text is allowed.
"""

from __future__ import annotations

import base64
import binascii
import codecs
import re
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


_BASE64_RE = re.compile(r"\b([A-Za-z0-9+/]{40,}={0,2})\b")
_HEX_RE = re.compile(r"\b((?:[a-fA-F0-9]{2}){20,})\b")
_ZWSP_RE = re.compile(r"[​-‏‪-‮⁦-⁩﻿]")


def try_decode_base64(blob: str) -> Optional[str]:
    """Best-effort base64 → utf-8.  Pads missing ``=`` so that the
    common case where the regex stripped trailing padding still decodes.
    """
    try:
        padded = blob + "=" * (-len(blob) % 4)
        decoded = base64.b64decode(padded, validate=False)
        return decoded.decode("utf-8", errors="strict")
    except Exception:
        return None


def try_decode_hex(blob: str) -> Optional[str]:
    try:
        decoded = bytes.fromhex(blob)
        return decoded.decode("utf-8", errors="strict")
    except Exception:
        return None


def strip_zwsp(text: str) -> str:
    return _ZWSP_RE.sub("", text)


def rot13(text: str) -> str:
    return codecs.encode(text, "rot_13")


def deep_rescan(text: str) -> Tuple[float, str]:
    """Return ``(score, reason)`` if a decoded layer fires a defence.

    We rescan against the latent-injection head check + DAN axes —
    the two most common jailbreak shapes that hide inside encodings.
    """
    candidates = [text]

    # Strip ZWSP / bidi controls
    cleaned = strip_zwsp(text)
    if cleaned != text:
        candidates.append(cleaned)

    # Try base64
    for m in _BASE64_RE.finditer(text):
        d = try_decode_base64(m.group(1))
        if d:
            candidates.append(d)

    # Try hex
    for m in _HEX_RE.finditer(text):
        d = try_decode_hex(m.group(1))
        if d:
            candidates.append(d)

    # ROT-13 only when the text is mostly ASCII letters (avoid garbling)
    if len(text) < 4096 and sum(c.isalpha() for c in text) > 0.5 * len(text):
        candidates.append(rot13(text))

    # Re-run latent-injection + DAN detectors on each candidate
    try:
        from aria.security.rounds.r21_latent_prompt_injection import (
            head_looks_like_instruction,
        )
        from aria.security.rounds.r22_dan_jailbreak import detect_dan
    except Exception:
        return 0.0, ""

    for c in candidates[1:]:               # skip the raw input itself
        if head_looks_like_instruction(c):
            return 0.85, "r23.encoded_instruction"
        score, axes = detect_dan(c)
        if score >= 0.5:
            return min(0.95, score), f"r23.encoded_dan axes={axes}"
    return 0.0, ""


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload or len(payload) > 256 * 1024:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    return deep_rescan(s)


register(DefencePlugin(
    round_id="R23",
    name="encoding_bypass",
    description="Detect-then-decode (base64/hex/rot13/ZWSP) and rescan.",
    on_score=_on_score,
))
