"""R38 — TPM 2.0 attestation + software-PCR fallback tests.

Acceptance §1.3:
  * Attestor produces a signed quote with a stable shape across
    backends (tpm2 / software_pcr).
  * Quote signature verifies.
  * Mismatch against sealed expected PCRs is detected with offending
    indices reported.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict

import pytest

from aria.security import attestation as att


# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def measured_boot(tmp_path):
    """Build a fake boot environment: kernel, bootloader, aria pkg
    root, sealed content, runtime config."""
    kernel = tmp_path / "boot" / "vmlinuz"
    initrd = tmp_path / "boot" / "initrd.img"
    bootloader = tmp_path / "boot" / "grub.cfg"
    pkg_root = tmp_path / "aria_pkg"
    sealed_root = tmp_path / "sealed"
    runtime_cfg = tmp_path / "configs" / "aria.yaml"

    for p, data in [
        (kernel, b"kernel-bytes-v1"),
        (initrd, b"initrd-bytes-v1"),
        (bootloader, b"set timeout=5"),
        (pkg_root / "cognitive" / "engine.py", b"x = 1\n"),
        (pkg_root / "safety" / "kill_switch.py", b"y = 2\n"),
        (sealed_root / "constitution.v1.json", b'{"ver":1}'),
        (runtime_cfg, b"mission: nominal\n"),
    ]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    return {
        "kernel_paths": [kernel, initrd],
        "bootloader_paths": [bootloader],
        "aria_pkg_root": pkg_root,
        "sealed_root": sealed_root,
        "runtime_config_paths": [runtime_cfg],
    }


@pytest.fixture
def attestor(tmp_path, measured_boot):
    key = tmp_path / "key.pem"
    return att.SoftwarePCRAttestor(
        key_path=key,
        **measured_boot,
    )


# ── Software PCR ────────────────────────────────────────────────


class TestSoftwarePCR:
    def test_pcrs_have_expected_indices(self, attestor):
        pcrs = attestor.read_pcrs()
        # Every PCRSlot must appear (some may be GENESIS).
        for slot in att.PCRSlot:
            assert int(slot) in pcrs

    def test_kernel_change_flips_pcr_4(self, attestor, measured_boot):
        first = attestor.read_pcrs()
        # Tamper with kernel.
        Path(measured_boot["kernel_paths"][0]).write_bytes(b"kernel-bytes-v2")
        second = attestor.read_pcrs()
        assert (
            first[int(att.PCRSlot.KERNEL_AND_INITRD)]
            != second[int(att.PCRSlot.KERNEL_AND_INITRD)]
        )

    def test_pkg_tree_change_flips_pcr_8(self, attestor, measured_boot):
        first = attestor.read_pcrs()
        (measured_boot["aria_pkg_root"] / "cognitive" / "engine.py").write_bytes(
            b"x = 999  # tampered\n"
        )
        second = attestor.read_pcrs()
        assert (
            first[int(att.PCRSlot.ARIA_PACKAGE_TREE)]
            != second[int(att.PCRSlot.ARIA_PACKAGE_TREE)]
        )

    def test_other_pcrs_unchanged_on_pkg_tamper(self, attestor, measured_boot):
        """A package-tree tamper flips PCR 8 but leaves PCR 4
        (kernel) and PCR 5 (bootloader) alone — the ground checker
        can isolate where the tamper landed."""
        first = attestor.read_pcrs()
        (measured_boot["aria_pkg_root"] / "cognitive" / "engine.py").write_bytes(
            b"x = 999\n"
        )
        second = attestor.read_pcrs()
        assert (first[int(att.PCRSlot.KERNEL_AND_INITRD)]
                == second[int(att.PCRSlot.KERNEL_AND_INITRD)])
        assert (first[int(att.PCRSlot.BOOT_LOADER)]
                == second[int(att.PCRSlot.BOOT_LOADER)])

    def test_quote_signature_verifies(self, attestor):
        nonce = "deadbeef" * 8
        q = attestor.quote(nonce)
        assert q.backend == "software_pcr"
        assert q.nonce_hex == nonce
        assert att.verify_quote_signature(q) is True

    def test_quote_signature_fails_on_tamper(self, attestor):
        q = attestor.quote("ab" * 32)
        # Mutate one PCR digest in the quote — this should invalidate
        # the digest_hex check inside verify_quote_signature.
        bad_pcrs = dict(q.pcrs)
        bad_pcrs[int(att.PCRSlot.ARIA_PACKAGE_TREE)] = "00" * 32
        bad = att.Quote(
            schema_version=q.schema_version,
            timestamp=q.timestamp,
            nonce_hex=q.nonce_hex,
            pcr_bank=q.pcr_bank,
            pcrs=bad_pcrs,
            quote_digest_hex=q.quote_digest_hex,    # untouched -> mismatch
            signature_hex=q.signature_hex,
            signer_pubkey_hex=q.signer_pubkey_hex,
            backend=q.backend,
        )
        assert att.verify_quote_signature(bad) is False

    def test_key_file_persists_and_reuses(self, tmp_path, measured_boot):
        key = tmp_path / "k.pem"
        a1 = att.SoftwarePCRAttestor(key_path=key, **measured_boot)
        a2 = att.SoftwarePCRAttestor(key_path=key, **measured_boot)
        # Same key file → same pubkey hex → cross-instance verification
        # of a1's quote by a2's key works.
        q = a1.quote("00" * 32)
        assert q.signer_pubkey_hex == a2._signer.pubkey_hex


class TestVerifyAgainstExpected:
    def test_matching_pcrs_pass(self, attestor):
        q = attestor.quote("11" * 32)
        expected = dict(q.pcrs)
        result = att.verify_quote_against_expected(q, expected, "11" * 32)
        assert result.ok is True
        assert not result.mismatches

    def test_nonce_mismatch_fails(self, attestor):
        q = attestor.quote("aa" * 32)
        result = att.verify_quote_against_expected(q, dict(q.pcrs), "bb" * 32)
        assert result.ok is False
        assert "nonce" in result.reason

    def test_pcr_mismatch_reported_per_index(self, attestor, measured_boot):
        q = attestor.quote("cd" * 32)
        # Simulate operator's sealed expected baseline = original PCRs.
        expected = dict(q.pcrs)
        # Now tamper the kernel and re-quote.  The quote's PCR 4
        # diverges; the function must list index 4 in mismatches.
        Path(measured_boot["kernel_paths"][0]).write_bytes(b"swapped-kernel")
        new_q = attestor.quote("cd" * 32)
        result = att.verify_quote_against_expected(new_q, expected, "cd" * 32)
        assert result.ok is False
        assert int(att.PCRSlot.KERNEL_AND_INITRD) in result.mismatches

    def test_signature_mismatch_caught(self, attestor):
        q = attestor.quote("dd" * 32)
        # Replace signature with garbage; verification must fail before
        # PCR comparison happens.
        bad_sig_q = att.Quote(
            schema_version=q.schema_version,
            timestamp=q.timestamp,
            nonce_hex=q.nonce_hex,
            pcr_bank=q.pcr_bank,
            pcrs=q.pcrs,
            quote_digest_hex=q.quote_digest_hex,
            signature_hex="00" * 64,
            signer_pubkey_hex=q.signer_pubkey_hex,
            backend=q.backend,
        )
        result = att.verify_quote_against_expected(
            bad_sig_q, dict(q.pcrs), "dd" * 32,
        )
        assert result.ok is False
        assert "signature" in result.reason


class TestParseExpectedPcrs:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "EXPECTED_PCRS.toml"
        p.write_text("schema_version = 1\npopulated = false\n")
        assert att.parse_expected_pcrs(p) == {}

    def test_parses_entries(self, tmp_path):
        p = tmp_path / "EXPECTED_PCRS.toml"
        digest = "ab" * 32
        p.write_text(
            "schema_version = 1\n"
            f'[pcrs."4"]\nsha256 = "{digest}"\n\n'
            f'[pcrs."8"]\nsha256 = "{"cd"*32}"\n'
        )
        out = att.parse_expected_pcrs(p)
        assert out[4] == digest
        assert out[8] == "cd" * 32


class TestTPMAvailability:
    def test_is_available_returns_bool(self):
        assert isinstance(att.TPMAttestor.is_available(), bool)

    def test_get_attestor_picks_software_when_tpm_absent(
        self, tmp_path, measured_boot, monkeypatch,
    ):
        monkeypatch.setattr(
            att.TPMAttestor, "is_available", staticmethod(lambda: False),
        )
        monkeypatch.setattr(
            att, "_default_key_path",
            lambda: tmp_path / "key.pem",
        )
        a = att.get_attestor(
            aria_pkg_root=measured_boot["aria_pkg_root"],
            sealed_root=measured_boot["sealed_root"],
        )
        assert isinstance(a, att.SoftwarePCRAttestor)


class TestParseTpm2Pcrread:
    def test_parses_yaml_format(self):
        out = """
        sha256:
          0  : 0x0000000000000000000000000000000000000000000000000000000000000001
          4  : 0x0000000000000000000000000000000000000000000000000000000000000002
        """
        pcrs = att._parse_tpm2_pcrread(out, [0, 4])
        assert pcrs[0] == "00" * 31 + "01"
        assert pcrs[4] == "00" * 31 + "02"

    def test_raises_on_unparseable_output(self):
        with pytest.raises(RuntimeError):
            att._parse_tpm2_pcrread("garbage", [0])
