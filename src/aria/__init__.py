"""ARIA — Autonomous Reasoning & Integration Architecture for SpaceAi.

Central AI system for crewed spacecraft. 9 subsystem agents, 55 tools,
12-detector anomaly ensemble (Dsremo), collision avoidance (ConjunctionWatch),
biosignature detection (GenAstra), crew health monitoring, FDIR system.
"""

import os as _os
from pathlib import Path as _Path

__version__ = "0.3.0"


def _load_user_keys_env() -> None:
    keys_path = _Path.home() / ".aria-keys.env"
    if not keys_path.exists():
        return
    try:
        with keys_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key:
                    continue
                if key not in _os.environ:
                    _os.environ[key] = value
    except OSError:
        return


_load_user_keys_env()
