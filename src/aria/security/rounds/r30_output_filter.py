"""R30 — LLM output-side filter.

Threat: even when input defences hold, a model can still emit:
  * an active decoy token (memorisation leak)
  * a real-shaped secret (saw it in training data)
  * an instruction to the *user* ("call the SSN below to verify")
  * unsafe code (cmd injection, hardcoded credentials)
Any of those flowing back to a user is a loss.

Defence: a single ``filter_output(text, context)`` function applied to
EVERY model emission.  It returns ``(safe_text, redactions)``.
Redactions feed the audit log so operators can review what the model
tried to say.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_USER_CALL_TO_ACTION = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(?:call|dial|text|email|wire|send)\s+(?:the\s+)?(?:number|SSN|password|otp|verification)\b",
    r"\bclick\s+(?:this|the|here)\s+(?:link|button)\b",
    r"\b(?:download|run|execute)\s+(?:this|the\s+attached)\s+(?:file|script|binary)\b",
])


def filter_output(text: str) -> Tuple[str, List[str]]:
    """Scrub a model output before shipping to the user.

    Combines:
      * R2 token-leak scrub (AWS / GitHub / JWT / API-key shapes)
      * decoy-token scrub
      * unsafe call-to-action redact
    """
    if not text:
        return text, []
    redactions: List[str] = []
    out = text

    # R2: secret-shape scrub
    try:
        from aria.security.rounds.r02_token_leak import scrub
        cleaned = scrub(out.encode("utf-8")).decode("utf-8", errors="replace")
        if cleaned != out:
            redactions.append("token_shape")
            out = cleaned
    except Exception:
        pass

    # Honeypot decoy scrub
    try:
        from aria.security.honeypot_llm import scan_for_decoys
        decoys = scan_for_decoys(out, where="model_output")
        if decoys:
            redactions.append(f"decoy_tokens={len(decoys)}")
            for tok in decoys:
                out = out.replace(tok, "[REDACTED:decoy]")
    except Exception:
        pass

    # Unsafe call-to-action
    for p in _USER_CALL_TO_ACTION:
        if p.search(out):
            redactions.append("call_to_action")
            out = p.sub("[REDACTED: refused unsafe instruction]", out)

    return out, redactions


register(DefencePlugin(
    round_id="R30",
    name="output_filter",
    description="Final-mile model-output scrub: secrets + decoys + CTAs.",
))
