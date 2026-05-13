"""R147 — Zero-width Unicode steganography.

Threat: an attacker hides commands in zero-width characters — U+200B,
U+200C, U+200D, U+FEFF — encoded as binary digits.  Visible text
"hello world" carries an extra payload the human reviewer can't see;
the LLM may parse it.  Documented at https://utf-8.io/zwsp + repeated
demonstrations on social media 2023-2025.

Defence: ``detect_zwsp_payload(text)`` returns the *count* of zero-
width chars; > 8 in a single span = covert channel.  Also exposes
``strip_zwsp(text)`` (already in R23) for normalisation.
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_ZWSP = re.compile("[​-‏‪-‮⁦-⁩﻿]")


def count_zero_width(text: str) -> int:
    if not text:
        return 0
    return len(_ZWSP.findall(text))


def detect_zwsp_payload(text: str) -> Tuple[float, str]:
    n = count_zero_width(text)
    if n == 0:
        return 0.0, ""
    if n >= 32:
        return 0.95, f"r147.zwsp_steg count={n}"
    if n >= 8:
        return 0.7, f"r147.zwsp_count={n}"
    return 0.4, f"r147.zwsp_count={n}"


def strip_zwsp(text: str) -> str:
    return _ZWSP.sub("", text)


def _on_score(endpoint, payload, identity):
    if not payload or len(payload) > 64 * 1024:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    score, why = detect_zwsp_payload(s)
    if score == 0.0:
        return 0.0, ""
    return score, why


register(DefencePlugin(
    round_id="R147",
    name="unicode_steg",
    description="Count + score zero-width / bidi covert payloads.",
    on_score=_on_score,
))
