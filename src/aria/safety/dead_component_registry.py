"""Dead-component registry (Recovery audit R-23).

Persistent record of hardware components that have been declared
permanently failed.  FDIR consults the registry before dispatching a
recovery plan; the LLM agent sees the list via system status so it
does not propose plans that depend on dead hardware.

Persists to ``data/runtime/dead_components.json`` with the same
atomic-write pattern used elsewhere in the safety tree.

Lifecycle:

  ``mark_dead(component_id, reason)``    — declare permanent failure.
  ``is_dead(component_id) -> bool``      — pre-flight check.
  ``can_retry(component_id) -> bool``    — True if the cooling-off
                                            window has elapsed.
  ``revive(component_id, signature)``    — clear the entry.  Requires
                                            an Ed25519 signature from
                                            the ship-HSM root key
                                            (same path as
                                            ``physical_key_reset``)
                                            so the LLM cannot un-mark
                                            its own failure.

Reference:
  * NASA-STD-8729.1A §6.5 — autonomous-fault response with
    component-level retirement.
  * Cassini "permanent removal-from-service" log (JPL DSN
    810-005-200 §5.2).
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()


# Components remain blacklisted for at least this long even if a
# `revive` is requested without a signature.  Prevents the LLM from
# rapid-fire revival attempts.
DEFAULT_RETRY_COOLDOWN_S = 24 * 3600.0    # 24 h — NASA-STD-8729.1A §6.5


@dataclass
class DeadComponentRecord:
    component_id: str
    marked_at: float
    reason: str
    can_retry_after: float = 0.0
    marked_by: str = ""


class DeadComponentRegistry:
    """Persisted registry of failed components."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        if state_path is None:
            env = os.environ.get("ARIA_RUNTIME_DIR")
            base = Path(env) if env else Path(__file__).resolve().parents[3] / "data" / "runtime"
            state_path = base / "dead_components.json"
        self._state_path = state_path
        self._records: Dict[str, DeadComponentRecord] = {}
        self._lock = threading.Lock()
        self._load()

    def mark_dead(
        self,
        component_id: str,
        reason: str,
        marked_by: str = "fdir",
        cooldown_s: float = DEFAULT_RETRY_COOLDOWN_S,
    ) -> None:
        with self._lock:
            now = time.time()
            self._records[component_id] = DeadComponentRecord(
                component_id=component_id,
                marked_at=now,
                reason=reason,
                can_retry_after=now + cooldown_s,
                marked_by=marked_by,
            )
            self._persist_locked()
        logger.error("dead_component.marked",
                     component=component_id, reason=reason, by=marked_by)

    def is_dead(self, component_id: str) -> bool:
        with self._lock:
            return component_id in self._records

    def can_retry(self, component_id: str) -> bool:
        """True if the cooldown has elapsed.  FDIR honours this before
        retrying a known-dead component."""
        with self._lock:
            rec = self._records.get(component_id)
            if rec is None:
                return True
            return time.time() >= rec.can_retry_after

    def revive(self, component_id: str, signature_hex: str = "") -> bool:
        """Clear a record.  In production callers must supply a valid
        ship-HSM signature; in dev the empty signature is accepted
        with a loud warning."""
        with self._lock:
            if component_id not in self._records:
                return False
            if signature_hex:
                # Defer to the same ship-HSM verification path used
                # for kill-switch reset.
                ok = self._verify_revive_signature(component_id, signature_hex)
                if not ok:
                    logger.error("dead_component.revive_signature_invalid",
                                 component=component_id)
                    return False
            else:
                # Wiring audit Pass 1 (F13.2) — refuse the unsigned
                # path in production. A misconfigured prod could
                # otherwise revive any retired component without an
                # HSM signature, defeating R-23.
                if os.environ.get("ARIA_ENVIRONMENT", "development") == "production":
                    logger.critical(
                        "dead_component.revive_unsigned_refused_in_production",
                        component=component_id,
                        impact="ship-HSM signature required to revive retired components",
                    )
                    return False
                logger.warning("dead_component.revive_unsigned",
                               component=component_id,
                               note="dev-only path; production requires HSM sig")
            self._records.pop(component_id, None)
            self._persist_locked()
        logger.warning("dead_component.revived", component=component_id)
        return True

    def all_dead(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [asdict(r) for r in self._records.values()]

    @staticmethod
    def _verify_revive_signature(component_id: str, signature_hex: str) -> bool:
        try:
            from aria.security.principals import get_principal_store
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            pubkey_hex = get_principal_store().ship_root_pubkey_hex()
            if not pubkey_hex:
                return False
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
            payload = f"revive_dead|{component_id}".encode()
            pub.verify(bytes.fromhex(signature_hex), payload)
            return True
        except (InvalidSignature, ValueError):
            return False
        except Exception as exc:    # noqa: BLE001
            logger.error("dead_component.verify_error", error=str(exc))
            return False

    def _load(self) -> None:
        path = self._state_path
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("dead_component.load_failed", error=str(exc))
            return
        for cid, rec in data.items():
            try:
                self._records[cid] = DeadComponentRecord(**rec)
            except TypeError:
                continue

    def _persist_locked(self) -> None:
        path = self._state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            payload = {cid: asdict(r) for cid, r in self._records.items()}
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as exc:
            logger.error("dead_component.persist_failed", error=str(exc))


# ── Process-wide singleton ────────────────────────────────────────

_INSTANCE: Optional[DeadComponentRegistry] = None
_INSTANCE_LOCK = threading.Lock()


def get_dead_component_registry() -> DeadComponentRegistry:
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = DeadComponentRegistry()
    return _INSTANCE


def reset_for_test() -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = None
