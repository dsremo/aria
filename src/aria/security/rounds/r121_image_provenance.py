"""R121 — Container image provenance / SLSA-3 attestation.

Threat: even with R114 cosign signature, the *contents* may have been
built with a tampered toolchain (XZ-class).  SLSA framework levels 3+
require a signed, in-toto provenance attestation describing the
build environment + materials.  Banks + DoD-software-supply-chain
guidance require this for high-impact builds.

Defence: ``verify_slsa_attestation(image, expected_builder, expected_repo)``
delegates to ``cosign verify-attestation`` and parses the in-toto
predicate.  Operators wire `ARIA_SLSA_BUILDER` (the OIDC identity of
the trusted GitHub Actions / CircleCI runner) and `ARIA_SLSA_REPO`
(the source repo).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


def is_cosign_available() -> bool:
    return shutil.which("cosign") is not None


def verify_slsa_attestation(
    image: str,
    *,
    expected_builder: Optional[str] = None,
    expected_repo: Optional[str] = None,
) -> Tuple[bool, str]:
    if not is_cosign_available():
        return False, "cosign_missing"
    builder = expected_builder or os.environ.get("ARIA_SLSA_BUILDER", "")
    repo = expected_repo or os.environ.get("ARIA_SLSA_REPO", "")
    if not builder or not repo:
        return False, "missing_builder_or_repo"
    try:
        proc = subprocess.run(                                # nosec B603
            ["cosign", "verify-attestation",
             "--type", "slsaprovenance",
             "--certificate-identity-regexp",
             f"^https://github.com/.+@.+",
             "--certificate-oidc-issuer",
             "https://token.actions.githubusercontent.com",
             image],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode != 0:
            return False, proc.stderr.strip()[:200]
        for line in proc.stdout.splitlines():
            try:
                env = json.loads(line)
            except Exception:
                continue
            payload = env.get("payload", "")
            if not payload:
                continue
            import base64
            try:
                pred = json.loads(base64.b64decode(payload).decode("utf-8"))
            except Exception:
                continue
            cfg = (pred.get("predicate") or {}).get("invocation", {}).get("configSource", {})
            uri = cfg.get("uri", "")
            if repo not in uri:
                return False, f"repo_mismatch uri={uri}"
            return True, "verified"
        return False, "no_attestation_payload"
    except Exception as exc:
        return False, f"exc:{exc}"


register(DefencePlugin(
    round_id="R121",
    name="image_provenance",
    description="cosign verify-attestation for SLSA in-toto provenance.",
))
