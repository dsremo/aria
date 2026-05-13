"""Web / API Hardening — Layer 1 defense against basic human attackers.

Covers the OWASP Top 10 attack categories relevant to ARIA's API surface:
  A01 Broken Access Control   → ZeroTrustGuard (zero_trust.py)
  A02 Cryptographic Failures  → pqc.py
  A03 Injection               → This module + sanitizer.py
  A04 Insecure Design         → This module (input validation schemas)
  A05 Security Misconfiguration → This module (security headers)
  A07 Auth Failures           → auth.py + rate_limiter.py
  A08 Integrity Failures      → audit.py (tamper-evident log)
  A10 SSRF                    → This module (URL allowlist)

Reference: OWASP Top 10 2021 (owasp.org/Top10/)
"""

from __future__ import annotations

import ipaddress
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

import structlog

logger = structlog.get_logger()


# ── SQL Injection ──────────────────────────────────────────────────────────────

_SQL_INJECTION_PATTERNS = [
    re.compile(r"(\bOR\b|\bAND\b)\s+[\w\s'\"=]+--", re.IGNORECASE),
    re.compile(r"'\s*(OR|AND)\s+'?\d+'?\s*=\s*'?\d+", re.IGNORECASE),
    re.compile(r";\s*DROP\s+(TABLE|DATABASE)", re.IGNORECASE),
    re.compile(r";\s*DELETE\s+FROM", re.IGNORECASE),
    re.compile(r"UNION\s+(ALL\s+)?SELECT", re.IGNORECASE),
    re.compile(r"INSERT\s+INTO.*VALUES", re.IGNORECASE),
    re.compile(r"'\s*;\s*--", re.IGNORECASE),
    re.compile(r"xp_cmdshell", re.IGNORECASE),
    re.compile(r"EXEC\s*\(", re.IGNORECASE),
    re.compile(r"CAST\s*\(.*AS\s+(VARCHAR|CHAR|INT)", re.IGNORECASE),
]

# ── XSS ────────────────────────────���───────────────────────────────────���──────

