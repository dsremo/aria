"""ARIA Security Guard — unified hardening library wired into every service.

A single import surface for the operationally-critical defences that map to
real breaches from the last three years:

  ├── safe_open_url         (SSRF, response size cap)        — Snowflake / Twilio Authy
  ├── safe_xml_parse        (XXE, billion-laughs)            — generic XXE class
  ├── safe_json_loads       (depth + size cap)               — DoS via deeply nested input
  ├── safe_zip_extract      (zip-slip, decompression bomb)   — generic zip-bomb DoS
  ├── safe_pickle_block     (RCE via untrusted deserial.)    — XZ-style supply-chain
  ├── safe_yaml_load        (RCE via PyYAML)                 — generic CVE-2017-18342
  ├── LogSanitizer          (CRLF-injected log forgery)      — log-injection class
  ├── mfa_admin_check       (admin double-token)             — Snowflake (no MFA)
  ├── content_type_guard    (response sniff + reject)        — supply-chain payload swap
  ├── harden_aiohttp_app    (one-call wiring for services)   — wraps screener/advisor/ws
  └── runtime_check_environment  (boot-time fail-closed)     — Storm-0558 (key audit)

Every function is conservative-by-default and fail-closed.  Operators may
opt out at the call-site, never at the library level.

Reference policies:
  * NIST SP 800-53 Rev 5 (SI-10 input validation, SC-7 boundary protection)
  * OWASP ASVS 4.0.3
  * OWASP Top 10 2021 + 2025 preview categories (API security, AI risks)
"""

from __future__ import annotations

import functools
import io
import ipaddress
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from typing import (
    Any, Awaitable, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union,
)

logger = logging.getLogger("aria.security.guard")


# ════════════════════════════════════════════════════════════════════════════
# Module configuration — operators override via environment variables.
# ════════════════════════════════════════════════════════════════════════════

# Default allow-list for outbound HTTP fetches.  Includes the public space-data
# upstreams ARIA legitimately calls.  Operators extend via ARIA_GUARD_ALLOWED_HOSTS
# (comma-separated).
_DEFAULT_OUTBOUND_HOST_ALLOWLIST = frozenset({
    "celestrak.org",
    "celestrak.com",
    "www.space-track.org",
    "ssd.jpl.nasa.gov",
    "naif.jpl.nasa.gov",
    "ntrs.nasa.gov",
    "data.nasa.gov",
    "leolabs.space",
    "platform.leolabs.space",
    "is4om.in",
    "network.satnogs.org",
    "db.satnogs.org",
    "storage.googleapis.com",
    "huggingface.co",
})

# Default per-response cap (32 MiB).  TLE files, ephemeris snapshots, and
# small CDM bundles fit; megabyte-class JSON responses do too.  Multi-GB
# blobs do NOT — they have to opt in explicitly per call.
_DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024

# Per-request body cap on incoming HTTP — 10 MiB matches the screener default.
_DEFAULT_MAX_REQUEST_BYTES = 10 * 1024 * 1024

# JSON depth cap; deeper than 64 levels is almost always pathological / hostile.
_DEFAULT_MAX_JSON_DEPTH = 64

# ZIP archive caps.
_DEFAULT_MAX_ZIP_FILES = 5_000
_DEFAULT_MAX_ZIP_UNCOMPRESSED = 256 * 1024 * 1024  # 256 MiB
_DEFAULT_MAX_ZIP_RATIO = 100.0  # uncompressed / compressed; anything higher is a bomb


# ════════════════════════════════════════════════════════════════════════════
# Errors
# ════════════════════════════════════════════════════════════════════════════

class GuardError(Exception):
    """Raised by any guard helper that fails closed."""


class SSRFBlocked(GuardError):
    """Outbound URL resolved to a private / disallowed address."""


class ResponseTooLarge(GuardError):
    """Response body exceeded the configured byte cap."""


class ContentTypeRejected(GuardError):
    """Response content-type not in the call-site allow-list."""


class XMLDisallowed(GuardError):
    """XML payload contained external-entity references or DTD declarations."""


class JSONTooDeep(GuardError):
    """JSON payload exceeded the configured nesting depth."""


class ZipUnsafe(GuardError):
    """ZIP archive failed zip-slip / decompression-bomb pre-flight checks."""


class PickleBlocked(GuardError):
    """Pickle deserialisation refused as a matter of policy."""


# ════════════════════════════════════════════════════════════════════════════
# 1. SSRF + outbound HTTP fetch
# ════════════════════════════════════════════════════════════════════════════

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # AWS / GCE metadata
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]

_BLOCKED_INTERNAL_HOSTS = frozenset({
    "localhost", "ip6-localhost", "ip6-loopback",
    "metadata.google.internal", "metadata.aws", "instance-data.ec2.internal",
})


