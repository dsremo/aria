"""R149 — Cookie security-flag enforcer (Secure / HttpOnly / SameSite).

Threat: a session cookie without ``Secure`` is sent over plaintext
HTTP → MITM steal.  Without ``HttpOnly`` it's visible to ``document.cookie``
→ XSS steal.  Without ``SameSite=Lax|Strict`` it's sent on cross-site
navigations → CSRF.  Banks + OWASP both mandate all three.

Defence: ``audit_set_cookie(header_value)`` parses a Set-Cookie line
and reports missing flags.  ``ensure_safe_cookie(name, value, …)``
mints a proper Set-Cookie string with the recommended flags as
defaults.
"""

from __future__ import annotations

from typing import List, Tuple

from aria.security.plugins import DefencePlugin, register


def audit_set_cookie(header_value: str) -> Tuple[bool, List[str]]:
    if not header_value:
        return False, ["empty"]
    issues: List[str] = []
    flags = [p.strip().lower() for p in header_value.split(";")[1:]]
    has_secure = any(f == "secure" for f in flags)
    has_httponly = any(f == "httponly" for f in flags)
    samesite = next((f for f in flags if f.startswith("samesite=")), "")
    if not has_secure:
        issues.append("missing_Secure")
    if not has_httponly:
        issues.append("missing_HttpOnly")
    if not samesite:
        issues.append("missing_SameSite")
    elif samesite.split("=", 1)[1] not in ("lax", "strict"):
        issues.append(f"weak_SameSite={samesite}")
    return len(issues) == 0, issues


def ensure_safe_cookie(
    *,
    name: str,
    value: str,
    max_age: int = 3600,
    path: str = "/",
    secure: bool = True,
    http_only: bool = True,
    same_site: str = "Lax",
) -> str:
    """Return a Set-Cookie value with the recommended flags."""
    if not name or not value:
        raise ValueError("R149: name + value required")
    parts = [
        f"{name}={value}",
        f"Path={path}",
        f"Max-Age={max_age}",
        f"SameSite={same_site}",
    ]
    if secure:
        parts.append("Secure")
    if http_only:
        parts.append("HttpOnly")
    return "; ".join(parts)


register(DefencePlugin(
    round_id="R149",
    name="cookie_flags",
    description="Audit Set-Cookie for Secure/HttpOnly/SameSite + safe minter.",
))
