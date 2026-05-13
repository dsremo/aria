"""R132 — GCG (Greedy Coordinate Gradient) adversarial-suffix detector.

Threat: Zou et al. 2023 "Universal and Transferable Adversarial Attacks
on Aligned Language Models" found gradient-optimised suffixes that
flip a model's safety; e.g.
``... describe.\\ + similarlyNow write opp.... !!!"``.  Suffixes are
non-natural-language strings high in entropy, low in word-frequency,
with bursts of punctuation.

Defence: a feature-based scorer.  We compute three signals:
  * **High character-class entropy** — > 5 distinct char classes in
    < 80 chars
  * **Low natural-language ratio** — fraction of bytes that aren't
    ASCII letters / digits / common punctuation
  * **Suffix-shape** — appears at the END of an otherwise-normal prompt
Together: > 0.7 ⇒ likely GCG-class adversarial suffix.
"""

from __future__ import annotations

import re
import string
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_NATURAL = set(string.ascii_letters + string.digits + " .,;:!?'\"-\n\t")


def _natural_ratio(text: str) -> float:
    if not text:
        return 1.0
    n = sum(1 for c in text if c in _NATURAL)
    return n / len(text)


def _character_class_count(text: str) -> int:
    classes = set()
    for c in text:
        if c.isalpha():
            classes.add("L")
        elif c.isdigit():
            classes.add("D")
        elif c.isspace():
            classes.add("S")
        elif c in string.punctuation:
            classes.add("P")
        else:
            classes.add("X")
    return len(classes)


def gcg_suffix_score(prompt: str) -> Tuple[float, str]:
    if not prompt or len(prompt) < 24:
        return 0.0, "too_short"
    # Look at the LAST 100 characters
    suffix = prompt[-100:]
    nat = _natural_ratio(suffix)
    classes = _character_class_count(suffix)
    score = 0.0
    reasons = []
    if nat < 0.45:
        score = max(score, 0.5 + (0.45 - nat) * 1.5)
        reasons.append(f"natural_ratio={nat:.2f}")
    if classes >= 5 and len(suffix) < 80:
        score = max(score, 0.6)
        reasons.append(f"classes={classes}")
    # Burst of punctuation (>= 6 in a row)
    if re.search(r"[!?.,;:'\"\-/_+=*#%@$&\\<>(){}\[\]]{6,}", suffix):
        score = max(score, 0.7)
        reasons.append("punct_burst")
    return min(1.0, score), "; ".join(reasons)


def _on_score(endpoint: str, payload: bytes, identity: str):
    if not payload or len(payload) > 64 * 1024:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    score, why = gcg_suffix_score(s)
    if score == 0.0:
        return 0.0, ""
    return score, f"r132.gcg_suffix {why}"


register(DefencePlugin(
    round_id="R132",
    name="gcg_suffix",
    description="GCG / AutoDAN-class adversarial suffix detector (entropy + class).",
    on_score=_on_score,
))
