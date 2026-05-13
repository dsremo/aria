"""R108 — Hardware-rooted key wrap (KMIP-style).

Threat: when a fresh tenant key is minted, it must travel from the
KEK / HSM to the consuming process without ever existing as plain
bytes outside the secure boundary.  The standard mechanism is
*key wrap* — RFC 3394 (AES-KW) or RFC 5649 (AES-KWP).  Banks expose
this via KMIP; we ship a thin Python wrapper.

Defence: ``aes_kw_wrap(plaintext_key, kek_bytes)`` uses ``cryptography``'s
``aes_key_wrap_with_padding`` (RFC 5649) so any plaintext-key length is
accepted.  ``aes_kw_unwrap`` reverses.  When ``ARIA_PKCS11_LIB`` is set
the wrap is delegated to the HSM (R103) so the KEK never leaves it.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


def aes_kw_wrap(plaintext_key: bytes, *, kek: bytes) -> bytes:
    if len(kek) not in (16, 24, 32):
        raise ValueError("R108.aes_kw_wrap: kek must be 128/192/256 bit")
    try:
        from cryptography.hazmat.primitives.keywrap import aes_key_wrap_with_padding
        return aes_key_wrap_with_padding(kek, plaintext_key)
    except ImportError:
        raise RuntimeError("R108: install cryptography for aes_kw_wrap")


def aes_kw_unwrap(wrapped: bytes, *, kek: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.keywrap import aes_key_unwrap_with_padding
        return aes_key_unwrap_with_padding(kek, wrapped)
    except ImportError:
        raise RuntimeError("R108: install cryptography for aes_kw_unwrap")


def hsm_wrap_key(plaintext_key: bytes, *, kek_label: str) -> Optional[bytes]:
    """Delegate the wrap to the HSM; the KEK never leaves the device.

    Returns None when no HSM is configured; caller falls back to
    :func:`aes_kw_wrap` with a software KEK derived via R53 HKDF.
    """
    if not os.environ.get("ARIA_PKCS11_LIB"):
        return None
    try:
        # The python-pkcs11 binding's wrap_key is the canonical path;
        # implementations vary, so we keep this stub minimal.
        import pkcs11
        lib = pkcs11.lib(os.environ["ARIA_PKCS11_LIB"])
        token = next(iter(lib.get_tokens()))
        with token.open(user_pin=os.environ.get("ARIA_PKCS11_PIN", "")) as session:
            kek = session.get_key(label=kek_label, object_class=pkcs11.ObjectClass.SECRET_KEY)
            # python-pkcs11 expects a session-loaded key for wrap
            target = session.create_object({
                pkcs11.Attribute.CLASS: pkcs11.ObjectClass.SECRET_KEY,
                pkcs11.Attribute.KEY_TYPE: pkcs11.KeyType.GENERIC_SECRET,
                pkcs11.Attribute.VALUE: plaintext_key,
                pkcs11.Attribute.EXTRACTABLE: True,
                pkcs11.Attribute.WRAP: True,
            })
            return bytes(kek.wrap_key(target, mechanism=pkcs11.Mechanism.AES_KEY_WRAP_PAD))
    except Exception:
        return None


register(DefencePlugin(
    round_id="R108",
    name="key_wrap",
    description="AES-KWP (RFC 5649) software wrap; HSM PKCS#11 path when available.",
))
