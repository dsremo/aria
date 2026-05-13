"""R198 — Volatile-artefact preservation.

Threat: the artefacts most useful to an investigator (active network
sockets, in-RAM keys, environment variables, /tmp) are precisely the
ones that vanish when the host is rebooted or the container exits.
Without a preserve step they are lost.

Defence: ``snapshot_volatile`` captures /proc/net/{tcp,udp},
/proc/self/environ (redacted), open file descriptors, and active
threads — into a single bundle.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict

from aria.security.plugins import DefencePlugin, register


def _redact_env(env: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in env.items():
        kl = k.lower()
        if any(s in kl for s in ("password", "secret", "token", "key", "credential")):
            out[k] = f"[REDACTED len={len(v)}]"
        else:
            out[k] = v
    return out


def snapshot_volatile() -> Dict[str, Any]:
    snap: Dict[str, Any] = {"timestamp": time.time(), "pid": os.getpid()}

    for name in ("tcp", "tcp6", "udp"):
        p = Path(f"/proc/net/{name}")
        if p.exists():
            try:
                snap[f"net_{name}"] = p.read_text(errors="ignore").splitlines()[:200]
            except OSError:
                pass

    snap["env"] = _redact_env(dict(os.environ))

    fds: Dict[str, str] = {}
    fd_dir = Path(f"/proc/{os.getpid()}/fd")
    if fd_dir.exists():
        try:
            for fd in fd_dir.iterdir():
                try:
                    fds[fd.name] = os.readlink(fd)
                except OSError:
                    continue
        except OSError:
            pass
    snap["fds"] = fds

    snap["threads"] = [t.name for t in threading.enumerate()]

    return snap


def write_bundle(out_dir: str = "/var/log/aria/volatile") -> str:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundle_path = p / f"volatile-{int(time.time())}.json"
    bundle_path.write_text(json.dumps(snapshot_volatile(), default=str, indent=2))
    return str(bundle_path)


register(DefencePlugin(
    round_id="R198",
    name="volatile_preserve",
    description="Snapshot volatile state (sockets, env, fds, threads) for forensics.",
))
