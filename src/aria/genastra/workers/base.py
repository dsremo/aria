"""Base worker with Redis Streams consumer, health check, and graceful shutdown.

Panel 9 (System Architect): "GPU inference MUST be decoupled from the API server.
Architecture: API -> Redis job queue -> GPU worker (separate process).
Use Redis Streams for job events — provides persistence, consumer groups,
and at-least-once delivery."
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from abc import ABC, abstractmethod
from typing import Any

import structlog

logger = structlog.get_logger()


class BaseWorker(ABC):
    """Abstract base class for async workers consuming from Redis Streams."""

    # P2-E9 (Bhatt): Time allowed to finish the current job before forced exit.
    # Kubernetes default termination grace period is 30s — match it.
    SHUTDOWN_DRAIN_TIMEOUT_S: float = 30.0

    def __init__(
        self,
        stream_name: str,
        consumer_group: str,
        consumer_name: str | None = None,
        poll_interval_ms: int = 1000,
        heartbeat_interval_s: float = 10.0,
    ) -> None:
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"worker-{os.getpid()}"
        self.poll_interval_ms = poll_interval_ms
        self.heartbeat_interval_s = heartbeat_interval_s
        self._running = False
        self._redis = None
        self._current_job_id: str | None = None  # P2-E9: track in-flight job for drain

    @abstractmethod
    async def process_job(self, job_id: str, job_data: dict[str, Any]) -> dict[str, Any]:
        """Process a single job. Override in subclass.

        Args:
            job_id: Unique job identifier.
            job_data: Job parameters from Redis Stream.

        Returns:
            Result dict to be stored.

        Raises:
            Any exception will be caught and the job marked as failed.
        """

    async def setup(self) -> None:  # noqa: B027
        """Optional setup hook (load models, etc.). Override in subclass."""

    async def teardown(self) -> None:  # noqa: B027
        """Optional teardown hook. Override in subclass."""

    async def run(self, redis_url: str = "redis://localhost:6379/0") -> None:
        """Main worker loop."""
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._running = True

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        # Create consumer group (idempotent)
        try:  # noqa: SIM105
            await self._redis.xgroup_create(self.stream_name, self.consumer_group, id="0", mkstream=True)
        except Exception:  # noqa: BLE001, S110
            pass  # Group already exists — xgroup_create raises if group exists, that's OK

        logger.info(
            "worker_started",
            stream=self.stream_name,
            group=self.consumer_group,
            consumer=self.consumer_name,
        )

        await self.setup()

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            while self._running:
                try:
                    # Read from stream (blocking with timeout)
                    messages = await self._redis.xreadgroup(
                        groupname=self.consumer_group,
                        consumername=self.consumer_name,
                        streams={self.stream_name: ">"},
                        count=1,
                        block=self.poll_interval_ms,
                    )

                    if not messages:
                        continue

                    for _stream_name, stream_messages in messages:
                        for msg_id, msg_data in stream_messages:
                            await self._handle_message(msg_id, msg_data)

                except asyncio.CancelledError:
                    break
                except Exception:
                    logger.exception("worker_loop_error")
                    await asyncio.sleep(1.0)

        finally:
            heartbeat_task.cancel()
            await self.teardown()
            await self._redis.aclose()
            logger.info("worker_stopped", consumer=self.consumer_name)

    async def _acquire_job_lock(self, job_id: str, ttl_s: int = 3600) -> bool:
        """Acquire a distributed lock for job_id using Redis SET NX EX.

        P0-E9 (Bhatt): Two workers can read the same job during consumer group
        rebalance — both GPU runs consume compute and the last DB write wins.
        A SETNX lock prevents duplicate execution.

        Returns True if lock was acquired, False if another worker holds it.
        """
        lock_key = f"genastra:job_lock:{job_id}"
        acquired = await self._redis.set(
            lock_key,
            self.consumer_name,
            nx=True,   # SET if Not eXists
            ex=ttl_s,  # expire after TTL to avoid orphaned locks
        )
        return bool(acquired)

    async def _release_job_lock(self, job_id: str) -> None:
        """Release the distributed lock for job_id (only if we hold it)."""
        lock_key = f"genastra:job_lock:{job_id}"
        holder = await self._redis.get(lock_key)
        if holder == self.consumer_name:
            await self._redis.delete(lock_key)

    async def _handle_message(self, msg_id: str, msg_data: dict[str, str]) -> None:
        """Process a single message from the stream."""
        job_id = msg_data.get("job_id", msg_id)

        # P0-E9: Acquire distributed lock before starting work.
        # During consumer group rebalance, multiple workers may receive the same
        # message. The lock ensures only one worker actually runs the job.
        if not await self._acquire_job_lock(job_id):
            logger.warning(
                "job_lock_already_held",
                job_id=job_id,
                worker=self.consumer_name,
            )
            # Acknowledge so the message isn't re-delivered to us again
            await self._redis.xack(self.stream_name, self.consumer_group, msg_id)
            return

        self._current_job_id = job_id  # P2-E9: track for graceful shutdown
        logger.info("job_started", job_id=job_id, worker=self.consumer_name)
        start = time.monotonic()

        try:
            result = await self.process_job(job_id, msg_data)

            # Acknowledge the message
            await self._redis.xack(self.stream_name, self.consumer_group, msg_id)

            # Publish result
            await self._redis.xadd(
                f"{self.stream_name}:results",
                {"job_id": job_id, "status": "completed", **{k: str(v) for k, v in result.items()}},
            )

            elapsed = time.monotonic() - start
            logger.info("job_completed", job_id=job_id, elapsed_s=round(elapsed, 2))

        except Exception as e:
            # Mark job as failed
            await self._redis.xack(self.stream_name, self.consumer_group, msg_id)
            await self._redis.xadd(
                f"{self.stream_name}:results",
                {"job_id": job_id, "status": "failed", "error": str(e)},
            )
            logger.exception("job_failed", job_id=job_id)
        finally:
            self._current_job_id = None
            await self._release_job_lock(job_id)

    async def _heartbeat_loop(self) -> None:
        """Periodically update heartbeat in Redis for readiness checks."""
        while self._running:
            try:
                if self._redis:
                    await self._redis.set(
                        f"genastra:{self.stream_name}:heartbeat",
                        str(time.time()),
                        ex=int(self.heartbeat_interval_s * 3),
                    )
            except Exception:  # noqa: S110, BLE001
                pass
            await asyncio.sleep(self.heartbeat_interval_s)

    def _handle_shutdown(self) -> None:
        """Handle SIGTERM/SIGINT for graceful shutdown.

        P2-E9 (Bhatt): On SIGTERM (Kubernetes rolling update, spot preemption),
        stop accepting new work and wait up to SHUTDOWN_DRAIN_TIMEOUT_S for the
        current job to finish. If it doesn't finish in time, mark it FAILED so
        it is not left stuck in RUNNING state permanently.
        """
        logger.info(
            "worker_shutdown_signal",
            consumer=self.consumer_name,
            current_job=self._current_job_id,
            drain_timeout_s=self.SHUTDOWN_DRAIN_TIMEOUT_S,
        )
        self._running = False

        if self._current_job_id is not None:
            # Schedule a drain task — waits up to SHUTDOWN_DRAIN_TIMEOUT_S for
            # the current job to complete, then marks it FAILED if still running.
            loop = asyncio.get_event_loop()
            loop.create_task(self._drain_current_job())

    async def _drain_current_job(self) -> None:
        """Wait for the in-flight job to finish; mark FAILED if it exceeds drain timeout."""
        deadline = time.monotonic() + self.SHUTDOWN_DRAIN_TIMEOUT_S
        while self._current_job_id is not None and time.monotonic() < deadline:
            await asyncio.sleep(0.5)

        if self._current_job_id is not None and self._redis is not None:
            # Job didn't finish within the drain window — mark it FAILED
            logger.error(
                "job_abandoned_on_shutdown",
                job_id=self._current_job_id,
                worker=self.consumer_name,
                drain_timeout_s=self.SHUTDOWN_DRAIN_TIMEOUT_S,
            )
            timeout_msg = (
                f"Worker {self.consumer_name} preempted during shutdown "
                f"(drain timeout {self.SHUTDOWN_DRAIN_TIMEOUT_S}s exceeded)"
            )
            import contextlib
            async with contextlib.AsyncExitStack() as _stack:  # noqa: SIM105, S110
                try:  # noqa: SIM105, S110
                    await self._redis.xadd(
                        f"{self.stream_name}:results",
                        {"job_id": self._current_job_id, "status": "failed", "error": timeout_msg},
                    )
                except Exception:  # noqa: BLE001, S110
                    pass  # Redis may already be unavailable at this point
