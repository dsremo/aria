"""R180 — OTA update bundle signature + rollback gate.

Threat: an OTA bundle without rollback protection lets an attacker
push a known-vulnerable older version and exploit a re-introduced
CVE.  ESP-IDF, Zephyr, and Mender all have config switches that
disable rollback by default.

Defence: ``verify_ota_bundle`` checks signature (via R176), refuses
to apply if version < current (anti-rollback), and demands a fresh
nonce signed by the operator's update key to prevent replay.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


@dataclass
class OTABundle:
    version: int
    blob: bytes
    signature: bytes
    nonce: bytes
    signed_nonce: bytes


def verify_ota_bundle(
    bundle: OTABundle,
    *,
    current_version: int,
    fw_pubkey: bytes,
    nonce_hmac_key: bytes,
    now_ts: float = 0.0,
    nonce_max_age_seconds: int = 600,
) -> Tuple[bool, str]:
    if bundle.version < current_version:
        return False, f"ota.rollback_attempt v={bundle.version} cur={current_version}"
    if bundle.version == current_version:
        return False, "ota.same_version"

    if len(bundle.nonce) != 32:
        return False, "ota.nonce_wrong_length"
    expected_sig = hmac.new(nonce_hmac_key, bundle.nonce, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, bundle.signed_nonce):
        return False, "ota.nonce_hmac_invalid"

    nonce_ts = int.from_bytes(bundle.nonce[:8], "big")
    age = (now_ts or time.time()) - nonce_ts
    if age > nonce_max_age_seconds or age < -60:
        return False, f"ota.nonce_stale age={age:.0f}"

    from aria.security.rounds.r176_firmware_signing import verify_firmware_blob
    ok, why = verify_firmware_blob(
        bundle.blob, bundle.signature, ed25519_pubkey=fw_pubkey,
    )
    if not ok:
        return False, why
    return True, f"ota.applied v={bundle.version}"


register(DefencePlugin(
    round_id="R180",
    name="ota_update",
    description="OTA bundle verify: signature + anti-rollback + fresh-nonce HMAC.",
))
