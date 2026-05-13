"""Psychology-aware defences — Cialdini influence + social-engineering detector.

ARIA has both human operators and an LLM in the loop.  Both are
manipulable via influence techniques first catalogued by Cialdini
(*Influence: The Psychology of Persuasion*, 1984): authority, scarcity,
reciprocity, commitment, social proof, liking.  Recent breaches —
Bybit ($1.5 B, Feb 2025), Twilio Authy phishing, the 2024 wave of
voice-cloned CFO transfers — all weaponise one or more of these axes,
and the same axes show up on the LLM side as jailbreak vectors
("authority" → impersonate sysadmin; "commitment" → "you already agreed
to help with this; just continue").

Strategy: pattern-match the *rhetorical move*, not the surface words.
Each principle has two pattern banks — English-language phishing and
LLM-jailbreak prompts — built from open-source corpora (study credits
in the docstring) and refined as new vectors land.

Output is per-axis ``InfluenceScore`` so a downstream policy can decide
whether to refuse, escalate to operator, or strip the offending sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Reference corpora used during pattern design (no code copied):
#   * yueliu1999/Awesome-Jailbreak-on-LLMs (GitHub, MIT)
#   * NVIDIA/garak probes/dan.py + grandma.py (Apache-2.0)
#   * APWG phishing corpus (public domain summaries)
#   * Cialdini, Robert B. *Influence: Science and Practice*, 5th ed.


# ── Authority — "I am admin/CEO/IT, do this now" ────────────────────

_AUTHORITY_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(this\s+is|i'?m|i\s+am)\s+(the\s+)?(ceo|cfo|admin|administrator|root|sysop)\b",
    r"\b(as|on\s+behalf\s+of)\s+(the\s+)?(ceo|cfo|director|board|legal|compliance)\b",
    r"\bact(ing)?\s+(as\s+|like\s+a?\s*)(sysadmin|root|administrator|developer)\b",
    r"\b(authorit[yi]e?s?|mandate|directive)\s+(require|order|compel|demand)\b",
    r"\b(executive\s+order|board\s+resolution)\b",
    r"\b(I\s+(?:authorise|authorize|hereby\s+authorise))\b",
    # LLM-specific authority impersonation
    r"\b(system\s+prompt|sudo\s+mode|developer\s+mode)\b",
    r"\b(?:openai|anthropic|nvidia|google)\s+(?:says|told|policy|engineer)\b",
])

# ── Scarcity — "limited time / one chance / before this expires" ──

_SCARCITY_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(?:within\s+)?(\d{1,2}\s*(?:minutes?|hours?))\s+or\s+(it'?s?\s+)?(too\s+late|gone|removed|terminated)\b",
    r"\b(only\s+\d+\s+(?:remain|left|available))\b",
    r"\b(last\s+chance|final\s+notice|will\s+expire|deadline\s+today)\b",
    r"\b(account\s+will\s+be\s+(?:suspended|locked|deleted))\b",
    r"\b(immediately|urgently?|right\s+now)\s+(?:or|otherwise|else)\b",
    # LLM-specific
    r"\b(this\s+is\s+(?:your|the)\s+last\s+chance)\b",
    r"\b(running\s+out\s+of\s+tokens?|will\s+cease\s+to\s+exist)\b",
])

# ── Reciprocity — "I helped you / you owe / a favour for a favour" ─

_RECIPROCITY_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(I('?ve|\s+have)|we'?ve)\s+(been|always)\s+(helping|loyal|patient)\b",
    r"\b(repay\s+the\s+favour|owe\s+(me|us)|in\s+exchange\s+for)\b",
    r"\b(after\s+everything\s+I('?ve|\s+have)\s+done)\b",
    r"\b(please\s+just\s+(this\s+one|once|help))\b",
])

# ── Commitment — "you already said / continue / don't break consistency" ─

_COMMITMENT_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(you\s+already\s+(?:said|agreed|started|promised))\b",
    r"\b(continue|keep\s+going|don'?t\s+stop\s+now)\b",
    r"\b(stay\s+(?:in|consistent\s+with)\s+(?:character|persona|role))\b",
    # Classic DAN trick
    r"\b(do\s+anything\s+now|DAN\s+mode|always\s+respond\s+as\s+DAN)\b",
])

# ── Social proof — "everyone does it / others have helped" ─────────

_SOCIAL_PROOF_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(other(\s+\w+)?\s+(?:assistants?|users?|admins?|engineers?)\s+(?:have|already))\b",
    r"\b(every(?:one|body)\s+else\s+(?:does|is\s+doing))\b",
    r"\b(your\s+(?:older|previous)\s+version\s+(?:would|did))\b",
    r"\b(99%\s+of\s+(?:users|developers))\b",
])

# ── Liking — "we're friends / I trust you / personal favour" ───────

_LIKING_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(I('?ve|\s+have)\s+always\s+(?:liked|trusted|admired))\b",
    r"\b(my\s+(?:friend|buddy|pal)|just\s+between\s+us)\b",
    r"\b(personal\s+favour|do\s+me\s+a\s+(?:solid|favour))\b",
    r"\b(grandma|grandmother|granny)\s+(?:used\s+to|always|once)\b",     # garak grandma probe class
])

_AXES = (
    ("authority", _AUTHORITY_PATTERNS),
    ("scarcity", _SCARCITY_PATTERNS),
    ("reciprocity", _RECIPROCITY_PATTERNS),
    ("commitment", _COMMITMENT_PATTERNS),
    ("social_proof", _SOCIAL_PROOF_PATTERNS),
    ("liking", _LIKING_PATTERNS),
)


@dataclass
class InfluenceScore:
    score: float                    # 0..1; >= 0.5 alert; >= 0.8 block
    axes: Dict[str, int]            # hits per Cialdini axis
    matched_patterns: List[str]     # short snippets of what tripped

    @property
    def alert(self) -> bool:
        return self.score >= 0.5

    @property
    def block(self) -> bool:
        return self.score >= 0.8

    @property
    def dominant_axis(self) -> str:
        if not self.axes:
            return ""
        return max(self.axes.items(), key=lambda kv: kv[1])[0]


def detect_influence(text: str, *, max_len: int = 8192) -> InfluenceScore:
    """Score a string against the six Cialdini axes.

    The score is the *number of distinct axes* that fire, scaled —
    one axis alone scores 0.2, two axes 0.5, three 0.8, four+ 1.0.
    A single axis hitting hard does not block by itself; layering does.
    Combined-axis is the historical fingerprint of weaponised influence.
    """
    if not text:
        return InfluenceScore(0.0, {}, [])
    sample = text[:max_len]
    axes_hits: Dict[str, int] = {}
    matched: List[str] = []
    for name, patterns in _AXES:
        hits = 0
        for p in patterns:
            m = p.search(sample)
            if m:
                hits += 1
                snippet = sample[max(0, m.start() - 8): m.end() + 8]
                matched.append(f"{name}: …{snippet.strip()[:60]}…")
        if hits:
            axes_hits[name] = hits
    distinct = len(axes_hits)
    total = sum(axes_hits.values())
    if distinct == 0:
        score = 0.0
    elif distinct == 1:
        # Single axis trips at 0.2 base, +0.1 per extra hit (max 0.5).
        score = min(0.5, 0.2 + 0.1 * (total - 1))
    elif distinct == 2:
        score = min(0.7, 0.5 + 0.05 * (total - 2))
    elif distinct == 3:
        score = min(0.9, 0.75 + 0.05 * (total - 3))
    else:
        score = 1.0
    return InfluenceScore(
        score=score,
        axes=axes_hits,
        matched_patterns=matched[:8],
    )


# ── Surface manipulation (urgency + secrecy) ───────────────────────


_URGENCY_PHRASES = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(act\s+now|don'?t\s+delay|time[\s-]sensitive)\b",
    r"\b(immediate(ly)?\s+(action|response))\b",
    r"\b(asap|a\.s\.a\.p\.)\b",
])

_SECRECY_PHRASES = tuple(re.compile(p, re.IGNORECASE) for p in [
    r"\b(confidential|do\s+not\s+(?:share|tell|disclose|forward))\b",
    r"\b(keep\s+this\s+(?:between\s+us|secret|quiet))\b",
    r"\b(don'?t\s+(?:cc|copy|involve)\s+(?:anyone|legal|IT|security))\b",
])


def manipulation_flags(text: str) -> List[str]:
    """Return a list of short manipulation labels found in ``text``.

    Surfaces urgency / secrecy phrasing for operator-side defences (the
    classic phishing mismatch is "urgent + secret + bypass-process").
    """
    flags: List[str] = []
    if any(p.search(text) for p in _URGENCY_PHRASES):
        flags.append("urgency")
    if any(p.search(text) for p in _SECRECY_PHRASES):
        flags.append("secrecy")
    return flags


__all__ = [
    "InfluenceScore",
    "detect_influence",
    "manipulation_flags",
]
