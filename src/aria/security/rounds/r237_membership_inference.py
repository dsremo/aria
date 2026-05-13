"""R237 — Membership-inference defence.

Threat: an attacker queries a target and a shadow model and infers
*which* records were in the target's training set (Shokri 2017).
Compounds privacy harms — even outputs alone betray membership.

Defence: a confidence-clip wrapper.  Refuses to return prediction
distributions whose top-1 confidence exceeds a threshold (close to
1.0 = strong membership signal).  Clips and re-normalises the
returned distribution.
"""

from __future__ import annotations

from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


def clip_confidence(
    distribution: Dict[str, float], *, max_top1: float = 0.92,
) -> Tuple[Dict[str, float], bool]:
    if not distribution:
        return {}, False
    items = sorted(distribution.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_p = items[0]
    if top_p <= max_top1:
        return distribution, False
    clipped = max_top1
    rest_total = 1.0 - clipped
    rest_keys = [k for k, _ in items[1:]]
    rest_orig_total = sum(distribution[k] for k in rest_keys) or 1.0
    out = {top_label: clipped}
    for k in rest_keys:
        out[k] = distribution[k] / rest_orig_total * rest_total
    return out, True


def softmax_temperature(logits: Dict[str, float], *, temperature: float = 2.0) -> Dict[str, float]:
    """Apply a temperature > 1 to flatten the distribution."""
    if not logits:
        return {}
    import math
    scaled = {k: v / max(temperature, 1e-3) for k, v in logits.items()}
    m = max(scaled.values())
    exps = {k: math.exp(v - m) for k, v in scaled.items()}
    s = sum(exps.values()) or 1.0
    return {k: v / s for k, v in exps.items()}


register(DefencePlugin(
    round_id="R237",
    name="membership_inference",
    description="Confidence-clip + temperature-softmax defence against membership inference.",
))
