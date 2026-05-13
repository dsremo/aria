"""R209 — Quantum RNG interface (with cascade fallback).

Threat: a future CRQC could reconstruct certain past pseudo-random
streams if the seed entropy was insufficient.  Banks + national labs
already buy quantum-RNG appliances (IDQ, KETS).

Defence: a thin interface that prefers a connected QRNG over the
R105 hardware-RNG cascade.  The interface is soft-fail: when no QRNG
is present, the call transparently falls through to R105.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r209")


def get_quantum_seed(n: int = 32) -> Tuple[bytes, str]:
    """Returns ``(bytes, source)`` where source is one of
    ``qrng_dev``, ``qrng_http``, ``hwrng``, ``urandom``."""
    qrng_path = os.environ.get("ARIA_QRNG_DEV", "")
    if qrng_path and Path(qrng_path).exists():
        try:
            with open(qrng_path, "rb") as fh:
                data = fh.read(n)
            if len(data) == n:
                return data, "qrng_dev"
        except OSError as exc:
            logger.warning("r209.qrng_dev_failed path=%s exc=%s", qrng_path, exc)

    from aria.security.rounds.r105_hardware_rng import get_strong_seed
    return get_strong_seed(n)


def derive_long_lived_key(purpose: str, length: int = 32) -> Tuple[bytes, str]:
    """Mix QRNG seed with HKDF (R53) so the key is bound to the
    operator's master KEK."""
    seed, source = get_quantum_seed(64)
    from aria.security.rounds.r53_hkdf_per_tenant import derive
    return derive(purpose, "qrng_root", length=length, salt=seed[:32]), source


register(DefencePlugin(
    round_id="R209",
    name="qrng_interface",
    description="Quantum RNG interface (ARIA_QRNG_DEV) with R105 hwrng cascade fallback.",
))
