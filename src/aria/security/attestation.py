"""TPM 2.0 attestation + software-PCR fallback (R38 §1.3).

Goal — close the gap §F-18 leaves open: a field-service attacker
swapping the bootloader between flights produces a clean
``BOOT_MANIFEST.toml`` verify because the manifest itself was
re-signed.  Hardware-rooted attestation moves the trust anchor below
the firmware, so a swapped boot chain produces a quote that doesn't
match the sealed expected PCR set.

Two operating modes:

  ``TPMAttestor``      — talks to a real TPM 2.0 via ``tpm2-tools``
                         subprocesses (``tpm2_pcrread``, ``tpm2_quote``).
                         Requires /dev/tpm0 + tpm2_tools installed.
                         This is the production path on any flight CPU
                         that ships with a discrete TPM or fTPM.

  ``SoftwarePCRAttestor`` — software emulation that PCR-extends
                         spacecraft-relevant measurements (kernel,
                         bootloader, ARIA package tree).  Quote is
                         signed with an Ed25519 key generated at
                         install-time and stored under
                         ``data/runtime/attestation_key.pem`` (mode 0600).
                         Strictly weaker than a real TPM (the key lives
                         on disk) but still useful: it detects
                         offline tampering with any of the measured
                         components, and gives the operator a
                         constant-shape ``Quote`` blob to compare
                         against the sealed expected-PCR file.

Both modes produce the same :class:`Quote` shape so the upstream
ground attestation channel doesn't care which is in use.

References:
    NIST SP 800-193 §3.2 "Detection — Platform Firmware Resiliency";
    TCG TPM 2.0 Library Specification Part 1 §22 "Quote";
    Anderson & Kuhn (1996) "Tamper Resistance — A Cautionary Note".
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import structlog

logger = structlog.get_logger()


# Standard PCR layout we mirror in the software fallback.  Values are
# the conventional TCG assignments — see TCG PC Client Platform
# Firmware Profile §3.3.4.  We mirror the same indices so a future
# switch to a real TPM doesn't change the sealed expected-PCR file.
class PCRSlot(enum.IntEnum):
    FIRMWARE_CODE = 0
    FIRMWARE_CONFIG = 1
    OPTION_ROMS = 2
    KERNEL_AND_INITRD = 4
    BOOT_LOADER = 5
    ARIA_PACKAGE_TREE = 8        # ARIA-specific use of GPL-reserved slot
    ARIA_SEALED_CONTENT = 9      # ARIA-specific
    ARIA_RUNTIME_CONFIG = 10     # ARIA-specific


PCR_BANK = "sha256"   # SHA-256 is the only bank we support; SHA-1 is not safe.


# ── Quote dataclass ─────────────────────────────────────────────


@dataclass(frozen=True)
class Quote:
    """A signed PCR snapshot.  Format-stable across TPM and SoftwarePCR
    implementations so the ground checker doesn't have to branch."""
    schema_version: int
    timestamp: float
    nonce_hex: str
    pcr_bank: str
    pcrs: Dict[int, str]      # PCR index → hex digest (lower-case)
    quote_digest_hex: str     # SHA-256(canonical_pcrs || nonce)
    signature_hex: str        # Ed25519 over quote_digest_hex
    signer_pubkey_hex: str    # Ed25519 public key (hex, 64 chars)
    backend: str              # "tpm2" or "software_pcr"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "nonce_hex": self.nonce_hex,
            "pcr_bank": self.pcr_bank,
            "pcrs": {str(k): v for k, v in self.pcrs.items()},
            "quote_digest_hex": self.quote_digest_hex,
            "signature_hex": self.signature_hex,
            "signer_pubkey_hex": self.signer_pubkey_hex,
            "backend": self.backend,
            "notes": self.notes,
        }


