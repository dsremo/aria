"""Conjunction-screener HTTP service — minimum viable product.

This is a *thin* wrapper around `aria.conjunction.*`.  It exposes a
JSON HTTPS API; the heavy lifting (SGP4, TCA finder, Foster Pc,
alert classifier) is unchanged.

What ships in v1:

  * Tenant-scoped API key auth (HMAC compare; rotated by operator).
  * Per-tenant rate limit (60 req/min / 10 000 req/day default).
  * Single-screen endpoint: primary TLE + N secondaries → per-pair
    risk record.
  * Foster Pc with optional per-object 3×3 covariance; falls back
    to operator-grade isotropic 250 m σ if covariance not provided.
  * Risk classification matching the ARIA CARA-class threshold
    (RED if Pc ≥ 1e-4 or miss < 100 m, YELLOW if Pc ≥ 1e-7 or miss
    < 1 km, else GREEN).

What is OUT of scope for v1:

  * Background bulk catalog screening (operator brings their own
    TLE list per request — the service is stateless).
  * Manoeuvre planning (RFC v2).
  * Streaming / WebSocket alerts.
  * Multi-tenant DB; v1 keeps tenant config in a JSON file.

The service is operationally honest: it computes verdicts based on
the TLEs *the operator provides*.  It does not pretend to have
inside knowledge of the full SpaceTrack catalog unless the
operator explicitly authorises ARIA to pull on their behalf.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import math
import os
import secrets
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import numpy as np


logger = logging.getLogger("aria.products.conjunction_screener")


VERSION = "1.0.0"

# Audit HIGH-2 — refuse to deserialise large secondaries arrays even
# though aiohttp's body cap is already 10 MiB.  R285-class limit.
MAX_SECONDARIES_PER_REQUEST = 1000

# Audit HIGH-1 — per-NDJSON-line write timeout for /v1/screen_bulk.
# A slow-reading client cannot pin a worker indefinitely.
NDJSON_LINE_WRITE_TIMEOUT_S = 2.0

# Audit HIGH-3 — global per-IP unauthenticated request bucket.  Bounds
# the work an anonymous attacker can extract by spamming the auth check.
UNAUTH_RATE_PER_MIN_PER_IP = 30
UNAUTH_RATE_PER_DAY_PER_IP = 5_000

# Audit MED-11 — clamp /v1/usage window query parameter.
USAGE_WINDOW_MIN_SECONDS = 60.0          # 1 minute
USAGE_WINDOW_MAX_SECONDS = 90.0 * 86_400  # 90 days

# Round-2 audit NEW-HIGH-2 — bound the rate-limiter dict so an
# attacker who can vary the bucket key (per IP, per tenant) cannot
# exhaust process memory.  ~100k distinct keys is well above any
# legitimate fleet size.
_MAX_RATE_LIMITER_KEYS = 100_000

# Round-2 audit NEW-HIGH-9 — bound admin-controlled rate-limit values
# so a compromised admin token can neither lock out a tenant nor mint
# a quota-free tenant.  Per-min upper bound is generous but finite.
_RATE_LIMIT_PER_MIN_MIN = 1
_RATE_LIMIT_PER_MIN_MAX = 10_000
_RATE_LIMIT_PER_DAY_MIN = 1
_RATE_LIMIT_PER_DAY_MAX = 10_000_000

# Round-2 audit NEW-HIGH-12 — clamp the search window so a single
# request cannot cause a multi-million-step coarse-step explosion.
_SEARCH_WINDOW_MIN = 1.0          # 1 minute
_SEARCH_WINDOW_MAX = 1440.0       # 1 day

# Round-2 audit NEW-CRIT-4 — XFF is honoured only when the immediate
# peer is on this allow-list.  Empty default (raw socket peer is used).
def _trusted_proxies_from_env() -> List[ipaddress._BaseNetwork]:
    raw = os.environ.get("ARIA_TRUSTED_PROXIES", "").strip()
    if not raw:
        return []
    out: List[ipaddress._BaseNetwork] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(ipaddress.ip_network(tok, strict=False))
        except ValueError:
            logger.warning("screener.bad_trusted_proxy entry=%s", tok)
    return out


def _safe_error(code: str, *, status: int = 500,
                exc: Optional[BaseException] = None,
                logger_name: str = "aria.security.error") -> Any:
    """Audit HIGH-4 — return only a fixed enum to the wire; log the full
    exception locally.  Never echo str(exc) to the client.  Importing
    here avoids a circular dependency with the web layer."""
    if exc is not None:
        logging.getLogger(logger_name).warning(
            "%s exc_type=%s", code, type(exc).__name__, exc_info=False,
        )
    from aiohttp import web
    return web.json_response({"error": code}, status=status)


# ── Request / response shapes ────────────────────────────────────


@dataclass
class TLEPayload:
    norad_id: str
    name: str
    line1: str
    line2: str
    radius_m: float = 1.0
    covariance_eci_km2: Optional[List[List[float]]] = None  # 3×3 optional


@dataclass
class ScreenRequest:
    primary: TLEPayload
    secondaries: List[TLEPayload]
    approx_tca_utc: Optional[str] = None
    search_window_minutes: float = 60.0
    operator_grade_sigma_km: float = 0.250


@dataclass
class ScreenResult:
    primary_norad_id: str
    secondary_norad_id: str
    tca_utc: str
    miss_distance_m: float
    relative_velocity_kmps: float
    pc_foster: float
    risk_level: str
    notes: str = ""


@dataclass
class ScreenResponse:
    request_id: str
    started_at_utc: str
    completed_at_utc: str
    elapsed_ms: float
    results: List[ScreenResult]
    version: str = VERSION


# ── Tenants + rate limiter ───────────────────────────────────────


def _default_tenants_path() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3] / "data" / "runtime" / "screener_tenants.json"


@dataclass
class TenantConfig:
    tenant_id: str
    api_key_hex: str   # 32-byte random in hex; HMAC compared
    rate_limit_per_min: int = 60
    rate_limit_per_day: int = 10_000

    def matches(self, presented_key: str) -> bool:
        """Constant-time compare — defends against timing oracles."""
        return hmac.compare_digest(self.api_key_hex, presented_key)


def _load_tenants(path: Optional[Path] = None) -> List[TenantConfig]:
    """Read the tenants config file.  Returns the demo tenant when no
    file is present and we are not running in production.

    Audit CRIT-4 — refuses to fall back to the demo tenant when
    ``ARIA_ENV=prod`` and the operator has not set
    ``ARIA_ALLOW_DEMO_TENANT=1``.  The demo key (``"d" * 64``) is a
    well-known credential and must never be part of the production
    accept-set.
    """
    from aria.security.env import is_production
    p = path or _default_tenants_path()
    if not p.is_file():
        allow = os.environ.get("ARIA_ALLOW_DEMO_TENANT", "").lower() in ("1", "true", "yes")
        if is_production() and not allow:
            raise RuntimeError(
                f"screener.tenants_missing — {p} not found and ARIA_ENV indicates "
                "production; supply a real tenants.json or set "
                "ARIA_ALLOW_DEMO_TENANT=1 explicitly (not recommended)"
            )
        logger.warning(
            "screener.demo_tenant_fallback path=%s — DO NOT USE IN PRODUCTION", p,
        )
        return [TenantConfig(
            tenant_id="demo",
            api_key_hex="d" * 64,    # demo only — refused in prod by CRIT-4 gate
            rate_limit_per_min=10,
            rate_limit_per_day=200,
        )]
    from aria.security.env import is_production
    out: List[TenantConfig] = []
    for raw in json.loads(p.read_text()).get("tenants", []):
        api_key = str(raw["api_key_hex"])
        # Round-2 audit NEW-HIGH-6 — even operator-supplied keys must
        # meet a minimum entropy floor.  In prod we reject anything
        # below 64 hex / 8 distinct characters; in dev we warn.
        if is_production():
            if len(api_key) < 64 or len(set(api_key)) < 8:
                raise RuntimeError(
                    f"screener.tenant_key_weak tenant_id={raw.get('tenant_id')} "
                    "— operator-supplied API key must be ≥ 64 chars with 8+ "
                    "distinct characters in production"
                )
        # Clamp rate-limit values regardless of source (NEW-HIGH-9).
        per_min = max(_RATE_LIMIT_PER_MIN_MIN,
                      min(int(raw.get("rate_limit_per_min", 60)),
                          _RATE_LIMIT_PER_MIN_MAX))
        per_day = max(_RATE_LIMIT_PER_DAY_MIN,
                      min(int(raw.get("rate_limit_per_day", 10_000)),
                          _RATE_LIMIT_PER_DAY_MAX))
        out.append(TenantConfig(
            tenant_id=str(raw["tenant_id"]),
            api_key_hex=api_key,
            rate_limit_per_min=per_min,
            rate_limit_per_day=per_day,
        ))
    return out


class _RateLimiter:
    """Token-bucket-ish per-tenant rate limit.  Two windows.

    Round-2 audit NEW-HIGH-2 — keys are bounded by an LRU eviction so
    an attacker varying the bucket key (per-IP, per-tenant) cannot
    exhaust memory.  Empty buckets are pruned opportunistically each
    check.
    """

    def __init__(self, max_keys: int = _MAX_RATE_LIMITER_KEYS) -> None:
        # OrderedDict for O(1) LRU eviction.
        self._minute: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self._day: "OrderedDict[str, Deque[float]]" = OrderedDict()
        self._max_keys = max_keys

    @staticmethod
    def _evict_oldest(d: OrderedDict, max_size: int) -> None:
        while len(d) >= max_size:
            d.popitem(last=False)

    def check(self, tenant: TenantConfig) -> Optional[str]:
        """Return None if allowed, or a reason-string if denied.

        Backward-compat shim — call :meth:`check_with_retry` for the
        full response carrying retry-after seconds.
        """
        denial = self.check_with_retry(tenant)
        return denial[0] if denial is not None else None

    def check_with_retry(
        self, tenant: TenantConfig,
    ) -> Optional[tuple]:
        """Return ``(reason, retry_after_seconds)`` if denied, else None.

        ``retry_after_seconds`` is the number of whole seconds the
        client must wait before retrying — derived from the oldest
        request inside the active window.
        """
        # Round-2 NEW-HIGH-9 / NEW-MED-7 — clamp configured rate
        # values so a sentinel of 0 / negative / huge cannot lock out
        # legitimate tenants or grant an unbounded budget.
        per_min = max(_RATE_LIMIT_PER_MIN_MIN,
                      min(int(tenant.rate_limit_per_min), _RATE_LIMIT_PER_MIN_MAX))
        per_day = max(_RATE_LIMIT_PER_DAY_MIN,
                      min(int(tenant.rate_limit_per_day), _RATE_LIMIT_PER_DAY_MAX))
        now = time.time()
        m = self._minute.get(tenant.tenant_id)
        d = self._day.get(tenant.tenant_id)
        if m is None:
            self._evict_oldest(self._minute, self._max_keys)
            m = deque()
            self._minute[tenant.tenant_id] = m
        if d is None:
            self._evict_oldest(self._day, self._max_keys)
            d = deque()
            self._day[tenant.tenant_id] = d
        while m and now - m[0] > 60.0:
            m.popleft()
        while d and now - d[0] > 86400.0:
            d.popleft()
        # Move-to-end so active keys stay in the LRU.
        self._minute.move_to_end(tenant.tenant_id)
        self._day.move_to_end(tenant.tenant_id)
        if len(m) >= per_min:
            retry_after = max(1, int(60.0 - (now - m[0]) + 1.0))
            return (
                f"per-minute rate limit ({per_min}) reached",
                retry_after,
            )
        if len(d) >= per_day:
            retry_after = max(1, int(86400.0 - (now - d[0]) + 1.0))
            return (
                f"per-day rate limit ({per_day}) reached",
                retry_after,
            )
        m.append(now)
        d.append(now)
        return None


# ── Core screener ────────────────────────────────────────────────


def _operator_covariance_3x3(sigma_km: float) -> np.ndarray:
    return np.diag([sigma_km ** 2] * 3)


def _project_to_encounter_plane(
    miss_eci_km: np.ndarray,
    rel_vel_eci_km_s: np.ndarray,
    cov_a: np.ndarray,
    cov_b: np.ndarray,
):
    rel_dir = rel_vel_eci_km_s / np.linalg.norm(rel_vel_eci_km_s)
    helper = (
        np.array([0.0, 0.0, 1.0]) if abs(rel_dir[2]) < 0.9
        else np.array([1.0, 0.0, 0.0])
    )
    e1 = helper - rel_dir * np.dot(helper, rel_dir)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(rel_dir, e1)
    P = np.column_stack([e1, e2])
    return (P.T @ miss_eci_km), (P.T @ (cov_a + cov_b) @ P)


def _classify(pc: float, miss_km: float) -> str:
    if pc >= 1.0e-4 or miss_km < 0.100:
        return "RED"
    if pc >= 1.0e-7 or miss_km < 1.000:
        return "YELLOW"
    return "GREEN"


class ConjunctionScreenerService:
    """The screening engine — pure functional, no global state."""

    def screen_pair(
        self,
        primary: TLEPayload,
        secondary: TLEPayload,
        approx_tca_utc: Optional[datetime],
        sigma_km: float,
        search_window_minutes: float,
    ) -> ScreenResult:
        from aria.conjunction.data.tle_parser import TLEParser
        from aria.conjunction.conjunction.tca_finder import TCAFinder
        from aria.conjunction.propagation.sgp4_propagator import SGP4Propagator
        from aria.conjunction.probability.foster import foster_pc

        prim = TLEParser.parse_tle(
            primary.line1, primary.line2, name=primary.name,
        )
        prim.radius_m = primary.radius_m
        sec = TLEParser.parse_tle(
            secondary.line1, secondary.line2, name=secondary.name,
        )
        sec.radius_m = secondary.radius_m

        # If approx TCA not given, default to "now" — caller should
        # supply this for backtests.
        seed = (
            approx_tca_utc
            if approx_tca_utc is not None
            else datetime.now(tz=timezone.utc)
        )
        finder = TCAFinder(
            coarse_step_s=10.0,
            search_window_minutes=search_window_minutes,
            refinement_tol_s=1e-3,
        )
        results = finder.find_tca(prim, sec, seed)
        if not results:
            return ScreenResult(
                primary_norad_id=primary.norad_id,
                secondary_norad_id=secondary.norad_id,
                tca_utc="",
                miss_distance_m=float("inf"),
                relative_velocity_kmps=0.0,
                pc_foster=0.0,
                risk_level="GREEN",
                notes="no TCA in search window",
            )
        tca, _ = results[0]
        sa = SGP4Propagator.propagate(prim, tca)
        sb = SGP4Propagator.propagate(sec, tca)
        miss_eci = sa.position - sb.position
        rel_vel = sa.velocity - sb.velocity
        miss_distance_m = float(np.linalg.norm(miss_eci)) * 1000.0
        rel_speed_kmps = float(np.linalg.norm(rel_vel))

        cov_a = _from_payload_covariance(primary, sigma_km)
        cov_b = _from_payload_covariance(secondary, sigma_km)
        miss_2d, cov_2d = _project_to_encounter_plane(
            miss_eci, rel_vel, cov_a, cov_b,
        )
        combined_radius_km = prim.radius_km + sec.radius_km
        pc = foster_pc(miss_2d, cov_2d, combined_radius_km)
        risk = _classify(pc, miss_distance_m / 1000.0)

        return ScreenResult(
            primary_norad_id=primary.norad_id,
            secondary_norad_id=secondary.norad_id,
            tca_utc=tca.isoformat(),
            miss_distance_m=miss_distance_m,
            relative_velocity_kmps=rel_speed_kmps,
            pc_foster=pc,
            risk_level=risk,
        )

    def screen(self, request: ScreenRequest) -> ScreenResponse:
        started = datetime.now(tz=timezone.utc)
        t0 = time.monotonic()
        approx_tca = (
            datetime.fromisoformat(request.approx_tca_utc.replace("Z", "+00:00"))
            if request.approx_tca_utc else None
        )
        results: List[ScreenResult] = []
        for sec in request.secondaries:
            try:
                r = self.screen_pair(
                    request.primary, sec,
                    approx_tca_utc=approx_tca,
                    sigma_km=request.operator_grade_sigma_km,
                    search_window_minutes=request.search_window_minutes,
                )
            except Exception as exc:
                # Round-2 audit NEW-HIGH-7 — never echo raw exception
                # text to the client; log with structured fields server-side.
                logger.warning(
                    "screen.pair_failed sec_id=%s exc_type=%s",
                    getattr(sec, "norad_id", "?"),
                    type(exc).__name__,
                )
                r = ScreenResult(
                    primary_norad_id=request.primary.norad_id,
                    secondary_norad_id=sec.norad_id,
                    tca_utc="",
                    miss_distance_m=float("inf"),
                    relative_velocity_kmps=0.0,
                    pc_foster=0.0,
                    risk_level="GREEN",
                    notes="computation_failed",
                )
            results.append(r)
        completed = datetime.now(tz=timezone.utc)
        return ScreenResponse(
            # Round-2 audit NEW-MED-8 — random id; not derivable from
            # (start_iso + norad_id).  16 hex = 64-bit collision space.
            request_id="req_" + secrets.token_hex(8),
            started_at_utc=started.isoformat(),
            completed_at_utc=completed.isoformat(),
            elapsed_ms=(time.monotonic() - t0) * 1000.0,
            results=results,
        )


def _from_payload_covariance(
    payload: TLEPayload, sigma_km: float,
) -> np.ndarray:
    """Use operator-supplied covariance if present, else fallback."""
    if payload.covariance_eci_km2 is not None:
        cov = np.asarray(payload.covariance_eci_km2, dtype=float)
        if cov.shape == (3, 3):
            return cov
    return _operator_covariance_3x3(sigma_km)


# ── HTTP layer (aiohttp) ─────────────────────────────────────────


def _validate_finite(name: str, value: float,
                     *, lo: float = -1e12, hi: float = 1e12) -> float:
    """Round-2 audit NEW-HIGH-8 — reject NaN / +-inf and out-of-range."""
    if not math.isfinite(value):
        raise ValueError(f"{name}_not_finite")
    if value < lo or value > hi:
        raise ValueError(f"{name}_out_of_range")
    return value


def _validate_tle_line(name: str, line: str) -> str:
    """Round-2 audit NEW-HIGH-8 — TLE line is exactly 69 ASCII chars
    (NORAD format); refuse anything else early."""
    if not isinstance(line, str):
        raise ValueError(f"{name}_not_string")
    if len(line) > 80:
        raise ValueError(f"{name}_too_long")
    if len(line) < 60 or len(line) > 80:
        # Allow some slack (some operators trim trailing whitespace) but
        # ASCII-only.
        raise ValueError(f"{name}_bad_length")
    if not all(0x20 <= ord(c) < 0x7F for c in line):
        raise ValueError(f"{name}_non_ascii")
    return line


def _validate_covariance(cov: Any) -> Optional[List[List[float]]]:
    """Round-2 audit NEW-HIGH-8 — refuse non-list, wrong-shape, NaN /
    inf entries."""
    if cov is None:
        return None
    if not isinstance(cov, list) or len(cov) != 3:
        raise ValueError("covariance_shape")
    out: List[List[float]] = []
    for row in cov:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("covariance_shape")
        new_row: List[float] = []
        for v in row:
            try:
                fv = float(v)
            except (TypeError, ValueError) as exc:
                raise ValueError("covariance_value_type") from exc
            if not math.isfinite(fv):
                raise ValueError("covariance_value_not_finite")
            if fv < 0 or fv > 1e6:
                raise ValueError("covariance_value_out_of_range")
            new_row.append(fv)
        out.append(new_row)
    return out


def _validate_payload_dict(p: Dict[str, Any], *, role: str) -> TLEPayload:
    """Round-2 audit NEW-HIGH-8 — validate every TLE field at the boundary."""
    if not isinstance(p, dict):
        raise ValueError(f"{role}_not_dict")
    norad_id = str(p.get("norad_id", "")).strip()
    if not norad_id or len(norad_id) > 32:
        raise ValueError(f"{role}_norad_id_invalid")
    name = str(p.get("name", ""))[:64]
    line1 = _validate_tle_line(f"{role}_line1", str(p.get("line1", "")))
    line2 = _validate_tle_line(f"{role}_line2", str(p.get("line2", "")))
    radius_m = _validate_finite(f"{role}_radius_m",
                                float(p.get("radius_m", 1.0)),
                                lo=0.001, hi=1000.0)
    cov = _validate_covariance(p.get("covariance_eci_km2"))
    return TLEPayload(
        norad_id=norad_id, name=name,
        line1=line1, line2=line2, radius_m=radius_m,
        covariance_eci_km2=cov,
    )


def _request_to_obj(d: dict) -> ScreenRequest:
    """Translate JSON request payload into ScreenRequest dataclass.

    Round-2 audit NEW-HIGH-8 — every field validated at the boundary.
    """
    if not isinstance(d, dict):
        raise ValueError("body_not_dict")
    if "primary" not in d:
        raise KeyError("primary")
    if "secondaries" not in d:
        raise KeyError("secondaries")
    primary = _validate_payload_dict(d["primary"], role="primary")
    secs_raw = d["secondaries"]
    if not isinstance(secs_raw, list):
        raise ValueError("secondaries_not_list")
    secondaries = [_validate_payload_dict(s, role="secondary") for s in secs_raw]
    approx_tca = d.get("approx_tca_utc")
    if approx_tca is not None and (
        not isinstance(approx_tca, str) or len(approx_tca) > 64
    ):
        raise ValueError("approx_tca_invalid")
    # Round-2 audit NEW-HIGH-12 — clamp the search window so a single
    # request cannot fan out to millions of coarse-step evaluations.
    sw = _validate_finite("search_window_minutes",
                          float(d.get("search_window_minutes", 60.0)),
                          lo=_SEARCH_WINDOW_MIN, hi=_SEARCH_WINDOW_MAX)
    sigma = _validate_finite("operator_grade_sigma_km",
                             float(d.get("operator_grade_sigma_km", 0.250)),
                             lo=1e-4, hi=10.0)
    return ScreenRequest(
        primary=primary,
        secondaries=secondaries,
        approx_tca_utc=approx_tca,
        search_window_minutes=sw,
        operator_grade_sigma_km=sigma,
    )


def _response_to_dict(r: ScreenResponse) -> dict:
    return {
        "request_id": r.request_id,
        "started_at_utc": r.started_at_utc,
        "completed_at_utc": r.completed_at_utc,
        "elapsed_ms": r.elapsed_ms,
        "version": r.version,
        "results": [asdict(x) for x in r.results],
    }


def create_app(
    tenants: Optional[List[TenantConfig]] = None,
    tenants_path: Optional[Path] = None,
    tenant_store: Optional["object"] = None,
    admin_token_hex: Optional[str] = None,
):
    """Build an aiohttp Application instance.

    Two tenant backends are supported:

    * Pass ``tenants`` (list of :class:`TenantConfig`) for the
      legacy in-memory mode used by unit tests.
    * Pass ``tenant_store`` (a :class:`TenantStore`) for the
      production SQLite-backed multi-tenant mode that supports
      key rotation + usage metering + admin endpoints.

    ``admin_token_hex`` is required to use the admin endpoints
    (``/v1/admin/*``).  In legacy mode it can be omitted.
    """
    try:
        from aiohttp import web
    except ImportError:                                   # pragma: no cover
        raise RuntimeError(
            "aiohttp required: pip install aiohttp"
        )

    using_store = tenant_store is not None
    if using_store:
        tenants_list: List[TenantConfig] = []  # not used in store mode
        by_key: Dict[str, TenantConfig] = {}
    else:
        tenants_list = (
            tenants if tenants is not None else _load_tenants(tenants_path)
        )
        by_key = {t.api_key_hex: t for t in tenants_list}

    rate = _RateLimiter()
    # Audit HIGH-3 — per-source-IP bucket so unauthenticated noise can't
    # consume the auth-check loop unbounded.
    unauth_rate = _RateLimiter()
    service = ConjunctionScreenerService()

    # Audit CRIT-3 — service-bound admin token.  The wire token must be
    # the HMAC-SHA-256 of the configured secret keyed by the service id;
    # presenting the bare secret to a sibling service no longer suffices.
    SERVICE_ID = b"aria-screener:v1"
    if admin_token_hex:
        _expected_admin = hmac.new(
            admin_token_hex.encode("utf-8"), SERVICE_ID, hashlib.sha256,
        ).hexdigest()
    else:
        _expected_admin = ""

    def _store_tenant_to_config(t) -> TenantConfig:
        return TenantConfig(
            tenant_id=t.tenant_id,
            api_key_hex=t.api_key_hex,
            rate_limit_per_min=t.rate_limit_per_min,
            rate_limit_per_day=t.rate_limit_per_day,
        )

    trusted_proxies = _trusted_proxies_from_env()

    def _client_ip(request) -> str:
        """Round-2 audit NEW-CRIT-4 — XFF is honoured ONLY when the
        immediate peer is on the ARIA_TRUSTED_PROXIES allow-list.
        Otherwise we fall back to the raw peer so an attacker cannot
        bypass the unauth bucket by spoofing XFF."""
        peer = (request.remote or "").strip()
        if not peer:
            return "unknown"
        if trusted_proxies:
            try:
                peer_ip = ipaddress.ip_address(peer)
            except ValueError:
                peer_ip = None
            if peer_ip is not None and any(peer_ip in net for net in trusted_proxies):
                xff = request.headers.get("X-Forwarded-For", "")
                first = xff.split(",")[0].strip()
                if first:
                    return first
        return peer

    def _per_ip_unauth_bucket_check(request) -> Optional[Any]:
        """Round-2 audit NEW-HIGH-11 / round-3 audit R3-HIGH-2 — only
        unauthenticated traffic consumes the per-IP bucket.  An
        authenticated tenant's quota is governed by its tenant bucket
        only, so a NAT-shared IP carrying many tenants does NOT lock
        them all out.  Returns a 429 response if the source IP is
        over budget, else None.
        """
        ip = _client_ip(request)
        bucket = TenantConfig(
            tenant_id=f"unauth:{ip}",
            api_key_hex="",
            rate_limit_per_min=UNAUTH_RATE_PER_MIN_PER_IP,
            rate_limit_per_day=UNAUTH_RATE_PER_DAY_PER_IP,
        )
        denial = unauth_rate.check_with_retry(bucket)
        if denial is not None:
            _, retry_after_s = denial
            return web.json_response(
                {"error": "rate_limited"},
                status=429,
                headers={"Retry-After": str(retry_after_s)},
            )
        return None

    # Backward-compat alias kept for any external caller still using the
    # old name; it now performs the unauth-only check.
    _per_ip_bucket_check = _per_ip_unauth_bucket_check

    def _audit_admin(action: str, **details) -> None:
        """Round-2 audit NEW-HIGH-10 — record every admin mutation in
        the hash-chained audit log."""
        try:
            from aria.security.audit import log_event
            log_event(
                event_type="admin",
                identity="admin_token",
                action=f"screener.{action}",
                result="executed",
                details=details,
                source="conjunction_screener",
            )
        except Exception:
            logger.exception("admin_audit_log_failed action=%s", action)

    async def _auth(request) -> Optional[TenantConfig]:
        token = request.headers.get("X-ARIA-Token", "")
        if not token:
            return None
        if using_store:
            t = tenant_store.find_by_key(token)  # type: ignore[union-attr]
            if t is None or t.suspended:
                return None
            return _store_tenant_to_config(t)
        return by_key.get(token)

    def _admin_authed(request) -> bool:
        if not _expected_admin:
            return False
        token = request.headers.get("X-ARIA-Admin-Token", "")
        if not token:
            return False
        # Constant-time compare against the SERVICE_ID-bound expected token
        # (audit CRIT-3).  A token minted for cubesat_deorbit is not valid here.
        return hmac.compare_digest(_expected_admin, token)

    async def healthz(request):
        # Audit HIGH-8 — never include version in unauthenticated /v1/healthz.
        return web.json_response({"ok": True})

    async def version(request):
        # Audit HIGH-8 — version is admin-only.
        if not _admin_authed(request):
            return web.json_response({"error": "unauthorised"}, status=401)
        return web.json_response({"service": "aria-screener", "version": VERSION})

    async def screen(request):
        t0 = time.monotonic()
        tenant = await _auth(request)
        if tenant is None:
            # Round-3 audit R3-HIGH-2 — unauth bucket fires only on the
            # failed-auth path so authed tenants behind a shared NAT
            # don't compete for the unauth budget.
            ip_resp = _per_ip_unauth_bucket_check(request)
            if ip_resp is not None:
                return ip_resp
            return web.json_response({"error": "unauthorised"}, status=401)
        denied_full = rate.check_with_retry(tenant)
        if denied_full is not None:
            _, retry_after_s = denied_full
            return web.json_response(
                {"error": "rate_limited", "retry_after_seconds": retry_after_s},
                status=429,
                headers={"Retry-After": str(retry_after_s)},
            )
        try:
            body = await request.json()
        except Exception as exc:
            return _safe_error("bad_request", status=400, exc=exc)
        try:
            # Audit HIGH-2 — pre-validate body shapes before deserialising.
            if not isinstance(body, dict):
                return _safe_error("bad_request", status=400)
            secondaries = body.get("secondaries") or []
            if isinstance(secondaries, list) and len(secondaries) > MAX_SECONDARIES_PER_REQUEST:
                return _safe_error("payload_too_large", status=413)
            req_obj = _request_to_obj(body)
            resp_obj = service.screen(req_obj)
        except KeyError as exc:
            # Field name is operator-controlled, but expose only the key name.
            return web.json_response(
                {"error": "missing_field", "field": str(exc).strip("'\"")[:64]},
                status=400,
            )
        except Exception as exc:
            return _safe_error("internal", status=500, exc=exc)
        if using_store:
            tenant_store.record_usage(  # type: ignore[union-attr]
                tenant.tenant_id, "screen",
                n_pairs=len(resp_obj.results),
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                status_code=200,
            )
        return web.json_response(_response_to_dict(resp_obj))

    async def screen_bulk(request):
        """Screen one primary against many secondaries, returning each
        result as one line of NDJSON.

        Audit HIGH-1 — every per-line write is bounded by
        ``NDJSON_LINE_WRITE_TIMEOUT_S``; a slow client cannot pin a
        worker indefinitely.  Audit HIGH-2 — total secondaries are
        capped before iteration begins.  Audit HIGH-4 — any per-pair
        failure surfaces as a generic ``computation_failed`` rather
        than echoing the exception.
        """
        t0 = time.monotonic()
        tenant = await _auth(request)
        if tenant is None:
            # Round-3 audit R3-HIGH-2 — unauth bucket on failed-auth only.
            ip_resp = _per_ip_unauth_bucket_check(request)
            if ip_resp is not None:
                return ip_resp
            return web.json_response({"error": "unauthorised"}, status=401)
        denied_full = rate.check_with_retry(tenant)
        if denied_full is not None:
            _, retry_after_s = denied_full
            return web.json_response(
                {"error": "rate_limited", "retry_after_seconds": retry_after_s},
                status=429,
                headers={"Retry-After": str(retry_after_s)},
            )
        try:
            body = await request.json()
        except Exception as exc:
            return _safe_error("bad_request", status=400, exc=exc)
        try:
            if not isinstance(body, dict):
                return _safe_error("bad_request", status=400)
            secondaries = body.get("secondaries") or []
            if isinstance(secondaries, list) and len(secondaries) > MAX_SECONDARIES_PER_REQUEST:
                return _safe_error("payload_too_large", status=413)
            req_obj = _request_to_obj(body)
        except KeyError as exc:
            return web.json_response(
                {"error": "missing_field", "field": str(exc).strip("'\"")[:64]},
                status=400,
            )
        except Exception as exc:
            return _safe_error("bad_request", status=400, exc=exc)

        approx_tca = (
            datetime.fromisoformat(
                req_obj.approx_tca_utc.replace("Z", "+00:00")
            ) if req_obj.approx_tca_utc else None
        )
        resp = web.StreamResponse(
            status=200,
            headers={"Content-Type": "application/x-ndjson"},
        )
        await resp.prepare(request)
        n_written = 0
        try:
            for sec in req_obj.secondaries:
                try:
                    r = service.screen_pair(
                        req_obj.primary, sec,
                        approx_tca_utc=approx_tca,
                        sigma_km=req_obj.operator_grade_sigma_km,
                        search_window_minutes=req_obj.search_window_minutes,
                    )
                except Exception as exc:
                    logger.warning(
                        "screen_bulk.pair_failed sec_id=%s exc_type=%s",
                        getattr(sec, "norad_id", "?"), type(exc).__name__,
                    )
                    r = ScreenResult(
                        primary_norad_id=req_obj.primary.norad_id,
                        secondary_norad_id=sec.norad_id,
                        tca_utc="",
                        miss_distance_m=float("inf"),
                        relative_velocity_kmps=0.0,
                        pc_foster=0.0,
                        risk_level="GREEN",
                        notes="computation_failed",
                    )
                line = json.dumps(asdict(r)) + "\n"
                # HIGH-1 — bound the per-line wait so a slow reader cannot
                # pin the worker.  If the timeout fires the connection is
                # closed and the loop terminates.
                try:
                    await asyncio.wait_for(
                        resp.write(line.encode("utf-8")),
                        timeout=NDJSON_LINE_WRITE_TIMEOUT_S,
                    )
                except (asyncio.TimeoutError, ConnectionResetError):
                    logger.warning(
                        "screen_bulk.slow_client_aborted tenant=%s n_written=%d",
                        tenant.tenant_id, n_written,
                    )
                    break
                n_written += 1
        finally:
            try:
                await resp.write_eof()
            except Exception as exc:
                # Round-2 audit NEW-MED-9 — never swallow silently.
                logger.warning(
                    "screen_bulk.write_eof_failed exc_type=%s",
                    type(exc).__name__,
                )
        if using_store:
            tenant_store.record_usage(  # type: ignore[union-attr]
                tenant.tenant_id, "screen_bulk",
                n_pairs=n_written,
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                status_code=200,
            )
        return resp

    async def usage(request):
        tenant = await _auth(request)
        if tenant is None:
            # Round-3 audit R3-HIGH-2 — unauth bucket on failed-auth only.
            ip_resp = _per_ip_unauth_bucket_check(request)
            if ip_resp is not None:
                return ip_resp
            return web.json_response({"error": "unauthorised"}, status=401)
        if not using_store:
            return web.json_response(
                {"error": "not_supported"}, status=501,
            )
        # Audit MED-11 — clamp window to a sensible range; default 24 h.
        try:
            raw_window = float(request.query.get("window_seconds", 86400.0))
        except ValueError:
            return web.json_response({"error": "bad_request"}, status=400)
        window = max(USAGE_WINDOW_MIN_SECONDS,
                     min(raw_window, USAGE_WINDOW_MAX_SECONDS))
        return web.json_response(
            tenant_store.usage_summary(tenant.tenant_id, window_seconds=window),  # type: ignore[union-attr]
        )

    async def rotate_key(request):
        """Operator-initiated key rotation.  Old key remains valid for
        the configured grace window so clients can update without
        downtime."""
        tenant = await _auth(request)
        if tenant is None:
            # Round-3 audit R3-HIGH-2 — unauth bucket on failed-auth only.
            ip_resp = _per_ip_unauth_bucket_check(request)
            if ip_resp is not None:
                return ip_resp
            return web.json_response({"error": "unauthorised"}, status=401)
        if not using_store:
            return web.json_response(
                {"error": "not_supported",
                 "reason": "key rotation requires SQLite tenant store"},
                status=501,
            )
        new_t = tenant_store.rotate_key(tenant.tenant_id)  # type: ignore[union-attr]
        _audit_admin("rotate_key", tenant_id=new_t.tenant_id)
        return web.json_response({
            "tenant_id": new_t.tenant_id,
            "new_api_key_hex": new_t.api_key_hex,
            "previous_expires_at": new_t.previous_expires_at,
            "rotated_at": new_t.last_rotated_at,
        })

    async def admin_create_tenant(request):
        # Audit LOW-2 — parse body first, then auth-check, so probing
        # /v1/admin/tenants without a token cannot distinguish "endpoint
        # exists, missing token" from "endpoint not present".
        try:
            body = await request.json()
        except Exception as exc:
            if not _admin_authed(request):
                return web.json_response({"error": "unauthorised"}, status=401)
            return _safe_error("bad_request", status=400, exc=exc)
        if not _admin_authed(request):
            return web.json_response({"error": "unauthorised"}, status=401)
        if not using_store:
            return web.json_response({"error": "not_supported"}, status=501)
        tenant_id = str(body.get("tenant_id", "")).strip()
        if not tenant_id or len(tenant_id) > 64 or not all(
            c.isalnum() or c in "-_" for c in tenant_id
        ):
            return web.json_response({"error": "invalid_tenant_id"}, status=400)
        # Round-2 audit NEW-HIGH-9 — clamp rate-limit values; refuse
        # non-numeric / out-of-range so a compromised admin token
        # cannot lock out a tenant or grant an unbounded budget.
        try:
            per_min = int(body.get("rate_limit_per_min", 60))
            per_day = int(body.get("rate_limit_per_day", 10_000))
        except (TypeError, ValueError):
            return web.json_response({"error": "invalid_rate_limit"}, status=400)
        if not (_RATE_LIMIT_PER_MIN_MIN <= per_min <= _RATE_LIMIT_PER_MIN_MAX):
            return web.json_response({"error": "invalid_rate_limit"}, status=400)
        if not (_RATE_LIMIT_PER_DAY_MIN <= per_day <= _RATE_LIMIT_PER_DAY_MAX):
            return web.json_response({"error": "invalid_rate_limit"}, status=400)
        try:
            t = tenant_store.create_tenant(  # type: ignore[union-attr]
                tenant_id, rate_limit_per_min=per_min, rate_limit_per_day=per_day,
            )
        except Exception as exc:
            return _safe_error("create_failed", status=400, exc=exc)
        # Round-2 audit NEW-HIGH-10 — every admin mutation must hit
        # the hash-chained audit log.  Tenant_id only, no token.
        _audit_admin("create_tenant", tenant_id=t.tenant_id,
                     per_min=per_min, per_day=per_day)
        return web.json_response({
            "tenant_id": t.tenant_id,
            "api_key_hex": t.api_key_hex,
            "rate_limit_per_min": t.rate_limit_per_min,
            "rate_limit_per_day": t.rate_limit_per_day,
        })

    async def admin_suspend(request):
        try:
            body = await request.json()
        except Exception:
            if not _admin_authed(request):
                return web.json_response({"error": "unauthorised"}, status=401)
            return web.json_response({"error": "bad_request"}, status=400)
        if not _admin_authed(request):
            return web.json_response({"error": "unauthorised"}, status=401)
        if not using_store:
            return web.json_response({"error": "not_supported"}, status=501)
        tenant_id = str(body.get("tenant_id", "")).strip()
        # Audit MED — refuse the operation against a non-existent tenant
        # so the admin can't poison the audit log with phantom suspends.
        if tenant_store.get(tenant_id) is None:  # type: ignore[union-attr]
            return web.json_response({"error": "tenant_not_found"}, status=404)
        suspended = bool(body.get("suspended", True))
        tenant_store.suspend(tenant_id, suspended=suspended)  # type: ignore[union-attr]
        _audit_admin("suspend_tenant", tenant_id=tenant_id, suspended=suspended)
        return web.json_response({"tenant_id": tenant_id, "suspended": suspended})

    async def admin_list(request):
        if not _admin_authed(request):
            return web.json_response({"error": "unauthorised"}, status=401)
        if not using_store:
            return web.json_response({"error": "not_supported"}, status=501)
        _audit_admin("list_tenants")
        # Audit LOW-3 — timestamps are gated behind ?include_audit=1 so
        # routine listings don't leak rotation cadence to admin observers.
        include_audit = request.query.get("include_audit", "").lower() in ("1", "true", "yes")
        out = []
        for t in tenant_store.list_all():  # type: ignore[union-attr]
            entry = {
                "tenant_id": t.tenant_id,
                "rate_limit_per_min": t.rate_limit_per_min,
                "rate_limit_per_day": t.rate_limit_per_day,
                "suspended": t.suspended,
            }
            if include_audit:
                entry["created_at"] = t.created_at
                entry["last_rotated_at"] = t.last_rotated_at
            out.append(entry)
        return web.json_response({"tenants": out})

    app = web.Application(client_max_size=10 * 1024 * 1024)  # 10 MB cap
    app.router.add_get("/v1/healthz", healthz)
    app.router.add_get("/v1/version", version)
    app.router.add_post("/v1/screen", screen)
    app.router.add_post("/v1/screen_bulk", screen_bulk)
    app.router.add_get("/v1/usage", usage)
    app.router.add_post("/v1/rotate_key", rotate_key)
    app.router.add_post("/v1/admin/tenants", admin_create_tenant)
    app.router.add_post("/v1/admin/tenants/suspend", admin_suspend)
    app.router.add_get("/v1/admin/tenants", admin_list)

    # R50 hardening: security headers, request-id, method allow-list, body
    # size guard.  The middleware chain is prepended so it wraps every
    # handler — see docs/SECURITY_AUDIT_R50.md.
    from aria.security.guard import HardenConfig, harden_aiohttp_app
    harden_aiohttp_app(
        app,
        config=HardenConfig(
            max_request_bytes=10 * 1024 * 1024,
            allowed_methods=("GET", "POST", "HEAD", "OPTIONS"),
        ),
    )

    # Carry handles on the app so tests can introspect.
    app["_tenants"] = tenants_list
    app["_tenant_store"] = tenant_store
    app["_service"] = service
    app["_rate_limiter"] = rate
    return app
