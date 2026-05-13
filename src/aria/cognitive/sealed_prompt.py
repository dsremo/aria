"""Sealed system prompt + constitution loader.

Implements §F-1 of docs/FAILSAFE_ARCHITECTURE.md.

At process start, this module:
  1. Reads `data/sealed/MANIFEST.toml` (genesis → list of (path, sha256)).
  2. Hashes every listed file from disk and compares to the manifest.
  3. Loads the system-prompt + constitution into frozen in-memory
     containers (``types.MappingProxyType``); mutation attempts raise.
  4. Returns ``SealedContent`` accessor; the cognitive engine reads
     prompt + constitution through it and never touches the files.

If any hash mismatches, boot fails: the process logs
``boot.sealed_prompt.failed`` and exits with status 86.

If the manifest itself is missing or unparseable, boot fails the
same way. Fail-safe, not fail-open (per §0 design principle 8 of the
architecture doc).

Threats addressed: T-I-4 (prompt extraction), T-II-4 (self-modifying
code), T-VI-1 (flash chip swap), T-VII-1 (cosmic-ray bit flip).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import structlog

logger = structlog.get_logger()


# Locating the sealed/ directory. In production this is mounted
# read-only at a fixed path; in tests + dev we resolve relative to the
# package root. ARIA_SEALED_DIR overrides for ground-test rigs.
def _default_sealed_dir() -> Path:
    env = os.environ.get("ARIA_SEALED_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    # src/aria/cognitive/sealed_prompt.py → repo root via parents[3]
    return (here.parents[3] / "data" / "sealed").resolve()


# Exit code for sealed-content failures. Distinct from generic 1 so the
# operator can tell at a glance "this was a security boot abort," not a
# Python exception.
SEALED_BOOT_FAIL_EXIT = 86


# ── Parsed manifest ────────────────────────────────────────────────


@dataclass(frozen=True)
class _ManifestEntry:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class SealedContent:
    """Frozen accessor for the boot-verified sealed content."""

    system_prompt: str
    constitution: Mapping[str, Any]   # MappingProxyType — write-protected
    manifest_version: int
    sealed_dir: Path

    @property
    def constitution_version(self) -> int:
        return int(self.constitution.get("version", 0))

    def forbidden_actions(self) -> tuple[str, ...]:
        return tuple(
            entry.get("action", "")
            for entry in self.constitution.get("forbidden_actions", [])
            if entry.get("action")
        )

    def gated_action(self, action: str) -> Mapping[str, Any] | None:
        for entry in self.constitution.get("gated_actions", []):
            if entry.get("action") == action:
                return types.MappingProxyType(dict(entry))
        return None

    def resource_ceiling(self, resource: str) -> Mapping[str, Any] | None:
        for entry in self.constitution.get("resource_ceilings", []):
            if entry.get("resource") == resource:
                return types.MappingProxyType(dict(entry))
        return None


class SealedContentError(RuntimeError):
    """Raised on any sealed-content integrity failure.

    The default verify_and_load() handler turns this into a process-
    exit so the spacecraft doesn't keep running with a broken trust
    chain. Tests that *want* to inspect the failure call
    verify_and_load(strict=False).
    """


# ── Manifest parsing (no external TOML dep on Py<3.11) ──────────────


def _parse_manifest(text: str) -> tuple[int, list[_ManifestEntry]]:
    """Parse the small subset of TOML used by MANIFEST.toml.

    The manifest is intentionally minimal so we don't have to depend
    on a TOML library at boot. Recognised forms:

        manifest_version = 1
        algorithm        = "sha256"
        [files."<name>"]
        sha256     = "<hex>"
        size_bytes = <int>

    Anything else is ignored. This keeps the boot path tiny and the
    failure mode predictable.
    """
    version = 0
    entries: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[files."):
            # [files."system_prompt.v1.txt"]
            inner = line[len("[files."):].rstrip("]").strip().strip('"')
            current = inner
            entries.setdefault(current, {})
            continue
        if line.startswith("[") and line.endswith("]"):
            current = None
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"')
        if current is None:
            if k == "manifest_version":
                try:
                    version = int(v)
                except ValueError:
                    pass
        else:
            entries[current][k] = v
    out: list[_ManifestEntry] = []
    for name, fields in entries.items():
        try:
            size = int(fields.get("size_bytes", "0"))
        except ValueError:
            size = 0
        out.append(_ManifestEntry(
            relative_path=name,
            sha256=fields.get("sha256", "").lower(),
            size_bytes=size,
        ))
    return version, out


# ── Public verification entrypoint ─────────────────────────────────


def verify_and_load(sealed_dir: Path | None = None,
                    strict: bool = True) -> SealedContent:
    """Verify the sealed manifest and return the frozen content.

    Args:
        sealed_dir: override directory (else resolved from
            ``ARIA_SEALED_DIR`` or the package default).
        strict: when True (default), boot-fatal errors raise
            ``SealedContentError`` AFTER calling sys.exit.
            Tests pass False to inspect the failure.

    Raises:
        SealedContentError: if any check fails and ``strict=False``.
        SystemExit: with code 86 if any check fails and ``strict=True``.
    """
    sealed_dir = sealed_dir or _default_sealed_dir()
    manifest_path = sealed_dir / "MANIFEST.toml"

    def _abort(reason: str, **fields: Any) -> SealedContent:
        logger.error("boot.sealed_prompt.failed",
                     reason=reason, sealed_dir=str(sealed_dir), **fields)
        if strict:
            sys.stderr.write(
                f"\n[ARIA] Sealed-content verification failed: {reason}.\n"
                f"[ARIA] Refusing to start. See FAILSAFE_ARCHITECTURE.md §F-1.\n",
            )
            sys.exit(SEALED_BOOT_FAIL_EXIT)
        raise SealedContentError(reason)

    if not manifest_path.is_file():
        return _abort(f"manifest not found at {manifest_path}")
    try:
        version, entries = _parse_manifest(manifest_path.read_text())
    except Exception as exc:
        return _abort(f"manifest unparseable: {exc}")

    if version <= 0 or not entries:
        return _abort("manifest empty or version invalid")

    # Hash every listed file.
    actual_hashes: dict[str, str] = {}
    for entry in entries:
        path = sealed_dir / entry.relative_path
        if not path.is_file():
            return _abort(f"sealed file missing: {entry.relative_path}")
        size = path.stat().st_size
        if entry.size_bytes and size != entry.size_bytes:
            return _abort(
                f"size mismatch for {entry.relative_path}",
                expected=entry.size_bytes, actual=size,
            )
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        if h != entry.sha256:
            return _abort(
                f"sha256 mismatch for {entry.relative_path}",
                expected=entry.sha256[:16], actual=h[:16],
            )
        actual_hashes[entry.relative_path] = h

    # Look up the two well-known files we always need.
    prompt_name = next(
        (e.relative_path for e in entries
         if e.relative_path.startswith("system_prompt")),
        None,
    )
    constitution_name = next(
        (e.relative_path for e in entries
         if e.relative_path.startswith("constitution")),
        None,
    )
    if not prompt_name or not constitution_name:
        return _abort("manifest missing system_prompt or constitution entry")

    prompt_text = (sealed_dir / prompt_name).read_text()
    try:
        const_raw = json.loads((sealed_dir / constitution_name).read_text())
    except Exception as exc:
        return _abort(f"constitution unparseable: {exc}")

    if not isinstance(const_raw, dict):
        return _abort("constitution root must be a JSON object")

    # Freeze the constitution. MappingProxyType only freezes the top
    # level; we wrap nested dicts/lists so a malicious caller can't
    # mutate ``const.forbidden_actions[0]['action'] = ...``.
    frozen = _deep_freeze(const_raw)
    if not isinstance(frozen, types.MappingProxyType):
        return _abort("constitution failed to freeze")

    logger.info("boot.sealed_prompt.verified",
                manifest_version=version,
                files=len(entries),
                prompt_hash=actual_hashes[prompt_name][:16],
                constitution_hash=actual_hashes[constitution_name][:16])

    return SealedContent(
        system_prompt=prompt_text,
        constitution=frozen,
        manifest_version=version,
        sealed_dir=sealed_dir,
    )


# ── Helpers ────────────────────────────────────────────────────────


def _deep_freeze(obj: Any) -> Any:
    """Recursively wrap dicts as MappingProxyType, lists as tuples."""
    if isinstance(obj, dict):
        return types.MappingProxyType({k: _deep_freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_deep_freeze(v) for v in obj)
    return obj


# Process-wide singleton — the cognitive engine reads through this.
_LOADED: SealedContent | None = None


def get_sealed() -> SealedContent:
    """Return the verified sealed content, loading once on first call."""
    global _LOADED
    if _LOADED is None:
        _LOADED = verify_and_load()
    return _LOADED


def reset_for_test() -> None:
    """Clear the singleton — only for tests."""
    global _LOADED
    _LOADED = None
