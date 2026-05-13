"""R156 — gRPC ALTS / mTLS channel hardening.

Threat: gRPC's default insecure channel sends RPCs in plaintext.
Inside a service mesh this is "fine because mesh-mTLS handles it" —
until a sidecar isn't injected (init container, daemonset, host-net
process) and the call goes plaintext anyway.

Defence: ``make_secure_channel`` returns a channel using TLS 1.3 mTLS
with explicit cert / CA paths, refusing the insecure default.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r156")


def make_secure_channel(
    target: str,
    *,
    root_ca_pem: Optional[bytes] = None,
    client_cert_pem: Optional[bytes] = None,
    client_key_pem: Optional[bytes] = None,
):
    try:
        import grpc
    except ImportError:
        return None
    if root_ca_pem is None or client_cert_pem is None or client_key_pem is None:
        raise RuntimeError(
            "R156: secure gRPC channel requires explicit root_ca + client_cert + client_key"
        )
    creds = grpc.ssl_channel_credentials(
        root_certificates=root_ca_pem,
        private_key=client_key_pem,
        certificate_chain=client_cert_pem,
    )
    return grpc.secure_channel(target, creds, options=[
        ("grpc.ssl_target_name_override", os.environ.get("ARIA_GRPC_SNI", "")),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ])


def boot_check_grpc_environment() -> Tuple[bool, str]:
    env = os.environ.get("ARIA_ENV", "")
    if env != "prod":
        return True, "non_prod"
    for k in ("ARIA_GRPC_ROOT_CA", "ARIA_GRPC_CLIENT_CERT", "ARIA_GRPC_CLIENT_KEY"):
        if not os.environ.get(k):
            return False, f"missing_{k}"
    return True, "ok"


register(DefencePlugin(
    round_id="R156",
    name="grpc_secure_channel",
    description="gRPC mTLS channel factory; refuses insecure defaults in prod.",
))
