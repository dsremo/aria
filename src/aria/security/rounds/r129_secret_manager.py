"""R129 — Cloud secret manager wrapper.

Threat: ARIA reads secrets from env vars.  Cloud-native deployments
should pull from Secrets Manager / Vault / Azure Key Vault / GCP
Secret Manager so secrets stay in a managed store with auto-rotation,
access logging, and KMS-wrapped at-rest encryption.

Defence: ``fetch_secret(name, provider)`` returns the secret value
from the configured provider.  Each provider is opt-in (uses the
already-installed SDK; doesn't add deps).  Pairs with R119 (don't put
secrets in env in prod).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from aria.security.plugins import DefencePlugin, register


logger = logging.getLogger("aria.security.rounds.r129")


def fetch_secret_aws(name: str, *, region: Optional[str] = None) -> Optional[str]:
    # Short-circuit: don't spin up boto3 unless the deployment is
    # actually configured for AWS.  Otherwise boto3 walks the IMDS
    # service which hangs in dev / CI without an EC2 metadata endpoint.
    has_aws_env = any(
        os.environ.get(k) for k in (
            "AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN",
            "AWS_PROFILE", "AWS_ROLE_ARN", "AWS_WEB_IDENTITY_TOKEN_FILE",
            "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        )
    )
    if not has_aws_env:
        return None
    try:
        import boto3
    except ImportError:
        return None
    try:
        client = boto3.client("secretsmanager",
                              region_name=region or os.environ.get("AWS_REGION", "us-east-1"))
        resp = client.get_secret_value(SecretId=name)
        return resp.get("SecretString")
    except Exception as exc:
        logger.warning("r129.aws_get_secret_failed name=%s exc=%s", name, exc)
        return None


def fetch_secret_vault(name: str) -> Optional[str]:
    """HashiCorp Vault — KV v2 path."""
    addr = os.environ.get("VAULT_ADDR", "")
    token = os.environ.get("VAULT_TOKEN", "")
    if not addr or not token:
        return None
    try:
        from aria.security.guard import safe_open_url
        url = f"{addr.rstrip('/')}/v1/secret/data/{name}"
        body = safe_open_url(
            url,
            timeout=5.0,
            max_bytes=64 * 1024,
            allowed_schemes=("https",),
            allowed_content_types=("application/json",),
            enforce_host_allowlist=False,
            headers={"X-Vault-Token": token, "User-Agent": "aria-core r129"},
        )
        import json
        data = json.loads(body.decode("utf-8"))
        return ((data.get("data") or {}).get("data") or {}).get("value")
    except Exception as exc:
        logger.warning("r129.vault_get_secret_failed name=%s exc=%s", name, exc)
        return None


def fetch_secret(name: str, *, provider: str = "auto") -> Optional[str]:
    if provider in ("auto", "aws"):
        v = fetch_secret_aws(name)
        if v is not None:
            return v
        if provider == "aws":
            return None
    if provider in ("auto", "vault"):
        v = fetch_secret_vault(name)
        if v is not None:
            return v
    return None


register(DefencePlugin(
    round_id="R129",
    name="secret_manager",
    description="Pluggable secret fetch (AWS Secrets Manager / Vault) for prod.",
))
