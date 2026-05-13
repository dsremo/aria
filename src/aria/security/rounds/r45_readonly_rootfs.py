"""R45 — Container read-only root filesystem + drop-capabilities.

Threat: a remote-code-execution defect that lands in the running
container would normally let the attacker drop a binary in
``/usr/bin/`` and persist.  A read-only rootfs blocks this; combined
with ``--cap-drop=ALL`` and ``no-new-privileges:true`` the blast radius
is limited to per-request ephemeral state.

Defence: a static checker for ``deploy/screener/docker-compose.yml`` +
``Dockerfile`` confirming the production-mode hardening is applied.
Operators who deploy via Kubernetes get an equivalent ``PodSecurityContext``
snippet in the docstring.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


_K8S_RECOMMENDED = """\
# R45 — PodSpec hardening for aria-screener / aria-advisor
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: aria
    image: aria-core:0.3.0
    securityContext:
      readOnlyRootFilesystem: true
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
      seccompProfile:
        type: RuntimeDefault
    volumeMounts:
    - name: data
      mountPath: /var/aria
  volumes:
  - name: data
    emptyDir: {sizeLimit: "1Gi"}
"""

_COMPOSE_RECOMMENDED = """\
# R45 — docker-compose hardening
services:
  aria-screener:
    image: aria-core:0.3.0
    read_only: true
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    user: "1000:1000"
    tmpfs:
      - /tmp:size=64m,mode=1777
    volumes:
      - aria_data:/var/aria
"""


def audit_compose_file(text: str) -> List[str]:
    issues: List[str] = []
    if "read_only:" not in text and "read-only:" not in text:
        issues.append("missing read_only: true on services")
    if "cap_drop" not in text:
        issues.append("missing cap_drop")
    if "no-new-privileges" not in text:
        issues.append("missing no-new-privileges:true security_opt")
    return issues


def audit_dockerfile(text: str) -> List[str]:
    issues: List[str] = []
    if "USER " not in text:
        issues.append("Dockerfile must declare a non-root USER")
    elif "USER 0" in text or "USER root" in text:
        issues.append("Dockerfile sets USER root")
    return issues


def audit_deploy_dir(path: Path) -> List[Tuple[str, List[str]]]:
    out: List[Tuple[str, List[str]]] = []
    if not path.is_dir():
        return out
    df = path / "Dockerfile"
    if df.is_file():
        i = audit_dockerfile(df.read_text(encoding="utf-8"))
        if i:
            out.append(("Dockerfile", i))
    for cf in path.glob("**/docker-compose*.yml"):
        i = audit_compose_file(cf.read_text(encoding="utf-8"))
        if i:
            out.append((str(cf), i))
    return out


def k8s_recommended() -> str:
    return _K8S_RECOMMENDED


def compose_recommended() -> str:
    return _COMPOSE_RECOMMENDED


register(DefencePlugin(
    round_id="R45",
    name="readonly_rootfs",
    description="Audit + recommend read-only rootfs + cap-drop deploy hardening.",
))
