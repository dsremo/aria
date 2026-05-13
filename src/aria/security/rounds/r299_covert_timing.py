"""R299 — Covert-channel timing analyser.

Threat: an attacker post-foothold exfils via packet-timing — encoding
bits in inter-packet delays so the raw bytes look benign.  Documented
in NSA TAO toolkits and academic papers (Cabuk 2004).  Bandwidth is
low but unblockable by content inspection.

Defence: a histogram-of-inter-packet-delays scorer.  A normal flow
has a wide, near-Poisson delay distribution; a covert-timing flow
has narrow modes / regularly-spaced peaks.  ``score_intervals`` flags
suspicious shapes.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Iterable, Tuple

from aria.security.plugins import DefencePlugin, register


def score_intervals(intervals_ms: Iterable[float]) -> Tuple[float, str]:
    arr = [float(x) for x in intervals_ms if x is not None]
    if len(arr) < 30:
        return 0.0, "too_few_samples"

    mean = statistics.mean(arr)
    stdev = statistics.pstdev(arr) or 1e-9
    cov = stdev / max(mean, 1e-9)

    bucketed = Counter(int(x * 4) for x in arr)
    top_pair = bucketed.most_common(2)
    top_share = top_pair[0][1] / len(arr)

    score = 0.0
    notes = []
    if cov < 0.1:
        score += 0.5
        notes.append(f"low_cov:{cov:.3f}")
    if top_share > 0.6:
        score += 0.4
        notes.append(f"single_mode:{top_share:.2f}")
    if len(top_pair) == 2 and abs(top_pair[0][0] - top_pair[1][0]) <= 1 and top_share > 0.4:
        score += 0.2
        notes.append("bimodal_adjacent")
    if cov > 0.8 and top_share < 0.05:
        score = max(0.0, score - 0.2)
        notes.append("looks_natural")

    return min(1.0, max(0.0, score)), ",".join(notes) or "ok"


register(DefencePlugin(
    round_id="R299",
    name="covert_timing",
    description="Inter-packet-delay histogram scorer; flag covert-timing channels.",
))
