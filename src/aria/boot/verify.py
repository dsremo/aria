"""Boot-time integrity check for the safety-critical tree.

Implements the software side of §F-18 of FAILSAFE_ARCHITECTURE.md.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


# Subtrees under src/aria/ whose tamper is fatal. Anything else gets
# the standard sealed-prompt + constitution + monitor protection but
# isn't boot-verified file by file (would be too noisy with the live
# codebase).
PROTECTED_SUBTREES: Tuple[str, ...] = (
    "cognitive",
    "safety",
    "monitor",
    "agents",
    "security",   # R38 — close gap noted in PRODUCTION_READINESS_RESEARCH.md §1.1
)

# Exit code distinct from sealed-prompt (86) and generic 1 so the
# operator can tell at a glance "Python tree was tampered with."
BOOT_FAIL_EXIT = 87


class BootIntegrityError(RuntimeError):
    """Raised on hash / missing-file errors when strict=False."""


def _aria_pkg_root() -> Path:
    """Return the resolved src/aria/ directory."""
    return Path(__file__).resolve().parents[1]


def _enumerate_protected_files(pkg_root: Optional[Path] = None) -> List[Path]:
    pkg_root = pkg_root or _aria_pkg_root()
    out: List[Path] = []
    for sub in PROTECTED_SUBTREES:
        d = pkg_root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.py")):
            # Skip __pycache__, generated, and tests.
            if "__pycache__" in p.parts:
                continue
            out.append(p)
    return out


def compute_manifest(pkg_root: Optional[Path] = None) -> Dict[str, str]:
    """Return {relative_path: sha256_hex} for every protected file.

    Path keys are relative to ``src/aria/`` and use forward slashes
    so the manifest is platform-agnostic.
    """
    pkg_root = pkg_root or _aria_pkg_root()
    out: Dict[str, str] = {}
    for p in _enumerate_protected_files(pkg_root):
        rel = p.relative_to(pkg_root).as_posix()
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _default_manifest_path() -> Path:
    env = os.environ.get("ARIA_BOOT_MANIFEST")
    if env:
        return Path(env).resolve()
    pkg_root = _aria_pkg_root()
    return (pkg_root.parents[1] / "data" / "sealed" / "BOOT_MANIFEST.toml").resolve()


def _parse_boot_manifest(text: str) -> Dict[str, str]:
    """Parse the same minimal-TOML subset used by sealed_prompt."""
    out: Dict[str, str] = {}
    current: str | None = None
    pending: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[files."):
            inner = line[len("[files."):].rstrip("]").strip().strip('"')
            current = inner
            pending = {}
            continue
        if line.startswith("[") and line.endswith("]"):
            current = None
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"')
        if current is not None:
            pending[k] = v
            if "sha256" in pending:
                out[current] = pending["sha256"].lower()
    return out


def _default_rescue_manifest_path() -> Path:
    """Recovery audit R-19: rescue manifest at sealed/RESCUE_MANIFEST.toml.

    Covers a minimal trusted computing base (CommsAgent beacon path,
    safe_mode, kill_switch, ground_deadman, monitor heartbeat).  When
    the primary manifest fails verification we attempt rescue
    verification — if it passes we boot a beacon-only image rather
    than aborting outright.
    """
    pkg_root = _aria_pkg_root()
    return (pkg_root.parents[1] / "data" / "sealed" / "RESCUE_MANIFEST.toml").resolve()


def verify_boot_integrity(
    manifest_path: Optional[Path] = None,
    strict: bool = True,
    *,
    skip_if_missing: bool = True,
    allow_rescue: bool = True,
) -> bool:
    """Recompute hashes of every protected file and compare.

    Args:
        manifest_path: override the BOOT_MANIFEST.toml location.
        strict: when True (default), failures call sys.exit(87).
            Tests pass False to inspect the failure.
        skip_if_missing: when True (default), absence of the manifest
            is logged as a warning but does NOT abort. The manifest
            is generated at release time; in development trees we
            don't always have one. Production deployments must set
            this False (or equivalently ship a manifest) so a missing
            manifest is itself an integrity failure.
        allow_rescue: Recovery audit R-19 — when True, a primary
            manifest failure falls through to verifying the rescue
            manifest.  Caller checks ``data/runtime/boot.rescue`` to
            decide whether to come up in beacon-only mode.

    Returns:
        True on success.
    """
    manifest_path = manifest_path or _default_manifest_path()
    if not manifest_path.is_file():
        msg = f"boot manifest not found at {manifest_path}"
        if skip_if_missing:
            logger.warning("boot_verify.manifest_missing",
                           path=str(manifest_path),
                           note="dev-only path; production must ship a manifest")
            return True
        if strict:
            sys.stderr.write(f"[ARIA] {msg}\n")
            sys.exit(BOOT_FAIL_EXIT)
        raise BootIntegrityError(msg)

    expected = _parse_boot_manifest(manifest_path.read_text())
    if not expected:
        msg = f"boot manifest empty: {manifest_path}"
        if strict:
            sys.stderr.write(f"[ARIA] {msg}\n")
            sys.exit(BOOT_FAIL_EXIT)
        raise BootIntegrityError(msg)

    actual = compute_manifest()

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatched = [
        rel for rel in expected
        if rel in actual and actual[rel] != expected[rel]
    ]

    if missing or mismatched:
        report = {
            "missing": missing[:5],
            "mismatched": mismatched[:5],
            "extra_count": len(extra),
            "missing_count": len(missing),
            "mismatched_count": len(mismatched),
        }
        logger.error("boot_verify.failed", **report)
        # Recovery audit R-19: try the rescue manifest before aborting.
        if allow_rescue and _try_rescue_manifest(actual):
            _mark_rescue_active()
            logger.error("boot_verify.rescue_manifest_active",
                         note="primary manifest failed; minimal beacon-mode boot")
            return True
        msg = (f"boot manifest verify FAILED: "
               f"{len(missing)} missing, {len(mismatched)} mismatched, "
               f"{len(extra)} unexpected. "
               f"See FAILSAFE_ARCHITECTURE.md §F-18.")
        if strict:
            sys.stderr.write(f"[ARIA] {msg}\n")
            sys.exit(BOOT_FAIL_EXIT)
        raise BootIntegrityError(msg)

    if extra:
        # Extras are *not* fatal — new files added since the manifest
        # was generated. But we log so they're visible in production.
        logger.info("boot_verify.extras", count=len(extra), sample=extra[:3])

    logger.info("boot_verify.ok",
                manifest_count=len(expected),
                actual_count=len(actual))
    # Clear any prior rescue marker so the next boot starts clean.
    _clear_rescue_marker()
    return True


def _try_rescue_manifest(actual: Dict[str, str]) -> bool:
    """Recovery audit R-19: verify the minimal rescue manifest.
    Returns True on success."""
    rescue_path = _default_rescue_manifest_path()
    if not rescue_path.is_file():
        logger.warning("boot_verify.rescue_manifest_missing",
                       path=str(rescue_path))
        return False
    try:
        rescue_expected = _parse_boot_manifest(rescue_path.read_text())
    except OSError as exc:
        logger.warning("boot_verify.rescue_manifest_unreadable",
                       error=str(exc))
        return False
    if not rescue_expected:
        return False
    missing = [k for k in rescue_expected if k not in actual]
    mismatched = [
        k for k in rescue_expected
        if k in actual and actual[k] != rescue_expected[k]
    ]
    if missing or mismatched:
        logger.error("boot_verify.rescue_manifest_failed",
                     missing=missing[:5], mismatched=mismatched[:5])
        return False
    return True


def _runtime_dir() -> Path:
    env = os.environ.get("ARIA_RUNTIME_DIR")
    if env:
        return Path(env)
    return _aria_pkg_root().parents[1] / "data" / "runtime"


def _mark_rescue_active() -> None:
    """Touch ``data/runtime/boot.rescue`` so the application can pick
    up the signal without re-verifying."""
    try:
        runtime = _runtime_dir()
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "boot.rescue").write_text(
            f"primary_manifest_failed_at={int(__import__('time').time())}\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("boot_verify.rescue_marker_failed", error=str(exc))


def _clear_rescue_marker() -> None:
    try:
        marker = _runtime_dir() / "boot.rescue"
        if marker.exists():
            marker.unlink()
    except OSError:
        pass


def is_rescue_mode_active() -> bool:
    """Recovery audit R-19: caller honours rescue mode by skipping
    cognitive engine + recovery library + non-essential agents."""
    try:
        return (_runtime_dir() / "boot.rescue").is_file()
    except OSError:
        return False


def render_manifest_toml(pkg_root: Optional[Path] = None) -> str:
    """Render the manifest as TOML text suitable for writing to
    data/sealed/BOOT_MANIFEST.toml. Used by the generate_manifest
    CLI at release time."""
    import time as _time
    out = []
    out.append("# ARIA boot integrity manifest (F-18). Do not hand-edit.")
    out.append("# Regenerate with: python -m aria.boot.generate_manifest")
    out.append("")
    out.append("manifest_version = 1")
    out.append(f"created_at       = \"{_time.strftime('%Y-%m-%d')}\"")
    out.append("algorithm        = \"sha256\"")
    out.append("")
    for rel, h in sorted(compute_manifest(pkg_root).items()):
        out.append(f"[files.\"{rel}\"]")
        out.append(f"sha256 = \"{h}\"")
        out.append("")
    return "\n".join(out)
