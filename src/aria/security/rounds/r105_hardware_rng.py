"""R105 — Hardware-rooted random source (RDRAND / RDSEED / TPM RNG / getrandom).

Threat: weak entropy at boot (containers cloned from the same image,
Linux ``/dev/urandom`` called before the kernel pool seeded) lets an
attacker predict tokens / nonces.  BSI 2024 advisory on entropy
fingerprints in cloud VMs cited this exact pattern.

Defence: a cascade source — TPM RNG > getrandom(GRND_RANDOM) >
``os.urandom`` — that returns the strongest available seed.  Caller
mixes it into application keys via HKDF (R53) so even a weak fallback
doesn't directly produce a key.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r105")


def get_strong_seed(n: int = 64) -> Tuple[bytes, str]:
    """Return ``(seed_bytes, source_label)``.  ``source_label`` documents
    which path produced the bytes so the audit log records it."""
    if n < 16 or n > 4096:
        raise ValueError("n must be 16..4096")
    # 1. TPM RNG via /dev/hwrng — preferred when present + permitted
    try:
        with open("/dev/hwrng", "rb") as f:
            data = f.read(n)
        if len(data) == n:
            return data, "hwrng"
    except OSError:
        pass
    # 2. getrandom(GRND_RANDOM) blocks until kernel pool ready
    try:
        data = os.getrandom(n, os.GRND_RANDOM)
        if len(data) == n:
            return data, "getrandom_GRND_RANDOM"
    except (AttributeError, OSError):
        pass
    # 3. secrets.token_bytes (uses os.urandom)
    return secrets.token_bytes(n), "secrets_token_bytes"


def boot_check_entropy() -> Tuple[bool, str]:
    """Verify the kernel reports adequate entropy at boot.  Returns
    ``(ok, reason)``."""
    try:
        with open("/proc/sys/kernel/random/entropy_avail") as f:
            avail = int(f.read().strip())
        if avail < 256:
            return False, f"low_entropy={avail}"
        return True, f"entropy_avail={avail}"
    except OSError:
        return True, "entropy_file_missing"


register(DefencePlugin(
    round_id="R105",
    name="hardware_rng",
    description="Cascade hardware-rooted random: hwrng > GRND_RANDOM > os.urandom.",
))