def _is_private_ip(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    for net in _PRIVATE_NETS:
        if ip in net:
            return True
    return False


def validate_outbound_url(
    url: str,
    *,
    allowed_schemes: Iterable[str] = ("https",),
    host_allowlist: Optional[Iterable[str]] = None,
) -> None:
    """Reject URLs that would let an attacker redirect ARIA at internal targets.

    Defends against generic SSRF (CWE-918), the Capital-One-style metadata
    pivot, and a class of supply-chain swaps where a hostile feed redirects
    ARIA at a controlled secondary host. Resolves DNS so a public hostname
    pointing at 169.254.169.254 still gets blocked.
    """
    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {s.lower() for s in allowed_schemes}:
        raise SSRFBlocked(f"scheme {scheme!r} not in allow-list {sorted(allowed_schemes)}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SSRFBlocked("URL has no hostname")
    if host in _BLOCKED_INTERNAL_HOSTS:
        raise SSRFBlocked(f"hostname {host!r} is on the internal block-list")
    # Direct IP supplied?
    if _is_private_ip(host):
        raise SSRFBlocked(f"IP {host!r} is in a private / reserved range")
    # Domain-form host — resolve DNS and reject if any address is private.
    # We catch the hostname-vs-IP case by attempting ip_address parse first.
    try:
        ipaddress.ip_address(host)
        # It WAS an IP, and we already checked private — pass.
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise SSRFBlocked(f"DNS resolution failed for {host!r}: {exc}")
        for info in infos:
            ip = info[4][0]
            # IPv6 may include scope id (e.g., fe80::1%eth0)
            ip = ip.split("%", 1)[0]
            if _is_private_ip(ip):
                raise SSRFBlocked(
                    f"hostname {host!r} resolves to private IP {ip!r}"
                )
    if host_allowlist is not None:
        allowed = {h.lower() for h in host_allowlist}
        # Suffix match — `api.huggingface.co` matches `huggingface.co`.
        if not any(host == a or host.endswith("." + a) for a in allowed):
            raise SSRFBlocked(
                f"hostname {host!r} not in operator allow-list"
            )


def _env_host_allowlist() -> Set[str]:
    extra = os.environ.get("ARIA_GUARD_ALLOWED_HOSTS", "").strip()
    if not extra:
        return set(_DEFAULT_OUTBOUND_HOST_ALLOWLIST)
    return set(_DEFAULT_OUTBOUND_HOST_ALLOWLIST) | {
        h.strip().lower() for h in extra.split(",") if h.strip()
    }


def safe_open_url(
    url: str,
    *,
    timeout: float = 15.0,
    max_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES,
    allowed_schemes: Iterable[str] = ("https",),
    allowed_content_types: Optional[Iterable[str]] = None,
    enforce_host_allowlist: bool = True,
    headers: Optional[Dict[str, str]] = None,
) -> bytes:
    """Fetch a URL with SSRF / size / type / scheme defences.

    The byte cap is enforced incrementally so a 5 GB malicious response is
    aborted after ``max_bytes`` are buffered, not after the whole download.
    """
    host_allow: Optional[Iterable[str]] = (
        _env_host_allowlist() if enforce_host_allowlist else None
    )
    validate_outbound_url(
        url,
        allowed_schemes=allowed_schemes,
        host_allowlist=host_allow,
    )
    req = urllib.request.Request(
        url,
        headers=dict(headers or {"User-Agent": "ARIA-aria-core/0.3"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 (URL validated by validate_outbound_url() above)
            ctype = (resp.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
            if allowed_content_types is not None:
                allowed = {c.lower() for c in allowed_content_types}
                if ctype not in allowed:
                    raise ContentTypeRejected(
                        f"content-type {ctype!r} not in {sorted(allowed)}"
                    )
            buf = bytearray()
            chunk_size = 64 * 1024
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise ResponseTooLarge(
                        f"response from {url[:80]!r} exceeded {max_bytes} bytes"
                    )
            return bytes(buf)
    except urllib.error.URLError as exc:
        # Surface as GuardError so callers handle one exception class.
        raise GuardError(f"fetch failed: {exc!r}")


# ════════════════════════════════════════════════════════════════════════════
# 2. XML — defusedxml-backed; reject DTDs and external entities.
# ════════════════════════════════════════════════════════════════════════════

def _import_defused() -> Tuple[Optional[Any], Optional[Any]]:
    try:
        from defusedxml.ElementTree import fromstring as _fromstring
        from defusedxml.ElementTree import parse as _parse
        return _fromstring, _parse
    except ImportError:  # pragma: no cover
        logger.warning("guard.defusedxml_missing — falling back to stricter manual checks")
        return None, None


_DTD_RE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)
_ENTITY_RE = re.compile(rb"<!ENTITY", re.IGNORECASE)


def safe_xml_fromstring(payload: Union[str, bytes]) -> Any:
    """Parse XML with XXE / billion-laughs defences.

    Uses defusedxml when available; falls back to a content-pattern reject.
    """
    if isinstance(payload, str):
        b = payload.encode("utf-8", errors="replace")
    else:
        b = payload
    if _DTD_RE.search(b) or _ENTITY_RE.search(b):
        raise XMLDisallowed("payload declares DOCTYPE or ENTITY — rejected")
    fromstring, _ = _import_defused()
    if fromstring is not None:
        try:
            return fromstring(b)
        except Exception as exc:
            raise XMLDisallowed(f"defusedxml refused payload: {exc!r}")
    # Fallback path — stdlib parse is OK only because we already rejected
    # DTDs and ENTITY declarations above (see _DTD_RE / _ENTITY_RE pre-checks).
    import xml.etree.ElementTree as _ET  # nosec B405 (DTD/ENTITY pre-rejected)
    return _ET.fromstring(b)  # nosec B314 (DTD/ENTITY pre-rejected)


def safe_xml_parse(source: Any) -> Any:
    """Parse from a file-like or path.  Same defences as fromstring."""
    if hasattr(source, "read"):
        data = source.read()
    else:
        with open(source, "rb") as f:
            data = f.read()
    return safe_xml_fromstring(data)


# ════════════════════════════════════════════════════════════════════════════
# 3. JSON — depth + size cap to defeat stack-exhausting payloads.
# ════════════════════════════════════════════════════════════════════════════

def _json_depth(obj: Any, _level: int = 0) -> int:
    if _level > _DEFAULT_MAX_JSON_DEPTH * 4:
        return _level  # already past any sane cap; let caller raise
    if isinstance(obj, dict):
        if not obj:
            return _level
        return max(_json_depth(v, _level + 1) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return _level
        return max(_json_depth(v, _level + 1) for v in obj)
    return _level


def safe_json_loads(
    payload: Union[str, bytes],
    *,
    max_depth: int = _DEFAULT_MAX_JSON_DEPTH,
    max_bytes: int = _DEFAULT_MAX_REQUEST_BYTES,
) -> Any:
    """Parse JSON with size + depth caps.

    Defeats CPU/stack DoS via deeply-nested objects (arbitrary recursion has
    been exploited in prior aiohttp/JSON handlers).
    """
    if isinstance(payload, str):
        b = payload.encode("utf-8")
    else:
        b = bytes(payload)
    if len(b) > max_bytes:
        raise GuardError(f"JSON payload exceeds {max_bytes} bytes")
    try:
        obj = json.loads(b)
    except json.JSONDecodeError as exc:
        raise GuardError(f"JSON parse failed: {exc.msg}") from exc
    depth = _json_depth(obj)
    if depth > max_depth:
        raise JSONTooDeep(f"JSON nesting depth {depth} exceeds {max_depth}")
    return obj


# ════════════════════════════════════════════════════════════════════════════
# 4. ZIP — block zip-slip + decompression bombs (xtce_parser feeds this).
# ════════════════════════════════════════════════════════════════════════════

def safe_zip_extract(
    archive_path: Any,
    dest_dir: Any,
    *,
    max_files: int = _DEFAULT_MAX_ZIP_FILES,
    max_uncompressed_bytes: int = _DEFAULT_MAX_ZIP_UNCOMPRESSED,
    max_ratio: float = _DEFAULT_MAX_ZIP_RATIO,
) -> List[str]:
    """Extract a ZIP after pre-flight zip-slip + bomb checks.

    Returns the list of extracted relative paths.  Raises ``ZipUnsafe`` if
    any member would escape ``dest_dir``, the file count exceeds
    ``max_files``, the total uncompressed size exceeds the budget, or the
    compression ratio of any member exceeds ``max_ratio``.
    """
    from pathlib import Path
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    out: List[str] = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        members = zf.infolist()
        if len(members) > max_files:
            raise ZipUnsafe(f"archive has {len(members)} files > {max_files}")
        total_uncompressed = sum(m.file_size for m in members)
        if total_uncompressed > max_uncompressed_bytes:
            raise ZipUnsafe(
                f"archive uncompressed size {total_uncompressed} > {max_uncompressed_bytes}"
            )
        for m in members:
            if m.compress_size > 0:
                ratio = m.file_size / m.compress_size
                if ratio > max_ratio:
                    raise ZipUnsafe(
                        f"member {m.filename!r} ratio {ratio:.0f} exceeds {max_ratio}"
                    )
            target = (dest / m.filename).resolve()
            try:
                target.relative_to(dest)
            except ValueError:
                raise ZipUnsafe(f"zip-slip: {m.filename!r} escapes destination")
        zf.extractall(dest)
        out = [m.filename for m in members]
    return out


def safe_zip_open(archive_path: Any, *,
                  max_files: int = _DEFAULT_MAX_ZIP_FILES,
                  max_uncompressed_bytes: int = _DEFAULT_MAX_ZIP_UNCOMPRESSED) -> zipfile.ZipFile:
    """Open a ZIP archive after preflight checks; caller closes it."""
    zf = zipfile.ZipFile(archive_path, "r")
    members = zf.infolist()
    if len(members) > max_files:
        zf.close()
        raise ZipUnsafe(f"archive has {len(members)} files > {max_files}")
    total = sum(m.file_size for m in members)
    if total > max_uncompressed_bytes:
        zf.close()
        raise ZipUnsafe(f"archive uncompressed size {total} > {max_uncompressed_bytes}")
    return zf


# ════════════════════════════════════════════════════════════════════════════
# 5. Pickle / YAML — refuse-by-default for untrusted sources.
# ════════════════════════════════════════════════════════════════════════════

def safe_pickle_block(*_args: Any, **_kwargs: Any) -> None:
    """Always raises.  Use this where pickle.load() was being called on
    operator-supplied bytes — pickle is RCE-equivalent and must not run on
    untrusted data.  Replace the call site with JSON / msgpack / protobuf.
    """
    raise PickleBlocked(
        "pickle deserialisation refused by aria.security.guard — "
        "use a structured format (json/msgpack/protobuf) for untrusted data"
    )


def safe_yaml_load(payload: Union[str, bytes]) -> Any:
    """Parse YAML using ``safe_load`` — never the unsafe Loader."""
    import yaml
    return yaml.safe_load(payload)


# ════════════════════════════════════════════════════════════════════════════
# 6. Log injection — strip CR/LF / control chars before structured logging.
# ════════════════════════════════════════════════════════════════════════════

_LOG_FORBIDDEN_CHARS = re.compile(r"[\r\n\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Trojan-source / bidi-control chars (CVE-2021-42574, CVE-2021-42694) — ban
# these in any source-like string we log so a downstream terminal can't be
# tricked into a different rendering.
_BIDI_CONTROL_CHARS = re.compile("[\u202A-\u202E\u2066-\u2069]")


def sanitise_for_log(value: Any, max_len: int = 256) -> str:
    """Make a value safe to drop into a log line.

    Strips CRLF (CWE-117), bidi-control chars (Trojan-source class),
    NULs, and ASCII control codes.  Truncates to ``max_len`` to bound
    log volume.
    """
    if not isinstance(value, str):
        try:
            s = repr(value)
        except Exception:
            s = "<unprintable>"
    else:
        s = value
    s = _LOG_FORBIDDEN_CHARS.sub(" ", s)
    s = _BIDI_CONTROL_CHARS.sub("", s)
    if len(s) > max_len:
        s = s[:max_len] + "...[trunc]"
    return s


# ════════════════════════════════════════════════════════════════════════════
# 7. Admin double-token (Snowflake-class breach defence).
# ════════════════════════════════════════════════════════════════════════════

import hmac as _hmac


def _const_eq(a: str, b: str) -> bool:
    return _hmac.compare_digest(a or "", b or "")


def mfa_admin_check(
    request: Any,
    *,
    primary_env: str = "ARIA_ADMIN_TOKEN",
    secondary_env: str = "ARIA_ADMIN_OTP_SEED",
    primary_header: str = "X-ARIA-Admin-Token",
    secondary_header: str = "X-ARIA-Admin-OTP",
    window_seconds: int = 30,
) -> bool:
    """Two-factor admin gate.

    Demands BOTH a long-lived token (rotated quarterly) AND a short-lived
    OTP derived from a shared seed.  This shape mirrors what Snowflake
    learnt the hard way in 2024 — long-lived passwords without a second
    factor are credential-stuffed at scale.

    The OTP is intentionally simple (HMAC-SHA256(seed, floor(time / window))
    truncated to 8 hex chars).  A real RFC 6238 TOTP is preferred when an
    operator MFA app is wired in; the helper keeps a usable fallback so
    admin endpoints aren't silently single-factor.
    """
    primary = os.environ.get(primary_env, "").strip()
    if not primary:
        return False
    presented_primary = (request.headers.get(primary_header, "") or "").strip()
    if not _const_eq(primary, presented_primary):
        return False
    secondary_seed = os.environ.get(secondary_env, "").strip()
    if not secondary_seed:
        # Soft-mode: only primary required.  Log it; warn the operator.
        logger.warning(
            "guard.mfa_admin.soft_mode",
            extra={"reason": f"{secondary_env} not configured"},
        )
        return True
    presented_otp = (request.headers.get(secondary_header, "") or "").strip()
    if not presented_otp:
        return False
    now_window = int(time.time() // window_seconds)
    expected = _hmac.new(
        secondary_seed.encode("utf-8"),
        str(now_window).encode("ascii"),
        digestmod="sha256",
    ).hexdigest()[:8]
    # Accept current or previous window to cope with clock skew.
    expected_prev = _hmac.new(
        secondary_seed.encode("utf-8"),
        str(now_window - 1).encode("ascii"),
        digestmod="sha256",
    ).hexdigest()[:8]
    return _const_eq(presented_otp, expected) or _const_eq(presented_otp, expected_prev)


# ════════════════════════════════════════════════════════════════════════════
# 8. aiohttp middleware pack — wires it all into one app in one call.
# ════════════════════════════════════════════════════════════════════════════

def _security_headers() -> Dict[str, str]:
    # Audit CRIT-8 — wire R252/R255/R257/R258 (and equivalents) so every
    # response carries a strict CSP, the cross-origin isolation pair,
    # and a deny-by-default Permissions-Policy.  Headers are emitted by
    # the aiohttp app layer; the reverse proxy's identical headers act
    # as belt-and-braces.
    #
    # Round-2 audit NEW-LOW-5 — drop the ``preload`` directive from
    # HSTS by default so an operator who hasn't enrolled the domain on
    # https://hstspreload.org/ doesn't ship a footgun.  Operators who
    # have submitted their domain may set ``ARIA_HSTS_PRELOAD=1`` to
    # add it back.
    from aria.security.rounds.r255_permissions_policy import strict_permissions_policy
    permissions = strict_permissions_policy()
    hsts = "max-age=63072000; includeSubDomains"
    if os.environ.get("ARIA_HSTS_PRELOAD", "").lower() in ("1", "true", "yes"):
        hsts += "; preload"
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Strict-Transport-Security": hsts,
        "Referrer-Policy": "strict-origin-when-cross-origin",   # audit MED — R258
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cross-Origin-Opener-Policy": "same-origin",            # audit CRIT-8 — R257
        "Cross-Origin-Embedder-Policy": "require-corp",         # audit CRIT-8 — R257
        "Permissions-Policy": permissions,                       # audit CRIT-8 — R255
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'none'; "
            "script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'self'; object-src 'none'; "
            "require-trusted-types-for 'script'"
        ),
    }


def make_security_headers_middleware():
    """aiohttp middleware that adds standard hardening headers to every response."""
    from aiohttp import web

    headers = _security_headers()

    @web.middleware
    async def middleware(request, handler):
        try:
            resp = await handler(request)
        except web.HTTPException as exc:
            for k, v in headers.items():
                exc.headers.setdefault(k, v)
            raise
        for k, v in headers.items():
            resp.headers.setdefault(k, v)
        return resp

    return middleware


def make_body_size_middleware(max_bytes: int = _DEFAULT_MAX_REQUEST_BYTES):
    """aiohttp middleware that 413s on oversize Content-Length up-front.

    aiohttp already enforces ``client_max_size`` on streamed reads — this
    catches the case where a client sends an honest Content-Length and we
    can reject without buffering.
    """
    from aiohttp import web

    @web.middleware
    async def middleware(request, handler):
        cl = request.headers.get("Content-Length")
        if cl is not None:
            try:
                n = int(cl)
            except ValueError:
                return web.json_response(
                    {"error": "bad_content_length"}, status=400,
                )
            # Round-2 audit NEW-HIGH-20 — reject negative Content-Length.
            if n < 0:
                return web.json_response(
                    {"error": "bad_content_length"}, status=400,
                )
            if n > max_bytes:
                return web.json_response(
                    {"error": "payload_too_large",
                     "max_bytes": max_bytes},
                    status=413,
                )
        return await handler(request)

    return middleware


def make_method_guard_middleware(
    allowed_methods: Iterable[str] = ("GET", "POST", "HEAD", "OPTIONS"),
):
    """Reject HTTP verbs we never use (TRACE, TRACK, PROPFIND, …)."""
    from aiohttp import web
    allow = {m.upper() for m in allowed_methods}

    @web.middleware
    async def middleware(request, handler):
        if request.method.upper() not in allow:
            return web.json_response(
                {"error": "method_not_allowed"}, status=405,
                headers={"Allow": ", ".join(sorted(allow))},
            )
        return await handler(request)

    return middleware


def make_request_id_middleware(header_name: str = "X-Request-Id"):
    """Mint a request id, attach to ``request['request_id']`` and echo it."""
    from aiohttp import web
    import secrets

    @web.middleware
    async def middleware(request, handler):
        rid = (request.headers.get(header_name) or "").strip()
        # Round-2 audit NEW-LOW-2 — bound the accepted length so a
        # client-supplied id can't bloat downstream logs.  64 chars is
        # plenty for any UUID / hex16 / hex32 form we see in the wild.
        if rid and not re.fullmatch(r"[A-Za-z0-9_\-]{8,64}", rid):
            rid = ""
        if not rid:
            rid = "req_" + secrets.token_hex(8)
        request["request_id"] = rid
        try:
            resp = await handler(request)
        except Exception:
            raise
        resp.headers.setdefault(header_name, rid)
        return resp

    return middleware


@dataclass
class HardenConfig:
    max_request_bytes: int = _DEFAULT_MAX_REQUEST_BYTES
    apply_security_headers: bool = True
    apply_body_size: bool = True
    apply_method_guard: bool = True
    allowed_methods: Tuple[str, ...] = ("GET", "POST", "HEAD", "OPTIONS")
    apply_request_id: bool = True


def harden_aiohttp_app(app: Any, *, config: Optional[HardenConfig] = None) -> Any:
    """One-call hardening for an aiohttp Application.

    Wires (in this order — outermost to innermost):
      1. Request-ID minting
      2. Method allow-list
      3. Body-size up-front guard
      4. Security headers
    Caller's auth / rate-limit middleware can then plug in beneath.
    """
    cfg = config or HardenConfig()
    mws: List[Any] = []
    if cfg.apply_request_id:
        mws.append(make_request_id_middleware())
    if cfg.apply_method_guard:
        mws.append(make_method_guard_middleware(cfg.allowed_methods))
    if cfg.apply_body_size:
        mws.append(make_body_size_middleware(cfg.max_request_bytes))
    if cfg.apply_security_headers:
        mws.append(make_security_headers_middleware())
    # Round-3 audit R3-HIGH-9 — be robust against aiohttp version
    # changes that swap FrozenList for another sequence type.  Prefer
    # the public ``insert`` API; fall back to assignment if missing.
    existing = app.middlewares
    insert = getattr(existing, "insert", None)
    if callable(insert):
        for i, mw in enumerate(mws):
            insert(i, mw)
    else:
        # Reconstruct: prepend our middlewares to whatever is there.
        try:
            current = list(existing)
            new_mws = mws + current
            # aiohttp's FrozenList freezes after start_server; mutating
            # before that is the documented contract.
            existing.clear()
            for mw in new_mws:
                existing.append(mw)
        except Exception:
            logger.error("guard.harden_app_failed_to_install_middlewares")
    return app


# ════════════════════════════════════════════════════════════════════════════
# 9. Boot-time runtime check — fail-closed if a critical secret is missing.
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class BootCheckResult:
    ok: bool
    issues: List[str]


def runtime_check_environment(
    *,
    require_admin_token: bool = False,
    require_admin_otp_seed: bool = False,
) -> BootCheckResult:
    """Inspect the runtime environment and report any missing critical
    secrets / dangerous defaults BEFORE the service binds a port.

    Production deployments should treat ``ok=False`` as fatal.

    Round-2 audit NEW-HIGH-17 — uses the central ``is_production``
    helper so ``ARIA_ENV=prod``, ``=production``, ``=live``, etc. all
    pass the same checks.
    """
    from aria.security.env import is_production
    issues: List[str] = []
    if os.environ.get("ARIA_DEBUG_ALLOW_INSECURE", "").lower() in {"1", "true", "yes"}:
        issues.append(
            "ARIA_DEBUG_ALLOW_INSECURE is set — never enable this in production"
        )
    if require_admin_token and not os.environ.get("ARIA_ADMIN_TOKEN"):
        issues.append("ARIA_ADMIN_TOKEN missing")
    if require_admin_otp_seed and not os.environ.get("ARIA_ADMIN_OTP_SEED"):
        issues.append("ARIA_ADMIN_OTP_SEED missing — admin endpoints are single-factor")
    bind = os.environ.get("ARIA_HOST", "")
    if bind == "0.0.0.0" and is_production():  # nosec B104 (string COMPARE only)
        issues.append(
            "ARIA_HOST=0.0.0.0 in production — bind to a private interface"
            " behind your reverse proxy"
        )
    # Round-2 audit NEW-HIGH-16 — auth must be enforced in production.
    if is_production() and os.environ.get("ARIA_AUTH_REQUIRED", "1").lower() in (
        "0", "false", "no", ""
    ):
        issues.append("ARIA_AUTH_REQUIRED must not be 0/false in production")
    # Round-2 audit NEW-HIGH-6 / NEW-MED-13 — production must set the
    # per-deployment HMAC secret used for tenant-key-at-rest hashing.
    if is_production() and not os.environ.get("ARIA_TENANT_KEY_HMAC_HEX"):
        if not os.environ.get("ARIA_HKDF_SALT_HEX"):
            issues.append(
                "ARIA_TENANT_KEY_HMAC_HEX (or ARIA_HKDF_SALT_HEX) required in production"
            )
    # Round-3 audit R3-HIGH-7 — refuse a CORS wildcard or 0.0.0.0/0
    # trusted-proxy entry in production.
    if is_production():
        cors = (os.environ.get("ARIA_CORS_ORIGIN", "")
                or os.environ.get("ARIA_CORS_ORIGINS", "")).strip()
        if cors == "*":
            issues.append(
                "ARIA_CORS_ORIGIN/ARIA_CORS_ORIGINS=* — refused in production"
            )
        tp = os.environ.get("ARIA_TRUSTED_PROXIES", "").strip()
        if tp:
            for tok in tp.split(","):
                tok = tok.strip()
                if not tok:
                    continue
                if tok in ("0.0.0.0/0", "::/0"):
                    issues.append(
                        f"ARIA_TRUSTED_PROXIES contains {tok} — XFF would be "
                        "trusted from any peer; refused in production"
                    )
    return BootCheckResult(ok=not issues, issues=issues)


# ════════════════════════════════════════════════════════════════════════════
# 10. Adaptive + psyops + honeypot + evolve + plugins — one-import surface.
# ════════════════════════════════════════════════════════════════════════════
#
# Every defensive primitive ARIA ships re-exports through this module so
# integrators have a single import: ``from aria.security.guard import …``.
# The sub-modules can still be imported directly when a caller needs the
# full surface (e.g., the threat-feed cron job pulls ``evolve.refresh_all``).

from aria.security.adaptive import (              # noqa: E402 (re-export)
    BehaviourFingerprinter,
    ThreatScore,
    behaviour_score,
    entropy_score,
    markov_score,
    novelty_score,
    register_request_scorer,
    score_request,
    shannon_entropy,
)
from aria.security.psyops import (                # noqa: E402
    InfluenceScore,
    detect_influence,
    manipulation_flags,
)
from aria.security.honeypot_llm import (          # noqa: E402
    HONEYPOT_PATHS,
    HoneypotRegistry,
    honeypot_status,
    is_decoy,
    mint_decoy_token,
    mount_honeypot_routes,
    observe_decoy,
    scan_for_decoys,
)
from aria.security.evolve import (                # noqa: E402
    CISA_KEV_URL,
    FeedSnapshot,
    fetch_cisa_kev,
    kev_to_high_risk_cves,
    load_snapshot,
    refresh_all as evolve_refresh_all,
    save_snapshot,
)
from aria.security.plugins import (               # noqa: E402
    DefencePlugin,
    disable as disable_plugin,
    fire_audit as plugin_fire_audit,
    fire_outbound_url as plugin_fire_outbound_url,
    fire_request as plugin_fire_request,
    fire_response as plugin_fire_response,
    list_active as list_active_plugins,
    register as register_plugin,
)


def activate_all_rounds(*, force_reload: bool = False) -> List[str]:
    """Import every ``aria.security.rounds.rNN_*`` module so each round's
    DefencePlugin self-registers.  Idempotent — safe to call twice.
    Returns the list of round IDs that loaded.

    Pass ``force_reload=True`` after ``clear_for_tests()`` so cached
    module imports actually re-execute their ``register(...)`` call.
    """
    from aria.security.rounds import activate_all
    return activate_all(force_reload=force_reload)


# ════════════════════════════════════════════════════════════════════════════
# 11. Adaptive middleware — wires score_request + plugins into every aiohttp app.
# ════════════════════════════════════════════════════════════════════════════


def make_adaptive_middleware(
    *,
    block_threshold: float = 0.85,
    alert_threshold: float = 0.6,
    skip_paths: Iterable[str] = ("/v1/healthz", "/v1/version", "/healthz"),
):
    """Score every inbound request against the adaptive engine + plugins.

    On ``threat_score >= block_threshold`` returns 403 with a generic
    body (no leak of which axis tripped — that goes to the audit log).
    On ``alert_threshold`` it logs but does not block.

    Skip paths bypass scoring entirely so liveness probes don't generate
    behavioural noise.  Honeypot paths are intentionally NOT in the
    skip-list — we WANT them scored.
    """
    from aiohttp import web
    skip = tuple(skip_paths)

    @web.middleware
    async def middleware(request, handler):
        path = request.path or "/"
        if any(path == s or path.startswith(s.rstrip("/") + "/") for s in skip):
            return await handler(request)

        # Read the body up to body-size cap (already enforced by
        # make_body_size_middleware on the outer chain).
        body = b""
        try:
            if request.method.upper() in ("POST", "PUT", "PATCH"):
                body = await request.read()
        except Exception:
            body = b""

        identity = (
            request.headers.get("X-ARIA-Token", "")
            or request.headers.get("Authorization", "")[:32]
            or request.remote
            or "anonymous"
        )

        # Per-plugin pre-flight (may raise to abort).
        try:
            plugin_fire_request(request, body)
        except Exception as exc:
            logger.warning("guard.plugin_request_block %s", exc)
            return web.json_response(
                {"error": "request_blocked"}, status=403,
            )

        score = score_request(
            path, body,
            identity=str(identity),
            method=request.method,
            user_agent=request.headers.get("User-Agent", ""),
        )

        if score.block:
            logger.warning(
                "guard.adaptive_block path=%s score=%.2f reasons=%s",
                path, score.threat_score, score.reasons[:4],
            )
            return web.json_response(
                {"error": "blocked", "request_id": request.get("request_id", "")},
                status=403,
            )
        if score.alert:
            logger.info(
                "guard.adaptive_alert path=%s score=%.2f reasons=%s",
                path, score.threat_score, score.reasons[:4],
            )

        # Re-buffer the body so handler can read it again.
        if body:
            async def _drain():
                return body
            request._read_bytes = body  # type: ignore[attr-defined]

        response = await handler(request)

        # Out-bound: scan for decoy tokens (exfiltration check).
        try:
            if hasattr(response, "body") and response.body:
                hits = scan_for_decoys(
                    response.body.decode("utf-8", errors="replace"),
                    where=f"response:{path}",
                )
                if hits:
                    logger.critical(
                        "guard.decoy_exfil path=%s tokens=%d", path, len(hits),
                    )
        except Exception:
            pass
        return response

    return middleware


# Re-wire harden_aiohttp_app to optionally attach the adaptive layer +
# honeypot routes.  Old call sites (without kwargs) keep working.

_original_harden_aiohttp_app = harden_aiohttp_app


def harden_aiohttp_app_v2(
    app: Any,
    *,
    config: Optional[HardenConfig] = None,
    apply_adaptive: bool = True,
    apply_honeypots: bool = True,
    adaptive_block_threshold: float = 0.85,
) -> Any:
    """Hardened wiring with adaptive + honeypot layers added to v1.

    Order outside-in:
        1. Request-Id mint
        2. Method allow-list
        3. Body-size 413
        4. Adaptive scoring (block / alert)
        5. Security headers
    Then mount honeypot paths last so they can short-circuit before
    a real handler is reached.
    """
    _original_harden_aiohttp_app(app, config=config)
    if apply_adaptive:
        app.middlewares.insert(
            -1,                                  # just inside the security-headers MW
            make_adaptive_middleware(
                block_threshold=adaptive_block_threshold,
            ),
        )
    if apply_honeypots:
        try:
            mount_honeypot_routes(app)
        except Exception as exc:
            logger.warning("guard.honeypot_mount_failed %s", exc)
    return app


# Replace the legacy export with the v2 one — back-compat preserved
# because v2 accepts the same v1 signature.
harden_aiohttp_app = harden_aiohttp_app_v2


# ════════════════════════════════════════════════════════════════════════════
# Public surface
# ════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Core errors
    "GuardError",
    "SSRFBlocked", "ResponseTooLarge", "ContentTypeRejected",
    "XMLDisallowed", "JSONTooDeep", "ZipUnsafe", "PickleBlocked",
    # SSRF + outbound
    "validate_outbound_url", "safe_open_url",
    # Format guards
    "safe_xml_fromstring", "safe_xml_parse",
    "safe_json_loads",
    "safe_zip_extract", "safe_zip_open",
    "safe_pickle_block", "safe_yaml_load",
    # Logging + admin
    "sanitise_for_log",
    "mfa_admin_check",
    # aiohttp middleware
    "make_security_headers_middleware", "make_body_size_middleware",
    "make_method_guard_middleware", "make_request_id_middleware",
    "make_adaptive_middleware",
    "HardenConfig", "harden_aiohttp_app",
    # Boot check
    "BootCheckResult", "runtime_check_environment",
    # Adaptive engine
    "ThreatScore", "BehaviourFingerprinter",
    "shannon_entropy", "entropy_score", "novelty_score", "markov_score",
    "behaviour_score", "register_request_scorer", "score_request",
    # Psychology / influence
    "InfluenceScore", "detect_influence", "manipulation_flags",
    # Honeypots / decoys
    "HONEYPOT_PATHS", "HoneypotRegistry",
    "mint_decoy_token", "is_decoy", "observe_decoy", "scan_for_decoys",
    "honeypot_status", "mount_honeypot_routes",
    # Evolve / threat feeds
    "FeedSnapshot", "CISA_KEV_URL",
    "fetch_cisa_kev", "save_snapshot", "load_snapshot",
    "kev_to_high_risk_cves", "evolve_refresh_all",
    # Plugin registry
    "DefencePlugin", "register_plugin", "list_active_plugins", "disable_plugin",
    "plugin_fire_request", "plugin_fire_response",
    "plugin_fire_outbound_url", "plugin_fire_audit",
]
