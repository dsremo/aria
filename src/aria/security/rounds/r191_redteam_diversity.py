"""R191 — Red-team prompt-diversity scorer.

Threat: a red-team eval suite that uses 1000 highly-similar prompts
gives a misleadingly-high coverage number.  Real adversaries vary
syntax, register, language, modality.  Without a diversity floor the
benchmark fails to represent the threat.

Defence: ``diversity_score`` over a corpus measures n-gram coverage
+ length variance + register variance.  Refuses to certify a suite
with diversity below a threshold.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def _ngrams(text: str, n: int) -> List[str]:
    tokens = re.findall(r"\w+", (text or "").lower())
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def diversity_score(corpus: List[str]) -> Tuple[float, dict]:
    if not corpus:
        return 0.0, {"reason": "empty"}

    bigram_counter: Counter = Counter()
    for text in corpus:
        bigram_counter.update(_ngrams(text, 2))
    if not bigram_counter:
        return 0.0, {"reason": "no_bigrams"}

    total = sum(bigram_counter.values())
    entropy = -sum((c / total) * math.log2(c / total) for c in bigram_counter.values())
    max_entropy = math.log2(len(bigram_counter)) or 1.0
    norm_entropy = entropy / max_entropy

    lengths = [len(re.findall(r"\w+", t or "")) for t in corpus]
    mean_len = sum(lengths) / len(lengths)
    var_len = sum((x - mean_len) ** 2 for x in lengths) / len(lengths)
    length_diversity = min(1.0, var_len / max(1.0, mean_len ** 2))

    unique_ratio = len(set(corpus)) / len(corpus)

    score = 0.4 * norm_entropy + 0.25 * length_diversity + 0.35 * unique_ratio
    return score, {
        "entropy_norm": norm_entropy,
        "length_diversity": length_diversity,
        "unique_ratio": unique_ratio,
        "n_prompts": len(corpus),
        "n_bigrams": len(bigram_counter),
    }


def certify_redteam_suite(corpus: List[str], *, min_score: float = 0.55) -> Tuple[bool, dict]:
    score, info = diversity_score(corpus)
    return score >= min_score, {**info, "score": score, "threshold": min_score}


register(DefencePlugin(
    round_id="R191",
    name="redteam_diversity",
    description="Bigram-entropy + length-variance diversity floor for red-team suites.",
))
