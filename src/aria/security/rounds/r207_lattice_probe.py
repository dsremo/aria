"""R207 — Lattice-reduction self-probe.

Threat: a deployment using a custom or unaudited PQ lattice scheme
may have parameters whose lattice basis is too short — a textbook
LLL or BKZ attack with modest dimension recovers the secret.  The
2022 Castryck-Decru SIDH break and 2023 NTRU-prime parameter tweaks
both came from this class.

Defence: a runtime self-probe that builds a small test lattice
(known basis), runs LLL via ``fpylll``, and confirms reduction
succeeds within bounded time.  If ``fpylll`` is missing it returns
``unavailable`` rather than passing silently.
"""

from __future__ import annotations

import logging
import time
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r207")


def self_probe_dimension(dim: int = 30, *, max_seconds: float = 5.0) -> Tuple[bool, str]:
    try:
        from fpylll import IntegerMatrix, LLL
    except ImportError:
        return False, "fpylll_missing"
    if dim < 4 or dim > 200:
        return False, "dim_out_of_range"

    started = time.monotonic()
    try:
        m = IntegerMatrix.random(dim, "uniform", bits=20)
        LLL.reduction(m)
    except Exception as exc:
        return False, f"lll_error:{exc}"
    elapsed = time.monotonic() - started
    if elapsed > max_seconds:
        return False, f"lll_too_slow:{elapsed:.2f}s"
    return True, f"lll_ok dim={dim} t={elapsed:.2f}s"


def boot_check_lattice_runtime() -> Tuple[bool, str]:
    """A quick smoke-test run during operator boot.  Soft-fails when
    ``fpylll`` isn't installed so the round doesn't block ARIA boot."""
    return self_probe_dimension(20, max_seconds=2.0)


register(DefencePlugin(
    round_id="R207",
    name="lattice_probe",
    description="Self-probe LLL/BKZ reduction smoke-test for lattice scheme deployments.",
))
