"""R310 — GPU side-channel hardening.

Threat: shared GPUs leak across workloads via memory-residue, MMU-
state aliasing, contention timings.  ``LeftoverLocals`` (Trail of
Bits 2024) showed Apple/AMD/Qualcomm GPUs leak prior-tenant data
through unsafe local-memory reads.

Defence: a config + audit helper that refuses MIG-shared partitions
without zeroisation + refuses CUDA visible devices when isolation
mode is "shared" in production.
"""

from __future__ import annotations

import os
from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def boot_check_gpu_isolation() -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if os.environ.get("ARIA_ENV") != "prod":
        return True, ["non_prod"]

    isolation = os.environ.get("ARIA_GPU_ISOLATION", "").lower()
    if isolation in ("", "shared"):
        issues.append("gpu.shared_isolation_in_prod")

    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if visible == "all" or "," in visible and isolation == "shared":
        issues.append("gpu.cuda_visible_too_broad")

    if os.environ.get("NVIDIA_VISIBLE_DEVICES", "") == "all" and isolation != "exclusive":
        issues.append("gpu.nvidia_visible_all")

    if os.environ.get("ARIA_GPU_ZEROISE", "false").lower() not in ("1", "true", "yes"):
        issues.append("gpu.zeroise_disabled")

    return not issues, issues


def recommend_gpu_isolation() -> str:
    return (
        "Set CUDA_VISIBLE_DEVICES to a single device per process, "
        "ARIA_GPU_ISOLATION=exclusive, ARIA_GPU_ZEROISE=true; "
        "for MIG, partition with 1 instance per workload."
    )


register(DefencePlugin(
    round_id="R310",
    name="gpu_side_channel",
    description="GPU isolation audit; refuse shared MIG + non-zeroised allocator in prod.",
))
