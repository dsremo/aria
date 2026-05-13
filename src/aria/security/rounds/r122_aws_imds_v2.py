"""R122 — AWS IMDS v2 enforcement.

Threat: a SSRF inside an EC2 instance can hit
``http://169.254.169.254/latest/meta-data/iam/security-credentials/``
(IMDSv1) and steal the instance role's STS token.  Capital One 2019
was this exact attack.  IMDSv2 requires a session token (PUT) before
any GET, and lets operators set ``HTTPPutResponseHopLimit=1`` so a
container reverse-proxy can't trivially relay the request.

Defence: ``boot_check_imds_v2()`` confirms the instance metadata is
reachable ONLY via the IMDSv2 PUT-then-GET dance, and refuses to start
in production if IMDSv1 is still answering.  Plus a ``recommended_aws_cli()``
snippet operators run to lock the instance.
"""

from __future__ import annotations

import os
import socket
import urllib.request
from typing import Tuple

from aria.security.plugins import DefencePlugin, register


_IMDS_HOST = "169.254.169.254"


def imds_v1_reachable(timeout: float = 1.0) -> bool:
    """Return True iff IMDSv1 (no token) returns 200 for a metadata path."""
    try:
        req = urllib.request.Request(f"http://{_IMDS_HOST}/latest/meta-data/")
        with urllib.request.urlopen(req, timeout=timeout) as resp:        # nosec B310
            return resp.status == 200
    except Exception:
        return False


def imds_v2_reachable(timeout: float = 1.0) -> bool:
    """Return True iff IMDSv2 (PUT-token then GET) works."""
    try:
        token_req = urllib.request.Request(
            f"http://{_IMDS_HOST}/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        with urllib.request.urlopen(token_req, timeout=timeout) as resp:  # nosec B310
            tok = resp.read().decode("ascii")
        if not tok:
            return False
        req = urllib.request.Request(
            f"http://{_IMDS_HOST}/latest/meta-data/",
            headers={"X-aws-ec2-metadata-token": tok},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:        # nosec B310
            return resp.status == 200
    except Exception:
        return False


def boot_check_imds_v2() -> Tuple[bool, str]:
    """Refuse production start when IMDSv1 still answers."""
    if os.environ.get("ARIA_ENV", "").lower() != "production":
        return True, "non_prod"
    # Confirm we're on EC2 — short-circuit if we can't even reach metadata
    try:
        socket.create_connection((_IMDS_HOST, 80), timeout=0.5).close()
    except Exception:
        return True, "not_ec2"
    if imds_v1_reachable():
        return False, "IMDSv1 still answers — set HttpTokens=required"
    if not imds_v2_reachable():
        return True, "IMDS unreachable"
    return True, "IMDSv2_only"


_AWS_CLI = """\
# R122 — lock IMDSv2 on the running instance
aws ec2 modify-instance-metadata-options \\
  --instance-id $INSTANCE_ID \\
  --http-tokens required \\
  --http-put-response-hop-limit 1 \\
  --http-endpoint enabled
"""


def recommended_aws_cli() -> str:
    return _AWS_CLI


register(DefencePlugin(
    round_id="R122",
    name="aws_imds_v2",
    description="Refuse production start when IMDSv1 still answers (Capital-One class).",
))