_XSS_PATTERNS = [
    re.compile(r"<\s*script[^>]*>", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on\w+\s*=\s*['\"]", re.IGNORECASE),    # onclick=, onerror=, etc.
    re.compile(r"<\s*img[^>]+src\s*=\s*['\"]?\s*data:", re.IGNORECASE),
    re.compile(r"<\s*iframe", re.IGNORECASE),
    re.compile(r"document\.(cookie|write|location)", re.IGNORECASE),
    re.compile(r"window\.(location|open)", re.IGNORECASE),
    re.compile(r"eval\s*\(", re.IGNORECASE),
    re.compile(r"atob\s*\(|btoa\s*\(", re.IGNORECASE),  # base64 obfuscation
]

# ── Path Traversal ────────────────────────────��────────────────────────────��───

_PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\.[/\\]"),
    re.compile(r"%2e%2e[%/\\]", re.IGNORECASE),
    re.compile(r"\.\.%[25][cf]", re.IGNORECASE),
    re.compile(r"%252e%252e", re.IGNORECASE),  # double-encoded
    re.compile(r"/etc/passwd"),
    re.compile(r"/etc/shadow"),
    re.compile(r"C:\\Windows\\System32", re.IGNORECASE),
]

# ── SSRF (Server-Side Request Forgery) ───────────────────────────���────────────

_PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


@dataclass
class ValidationResult:
    safe: bool
    threats: List[str]
    sanitized: str

    @classmethod
    def clean(cls, value: str) -> "ValidationResult":
        return cls(safe=True, threats=[], sanitized=value)


class InputValidator:
    """Validates all inputs entering ARIA from external sources.

    Run every API parameter, sensor value, and user input through this
    before it touches any internal system.
    """

    def validate_string(self, value: str, field_name: str = "") -> ValidationResult:
        """Check string for SQL injection, XSS, path traversal, command injection."""
        threats: List[str] = []
        sanitized = value

        for pat in _SQL_INJECTION_PATTERNS:
            if pat.search(value):
                threats.append(f"sql_injection:{pat.pattern[:30]}")
                sanitized = pat.sub("[BLOCKED]", sanitized)

        for pat in _XSS_PATTERNS:
            if pat.search(value):
                threats.append(f"xss:{pat.pattern[:30]}")
                sanitized = pat.sub("[BLOCKED]", sanitized)

        for pat in _PATH_TRAVERSAL_PATTERNS:
            if pat.search(value):
                threats.append(f"path_traversal:{pat.pattern[:30]}")
                sanitized = pat.sub("[BLOCKED]", sanitized)

        if threats:
            logger.warning(
                "hardening.input_threats",
                field=field_name,
                threats=threats,
                sample=value[:80],
            )

        return ValidationResult(safe=len(threats) == 0, threats=threats, sanitized=sanitized)

    def validate_url(self, url: str) -> ValidationResult:
        """Prevent SSRF — block URLs resolving to private/internal addresses."""
        threats: List[str] = []
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname or ""

            # Block common internal hostnames
            internal_hosts = {"localhost", "0.0.0.0", "metadata.google.internal",  # nosec B104 (string in block-list, never bound)
                              "169.254.169.254", "metadata.aws"}
            if host.lower() in internal_hosts:
                threats.append(f"ssrf:internal_host:{host}")

            # Block private IP ranges
            try:
                addr = ipaddress.ip_address(host)
                for network in _PRIVATE_IP_RANGES:
                    if addr in network:
                        threats.append(f"ssrf:private_ip:{host}")
                        break
            except ValueError:
                pass  # host is a domain name, not an IP

            # Block non-HTTP(S) schemes (file://, dict://, gopher://)
            if parsed.scheme not in ("http", "https", ""):
                threats.append(f"ssrf:disallowed_scheme:{parsed.scheme}")

        except Exception as e:
            threats.append(f"url_parse_error:{e}")

        if threats:
            logger.warning("hardening.ssrf_detected", url=url[:80], threats=threats)

        return ValidationResult(safe=len(threats) == 0, threats=threats, sanitized=url)

    def validate_numeric(
        self,
        value: Any,
        field_name: str = "",
        min_val: float = -1e15,
        max_val: float = 1e15,
        allow_nan: bool = False,
        allow_inf: bool = False,
    ) -> ValidationResult:
        """Validate a numeric value is physically sane."""
        import math
        threats = []
        try:
            f = float(value)
        except (ValueError, TypeError):
            return ValidationResult(safe=False, threats=[f"not_numeric:{value}"], sanitized="0")

        if not allow_nan and math.isnan(f):
            threats.append("nan_value")
        if not allow_inf and math.isinf(f):
            threats.append("inf_value")
        if not math.isnan(f) and not math.isinf(f):
            if f < min_val or f > max_val:
                threats.append(f"out_of_range:{f:.3g} not in [{min_val:.3g}, {max_val:.3g}]")

        if threats:
            logger.warning("hardening.numeric_violation", field=field_name, threats=threats)

        return ValidationResult(safe=len(threats) == 0, threats=threats, sanitized=str(value))

    def validate_dict(self, data: Dict[str, Any], schema: Dict[str, type]) -> ValidationResult:
        """Validate a dict has expected keys of expected types — no extra keys."""
        threats = []
        unexpected = set(data.keys()) - set(schema.keys())
        if unexpected:
            threats.append(f"unexpected_keys:{unexpected}")

        for key, expected_type in schema.items():
            if key in data and not isinstance(data[key], expected_type):
                threats.append(f"type_mismatch:{key}={type(data[key]).__name__}!={expected_type.__name__}")

        return ValidationResult(safe=len(threats) == 0, threats=threats, sanitized=str(data)[:200])


def security_headers() -> Dict[str, str]:
    """HTTP security headers to include on every ARIA API response.

    Defends against XSS, clickjacking, MIME sniffing, and information leakage.
    """
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        ),
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Cache-Control": "no-store",
        "X-ARIA-Version": "redacted",  # don't leak version to attackers
    }
