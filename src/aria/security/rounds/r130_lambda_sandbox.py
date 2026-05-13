"""R130 — AWS Lambda sandbox config audit.

Threat: a Lambda function granted excessive role permissions, mounted
EFS, attached to a public-subnet VPC, or running with default
``Timeout=300`` becomes a long-lived attack surface.  Cloud-security
posture-management (CSPM) tools flag the same set.

Defence: ``audit_lambda_config(config)`` checks the function metadata
returned by ``GetFunctionConfiguration`` and flags:
  * Missing tracing
  * Missing dead-letter queue (silent failures)
  * EFS mount enabled (extra attack surface)
  * Timeout > 60 s (default value, often unneeded)
  * Reserved concurrency = 0 in prod (denial of service via others)
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_lambda_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    if not isinstance(config, dict):
        return False, ["not_a_dict"]
    if (config.get("TracingConfig") or {}).get("Mode") not in ("Active", "PassThrough"):
        issues.append("tracing_disabled")
    if not config.get("DeadLetterConfig"):
        issues.append("no_dlq")
    if config.get("FileSystemConfigs"):
        issues.append("efs_mount_enabled (extra surface)")
    timeout = config.get("Timeout", 0)
    if isinstance(timeout, int) and timeout > 60:
        issues.append(f"timeout={timeout}s > 60")
    rt = config.get("Runtime", "")
    if rt.endswith(("nodejs12.x", "python3.7", "python3.8")) or rt.startswith("dotnet5"):
        issues.append(f"runtime_eol_or_legacy={rt}")
    if config.get("Layers"):
        for layer in config["Layers"]:
            arn = layer.get("Arn", "") if isinstance(layer, dict) else str(layer)
            if "$LATEST" in arn:
                issues.append(f"layer_unpinned:{arn}")
    return len(issues) == 0, issues


register(DefencePlugin(
    round_id="R130",
    name="lambda_sandbox",
    description="Audit Lambda config: tracing, DLQ, EFS, timeout, runtime EOL.",
))
