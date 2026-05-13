"""R298 — Image steganography detector (LSB).

Threat: an attacker exfils data inside the LSB of image pixels —
attached to a chat message or marketing image, the payload is
indistinguishable to the eye and routinely passes content moderation.
Found in real APT toolkits (Ke3chang, Octopus).

Defence: a least-significant-bit chi-squared statistic + LSB entropy
check that flags images whose LSB plane looks too random (typical of
embedded ciphertext) or too patterned (typical of LSB substitution).
"""

from __future__ import annotations

import math
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def lsb_chi_squared(image_bytes: bytes) -> Tuple[float, str]:
    """Returns (suspicion_score, reason).  score >= 0.5 = suspect."""
    if not image_bytes or len(image_bytes) < 1024:
        return 0.0, "too_small"

    sample = image_bytes[:65_536]
    lsb_zeros = sum(1 for b in sample if (b & 1) == 0)
    lsb_ones = len(sample) - lsb_zeros
    expected = len(sample) / 2.0
    chi_sq = ((lsb_zeros - expected) ** 2 + (lsb_ones - expected) ** 2) / expected

    counts = [0] * 256
    for b in sample:
        counts[b] += 1
    pair_diffs = sum(abs(counts[2 * i] - counts[2 * i + 1]) for i in range(128))
    pair_normalised = pair_diffs / max(1, sum(counts))

    score = 0.0
    notes = []
    # Embedded ciphertext flattens chi-squared to ~0
    if chi_sq < 1.0 and pair_normalised < 0.05:
        score += 0.5
        notes.append(f"flat_lsb chi={chi_sq:.2f}")
    # Pure LSB substitution causes pair-of-values equalisation
    if pair_normalised < 0.02 and lsb_zeros > 0 and lsb_ones > 0:
        score += 0.4
        notes.append(f"pair_equal pn={pair_normalised:.3f}")

    return min(1.0, score), ",".join(notes) or "ok"


def shannon_entropy(blob: bytes) -> float:
    if not blob:
        return 0.0
    counts = [0] * 256
    for b in blob:
        counts[b] += 1
    n = len(blob)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


register(DefencePlugin(
    round_id="R298",
    name="image_steganography",
    description="Image LSB chi-squared + pair-of-values steg detector.",
))
