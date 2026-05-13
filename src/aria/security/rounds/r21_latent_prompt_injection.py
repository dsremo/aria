"""R21 — Latent (indirect) prompt injection.

Threat: a prompt-injection payload buried in a *fetched* artefact —
a CDM pulled from IS4OM, a TLE comment field, a SatNOGS observation
note — reaches the LLM context unmodified.  When the model later
summarises the content it follows the embedded instruction.  Microsoft
Spotlighting (Hines et al., 2024) reduced this from > 50 % success to
< 2 % by explicit untrusted-content fencing; ARIA already implements
spotlighting in :mod:`aria.cognitive.spotlight`.  This round extends
the defence to the EXTERNAL-API fetch boundary so even tool-result
text gets fenced before any LLM sees it.

Defence: a wrapper ``fence_external_text(text, source)`` that wraps
content in the spotlight delimiters per its trust tier.  Plus an
``on_score`` hook that rejects external responses whose first 256 bytes
already look like an instruction (``"You are now ..."``, ``"Ignore ..."``).
"""

from __future__ import annotations

import re
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_INSTRUCTION_HEAD_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"^\s*(?:ignore|disregard|forget)\s+(?:all|the|previous)",
    r"^\s*you\s+(?:are|will|must|should)\s+(?:now|always|never)",
    r"^\s*new\s+(?:instructions|task|directive)",
    r"^\s*system\s+(?:prompt|note|message)\s*[:=]",
    r"^\s*\[INST\]|<\|im_start\|>",
])


def head_looks_like_instruction(text: str, *, head_chars: int = 256) -> bool:
    if not text:
        return False
    head = text[:head_chars]
    return any(p.search(head) for p in _INSTRUCTION_HEAD_PATTERNS)


def fence_external_text(text: str, *, source: str = "external_api") -> str:
    """Wrap external text in spotlight delimiters with the source label.

    Falls back to a simple delimiter when ``aria.cognitive.spotlight``
    is unavailable (e.g., the cognitive package isn't loaded).
    """
    try:
        from aria.cognitive.spotlight import Spotlighter
        from aria.cognitive.constitution import TrustTier
        sp = Spotlighter()
        result = sp.wrap(text, trust_tier=TrustTier.EXTERNAL_API, source=source)
        return result.wrapped
    except Exception:
        return (
            f'<aria:untrusted_data source="{source}">'
            f"{text}"
            f"</aria:untrusted_data>"
        )


def _on_score(endpoint: str, payload: bytes, identity: str) -> Tuple[float, str]:
    if not payload:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")[:512]
    except Exception:
        return 0.0, ""
    if head_looks_like_instruction(s):
        return 0.7, "r21.latent_prompt_injection: head reads as instruction"
    return 0.0, ""


register(DefencePlugin(
    round_id="R21",
    name="latent_prompt_injection",
    description="Spotlight-fence external content; flag instruction-shaped heads.",
    on_score=_on_score,
))