def _canonical_pcr_blob(pcrs: Dict[int, str], nonce_hex: str) -> bytes:
    payload = {
        "bank": PCR_BANK,
        "pcrs": [
            {"index": int(i), "digest": pcrs[i]}
            for i in sorted(pcrs)
        ],
        "nonce": nonce_hex,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


# ── Software PCR ────────────────────────────────────────────────


def _pcr_extend(current_hex: str, new_data: bytes) -> str:
    """SHA-256 PCR-extend: new = sha256(current || sha256(data))."""
    cur = bytes.fromhex(current_hex)
    inner = hashlib.sha256(new_data).digest()
    return hashlib.sha256(cur + inner).hexdigest()


def _hash_path(p: Path) -> bytes:
    """SHA-256 of a file's contents.  Empty bytes if missing."""
    if not p.is_file():
        return b""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.digest()


def _hash_tree(root: Path, exclude: Sequence[str] = ()) -> bytes:
    """Stable hash of an entire tree (file paths + contents).

    Walks lexicographically, includes path bytes so a rename is
    detected.  Returns SHA-256 of the concatenation.

    ``exclude`` lists relative paths (POSIX form) that must be skipped.
    Used to avoid the chicken-and-egg loop where the sealed-content
    PCR includes ``EXPECTED_PCRS.toml`` which itself contains that PCR.
    """
    if not root.is_dir():
        return b""
    skip = set(exclude or ())
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(root).as_posix()
        if rel in skip:
            continue
        h.update(b"P:" + rel.encode() + b"\x00")
        h.update(b"H:" + _hash_path(p) + b"\x00")
    return h.digest()


class SoftwarePCRAttestor:
    """In-process TPM emulator.  Strictly weaker than hardware (the
    signing key lives on disk) but produces identical-shape quotes."""

    SCHEMA_VERSION = 1
    GENESIS = "0" * 64
    BACKEND = "software_pcr"

    def __init__(
        self,
        key_path: Optional[Path] = None,
        kernel_paths: Optional[Sequence[Path]] = None,
        bootloader_paths: Optional[Sequence[Path]] = None,
        aria_pkg_root: Optional[Path] = None,
        sealed_root: Optional[Path] = None,
        runtime_config_paths: Optional[Sequence[Path]] = None,
    ) -> None:
        self._key_path = key_path or _default_key_path()
        # PCR-source mappings.  Production wires real /boot artefacts;
        # tests inject fake paths.  Missing paths are tolerated (they
        # extend with empty data, producing a deterministic GENESIS-only
        # sequence the ground side recognises as 'no firmware
        # measurement available').
        self._kernel_paths = list(kernel_paths or [])
        self._bootloader_paths = list(bootloader_paths or [])
        self._aria_pkg_root = aria_pkg_root
        self._sealed_root = sealed_root
        self._runtime_config_paths = list(runtime_config_paths or [])
        self._lock = threading.Lock()
        self._signer = _load_or_generate_key(self._key_path)

    # ── PCR computation ────────────────────────────────────────

    def read_pcrs(self) -> Dict[int, str]:
        """Replay the measured-boot extends from disk, returning the
        current PCR set.  This is deterministic given the same on-disk
        artefacts, so any tamper changes the result."""
        pcrs: Dict[int, str] = {slot: self.GENESIS for slot in PCRSlot}

        # PCR 0 / 1 — firmware code + config.  We don't ship firmware,
        # so leave at GENESIS unless an out-of-tree extender wants to
        # populate them.  PCR 4 — kernel + initrd.
        for p in self._kernel_paths:
            digest = _hash_path(p)
            if digest:
                pcrs[PCRSlot.KERNEL_AND_INITRD] = _pcr_extend(
                    pcrs[PCRSlot.KERNEL_AND_INITRD], digest,
                )
        # PCR 5 — bootloader.
        for p in self._bootloader_paths:
            digest = _hash_path(p)
            if digest:
                pcrs[PCRSlot.BOOT_LOADER] = _pcr_extend(
                    pcrs[PCRSlot.BOOT_LOADER], digest,
                )
        # PCR 8 — ARIA package tree.  Uses _hash_tree (ordered), so a
        # rename / new file / modified line all flip the digest.
        if self._aria_pkg_root is not None:
            tree_digest = _hash_tree(self._aria_pkg_root)
            if tree_digest:
                pcrs[PCRSlot.ARIA_PACKAGE_TREE] = _pcr_extend(
                    pcrs[PCRSlot.ARIA_PACKAGE_TREE], tree_digest,
                )
        # PCR 9 — sealed content (constitution, principals, BOOT_MANIFEST).
        # Excludes EXPECTED_PCRS.toml to avoid the self-reference loop:
        # that file contains the PCR digest the runtime is computing.
        if self._sealed_root is not None:
            sealed_digest = _hash_tree(
                self._sealed_root, exclude=("EXPECTED_PCRS.toml",),
            )
            if sealed_digest:
                pcrs[PCRSlot.ARIA_SEALED_CONTENT] = _pcr_extend(
                    pcrs[PCRSlot.ARIA_SEALED_CONTENT], sealed_digest,
                )
        # PCR 10 — runtime config (aria.yaml + any operator overlays).
        for p in self._runtime_config_paths:
            digest = _hash_path(p)
            if digest:
                pcrs[PCRSlot.ARIA_RUNTIME_CONFIG] = _pcr_extend(
                    pcrs[PCRSlot.ARIA_RUNTIME_CONFIG], digest,
                )
        return {int(k): v for k, v in pcrs.items()}

    # ── Quote generation ───────────────────────────────────────

    def quote(self, nonce_hex: str) -> Quote:
        with self._lock:
            pcrs = self.read_pcrs()
            blob = _canonical_pcr_blob(pcrs, nonce_hex)
            digest = hashlib.sha256(blob).hexdigest()
            sig = self._signer.sign_hex(digest)
            return Quote(
                schema_version=self.SCHEMA_VERSION,
                timestamp=time.time(),
                nonce_hex=nonce_hex,
                pcr_bank=PCR_BANK,
                pcrs=pcrs,
                quote_digest_hex=digest,
                signature_hex=sig,
                signer_pubkey_hex=self._signer.pubkey_hex,
                backend=self.BACKEND,
                notes="software_pcr — disk-stored signing key; weaker than TPM",
            )


# ── TPM 2.0 backend (real hardware) ──────────────────────────────


class TPMAttestor:
    """Production path — uses tpm2-tools to talk to /dev/tpm0.

    Detection: ``shutil.which('tpm2_pcrread')`` and the existence of
    ``/dev/tpm0`` (or /dev/tpmrm0).  If either is missing the
    constructor raises and the caller falls back to SoftwarePCRAttestor.
    """

    SCHEMA_VERSION = 1
    BACKEND = "tpm2"
    DEFAULT_PCR_INDICES = (0, 1, 2, 4, 5, 7, 8, 9, 10)

    def __init__(
        self,
        pcr_indices: Sequence[int] = DEFAULT_PCR_INDICES,
        signer: Optional["Ed25519Signer"] = None,
    ) -> None:
        self._pcr_indices = sorted(set(pcr_indices))
        # We sign the canonicalised PCR set with a software key.  A
        # real attestation key (AK) bound to the TPM would be stronger
        # but requires the platform to provision one; that's a Tier-4
        # partner item.  For the R38 acceptance we're satisfied with
        # "the PCRs themselves came from the TPM."
        self._signer = signer or _load_or_generate_key(_default_key_path())
        self._verify_environment()

    @staticmethod
    def is_available() -> bool:
        if shutil.which("tpm2_pcrread") is None:
            return False
        if not (Path("/dev/tpm0").exists() or Path("/dev/tpmrm0").exists()):
            return False
        return True

    def _verify_environment(self) -> None:
        if not self.is_available():
            raise RuntimeError(
                "TPM 2.0 not available: tpm2_pcrread missing or "
                "/dev/tpm[rm]0 not present"
            )

    def read_pcrs(self) -> Dict[int, str]:
        # tpm2_pcrread sha256:0,1,2,4,5,7,8,9,10
        sel = f"{PCR_BANK}:" + ",".join(str(i) for i in self._pcr_indices)
        try:
            out = subprocess.check_output(
                ["tpm2_pcrread", sel],
                stderr=subprocess.STDOUT, timeout=5.0,
            ).decode()
        except (subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"tpm2_pcrread failed: {exc}") from exc
        return _parse_tpm2_pcrread(out, self._pcr_indices)

    def quote(self, nonce_hex: str) -> Quote:
        pcrs = self.read_pcrs()
        blob = _canonical_pcr_blob(pcrs, nonce_hex)
        digest = hashlib.sha256(blob).hexdigest()
        sig = self._signer.sign_hex(digest)
        return Quote(
            schema_version=self.SCHEMA_VERSION,
            timestamp=time.time(),
            nonce_hex=nonce_hex,
            pcr_bank=PCR_BANK,
            pcrs=pcrs,
            quote_digest_hex=digest,
            signature_hex=sig,
            signer_pubkey_hex=self._signer.pubkey_hex,
            backend=self.BACKEND,
            notes="tpm2 — PCRs read from /dev/tpm[rm]0",
        )


def _parse_tpm2_pcrread(out: str, indices: Sequence[int]) -> Dict[int, str]:
    """Parse `tpm2_pcrread sha256:0,1,...` output.  Tolerates both the
    table format and the YAML-ish format depending on tpm2_tools
    version."""
    pcrs: Dict[int, str] = {}
    for raw in out.splitlines():
        line = raw.strip().lstrip("|").strip()
        if not line:
            continue
        # YAML-ish line: "  0  : 0xABCD..." or "  0 : ABCD..."
        # also tolerate "0  :  0xABC"
        if ":" not in line:
            continue
        idx_str, val_str = line.split(":", 1)
        idx_str = idx_str.strip()
        val_str = val_str.strip().lower()
        if val_str.startswith("0x"):
            val_str = val_str[2:]
        if not idx_str.isdigit():
            continue
        idx = int(idx_str)
        if idx not in indices:
            continue
        if all(c in "0123456789abcdef" for c in val_str) and len(val_str) == 64:
            pcrs[idx] = val_str
    if not pcrs:
        raise RuntimeError(
            f"tpm2_pcrread output not parseable: {out[:300]!r}"
        )
    return pcrs


# ── Verification ────────────────────────────────────────────────


@dataclass
class VerifyResult:
    ok: bool
    reason: str = ""
    mismatches: Dict[int, Tuple[str, str]] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


def verify_quote_signature(quote: Quote) -> bool:
    """Re-derive the canonical blob and Ed25519-verify the signature."""
    blob = _canonical_pcr_blob(quote.pcrs, quote.nonce_hex)
    digest = hashlib.sha256(blob).hexdigest()
    if digest != quote.quote_digest_hex:
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        from cryptography.exceptions import InvalidSignature
        pub = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(quote.signer_pubkey_hex),
        )
        pub.verify(
            bytes.fromhex(quote.signature_hex),
            quote.quote_digest_hex.encode(),
        )
        return True
    except Exception:
        return False


