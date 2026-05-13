"""R114 — Container image signing (Sigstore / cosign).

Threat: an attacker swaps the upstream image for ``aria-core:0.3.0``
between build and deploy (Polyfill-class attack on container registry).
Sigstore + cosign sign the image with a public-transparency-log entry;
verifiers refuse unsigned or revoked images.

Defence: a small wrapper that runs ``cosign verify --certificate-identity
=$ARIA_COSIGN_IDENTITY --certificate-oidc-issuer=$ARIA_COSIGN_ISSUER
$image`` and parses the result.  Used both at deploy-time (CI) and
opt-in at boot (when ``ARIA_VERIFY_OWN_IMAGE=1``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


def is_cosign_available() -> bool:
    return shutil.which("cosign") is not None


def verify_image(image: str, *,
                 identity: str = "",
                 oidc_issuer: str = "") -> Tuple[bool, str]:
    """Return ``(signed, reason)`` for ``image``."""
    if not is_cosign_available():
        return False, "cosign_not_installed"
    identity = identity or os.environ.get("ARIA_COSIGN_IDENTITY", "")
    issuer = oidc_issuer or os.environ.get("ARIA_COSIGN_ISSUER", "")
    if not identity or not issuer:
        return False, "missing_identity_or_issuer_env"
    try:
        proc = subprocess.run(                                # nosec B603
            ["cosign", "verify",
             "--certificate-identity", identity,
             "--certificate-oidc-issuer", issuer,
             image],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if proc.returncode == 0:
            return True, "verified"
        return False, proc.stderr.strip()[:200]
    except Exception as exc:
        return False, f"exc:{exc}"


register(DefencePlugin(
    round_id="R114",
    name="cosign_verify",
    description="cosign verify wrapper for container image signature integrity.",
))
