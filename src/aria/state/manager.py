"""State manager: versioned key-value store with change notifications.

ARIA agents read/write state here. Changes trigger notifications to subscribers.

Sensor-fusion audit hardenings:
    * S-13: per-namespace schema validators reject malformed values at
            ``set`` time so a compromised agent cannot pollute the
            store with arbitrary JSON.
    * S-22: ``_save`` writes via ``tmp + os.fsync + os.replace`` so a
            partial write on power-loss does not corrupt the store.
    * S-23: ``snapshot`` returns deep-copied values so caller mutation
            cannot reach the live store.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog

logger = structlog.get_logger()

StateObserver = Callable[[str, Any, Any], None]  # (key, old_value, new_value)
StateValidator = Callable[[str, Any], None]      # raise ValueError on bad value


@dataclass
class StateEntry:
    """A versioned state entry."""

    key: str
    value: Any
    version: int = 1
    updated_at: float = field(default_factory=time.time)
    updated_by: str = ""


class StateManager:
    """Centralized state store for ARIA.

    Features:
      - Get/set with automatic versioning
      - Persistence to JSON file (atomic + fsync — S-22)
      - Namespace support (agent.telemetry.last_anomaly)
      - Rollback to previous version
      - Per-namespace schema validators (S-13)
    """

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._store: dict[str, StateEntry] = {}
        self._observers: list[StateObserver] = []
        self._validators: dict[str, StateValidator] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        self._history: dict[str, list[StateEntry]] = {}
        self._lock = threading.Lock()

        if self._persist_path and self._persist_path.exists():
            self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a state value."""
        entry = self._store.get(key)
        return entry.value if entry is not None else default

    def get_entry(self, key: str) -> StateEntry | None:
        """Get full state entry with metadata."""
        return self._store.get(key)

    def register_validator(self, key_prefix: str, validator: StateValidator) -> None:
        """Register a validator for keys starting with ``key_prefix``.

        Validators are called with ``(key, value)`` and MUST raise
        ``ValueError`` on invalid input.  More-specific prefixes win
        over shorter ones (longest-prefix match).  Sensor-fusion audit
        S-13.
        """
        self._validators[key_prefix] = validator

    def _resolve_validator(self, key: str) -> StateValidator | None:
        """Longest-prefix match against registered validators."""
        best_prefix = ""
        for prefix in self._validators:
            if key.startswith(prefix) and len(prefix) > len(best_prefix):
                best_prefix = prefix
        return self._validators.get(best_prefix) if best_prefix else None

    def set(self, key: str, value: Any, updated_by: str = "system") -> None:
        """Set a state value. Notifies observers and persists.

        Sensor-fusion audit S-13: routes through any registered
        validator before mutating state.  Validators may raise
        ``ValueError`` to reject the write.
        """
        validator = self._resolve_validator(key)
        if validator is not None:
            validator(key, value)

        with self._lock:
            old_entry = self._store.get(key)
            old_value = old_entry.value if old_entry else None
            new_version = (old_entry.version + 1) if old_entry else 1

            # Archive old version
            if old_entry:
                self._history.setdefault(key, []).append(old_entry)
                self._history[key] = self._history[key][-10:]

            entry = StateEntry(
                key=key,
                value=value,
                version=new_version,
                updated_by=updated_by,
            )
            self._store[key] = entry
            persist_path = self._persist_path

        # Notify observers OUTSIDE the lock so a slow handler cannot
        # block other writers.
        for observer in self._observers:
            try:
                observer(key, old_value, value)
            except Exception as exc:
                logger.error("state.observer_error", key=key, error=str(exc))

        if persist_path:
            self._save()

    def delete(self, key: str) -> bool:
        """Delete a state entry."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                persist_path = self._persist_path
            else:
                return False
        if persist_path:
            self._save()
        return True

    def rollback(self, key: str) -> bool:
        """Rollback to previous version of a key."""
        with self._lock:
            history = self._history.get(key)
            if not history:
                return False
            previous = history.pop()
            self._store[key] = previous
            persist_path = self._persist_path
            version = previous.version
        if persist_path:
            self._save()
        logger.info("state.rollback", key=key, version=version)
        return True

    def keys(self, prefix: str = "") -> list[str]:
        """List all keys, optionally filtered by prefix."""
        if prefix:
            return [key for key in self._store if key.startswith(prefix)]
        return list(self._store.keys())

    def subscribe(self, observer: StateObserver) -> None:
        """Register an observer for state changes."""
        self._observers.append(observer)

    def unsubscribe(self, observer: StateObserver) -> None:
        """Remove an observer."""
        self._observers = [observer_fn for observer_fn in self._observers
                           if observer_fn is not observer]

    def snapshot(self) -> dict[str, Any]:
        """Return full state as a plain dict (for checkpointing).

        Sensor-fusion audit S-23: values are deep-copied so the caller
        can mutate the returned dict freely without affecting the live
        store.
        """
        with self._lock:
            return {key: copy.deepcopy(entry.value)
                    for key, entry in self._store.items()}

    def _save(self) -> None:
        """Persist state to JSON atomically (sensor-fusion audit S-22).

        Writes to a sibling tmp file, fsyncs the file, replaces atomically,
        then fsyncs the parent directory so the rename is durable on
        crash.  Mirrors the same pattern used by replay_guard._persist_locked.
        """
        path = self._persist_path
        if not path:
            return
        with self._lock:
            data = {
                key: {
                    "value": entry.value,
                    "version": entry.version,
                    "updated_by": entry.updated_by,
                }
                for key, entry in self._store.items()
            }

        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2, default=str)
                fp.flush()
                try:
                    os.fsync(fp.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            try:
                dir_fd = os.open(str(path.parent), os.O_DIRECTORY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except (OSError, AttributeError):
                # Directory fsync is unavailable on Windows / some
                # filesystems; the os.replace above is still atomic
                # within the FS — only durability is weakened.
                pass
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("state.save_failed", error=str(exc))

    def _load(self) -> None:
        """Load state from JSON."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text())
            for key, entry_data in data.items():
                self._store[key] = StateEntry(
                    key=key,
                    value=entry_data.get("value"),
                    version=entry_data.get("version", 1),
                    updated_by=entry_data.get("updated_by", "loaded"),
                )
            logger.info("state.loaded", keys=len(self._store))
        except Exception as exc:
            logger.error("state.load_error", error=str(exc))
