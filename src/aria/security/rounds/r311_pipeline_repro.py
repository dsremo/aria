"""R311 — ML pipeline reproducibility audit.

Threat: a non-reproducible training pipeline cannot be audited —
when a model misbehaves, you can't recover the exact inputs that
produced it.  ML supply-chain reviews (NIST AI RMF, EU AI Act §13)
require provenance + reproducibility.

Defence: a reproducibility manifest tracking deterministic flags +
input checksums.  ``audit_pipeline_run`` refuses runs missing
deterministic seeds, declared environment hash, or input-data
manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class PipelineRunDescriptor:
    run_id: str
    seed: int = -1
    cudnn_deterministic: bool = False
    inputs_manifest_sha256: str = ""
    env_lockfile_sha256: str = ""
    framework_versions: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)


def audit_pipeline_run(d: PipelineRunDescriptor) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if d.seed < 0:
        issues.append("pipeline.no_seed")
    if not d.cudnn_deterministic:
        issues.append("pipeline.cudnn_non_deterministic")
    if not d.inputs_manifest_sha256:
        issues.append("pipeline.no_inputs_manifest")
    if not d.env_lockfile_sha256:
        issues.append("pipeline.no_env_lockfile")
    if not d.framework_versions:
        issues.append("pipeline.no_framework_versions")
    return not issues, issues


def diff_runs(a: PipelineRunDescriptor, b: PipelineRunDescriptor) -> List[str]:
    diffs: List[str] = []
    for field_name in ("seed", "cudnn_deterministic", "inputs_manifest_sha256", "env_lockfile_sha256"):
        if getattr(a, field_name) != getattr(b, field_name):
            diffs.append(f"diff.{field_name}")
    if a.framework_versions != b.framework_versions:
        diffs.append("diff.framework_versions")
    return diffs


register(DefencePlugin(
    round_id="R311",
    name="pipeline_repro",
    description="Pipeline-run reproducibility manifest audit (seed + env + inputs).",
))
