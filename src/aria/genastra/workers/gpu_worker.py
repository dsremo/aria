"""GPU inference worker — runs ESMFold in an isolated process.

Panel 1 (Google SRE): "GPU inference is a global mutable singleton. If the
model OOMs on a 2500-residue protein, the entire process crashes. Need process
isolation — run inference in a separate worker process with watchdog."

This worker:
1. Loads ESMFold on startup (~30-60s, ~8 GB GPU RAM)
2. Consumes jobs from Redis Stream 'genastra:gpu_jobs'
3. Writes results back to 'genastra:gpu_jobs:results'
4. Sends heartbeat for readiness checks
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.genastra.workers.base import BaseWorker

logger = structlog.get_logger()


class GPUWorker(BaseWorker):
    """GPU worker for protein structure prediction."""

    def __init__(self, device: str = "cuda") -> None:
        super().__init__(
            stream_name="genastra:gpu_jobs",
            consumer_group="gpu_workers",
        )
        self._device = device
        self._engine = None

    async def setup(self) -> None:
        """Load ESMFold model onto GPU."""
        from aria.genastra.protein.esmfold import ESMFoldEngine

        self._engine = ESMFoldEngine()
        self._engine.load_model(device=self._device)
        logger.info("gpu_worker_model_loaded", device=self._device)

    async def process_job(self, job_id: str, job_data: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        """Run structure prediction for a single sequence."""
        if self._engine is None:
            raise RuntimeError("ESMFold model not loaded")

        sequence = job_data.get("sequence", "")
        tenant_id = job_data.get("tenant_id", "")

        # Run inference (CPU-bound, but in this dedicated process it's fine)
        result = self._engine.predict(sequence)

        return {
            "pdb_string": result.pdb_string[:100] + "...",  # truncated for Redis
            "mean_plddt": str(result.mean_plddt),
            "ptm_score": str(result.ptm_score) if result.ptm_score else "",
            "inference_time_ms": str(result.inference_time_ms),
            "sequence_length": str(result.sequence_length),
            "model_name": result.model_name,
            "model_version": result.model_version,
            "tenant_id": tenant_id,
        }

    async def teardown(self) -> None:
        """Release GPU memory."""
        self._engine = None
        logger.info("gpu_worker_model_unloaded")


async def main() -> None:
    """Entry point for GPU worker process."""
    import argparse

    parser = argparse.ArgumentParser(description="GenAstra GPU Worker")
    parser.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    args = parser.parse_args()

    worker = GPUWorker(device=args.device)
    await worker.run(redis_url=args.redis_url)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