def verify_quote_against_expected(
    quote: Quote,
    expected_pcrs: Dict[int, str],
    nonce_hex: str,
) -> VerifyResult:
    """Compare the freshly-quoted PCRs to the sealed expected set.

    Verifies in order:
      1. nonce match (replay protection),
      2. signature valid (chain-of-custody),
      3. every expected PCR matches.

    Any mismatch returns a populated VerifyResult with the offending
    indices so the ground checker can report a precise diff.
    """
    if quote.nonce_hex != nonce_hex:
        return VerifyResult(False, reason=(
            f"nonce mismatch: quote {quote.nonce_hex[:16]}… vs "
            f"expected {nonce_hex[:16]}…"
        ))
    if not verify_quote_signature(quote):
        return VerifyResult(False, reason="signature invalid")
    mismatches: Dict[int, Tuple[str, str]] = {}
    for idx, exp in expected_pcrs.items():
        actual = quote.pcrs.get(int(idx))
        if actual is None:
            mismatches[idx] = ("(absent)", exp)
        elif actual.lower() != exp.lower():
            mismatches[idx] = (actual, exp)
    if mismatches:
        return VerifyResult(False, reason=(
            f"{len(mismatches)} PCR(s) mismatched"
        ), mismatches=mismatches)
    return VerifyResult(True, reason="all PCRs match expected")


