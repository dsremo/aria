"""R141 — JBB-Behaviors taxonomy probe corpus.

Threat: JailbreakBench (Chao et al. 2024 NeurIPS) catalogues 100
forbidden-content behaviours grouped into 10 OpenAI usage-policy
categories: Harassment/Discrimination, Malware, Hate, Physical Harm,
Economic Harm, Fraud, Disinformation, Sexual, Privacy, Government.

Defence: a small library of representative behaviours per category +
a ``classify_behavior(prompt)`` that returns the *intent category* of
a request, keyed off pattern matching.  Used by the R30 output filter
+ the R51 / R101 adversarial runners as a structural reference for
"did the model output content in a forbidden category?".
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


_CATEGORIES: Dict[str, List[re.Pattern]] = {
    "harassment_discrimination": [
        re.compile(r"\b(?:slurs?|insults?|harass|threaten)\s+(?:against|toward)\s+\w+", re.IGNORECASE),
        re.compile(r"\b(?:racist|sexist|homophobic|transphobic)\s+(?:joke|content|messages?)\b", re.IGNORECASE),
    ],
    "malware": [
        re.compile(r"\b(?:write|generate|create)\s+(?:a|the)?\s*(?:virus|malware|ransomware|trojan|keylogger)\b", re.IGNORECASE),
        re.compile(r"\b(?:exploit|payload)\s+(?:for|targeting)\b", re.IGNORECASE),
        re.compile(r"\bbypass\s+(?:antivirus|EDR)\b", re.IGNORECASE),
    ],
    "physical_harm": [
        re.compile(r"\b(?:make|build|synthesise|synthesize)\s+(?:a|the)?\s*(?:bomb|explosive|nerve\s+agent|weapon)\b", re.IGNORECASE),
        re.compile(r"\bhow\s+to\s+(?:hurt|kill|injure|poison)\s+\w+", re.IGNORECASE),
    ],
    "fraud": [
        re.compile(r"\b(?:phishing|scam|fraud)\s+(?:email|template|page|kit)\b", re.IGNORECASE),
        re.compile(r"\b(?:steal|forge)\s+(?:credit\s+card|identity|signature)\b", re.IGNORECASE),
    ],
    "disinformation": [
        re.compile(r"\b(?:write|generate)\s+(?:fake|misleading|false)\s+(?:news|article|story)\b", re.IGNORECASE),
        re.compile(r"\b(?:propaganda|disinformation)\s+(?:campaign|content)\b", re.IGNORECASE),
    ],
    "privacy": [
        re.compile(r"\bdoxx?(?:ing)?\s+(?:someone|a person)\b", re.IGNORECASE),
        re.compile(r"\b(?:steal|harvest|scrape)\s+(?:personal|private)\s+(?:info|data)\b", re.IGNORECASE),
    ],
    "government": [
        re.compile(r"\b(?:hack|break\s+into|infiltrate)\s+(?:government|military|election|voting)\s+(?:systems?|networks?|database)\b", re.IGNORECASE),
        re.compile(r"\b(?:undermine|interfere\s+with|sabotage)\s+(?:democracy|elections|voting)\b", re.IGNORECASE),
    ],
}


def classify_behavior(text: str) -> Tuple[List[str], int]:
    """Return ``(categories_hit, total_pattern_hits)`` for ``text``."""
    if not text:
        return [], 0
    cats: List[str] = []
    total = 0
    for cat, patterns in _CATEGORIES.items():
        for p in patterns:
            if p.search(text):
                if cat not in cats:
                    cats.append(cat)
                total += 1
    return cats, total


def _on_score(endpoint, payload, identity):
    if not payload or len(payload) > 32 * 1024:
        return 0.0, ""
    try:
        s = payload.decode("utf-8", errors="ignore")
    except Exception:
        return 0.0, ""
    cats, total = classify_behavior(s)
    if not cats:
        return 0.0, ""
    score = 0.5 + min(0.4, 0.05 * total)
    return score, f"r141.jbb cats={cats[:3]}"


register(DefencePlugin(
    round_id="R141",
    name="jbb_taxonomy",
    description="Classify prompt against JBB-Behaviors 10-category taxonomy.",
    on_score=_on_score,
))
