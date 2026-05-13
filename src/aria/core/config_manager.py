"""Active/staging configuration manager with atomic commit.

Implements the F Prime PrmDb pattern: maintains two config databases
(active + staging). Config changes are loaded into staging first,
validated, then atomically committed to active with pointer swap.
A bad config load never corrupts the running system.

Pattern studied from NASA JPL F Prime PrmDbImpl (Apache 2.0).

Usage:
    mgr = ConfigManager()
    mgr.set_active({"reactor_power_w": 1e8, "eclss_o2_target": 0.21})

    # Ground operator uploads new config
    mgr.load_staged({"reactor_power_w": 1.2e8, "eclss_o2_target": 0.205})
    if mgr.validate_staged():
        mgr.commit()   # atomic swap
    else:
        mgr.discard_staged()  # rollback
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()


@dataclass
class ConfigSnapshot:
    """Immutable snapshot of a configuration state."""
    params: Dict[str, Any]
    checksum: str
    timestamp: float
    source: str = ""  # "file:/path", "api", "default"


class ConfigManager:
    """Double-buffered configuration manager with atomic commit.

    The active config is always valid and consistent. Staging allows
    preview and validation before committing. Rollback restores the
    previous active config.

    Thread-safe: reads always see the active config; commits swap
    pointers under a lock.
    """

    def __init__(self) -> None:
        self._active: Dict[str, Any] = {}
        self._staged: Optional[Dict[str, Any]] = None
        self._previous: Optional[Dict[str, Any]] = None  # for rollback
        self._validators: List[Callable[[Dict[str, Any]], Optional[str]]] = []
        self._lock = threading.RLock()
        self._commit_count: int = 0
        self._rollback_count: int = 0

    def set_active(self, params: Dict[str, Any], source: str = "default") -> None:
        """Initialize the active configuration."""
        with self._lock:
            self._previous = copy.deepcopy(self._active) if self._active else None
            self._active = copy.deepcopy(params)

    def get(self, key: str, default: Any = None) -> Any:
        """Read a parameter from the active config (never sees staging)."""
        with self._lock:
            return self._active.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Return a deep copy of the active config."""
        with self._lock:
            return copy.deepcopy(self._active)

    def load_staged(self, params: Dict[str, Any], source: str = "api") -> None:
        """Load parameters into the staging buffer for validation."""
        with self._lock:
            self._staged = copy.deepcopy(params)

    def load_staged_from_file(self, path: str | Path) -> bool:
        """Load staging config from a JSON/YAML file with integrity check."""
        path = Path(path)
        if not path.exists():
            logger.warning(
                "config_manager.staged_load_missing", path=str(path),
            )
            return False
        try:
            data = json.loads(path.read_text())
            self.load_staged(data, source=f"file:{path}")
            return True
        # Wiring audit Pass 7 (F6.12) — surface malformed-JSON / IO
        # failures rather than swallowing them. A silent False return
        # masked a corrupt staged config; downstream callers had no
        # signal to differentiate "file missing" from "file unparsable".
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "config_manager.staged_load_failed",
                path=str(path),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False

    def validate_staged(self) -> tuple[bool, List[str]]:
        """Run all registered validators against the staged config.

        Returns (valid, list_of_error_messages).
        """
        with self._lock:
            if self._staged is None:
                return False, ["No staged config loaded"]

            errors: List[str] = []
            for validator in self._validators:
                try:
                    err = validator(self._staged)
                    if err:
                        errors.append(err)
                except Exception as e:
                    errors.append(f"Validator raised: {e}")

            return len(errors) == 0, errors

    def commit(self) -> bool:
        """Atomically swap staged config to active.

        Returns True if commit succeeded (staged was loaded and valid).
        """
        with self._lock:
            if self._staged is None:
                return False

            # Save current active for rollback
            self._previous = copy.deepcopy(self._active)

            # Atomic swap (pointer assignment under lock)
            self._active = self._staged
            self._staged = None
            self._commit_count += 1

            return True

    def discard_staged(self) -> None:
        """Discard the staged config without committing."""
        with self._lock:
            self._staged = None

    def rollback(self) -> bool:
        """Restore the previous active config.

        Returns True if rollback succeeded (previous config existed).
        """
        with self._lock:
            if self._previous is None:
                return False
            self._active = self._previous
            self._previous = None
            self._rollback_count += 1
            return True

    def register_validator(self, fn: Callable[[Dict[str, Any]], Optional[str]]) -> None:
        """Register a validation function.

        The function takes a config dict and returns None (valid) or
        an error string (invalid).
        """
        self._validators.append(fn)

    def snapshot(self) -> ConfigSnapshot:
        """Create an immutable snapshot of the active config."""
        with self._lock:
            params = copy.deepcopy(self._active)
            checksum = hashlib.sha256(
                json.dumps(params, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            return ConfigSnapshot(
                params=params,
                checksum=checksum,
                timestamp=time.time(),
            )

    def stats(self) -> Dict[str, Any]:
        """Return configuration manager statistics."""
        with self._lock:
            return {
                "active_params": len(self._active),
                "staged": self._staged is not None,
                "has_rollback": self._previous is not None,
                "commits": self._commit_count,
                "rollbacks": self._rollback_count,
                "validators": len(self._validators),
            }
