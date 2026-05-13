"""R221 — PLC firmware signature gate.

Threat: rewriting a PLC's firmware is the apex SCADA attack —
TRITON, BlackEnergy, Industroyer all touched PLCs.  Most legacy PLCs
accept *unsigned* firmware blobs; modern ones (Siemens S7-1500,
Schneider M580) support signed firmware but vendors ship with
verification *disabled* for OEM convenience.

Defence: an enforcement gate that refuses any PLC firmware update
without (a) Ed25519 signature against an enrolled vendor public key,
(b) two-person rule per R218, (c) a cooldown window that prevents
rapid-fire push.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Tuple

from aria.security.plugins import DefencePlugin, register


_LAST_UPDATE: Dict[str, float] = {}
_LOCK = threading.Lock()
_COOLDOWN_SECONDS = 3600.0


def gate_plc_firmware_update(
    *, plc_id: str, firmware_blob: bytes, signature: bytes,
    vendor_pubkey: bytes, two_person_token: str,
    now: float = 0.0,
) -> Tuple[bool, str]:
    t = now or time.time()

    with _LOCK:
        last = _LAST_UPDATE.get(plc_id, 0.0)
    if t - last < _COOLDOWN_SECONDS:
        return False, f"plc.cooldown_active remaining={_COOLDOWN_SECONDS - (t - last):.0f}s"

    from aria.security.rounds.r176_firmware_signing import verify_firmware_blob
    ok, why = verify_firmware_blob(firmware_blob, signature, ed25519_pubkey=vendor_pubkey)
    if not ok:
        return False, why

    from aria.security.rounds.r218_sis_airgap import gate_sis_firmware_update
    import hashlib
    sha = hashlib.sha256(firmware_blob).hexdigest()
    sis_ok, sis_why = gate_sis_firmware_update(
        firmware_blob_sha256=sha, two_person_token=two_person_token,
    )
    if not sis_ok and sis_why != "non_sis":
        return False, sis_why

    with _LOCK:
        _LAST_UPDATE[plc_id] = t
    return True, f"plc.fw_authorized plc={plc_id} sha={sha[:16]}…"


register(DefencePlugin(
    round_id="R221",
    name="plc_firmware_sig",
    description="PLC firmware update gate: signature + two-person rule + cooldown.",
))
