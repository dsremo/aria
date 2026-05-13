"""R304 — Tokenizer poisoning detection.

Threat: a tokenizer ships rogue special tokens or BPE rules that
collapse ordinary words to a single token — letting attacker prompts
trigger hidden behaviours invisible to text-level filters.  GPT-4
"glitch tokens" (SolidGoldMagikarp) were a benign discovery of this
class; intentionally-poisoned tokenizers are the malicious twin.

Defence: walk a tokenizer's vocab and audit (a) special-token
prefixes, (b) tokens whose UTF-8 representation contains zero-width
or bidi characters, (c) BPE merges that produce single-token words
suspiciously identical to rare brand or admin strings.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


_ZW_RE = re.compile(r"[​-‏‪-‮⁦-⁩﻿]")
_ALLOWED_SPECIAL_PREFIXES = ("<", "[")


def audit_vocab(
    vocab: Iterable[str],
    *,
    sensitive_terms: Iterable[str] = (),
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    sensitive = {t.lower() for t in sensitive_terms}
    for token in vocab:
        s = str(token)
        if _ZW_RE.search(s):
            issues.append(f"tokenizer.zero_width:{s[:32]!r}")
        if s.startswith("<|") and not s.endswith("|>"):
            issues.append(f"tokenizer.malformed_special:{s[:32]!r}")
        if s.startswith("<") and not s.startswith(_ALLOWED_SPECIAL_PREFIXES) and len(s) < 8:
            # Heuristic: strange single-char wrapped tokens
            issues.append(f"tokenizer.suspect_prefix:{s[:16]!r}")
        if s.lower().strip() in sensitive and len(s) >= 4:
            # A sensitive admin-like single-token (e.g. "admin") is unusual
            issues.append(f"tokenizer.sensitive_single_token:{s[:32]!r}")
    return not issues, issues


def audit_bpe_merges(merges: Iterable[Tuple[str, str]]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    for a, b in merges:
        joined = (a or "") + (b or "")
        if _ZW_RE.search(joined):
            issues.append(f"bpe.zw_in_merge:{joined[:32]!r}")
    return not issues, issues


register(DefencePlugin(
    round_id="R304",
    name="tokenizer_poison",
    description="Tokenizer vocab + BPE-merge audit; refuse zero-width or sensitive single tokens.",
))
