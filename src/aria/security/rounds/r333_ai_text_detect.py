"""R333 — AI-generated text detector (statistical heuristic).

Threat: bulk LLM-generated content floods user-generated platforms,
inflates fake reviews, automates phishing-grade emails.  Stylometric
heuristics flag text that has the LLM signature even when it bypasses
purpose-built detectors.

Defence: a tiny stylometric scorer — sentence-length variance, type-
token ratio, function-word burstiness, unusual em-dash density.  Soft
score in [0, 1]; calibrated against natural-text corpora.
"""

from __future__ import annotations

import re
import statistics
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_FUNCTION_WORDS = {"the", "of", "and", "to", "a", "in", "is", "for", "on", "with", "as"}


def score_ai_text(text: str) -> Tuple[float, str]:
    body = text or ""
    if len(body) < 200:
        return 0.0, "too_short"

    sentences = [s.strip() for s in re.split(r"[\.!?]+", body) if s.strip()]
    if len(sentences) < 5:
        return 0.0, "too_few_sentences"
    sent_lens = [len(s.split()) for s in sentences]
    sent_var = statistics.pstdev(sent_lens) / max(1, statistics.mean(sent_lens))

    words = re.findall(r"[A-Za-z']+", body.lower())
    if not words:
        return 0.0, "no_words"
    type_token = len(set(words)) / len(words)

    fw_share = sum(1 for w in words if w in _FUNCTION_WORDS) / len(words)
    em_dash = body.count("—")
    em_density = em_dash / max(1, len(sentences))

    score = 0.0
    notes = []
    if sent_var < 0.25:
        score += 0.3
        notes.append(f"low_sent_var:{sent_var:.2f}")
    if 0.4 <= type_token <= 0.55:
        score += 0.25
        notes.append(f"narrow_ttr:{type_token:.2f}")
    if 0.42 <= fw_share <= 0.55:
        score += 0.2
        notes.append(f"high_fw:{fw_share:.2f}")
    if em_density >= 0.5:
        score += 0.25
        notes.append(f"em_dash_burst:{em_density:.2f}")
    return min(1.0, score), ",".join(notes) or "ok"


register(DefencePlugin(
    round_id="R333",
    name="ai_text_detect",
    description="Stylometric heuristic scorer for AI-generated text (sent-var + TTR + em-dash).",
))
