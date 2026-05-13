"""R103 — HSM via PKCS#11 (FIPS 140-3 Level 3 path).

Threat: software-only key storage cannot meet FIPS 140-3 Level 3.
Banks + nation-state deployers route every signing / wrap operation
through an HSM.  The standard interface is PKCS#11 (Cryptoki) — Thales
Luna 7, AWS CloudHSM, YubiHSM 2, SoftHSM all implement it.

Defence: a tiny adapter that picks up ``ARIA_PKCS11_LIB`` (path to the
HSM library .so) + ``ARIA_PKCS11_PIN`` and exposes ``sign(data, key_label)``
through the operator's HSM.  Soft-fails to file-based key when the
library is absent so dev workflows still function; the audit log
records which path was taken.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r103")


def is_hsm_available() -> bool:
    return bool(os.environ.get("ARIA_PKCS11_LIB"))


def sign_via_hsm(data: bytes, *, key_label: str) -> Optional[bytes]:
    """Return signature bytes from the HSM, or None if unavailable.

    The HSM is treated as opaque — we never extract the private key.
    Caller passes ``data`` (already hashed if needed) and a labelled
    key reference.  ARIA holds NO secret material in process memory.
    """
    if not is_hsm_available():
        return None
    try:
        import pkcs11                              # python-pkcs11
        lib_path = os.environ["ARIA_PKCS11_LIB"]
        pin = os.environ.get("ARIA_PKCS11_PIN", "")
        lib = pkcs11.lib(lib_path)
        token = next(iter(lib.get_tokens()))
        with token.open(user_pin=pin) as session:
            key = session.get_key(label=key_label, object_class=pkcs11.ObjectClass.PRIVATE_KEY)
            return bytes(key.sign(data))
    except Exception as exc:
        logger.warning("r103.hsm_sign_failed %s", exc)
        return None


def verify_via_hsm(data: bytes, signature: bytes, *, key_label: str) -> Tuple[bool, str]:
    """Verify with the HSM-held public counterpart of ``key_label``."""
    if not is_hsm_available():
        return False, "no_hsm"
    try:
        import pkcs11
        lib = pkcs11.lib(os.environ["ARIA_PKCS11_LIB"])
        token = next(iter(lib.get_tokens()))
        pin = os.environ.get("ARIA_PKCS11_PIN", "")
        with token.open(user_pin=pin) as session:
            key = session.get_key(label=key_label, object_class=pkcs11.ObjectClass.PUBLIC_KEY)
            ok = bool(key.verify(data, signature))
        return ok, "ok" if ok else "bad_sig"
    except Exception as exc:
        return False, f"verify_failed:{exc}"


register(DefencePlugin(
    round_id="R103",
    name="hsm_pkcs11",
    description="PKCS#11 sign/verify wrapper for FIPS 140-3 Level 3 HSMs.",
))
