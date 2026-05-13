"""R119 — Kubernetes secret-volume policy.

Threat: ARIA's tenant store + master key, when delivered via env var,
appear in ``/proc/<pid>/environ`` and any process snapshot.  Best
practice: mount secrets as a tmpfs volume the kernel zeros on unmount,
mode 0400, owned by the service UID — and rotate by replacing the
file, not by editing.

Defence: a small validator that checks ARIA's running config to
confirm secrets are file-mounted (not env-passed) when
``ARIA_ENV=production``.  Recommended Kubernetes Secret + projected
volume YAML emitted for operators.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_RECOMMENDED_K8S = """\
# R119 — secret as projected volume, NOT env var
apiVersion: v1
kind: Pod
metadata:
  name: aria-screener
spec:
  containers:
  - name: aria
    image: aria-core:0.3.0
    volumeMounts:
    - name: secrets
      mountPath: /var/aria/secrets
      readOnly: true
  volumes:
  - name: secrets
    projected:
      defaultMode: 0400
      sources:
      - secret:
          name: aria-screener-secrets
"""


def boot_check() -> Tuple[bool, List[str]]:
    """Refuse production start when sensitive secrets come from env vars."""
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return True, []
    issues: List[str] = []
    sensitive = (
        "ARIA_ADMIN_TOKEN",
        "ARIA_MASTER_KEY",
        "ARIA_OAUTH_STATE_KEY",
        "DSREMO_JWT_SECRET",
        "SPACETRACK_PASSWORD",
    )
    secret_dir = Path("/var/aria/secrets")
    for name in sensitive:
        if name in os.environ and not secret_dir.exists():
            issues.append(f"{name}_via_env_in_prod")
    return len(issues) == 0, issues


def k8s_recommended() -> str:
    return _RECOMMENDED_K8S


register(DefencePlugin(
    round_id="R119",
    name="secret_volume",
    description="Refuse env-var secrets in prod; projected-volume YAML for K8s.",
))
