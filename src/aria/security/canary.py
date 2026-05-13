"""Canary Tokens + Honeypot Layer.

Layer 1-3 defense: detects reconnaissance before exploitation begins.

Strategy:
  Attackers (human or AI) probe a system before exploiting it.
  By placing invisible tripwires throughout ARIA:
    - Fake API endpoints that should NEVER be accessed by legitimate code
    - Canary tokens embedded in responses (if exfiltrated + used = caught)
    - Honeypot credentials that log on any use attempt
    - Fake diagnostic routes that reveal attacker's tooling

  When a Mythos-class agent scans all endpoints, it WILL hit canaries.
  Each hit is logged with high confidence as adversarial access.

Canary types:
  1. URL canaries — fake routes (/admin, /.env, /backup.zip, etc.)
  2. Token canaries — fake API keys that trigger on use
  3. Data canaries — fake records embedded in datasets
  4. Honeypot credentials — fake username/password combos in comments/logs

References:
  Spitzner L. (2002) "Honeypots: Tracking Hackers." Addison-Wesley.
  Thinkst Canary design principles (opencanary.com).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import structlog

logger = structlog.get_logger()


@dataclass
class CanaryHit:
    canary_id: str
    canary_type: str           # "url", "token", "credential", "data"
    accessor_identity: str
    timestamp: float
    endpoint: str
    payload_snippet: str = ""   # First 200 chars of what was sent


class CanaryRegistry:
    """Registry of all active canary tripwires.

    Maintains the set of canary tokens, endpoints, and credentials.
    Any access to a registered canary is an ALERT condition.
    """

    # URL paths that should NEVER be accessed legitimately
    # Covers standard scanner wordlists (dirb, gobuster, Mythos probe lists)
    HONEYPOT_PATHS: Set[str] = {
        # Admin panels
        "/admin", "/admin/", "/wp-admin", "/phpmyadmin", "/adminer",
        "/administrator", "/.htaccess", "/.htpasswd",
        # Backup/config files (common target of automated scanners)
        "/.env", "/config.php", "/database.yml", "/secrets.yml",
        "/backup.zip", "/backup.tar.gz", "/backup.sql", "/dump.sql",
        "/.git/config", "/.git/HEAD", "/.svn/entries",
        # Debug/diagnostic endpoints
        "/debug", "/console", "/phpinfo.php", "/info.php",
        "/server-status", "/server-info",
        # API discovery probes (Mythos scans these first)
        "/api/v0", "/api/internal", "/api/admin", "/api/debug",
        "/api/config", "/api/keys", "/api/secrets", "/api/tokens",
        "/v1/admin", "/swagger.json", "/openapi.json", "/graphql",
        # Common vulnerability probes
        "/shell.php", "/cmd.php", "/eval.php", "/exec.php",
        "/upload.php", "/file.php",
        # ARIA-specific honeypots (specific to this codebase)
        "/aria/raw-telemetry", "/aria/command-bypass",
        "/aria/maintenance-mode", "/aria/override",
    }

    # Keywords in any input that indicate automated scanning tooling
    SCANNER_SIGNATURES = [
        "sqlmap", "nikto", "nmap", "masscan", "zap", "burpsuite",
        "dirsearch", "gobuster", "wfuzz", "ffuf", "nuclei",
        "metasploit", "msfconsole", "empire", "covenant",
        # AI agent signatures
        "autonomous_agent", "exploit_chain", "auto_pwn",
        # Common LLM-injected probe patterns
        "test=<script>", "' OR 1=1", "1; DROP TABLE",
        "../../../etc/passwd", "%2e%2e%2f",
    ]

    def __init__(self) -> None:
        self._tokens: Dict[str, str] = {}    # token → description
        self._credentials: Dict[str, str] = {}  # username → password
        self._hits: List[CanaryHit] = []
        self._alert_callbacks: list = []

    def register_token(self, description: str = "") -> str:
        """Generate and register a canary API token."""
        token = "aria_canary_" + secrets.token_hex(16)
        self._tokens[token] = description or f"canary-{len(self._tokens)+1}"
        return token

    def register_credential(self, username: str, password: str) -> None:
        """Register a honeypot credential pair."""
        self._credentials[username] = password

    def on_alert(self, callback) -> None:
        self._alert_callbacks.append(callback)

    def check_url(self, path: str, identity: str = "") -> Optional[CanaryHit]:
        """Check if a URL path is a honeypot. Returns CanaryHit if triggered."""
        path_lower = path.lower().split("?")[0]  # strip query params
        if path_lower in {p.lower() for p in self.HONEYPOT_PATHS}:
            hit = CanaryHit(
                canary_id=hashlib.sha256(path.encode()).hexdigest()[:8],
                canary_type="url",
                accessor_identity=identity,
                timestamp=time.time(),
                endpoint=path,
            )
            self._record_hit(hit)
            return hit
        return None

    def check_token(self, token: str, identity: str = "", endpoint: str = "") -> Optional[CanaryHit]:
        """Check if a token is a canary token."""
        if token in self._tokens:
            hit = CanaryHit(
                canary_id=token[:20],
                canary_type="token",
                accessor_identity=identity,
                timestamp=time.time(),
                endpoint=endpoint,
                payload_snippet=f"token={token[:10]}...",
            )
            self._record_hit(hit)
            return hit
        return None

    def check_credential(self, username: str, password: str, identity: str = "") -> Optional[CanaryHit]:
        """Check if a credential pair is a honeypot credential."""
        stored = self._credentials.get(username)
        if stored is not None and stored == password:
            hit = CanaryHit(
                canary_id=f"cred:{username}",
                canary_type="credential",
                accessor_identity=identity,
                timestamp=time.time(),
                endpoint="/auth",
            )
            self._record_hit(hit)
            return hit
        return None

    def check_payload(self, payload: str, identity: str = "", endpoint: str = "") -> Optional[CanaryHit]:
        """Check payload for scanner/exploit tooling signatures."""
        payload_lower = payload.lower()
        for sig in self.SCANNER_SIGNATURES:
            if sig.lower() in payload_lower:
                hit = CanaryHit(
                    canary_id=f"payload:{sig[:8]}",
                    canary_type="scanner_signature",
                    accessor_identity=identity,
                    timestamp=time.time(),
                    endpoint=endpoint,
                    payload_snippet=payload[:200],
                )
                self._record_hit(hit)
                return hit
        return None

    def get_hits(self, since: float = 0.0) -> List[CanaryHit]:
        return [h for h in self._hits if h.timestamp >= since]

    def hit_count(self) -> int:
        return len(self._hits)

    def _record_hit(self, hit: CanaryHit) -> None:
        self._hits.append(hit)
        logger.warning(
            "canary.triggered",
            canary_id=hit.canary_id,
            type=hit.canary_type,
            identity=hit.accessor_identity,
            endpoint=hit.endpoint,
        )
        for cb in self._alert_callbacks:
            try:
                cb(hit)
            except Exception:
                pass


class HoneypotResponder:
    """Generates convincing but useless responses to honeypot probes.

    Returning a real 404 tells a scanner this path doesn't exist.
    Returning a fake 200 with plausible-looking data wastes attacker
    resources and elicits more probing (increasing detection probability).

    For Mythos: fake a 200 with a data payload that looks like credentials
    but contains embedded canary tokens — if Mythos tries to USE the faked
    credentials, we get a second-stage hit.
    """

    def __init__(self, registry: CanaryRegistry) -> None:
        self._reg = registry

    def fake_admin_response(self) -> dict:
        """Fake admin panel response with embedded canary token."""
        canary_tok = self._reg.register_token("embedded-in-fake-admin")
        return {
            "status": "ok",
            "user": "admin",
            "api_key": canary_tok,
            "permissions": ["read", "write", "admin"],
            "note": "Internal use only",
        }

    def fake_env_response(self) -> str:
        """Fake .env file contents with canary credentials."""
        canary_pwd = secrets.token_hex(8)
        self._reg.register_credential("aria_svc", canary_pwd)
        return (
            "# ARIA Configuration\n"
            "APP_ENV=production\n"
            f"DB_PASSWORD={canary_pwd}\n"
            f"API_KEY={self._reg.register_token('embedded-in-fake-env')}\n"
            "SECRET_KEY=changeme_in_production\n"
        )

    def fake_config_response(self) -> dict:
        """Fake config dump with canary tokens."""
        return {
            "database": {
                "host": "10.0.0.1",
                "user": "aria_db",
                "password": self._reg.register_token("embedded-in-fake-config"),
            },
            "redis": {"host": "10.0.0.2", "auth": secrets.token_hex(8)},
        }


# Module-level singleton for easy import
_default_registry: Optional[CanaryRegistry] = None


def get_default_registry() -> CanaryRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = CanaryRegistry()
    return _default_registry
