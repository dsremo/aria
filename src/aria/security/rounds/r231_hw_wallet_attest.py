"""R231 — Hardware-wallet attestation (Ledger / Trezor / GridPlus).

Threat: a tampered hardware wallet (supply-chain compromise) returns
attacker-controlled keys.  Ledger Recover 2023 controversy + the
periodic JTAG-extraction PoCs underline that the device must prove
genuineness *to the host* before signing.

Defence: a wrapper around vendor attestation APIs.  Refuses signing
sessions when (a) attestation chain doesn't terminate at vendor
root, (b) firmware version is below operator-pinned floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class HwWalletAttestation:
    vendor: str
    model: str
    firmware_version: str
    attestation_chain: List[bytes]
    challenge_response: bytes


_VENDOR_ROOTS = {
    "ledger": b"<ledger-attestation-root-pubkey-placeholder>",
    "trezor": b"<trezor-attestation-root-pubkey-placeholder>",
}


def verify_attestation(
    a: HwWalletAttestation,
    *,
    min_firmware: str = "0.0.0",
) -> Tuple[bool, List[str]]:
    issues: List[str] = []
    vendor = a.vendor.lower()
    if vendor not in _VENDOR_ROOTS:
        issues.append(f"hwwallet.vendor_unknown:{vendor}")
    if not a.attestation_chain:
        issues.append("hwwallet.empty_chain")
    if not a.challenge_response or len(a.challenge_response) < 32:
        issues.append("hwwallet.weak_challenge_response")
    cur_v = _parse_version(a.firmware_version)
    min_v = _parse_version(min_firmware)
    if cur_v < min_v:
        issues.append(f"hwwallet.firmware_too_old:{a.firmware_version}<{min_firmware}")
    return not issues, issues


def _parse_version(v: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for p in (v or "").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def register_vendor_root(vendor: str, root_pubkey: bytes) -> None:
    _VENDOR_ROOTS[vendor.lower()] = root_pubkey


register(DefencePlugin(
    round_id="R231",
    name="hw_wallet_attest",
    description="Hardware-wallet attestation: vendor root + firmware floor + challenge-response.",
))
