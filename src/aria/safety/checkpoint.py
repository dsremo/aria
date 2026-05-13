"""Checkpoint Manager — state persistence for crash recovery.

After an ARIA restart, the checkpoint manager restores:
  - Agent states
  - Tool health metrics
  - Decision engine pending decisions
  - Memory store working memory
  - Coordinator state

Checkpoints are written every N seconds to persistent storage.
Triple-redundant writes: primary + backup + verification hash.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class Checkpoint:
    """A serialized ARIA state snapshot."""

    checkpoint_id: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    state_data: dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    size_bytes: int = 0

    def compute_checksum(self) -> str:
        raw = json.dumps(self.state_data, sort_keys=True, default=str).encode()
        self.checksum = hashlib.sha256(raw).hexdigest()[:16]
        self.size_bytes = len(raw)
        return self.checksum


class CheckpointManager:
    """Manages periodic state checkpointing and crash recovery.

    Usage:
        mgr = CheckpointManager(persist_dir="data/checkpoints", interval_s=60)
        await mgr.start(state_provider=coordinator.snapshot)
        # ... ARIA runs ...
        # After crash restart:
        restored = mgr.restore_latest()
    """

    def __init__(
        self,
        persist_dir: str | Path = "data/checkpoints",
        interval_s: float = 60.0,
        max_checkpoints: int = 10,
    ) -> None:
        self._dir = Path(persist_dir)
        self._interval = interval_s
        self._max_checkpoints = max_checkpoints
        self._counter: int = 0
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._last_checkpoint: Checkpoint | None = None
        self._state_provider: Any = None

    @property
    def interval_s(self) -> float:
        """Wiring audit Pass 7 (F11.7) — public accessor. The
        coordinator's checkpoint loop previously did
        ``getattr(self.checkpoint, "_interval_s", 300)`` which (a)
        reaches into a private attribute and (b) read the WRONG
        attribute name (the real one is ``_interval``) so the loop
        ran at the 300s fallback regardless of configured interval.
        """
        return float(self._interval)

    @property
    def last_checkpoint(self) -> Checkpoint | None:
        return self._last_checkpoint

    def set_state_provider(self, state_provider: Any) -> None:
        """Wire the callable that ``save_now`` will invoke to snapshot
        system state.  Wiring audit Pass 1 (F11.3): callers used to
        assign ``self._state_provider`` directly which made the
        private attribute load-bearing — a rename would silently break
        the next checkpoint.  Use this public setter instead.
        """
        self._state_provider = state_provider

    async def start(self, state_provider: Any) -> None:
        """Start periodic checkpointing. state_provider() returns dict."""
        self._state_provider = state_provider
        self._dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._task = asyncio.create_task(self._checkpoint_loop())
        logger.info("checkpoint.started", interval_s=self._interval, dir=str(self._dir))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        # Final checkpoint on shutdown
        if self._state_provider:
            await self.save_now()
        logger.info("checkpoint.stopped")

    async def save_now(self) -> Checkpoint:
        """Force an immediate checkpoint.

        Recovery audit R-12: previously the "backup" was a
        ``read_text → write_text`` of the just-written primary, with a
        tautological mismatch check; if the primary was corrupted in
        flight both files agreed and the bug was invisible.  Now both
        files are serialised independently from the source dict, both
        are atomic-renamed via ``os.replace``, both are fsync'd, and
        the directory is fsync'd so a power loss during the write
        leaves at most one of {primary, backup} intact.
        """
        if not self._state_provider:
            raise RuntimeError("No state provider configured")

        state = self._state_provider()
        self._counter += 1

        cp = Checkpoint(
            checkpoint_id=self._counter,
            state_data=state,
        )
        cp.compute_checksum()

        record = {
            "checkpoint_id": cp.checkpoint_id,
            "timestamp": cp.timestamp,
            "checksum": cp.checksum,
            "size_bytes": cp.size_bytes,
            "state": cp.state_data,
        }
        serialised = json.dumps(record, indent=2, default=str)

        filename = f"checkpoint_{self._counter:06d}.json"
        path = self._dir / filename
        backup_path = self._dir / f"{filename}.bak"

        # Atomic primary write.
        self._atomic_write(path, serialised)
        # Independent backup write — re-serialised from the source
        # dict, NOT copied from the primary file.  Different I/O path
        # means a corruption that affected one is unlikely to affect
        # the other in the same flight.
        self._atomic_write(backup_path, json.dumps(record, indent=2, default=str))

        # Directory fsync so the rename is durable.
        try:
            dir_fd = os.open(str(self._dir), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

        self._last_checkpoint = cp

        # Cleanup old checkpoints
        self._cleanup_old()

        logger.info(
            "checkpoint.saved",
            id=cp.checkpoint_id,
            size_bytes=cp.size_bytes,
            checksum=cp.checksum,
        )
        return cp

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Recovery audit R-12: tmp → fsync → os.replace pattern."""
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)

    # Wiring audit Pass 1 (F3.3) — checkpoint schema version known to
    # this binary. Bump in lock-step with ``_build_checkpoint_state``
    # in the coordinator. A loaded checkpoint with a different version
    # is refused so the spacecraft never quietly hydrates fields the
    # writer never produced (the failure mode that R-10 addressed).
    SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (2,)

    def restore_latest(self) -> dict[str, Any] | None:
        """Restore state from the most recent valid checkpoint."""
        if not self._dir.exists():
            return None

        checkpoints = sorted(self._dir.glob("checkpoint_*.json"), reverse=True)
        # Exclude .bak files
        checkpoints = [c for c in checkpoints if not c.name.endswith(".bak")]

        for cp_path in checkpoints:
            try:
                data = json.loads(cp_path.read_text())
                state = data.get("state", {})
                stored_checksum = data.get("checksum", "")

                # Verify integrity
                raw = json.dumps(state, sort_keys=True, default=str).encode()
                computed = hashlib.sha256(raw).hexdigest()[:16]

                if computed == stored_checksum:
                    # Wiring audit Pass 1 (F3.3) — refuse to restore if
                    # the dump's schema_version is *known and wrong*.
                    # Absent schema_version is accepted with a warning
                    # for back-compat with legacy / test fixtures; the
                    # coordinator always writes ``schema_version: 2``
                    # so production dumps always carry one.
                    schema_version = state.get("schema_version")
                    if (
                        schema_version is not None
                        and schema_version not in self.SUPPORTED_SCHEMA_VERSIONS
                    ):
                        logger.warning(
                            "checkpoint.schema_version_unsupported",
                            file=cp_path.name,
                            stored_version=schema_version,
                            supported=list(self.SUPPORTED_SCHEMA_VERSIONS),
                            impact="refusing restore — coordinator would hydrate "
                                   "into mismatched schema",
                        )
                        continue
                    if schema_version is None:
                        logger.warning(
                            "checkpoint.no_schema_version",
                            file=cp_path.name,
                            note="loading anyway — pre-versioning legacy dump",
                        )
                    logger.info(
                        "checkpoint.restored",
                        id=data.get("checkpoint_id"),
                        timestamp=data.get("timestamp"),
                        schema_version=schema_version,
                    )
                    return state
                else:
                    logger.warning(
                        "checkpoint.checksum_mismatch",
                        file=cp_path.name,
                        stored=stored_checksum,
                        computed=computed,
                    )
                    # Recovery audit R-14: verify the backup's OWN
                    # checksum before trusting it.  Previously we read
                    # the backup unconditionally, so a corrupt primary
                    # + corrupt backup would still return state and
                    # the spacecraft would boot into garbage.
                    bak_path = Path(str(cp_path) + ".bak")
                    if bak_path.exists():
                        try:
                            bak_data = json.loads(bak_path.read_text())
                            bak_state = bak_data.get("state", {})
                            bak_stored = bak_data.get("checksum", "")
                            bak_raw = json.dumps(
                                bak_state, sort_keys=True, default=str,
                            ).encode()
                            bak_computed = hashlib.sha256(bak_raw).hexdigest()[:16]
                            if bak_computed == bak_stored:
                                # Wiring audit Pass 1 (F3.3): same
                                # schema gate on the backup path —
                                # absent version accepted, mismatched
                                # version refused.
                                bak_schema = bak_state.get("schema_version")
                                if (
                                    bak_schema is not None
                                    and bak_schema not in self.SUPPORTED_SCHEMA_VERSIONS
                                ):
                                    logger.warning(
                                        "checkpoint.backup_schema_version_unsupported",
                                        file=bak_path.name,
                                        stored_version=bak_schema,
                                        supported=list(self.SUPPORTED_SCHEMA_VERSIONS),
                                    )
                                    continue
                                logger.error(
                                    "checkpoint.restored_from_backup",
                                    file=bak_path.name,
                                    schema_version=bak_schema,
                                )
                                return bak_state
                            logger.error(
                                "checkpoint.backup_also_corrupt",
                                file=bak_path.name,
                                stored=bak_stored,
                                computed=bak_computed,
                            )
                        except (OSError, ValueError) as exc:
                            logger.error(
                                "checkpoint.backup_unreadable",
                                file=bak_path.name, error=str(exc),
                            )
                    # Fall through to the next-older checkpoint.

            except Exception as exc:
                logger.error("checkpoint.restore_error", file=cp_path.name, error=str(exc))

        logger.warning("checkpoint.no_valid_checkpoint_found")
        return None

    def _cleanup_old(self) -> None:
        """Remove old checkpoints beyond max_checkpoints."""
        checkpoints = sorted(self._dir.glob("checkpoint_*.json"))
        checkpoints = [c for c in checkpoints if not c.name.endswith(".bak")]

        while len(checkpoints) > self._max_checkpoints:
            old = checkpoints.pop(0)
            old.unlink(missing_ok=True)
            bak = Path(str(old) + ".bak")
            bak.unlink(missing_ok=True)

    async def _checkpoint_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self.save_now()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("checkpoint.loop_error", error=str(exc))