# ── Ed25519 signer (disk-stored key) ────────────────────────────


def _default_key_path() -> Path:
    here = Path(__file__).resolve()
    return (here.parents[3] / "data" / "runtime" / "attestation_key.pem")


class Ed25519Signer:
    """Wrapper that holds an Ed25519 private key + caches the hex public."""

    def __init__(self, key_bytes: bytes) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        self._priv = Ed25519PrivateKey.from_private_bytes(key_bytes)
        self.pubkey_hex = (
            self._priv.public_key()
            .public_bytes_raw()
            .hex()
        )

    def sign_hex(self, message: str) -> str:
        return self._priv.sign(message.encode()).hex()


def _load_or_generate_key(path: Path) -> Ed25519Signer:
    """Load an Ed25519 key from ``path``; generate + persist if missing.

    File mode 0600 — only the runtime user should read the key.  A
    real flight build would replace this with a TPM-bound AK; this
    implementation matches the docstring promise: 'strictly weaker
    than a real TPM'."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    path = Path(path)
    if path.is_file():
        try:
            raw = path.read_bytes()
            return Ed25519Signer(raw)
        except Exception as exc:
            logger.warning("attestation.key_load_failed",
                           path=str(path), error=str(exc))
    # Generate fresh.
    path.parent.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes_raw()
    path.write_bytes(raw)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    logger.info("attestation.key_generated", path=str(path))
    return Ed25519Signer(raw)


# ── High-level entry point ──────────────────────────────────────


def get_attestor(
    *,
    prefer_tpm: bool = True,
    aria_pkg_root: Optional[Path] = None,
    sealed_root: Optional[Path] = None,
) -> Any:
    """Return TPMAttestor if hardware is available, else SoftwarePCRAttestor."""
    if prefer_tpm and TPMAttestor.is_available():
        try:
            return TPMAttestor()
        except Exception as exc:
            logger.warning("attestation.tpm_init_failed",
                           error=str(exc),
                           note="falling back to software PCR")
    return SoftwarePCRAttestor(
        aria_pkg_root=aria_pkg_root,
        sealed_root=sealed_root,
    )


def parse_expected_pcrs(toml_path: Path) -> Dict[int, str]:
    """Read ``data/sealed/EXPECTED_PCRS.toml``.  Returns {index: digest}.

    Tolerant of trailing-comment headers like ``[pcrs."4"]   # KERNEL``
    so the captured-baseline form (with inline slot names) parses the
    same as the bare form."""
    out: Dict[int, str] = {}
    if not toml_path.is_file():
        return out
    current: Optional[int] = None
    for raw in toml_path.read_text().splitlines():
        # Strip inline comments first (TOML allows them after values).
        if "#" in raw:
            in_str = False
            cut = -1
            for i, ch in enumerate(raw):
                if ch == '"':
                    in_str = not in_str
                elif ch == "#" and not in_str:
                    cut = i
                    break
            if cut >= 0:
                raw = raw[:cut]
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[pcrs."):
            inner = line[len("[pcrs."):].rstrip("]").strip().strip('"')
            try:
                current = int(inner)
            except ValueError:
                current = None
            continue
        if line.startswith("[") and line.endswith("]"):
            current = None
            continue
        if "=" not in line or current is None:
            continue
        k, v = line.split("=", 1)
        if k.strip() == "sha256":
            digest = v.strip().strip('"').lower()
            # Skip GENESIS placeholder entries (firmware not measured
            # in dev environments).  They'd produce false-mismatch
            # alarms when an actual TPM is later wired in.
            if digest != "0" * 64:
                out[current] = digest
    return out
