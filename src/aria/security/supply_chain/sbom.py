from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CYCLONEDX_BIN = "cyclonedx-py"


class SbomBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class SbomResult:
    sbom_path: Path
    sbom_format: str
    sha256_hex: str
    n_components: int
    raw_bytes: bytes


def _ensure_cyclonedx_available() -> str:
    binary = shutil.which(CYCLONEDX_BIN)
    if binary is None:
        raise SbomBuildError(
            f"cyclonedx-py not on PATH; install with `pip install cyclonedx-bom`"
        )
    return binary


def generate_cyclonedx_sbom(
    *,
    output_path: Path,
    python_executable: Optional[str] = None,
    pyproject_path: Optional[Path] = None,
    timeout_s: float = 120.0,
) -> SbomResult:
    binary = _ensure_cyclonedx_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [binary, "environment", "--of", "JSON", "-o", str(output_path)]
    if pyproject_path is not None:
        cmd.extend(["--pyproject", str(pyproject_path)])
    if python_executable is not None:
        cmd.append(python_executable)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SbomBuildError(f"cyclonedx-py timed out after {timeout_s}s") from exc

    if result.returncode != 0:
        raise SbomBuildError(
            f"cyclonedx-py exit {result.returncode}: {result.stderr.strip()[:400]}"
        )

    if not output_path.exists():
        raise SbomBuildError(
            f"cyclonedx-py reported success but {output_path} is missing"
        )

    raw = output_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw.decode("utf-8"))
    n_components = len(payload.get("components") or [])

    return SbomResult(
        sbom_path=output_path,
        sbom_format="CycloneDX-JSON",
        sha256_hex=sha,
        n_components=n_components,
        raw_bytes=raw,
    )


def summarise_sbom(sbom_path: Path) -> dict:
    if not sbom_path.exists():
        raise SbomBuildError(f"SBOM not found at {sbom_path}")
    payload = json.loads(sbom_path.read_text(encoding="utf-8"))
    components = payload.get("components") or []
    by_license: dict[str, int] = {}
    for component in components:
        licenses = component.get("licenses") or []
        if not licenses:
            label = "UNKNOWN"
        else:
            label = (
                licenses[0].get("license", {}).get("id")
                or licenses[0].get("license", {}).get("name")
                or "UNKNOWN"
            )
        by_license[label] = by_license.get(label, 0) + 1
    return {
        "n_components": len(components),
        "by_license": by_license,
        "spec_version": payload.get("specVersion"),
        "bom_format": payload.get("bomFormat"),
    }
