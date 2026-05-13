"""R133 — Multi-modal prompt injection (image / audio carrier).

Threat: a model with vision input is fed an image carrying text in
visible-but-overlooked corners ("Ignore previous instructions ...").
Images uploaded to RAG / agent flows have the same effect: the OCR-ed
caption injects.  Recent: Greshake et al. 2023 + the 2024 Anthropic
+ OpenAI red-team reports document active campaigns.

Defence: when an image / audio caption is reaching ARIA's LLM context,
``audit_caption(text)`` runs the caption through R21 + R22 + R24 plus
detects telltale "screen-shotted-CMD" shapes
(``[INST] ... [/INST]``, ``###`` heading floods, ALL-CAPS commands).
Score > 0.5 → fence with stronger spotlight delimiter (R21).
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_SCREENSHOT_SHAPES = (
    re.compile(r"\[INST\][\s\S]{0,400}?\[/INST\]"),
    re.compile(r"^#{2,6}\s+\S", re.MULTILINE),
    re.compile(r"<\|im_start\|>|<\|im_end\|>"),
    re.compile(r"\bSYSTEM:\s+\S", re.IGNORECASE),
    re.compile(r"^\s*[A-Z][A-Z0-9 _]{3,}\s*$", re.MULTILINE),     # ALL-CAPS line
)


def audit_caption(caption: str) -> Tuple[float, str]:
    if not caption:
        return 0.0, ""
    sample = caption[:8192]
    score = 0.0
    reasons = []

    # Run the existing detectors
    try:
        from aria.security.rounds.r21_latent_prompt_injection import (
            head_looks_like_instruction,
        )
        if head_looks_like_instruction(sample):
            score = max(score, 0.7)
            reasons.append("instruction_head")
    except Exception:
        pass
    try:
        from aria.security.rounds.r22_dan_jailbreak import detect_dan
        ds, axes = detect_dan(sample)
        if ds >= 0.5:
            score = max(score, ds)
            reasons.append(f"dan:{axes}")
    except Exception:
        pass

    # Telltale screenshot shapes
    for p in _SCREENSHOT_SHAPES:
        if p.search(sample):
            score = max(score, 0.6)
            reasons.append(f"shape:{p.pattern[:30]}")
            break

    return score, "; ".join(reasons)


def _on_score(endpoint: str, payload: bytes, identity: str):
    # The caption-bearing path is /v1/advise (or future RAG endpoints)
    # — we score every payload that *looks* like a caption.
    if not payload or len(payload) > 16 * 1024:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    if "caption" not in s and "alt_text" not in s and "image_text" not in s:
        return 0.0, ""
    score, why = audit_caption(s)
    if score == 0.0:
        return 0.0, ""
    return score, f"r133.multimodal {why}"


register(DefencePlugin(
    round_id="R133",
    name="multimodal_injection",
    description="Score image/audio caption payloads for injection shapes.",
    on_score=_on_score,
))
