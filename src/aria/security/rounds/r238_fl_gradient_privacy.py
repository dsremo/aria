"""R238 — Federated-learning gradient-privacy clip.

Threat: in federated learning, raw gradient updates leak training-
data attributes — Zhu 2019 ("Deep Leakage from Gradients") fully
reconstructs samples from a single update.  Apple's & Google's FL
deployments thus require gradient clipping + DP noise.

Defence: a clip-and-noise helper that operates on a flat float
vector — clip per-sample L2 to a cap, then add Gaussian noise
calibrated to (sigma, sensitivity).
"""

from __future__ import annotations

import math
import secrets
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


def clip_l2(gradient: Iterable[float], *, max_norm: float = 1.0) -> Tuple[List[float], float]:
    g = list(gradient)
    norm = math.sqrt(sum(x * x for x in g)) or 1e-12
    if norm <= max_norm:
        return g, norm
    factor = max_norm / norm
    return [x * factor for x in g], norm


def add_gaussian_noise(
    gradient: Iterable[float],
    *,
    sigma: float = 1.0,
    seed: int = 0,
) -> List[float]:
    g = list(gradient)
    out: List[float] = []
    for v in g:
        u1 = (secrets.randbits(53) / (1 << 53)) or 1e-15
        u2 = secrets.randbits(53) / (1 << 53)
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        out.append(v + sigma * z)
    return out


def privatise_update(
    gradient: Iterable[float],
    *,
    max_norm: float = 1.0,
    sigma: float = 0.5,
) -> Tuple[List[float], float]:
    clipped, original_norm = clip_l2(gradient, max_norm=max_norm)
    noisy = add_gaussian_noise(clipped, sigma=sigma)
    return noisy, original_norm


register(DefencePlugin(
    round_id="R238",
    name="fl_gradient_privacy",
    description="Federated learning gradient L2-clip + Gaussian noise for DP-FL.",
))
