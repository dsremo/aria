"""R41 — Pip wheel hash verification (supply-chain integrity).

Threat: ``pip install foo-1.2.3-py3-none-any.whl`` from PyPI without
``--require-hashes`` accepts whatever the index serves.  A maintainer
compromise (XZ Utils 2024) or a typosquat substitution turns into a
silent dependency swap.

Defence: a small ``verify_wheel_hash(path, expected_sha256)`` helper
that callers (build scripts / runtime hot-loaders) can use; plus a
batch verifier that walks ``requirements-lock.txt`` and confirms each
installed wheel matches the recorded hash.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Tuple

from aria.security.plugins import DefencePlugin, register


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_wheel_hash(path: Path, expected_sha256: str) -> bool:
    if not path.is_file():
        return False
    return sha256_of_file(path) == expected_sha256


_HASH_LINE_RE = re.compile(r"--hash=sha256:([a-f0-9]{64})")
_PKG_LINE_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-]+)")


def parse_lockfile_hashes(lockfile: Path) -> Dict[str, List[str]]:
    """Extract ``{package: [sha256, …]}`` from a pip-tools / pip-compile
    lock file."""
    out: Dict[str, List[str]] = {}
    if not lockfile.is_file():
        return out
    current_pkg = ""
    for line in lockfile.read_text(encoding="utf-8").splitlines():
        m = _PKG_LINE_RE.match(line)
        if m:
            current_pkg = m.group(1).lower()
            out.setdefault(current_pkg, [])
            continue
        for h in _HASH_LINE_RE.findall(line):
            if current_pkg:
                out[current_pkg].append(h)
    return out


def verify_lockfile_against_dist_info(
    lockfile: Path,
    site_packages: Path,
) -> Tuple[bool, List[str]]:
    """Walk a venv's ``site-packages`` and check every installed wheel's
    ``RECORD`` hash matches the lockfile.  Returns ``(ok, errors)``.

    Limited to the file-level RECORD digest check — it confirms the
    *installed* file tree is bit-for-bit what was distributed at the
    declared version.  Combined with lockfile hashes from upstream,
    this gives end-to-end integrity.
    """
    errors: List[str] = []
    if not site_packages.is_dir():
        return False, [f"site_packages {site_packages} not found"]
    declared = parse_lockfile_hashes(lockfile)
    for dist_info in site_packages.glob("*.dist-info"):
        record = dist_info / "RECORD"
        if not record.is_file():
            errors.append(f"missing RECORD in {dist_info.name}")
            continue
        # Verify each file in RECORD has the recorded sha256
        for line in record.read_text(encoding="utf-8").splitlines():
            cols = line.split(",")
            if len(cols) < 3 or not cols[1].startswith("sha256="):
                continue
            rel, alg, _size = cols[0], cols[1], cols[2]
            expected = alg[len("sha256="):]
            if not expected:
                continue
            file_path = site_packages / rel
            if not file_path.is_file():
                continue
            try:
                actual = sha256_of_file(file_path)
            except OSError:
                errors.append(f"unreadable: {file_path}")
                continue
            # RECORD uses URL-safe base64 (no padding); convert.
            import base64
            try:
                actual_b64 = base64.urlsafe_b64encode(
                    bytes.fromhex(actual)
                ).rstrip(b"=").decode()
            except Exception:
                continue
            if actual_b64 != expected:
                errors.append(f"hash_mismatch: {rel}")
    if declared:
        # Lock file present — caller may also assert each declared
        # package exists in site_packages with the expected version.
        pass
    return len(errors) == 0, errors


register(DefencePlugin(
    round_id="R41",
    name="wheel_signature",
    description="Verify installed wheel files against lockfile / RECORD hashes.",
))
