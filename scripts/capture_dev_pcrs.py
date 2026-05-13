"""Capture dev-tree PCR baseline into ``data/sealed/EXPECTED_PCRS.toml``.

What this is — and isn't
------------------------

This script runs :class:`SoftwarePCRAttestor` against the *current dev
tree* and writes the result as the sealed expected baseline.  The
output is a real, end-to-end-functional baseline against which a
runtime tamper of the dev tree will trip an attestation_mismatch
event.  That makes the attestation comparison work in the dev
environment — useful as a regression detector during development.

It is **NOT** a flight baseline.  A flight baseline requires:

  1. The actual flight CPU + bootloader + RTOS image installed.
  2. A real TPM 2.0 reading PCRs 0/1/2/4/5 from the measured-boot chain.
  3. A capture step performed in a known-clean configuration on the
     production hardware, then signed and sealed before the spacecraft
     ships.

Until those three conditions are met, the value of this baseline is
*regression detection in dev*, not flight-grade tamper detection.  The
banner in ``EXPECTED_PCRS.toml`` reflects this.

Usage::

    python scripts/capture_dev_pcrs.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    from aria.security.attestation import (
        SoftwarePCRAttestor, _default_key_path, PCRSlot,
    )

    pkg = repo_root() / "src" / "aria"
    sealed = repo_root() / "data" / "sealed"

    if not pkg.is_dir():
        print(f"[capture_dev_pcrs] aria pkg not found at {pkg}", file=sys.stderr)
        return 1

    attestor = SoftwarePCRAttestor(
        aria_pkg_root=pkg,
        sealed_root=sealed,
    )
    pcrs = attestor.read_pcrs()

    out_path = sealed / "EXPECTED_PCRS.toml"
    lines: list[str] = []
    lines.append("# R43 — DEV-tree PCR baseline (NOT a flight baseline).")
    lines.append("#")
    lines.append("# Captured on:  " + time.strftime("%Y-%m-%d %H:%M:%S %Z"))
    lines.append("# Captured by:  scripts/capture_dev_pcrs.py")
    lines.append("# Tree path:    src/aria/")
    lines.append("#")
    lines.append("# Caveats — read carefully:")
    lines.append("#   * These PCRs come from SoftwarePCRAttestor — software")
    lines.append("#     emulation, signing key on disk.  Strictly weaker than")
    lines.append("#     a real TPM 2.0 attestation key.")
    lines.append("#   * Re-run after every legitimate change to src/aria/ or")
    lines.append("#     data/sealed/, otherwise the runtime attestor will")
    lines.append("#     report mismatches against this stale baseline.")
    lines.append("#   * BEFORE FLIGHT: regenerate this file from the actual")
    lines.append("#     flight-CPU TPM 2.0 quote captured against the")
    lines.append("#     production-image measured-boot chain.")
    lines.append("#")
    lines.append("# See aria.security.attestation + docs/UNCERTAINTY.md.")
    lines.append("")
    lines.append("schema_version = 1")
    lines.append('hash_alg       = "sha256"')
    lines.append("populated      = true")
    lines.append("dev_baseline   = true")
    lines.append("")

    for slot in PCRSlot:
        idx = int(slot)
        digest = pcrs.get(idx, "0" * 64)
        lines.append(f"[pcrs.\"{idx}\"]   # {slot.name}")
        lines.append(f'sha256 = "{digest}"')
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"[capture_dev_pcrs] wrote {out_path}")
    print(f"[capture_dev_pcrs] {len(pcrs)} PCR slot(s) populated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
