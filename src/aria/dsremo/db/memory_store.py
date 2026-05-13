"""In-memory store — drop-in replacement for DB queries in unit tests.

Used exclusively by the test suite via `create_app(demo=True)`.
All data lives in module-level dicts and is reset between test runs.
Never used in production — the server always connects to PostgreSQL.

Implements the same async interface as dsremo.db.queries so the rest of the
codebase doesn't need to know the difference.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock

import structlog

from aria.dsremo.core.models import Anomaly, TelemetryPoint

logger = structlog.get_logger()

# --- In-memory storage ---
_lock = Lock()
_telemetry: list[dict] = []
_anomalies: list[dict] = []
_alerts: list[dict] = []
_api_keys: list[dict] = []
_channel_configs: dict[tuple[str, str], dict] = {}  # (satellite_id, parameter) → config
_alert_configs: dict[str, dict] = {}               # tenant_id → config
_channels_seen: dict[tuple[str, str], dict] = {}   # (satellite_id, parameter) → metadata
_satellites_seen: dict[str, dict] = {}             # satellite_id → metadata
_mission_configs: dict[tuple[str, str], dict] = {} # (tenant_id, satellite_id) → mission config (V3-F4)
_MAX_TELEMETRY = 100_000  # cap to prevent OOM in long demos

# --- Admin stores (seeded with demo defaults) ---
_users: dict[str, dict] = {}          # user_id → user record
_tenants: dict[str, dict] = {}        # tenant_id → tenant record
_admin_api_keys: list[dict] = []      # key records (separate from RLS-scoped _api_keys)

# Seed demo tenants and admin user so the Admin tab works out-of-box
_demo_admin_id = str(uuid.uuid4())
_tenants["default"] = {
    "id": "default",
    "name": "Default Tenant",
    "plan": "free",
    "active": True,
    "settings": {},
    "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
}
_tenants["esa-mission1"] = {
    "id": "esa-mission1",
    "name": "ESA Mission 1",
    "plan": "enterprise",
    "active": True,
    "settings": {},
    "created_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
}
_tenants["satnogs"] = {
    "id": "satnogs",
    "name": "SatNOGS Network",
    "plan": "pro",
    "active": True,
    "settings": {},
    "created_at": datetime(2024, 1, 3, tzinfo=timezone.utc),
}
_users[_demo_admin_id] = {
    "id": _demo_admin_id,
    "tenant_id": "default",
    "email": "admin@demo.local",
    "display_name": "Demo Admin",
    "phone": "",
    "role": "admin",
    "active": True,
    "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "last_login": None,
    "password_hash": "",  # login not supported in demo mode
}


def _point_to_dict(p: TelemetryPoint) -> dict:
    return {
        "satellite_id": p.satellite_id,
        "timestamp": p.timestamp,
        "subsystem": p.subsystem,
        "parameter": p.parameter,
        "value": p.value,
        "unit": p.unit,
        "quality": p.quality,
    }


def _anomaly_to_dict(a: Anomaly) -> dict:
    return {
        "id": a.id,
        "satellite_id": a.satellite_id,
        "timestamp": a.timestamp,
        "subsystem": a.subsystem,
        "parameter": a.parameter,
        "value": a.value,
        "severity": a.severity.value,
        "confidence": a.confidence,
        "detectors_triggered": list(a.detectors_triggered),
        "explanation": a.explanation,
        "root_cause_group": a.root_cause_group,
        "contributing_params": json.dumps(a.contributing_params),
        "reviewed": False,
        "false_positive": False,
    }


# ---------------------------------------------------------------------------
# Telemetry (same signatures as queries.py)
# ---------------------------------------------------------------------------

async def insert_telemetry(points: list[TelemetryPoint]) -> int:
    if not points:
        return 0
    with _lock:
        for p in points:
            _telemetry.append(_point_to_dict(p))
        # Trim oldest if over cap
        if len(_telemetry) > _MAX_TELEMETRY:
            del _telemetry[: len(_telemetry) - _MAX_TELEMETRY]
    return len(points)


async def get_telemetry(
    satellite_id: str,
    parameter: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 1000,
) -> list[dict]:
    with _lock:
        results = [r for r in _telemetry if r["satellite_id"] == satellite_id]
    if parameter:
        results = [r for r in results if r["parameter"] == parameter]
    if since:
        results = [r for r in results if r["timestamp"] >= since]
    if until:
        results = [r for r in results if r["timestamp"] <= until]
    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results[:min(limit, 10_000)]


async def get_recent_telemetry_window(
    satellite_id: str,
    parameter: str,
    window_size: int = 300,
) -> list[dict]:
    with _lock:
        results = [
            {"timestamp": r["timestamp"], "value": r["value"], "quality": r["quality"]}
            for r in _telemetry
            if r["satellite_id"] == satellite_id and r["parameter"] == parameter
        ]
    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results[:window_size]


async def get_latest_values(satellite_id: str) -> list[dict]:
    with _lock:
        by_param: dict[str, dict] = {}
        for r in _telemetry:
            if r["satellite_id"] != satellite_id:
                continue
            param = r["parameter"]
            if param not in by_param or r["timestamp"] > by_param[param]["timestamp"]:
                by_param[param] = r
    return list(by_param.values())


# ---------------------------------------------------------------------------
# Anomalies
# ---------------------------------------------------------------------------

async def insert_anomaly(anomaly: Anomaly) -> str:
    with _lock:
        _anomalies.append(_anomaly_to_dict(anomaly))
    return anomaly.id


async def get_anomalies(
    satellite_id: str | None = None,
    severity: str | None = None,
    since: datetime | None = None,
    before: datetime | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    include_false_positives: bool = False,
    ml_only: bool | None = None,
) -> list[dict]:
    with _lock:
        results = list(_anomalies)
    if not include_false_positives:
        results = [r for r in results if not r.get("false_positive", False)]
    if satellite_id:
        results = [r for r in results if r["satellite_id"] == satellite_id]
    if severity:
        results = [r for r in results if r["severity"] == severity]
    if since:
        results = [r for r in results if r["timestamp"] >= since]
    if before:
        results = [r for r in results if r["timestamp"] < before]
    if date_from:
        results = [r for r in results if r["timestamp"] >= date_from]
    if date_to:
        results = [r for r in results if r["timestamp"] <= date_to]
    _ML_DETS = {"lstm", "tcn"}
    if ml_only is True:
        results = [r for r in results
                   if r.get("detectors_triggered")
                   and set(r["detectors_triggered"]).issubset(_ML_DETS)]
    elif ml_only is False:
        results = [r for r in results
                   if not (r.get("detectors_triggered")
                           and set(r["detectors_triggered"]).issubset(_ML_DETS))]
    results.sort(key=lambda r: r["timestamp"], reverse=True)
    return results[:min(limit, 1000)]


async def get_anomaly_by_id(anomaly_id: str) -> dict | None:
    with _lock:
        for r in _anomalies:
            if r["id"] == anomaly_id:
                return r
    return None


async def update_anomaly_review(anomaly_id: str, *, false_positive: bool) -> bool:
    """Set reviewed=True and false_positive verdict. Returns True if found."""
    with _lock:
        for r in _anomalies:
            if r["id"] == anomaly_id:
                r["reviewed"] = True
                r["false_positive"] = false_positive
                return True
    return False


async def mark_false_positive(anomaly_id: str) -> bool:
    """Flag anomaly as false positive (backward-compat shim)."""
    return await update_anomaly_review(anomaly_id, false_positive=True)


async def get_telemetry_stats() -> dict:
    with _lock:
        return {
            "total_telemetry_points": len(_telemetry),
            "points_last_hour": 0,
            "active_satellites": len({t.get("satellite_id") for t in _telemetry}),
        }


async def get_anomaly_count() -> int:
    with _lock:
        return len(_anomalies)


async def get_anomaly_severity_counts() -> dict:
    counts: dict[str, int] = {}
    with _lock:
        for r in _anomalies:
            sev = r.get("severity", "watch")
            counts[sev] = counts.get(sev, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Incidents (Sprint 17 — Hierarchical Alert Routing)
# ---------------------------------------------------------------------------

_incidents: list[dict] = []


async def upsert_incident(incident: object) -> None:  # type: ignore[type-arg]
    """Insert or update an incident (in-memory shim for tests)."""
    from aria.dsremo.core.models import Incident  # noqa: PLC0415
    # R65 (2026-04-24): was `assert isinstance(...)` — stripped under -O.
    if not isinstance(incident, Incident):
        raise TypeError(f"upsert_incident expects Incident, got {type(incident).__name__}")
    with _lock:
        for i, existing in enumerate(_incidents):
            if existing["id"] == incident.id:
                _incidents[i] = _incident_to_dict(incident)
                return
        _incidents.append(_incident_to_dict(incident))


async def get_incidents_v2(
    satellite_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    with _lock:
        rows = list(_incidents)
    if satellite_id is not None:
        rows = [r for r in rows if r["satellite_id"] == satellite_id]
    if status is not None:
        rows = [r for r in rows if r["status"] == status]
    rows.sort(key=lambda r: r["last_anomaly_at"], reverse=True)
    return rows[:limit]


async def update_incident_status(incident_id: str, status: str) -> bool:
    with _lock:
        for r in _incidents:
            if r["id"] == incident_id:
                r["status"] = status
                return True
    return False


async def get_subsystem_health(satellite_id: str) -> list[dict]:
    """Memory-store shim — returns empty list (no channel_registry in tests)."""
    return []


def _incident_to_dict(incident: object) -> dict:
    from datetime import timezone  # noqa: PLC0415
    from aria.dsremo.core.models import Incident  # noqa: PLC0415
    # R65 (2026-04-24): was `assert isinstance(...)` — stripped under -O.
    if not isinstance(incident, Incident):
        raise TypeError(f"_incident_to_dict expects Incident, got {type(incident).__name__}")
    return {
        "id":                 incident.id,
        "satellite_id":       incident.satellite_id,
        "severity":           incident.severity.value,
        "status":             incident.status,
        "confidence":         incident.confidence,
        "channels":           list(incident.channels),
        "root_cause_summary": incident.root_cause_summary,
        "anomaly_count":      incident.anomaly_count,
        "first_anomaly_at":   incident.first_anomaly_at,
        "last_anomaly_at":    incident.last_anomaly_at,
        "closed_at":          incident.closed_at,
        "created_at":         datetime.now(timezone.utc),
    }


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

async def store_api_key(key_hash: str, label: str) -> None:
    record = {
        "key_hash": key_hash,
        "hash_prefix": key_hash[:8],
        "label": label,
        "active": True,
        "tenant_id": "default",
        "created_at": datetime.now(timezone.utc),
        "last_used_at": None,
    }
    with _lock:
        _api_keys.append(record)
        _admin_api_keys.append(record)


async def verify_api_key_exists(key_hash: str) -> bool:
    with _lock:
        return any(k["key_hash"] == key_hash and k["active"] for k in _api_keys)


# ---------------------------------------------------------------------------
# Satellites
# ---------------------------------------------------------------------------

async def get_known_satellites() -> list[str]:
    with _lock:
        sats = sorted(
            {r["satellite_id"] for r in _telemetry}
            | set(_satellites_seen.keys())
        )
    return sats


async def upsert_satellite_seen(satellite_id: str, ts: "datetime") -> None:
    """Demo stub: register or update satellite first/last seen timestamps."""
    with _lock:
        existing = _satellites_seen.get(satellite_id, {})
        _satellites_seen[satellite_id] = {
            "satellite_id": satellite_id,
            "first_telemetry_at": existing.get("first_telemetry_at", ts),
            "last_telemetry_at": ts,
        }


# ---------------------------------------------------------------------------
# Channel registry + per-channel config (demo stubs)
# ---------------------------------------------------------------------------

async def upsert_channel_seen(
    satellite_id: str,
    parameter: str,
    subsystem: str,
    unit: str,
    point_count: int = 1,
) -> None:
    """Demo stub: register or update channel metadata."""
    key = (satellite_id, parameter)
    with _lock:
        existing = _channels_seen.get(key, {})
        _channels_seen[key] = {
            "satellite_id": satellite_id,
            "parameter": parameter,
            "subsystem": subsystem,
            "unit": unit,
            "total_points": existing.get("total_points", 0) + point_count,
            "first_seen": existing.get("first_seen"),
            "last_seen": None,
        }


async def get_channel_stats(satellite_id: str | None = None) -> list[dict]:
    """Return registered channels. Includes XTCE-imported channels in demo mode."""
    with _lock:
        rows = list(_channels_seen.values())
    if satellite_id is not None:
        rows = [r for r in rows if r["satellite_id"] == satellite_id]
    return rows


async def get_channel_config(satellite_id: str, parameter: str) -> dict | None:
    """Return in-memory config override for the channel, or None."""
    with _lock:
        return dict(_channel_configs.get((satellite_id, parameter), {})) or None


async def upsert_channel_config(
    satellite_id: str,
    parameter: str,
    *,
    z_threshold: float | None = None,
    cusum_h: float | None = None,
    cusum_k: float | None = None,
    ewma_lambda: float | None = None,
    ewma_sigma_mult: float | None = None,
    min_confidence: float | None = None,
    alert_cooldown_s: int | None = None,
    variance_z_threshold: float | None = None,
) -> dict:
    """Insert or partial-update in-memory channel config. Returns the full row."""
    from datetime import timezone
    key = (satellite_id, parameter)
    with _lock:
        existing = _channel_configs.get(key, {})
        _FIELDS = ("z_threshold", "cusum_h", "cusum_k", "ewma_lambda",
                   "ewma_sigma_mult", "min_confidence", "alert_cooldown_s",
                   "variance_z_threshold")
        new_vals = dict(zip(
            _FIELDS,
            (z_threshold, cusum_h, cusum_k, ewma_lambda, ewma_sigma_mult,
             min_confidence, alert_cooldown_s, variance_z_threshold),
        ))
        merged = {
            f: (new_vals[f] if new_vals[f] is not None else existing.get(f))
            for f in _FIELDS
        }
        merged["updated_at"] = datetime.now(timezone.utc)
        merged["satellite_id"] = satellite_id
        merged["parameter"] = parameter
        _channel_configs[key] = merged
        return dict(merged)


async def delete_channel_config(satellite_id: str, parameter: str) -> bool:
    """Remove in-memory config override. Returns True if row existed."""
    key = (satellite_id, parameter)
    with _lock:
        existed = key in _channel_configs
        _channel_configs.pop(key, None)
    return existed


async def load_all_channel_configs(satellite_id: str | None = None) -> list[dict]:
    """Return all in-memory channel config rows (no RLS needed in demo mode)."""
    with _lock:
        configs = list(_channel_configs.values())
    if satellite_id is not None:
        configs = [c for c in configs if c.get("satellite_id") == satellite_id]
    return configs


# ---------------------------------------------------------------------------
# Alert dispatch records (demo stubs)
# ---------------------------------------------------------------------------

async def insert_alert(anomaly: "Anomaly") -> str:  # type: ignore[name-defined]
    """Stub: store alert in-memory."""
    from datetime import timezone
    import uuid as _uuid
    alert_id = str(_uuid.uuid4())
    title = f"[{anomaly.severity.value.upper()}] {anomaly.satellite_id} — {anomaly.parameter}"
    with _lock:
        _alerts.append({
            "id": alert_id,
            "satellite_id": anomaly.satellite_id,
            "severity": anomaly.severity.value,
            "title": title,
            "message": anomaly.explanation,
            "dispatched_at": datetime.now(timezone.utc),
            "acknowledged": False,
            "subsystem": anomaly.subsystem,
            "parameter": anomaly.parameter,
            "value": anomaly.value,
            "confidence": anomaly.confidence,
            "anomaly_timestamp": anomaly.timestamp,
            "explanation": anomaly.explanation,
        })
    return alert_id


async def get_alerts(
    satellite_id: str | None = None,
    severity: str | None = None,
    since: "datetime | None" = None,
    acknowledged: bool | None = None,
    limit: int = 100,
) -> list[dict]:
    """Demo stub: return in-memory alert records."""
    with _lock:
        results = list(_alerts)
    if satellite_id:
        results = [r for r in results if r["satellite_id"] == satellite_id]
    if severity:
        results = [r for r in results if r["severity"] == severity]
    if since:
        results = [r for r in results if r["dispatched_at"] >= since]
    if acknowledged is not None:
        results = [r for r in results if r["acknowledged"] == acknowledged]
    results.sort(key=lambda r: r["dispatched_at"], reverse=True)
    return results[:min(limit, 1000)]


async def acknowledge_alert(alert_id: str) -> bool:
    """Demo stub: mark alert acknowledged."""
    with _lock:
        for alert in _alerts:
            if alert["id"] == alert_id and not alert["acknowledged"]:
                alert["acknowledged"] = True
                return True
    return False


# ---------------------------------------------------------------------------
# Alert configs (per-tenant delivery settings — demo stubs)
# ---------------------------------------------------------------------------

async def upsert_alert_config(
    tenant_id: str,
    *,
    webhook_url: str | None = None,
    webhook_secret: str | None = None,
    email_to: list[str] | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    min_severity: str | None = None,
    dedup_window_s: int | None = None,
    escalation_delay_s: int | None = None,
    enabled: bool | None = None,
) -> dict:
    """Demo stub: insert or partial-update alert config in memory."""
    from datetime import timezone
    with _lock:
        existing = _alert_configs.get(tenant_id, {
            "tenant_id": tenant_id,
            "webhook_url": None,
            "webhook_secret": None,
            "email_to": None,
            "smtp_host": None,
            "smtp_port": 587,
            "smtp_user": None,
            "smtp_password": None,
            "min_severity": "warning",
            "dedup_window_s": 300,
            "escalation_delay_s": 600,
            "enabled": True,
            "updated_at": None,
        })
        # Partial update: only overwrite non-None values
        updates = {
            "webhook_url": webhook_url,
            "webhook_secret": webhook_secret,
            "email_to": email_to,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
            "smtp_password": smtp_password,
            "min_severity": min_severity,
            "dedup_window_s": dedup_window_s,
            "escalation_delay_s": escalation_delay_s,
            "enabled": enabled,
        }
        merged = dict(existing)
        for k, v in updates.items():
            if v is not None:
                merged[k] = v
        merged["updated_at"] = datetime.now(timezone.utc)
        _alert_configs[tenant_id] = merged
    return dict(merged)


async def get_alert_config(tenant_id: str | None = None) -> dict | None:
    """Demo stub: return alert config for the given (or default) tenant."""
    key = tenant_id or "default"
    with _lock:
        row = _alert_configs.get(key)
    return dict(row) if row else None


async def delete_alert_config(tenant_id: str) -> bool:
    """Demo stub: remove alert config."""
    with _lock:
        existed = tenant_id in _alert_configs
        _alert_configs.pop(tenant_id, None)
    return existed


async def load_all_alert_configs() -> list[dict]:
    """Demo stub: return all alert configs."""
    with _lock:
        return [dict(v) for v in _alert_configs.values() if v.get("enabled", True)]


# ---------------------------------------------------------------------------
# User management stubs (Sprint 7)
# ---------------------------------------------------------------------------

async def get_user_by_email(email: str) -> dict | None:
    """Demo stub: look up user by email (tenant-scoped via email match)."""
    with _lock:
        for u in _users.values():
            if u["email"] == email:
                return dict(u)
    return None


async def get_user_by_id(user_id: str) -> dict | None:
    """Demo stub: look up user by UUID."""
    with _lock:
        u = _users.get(user_id)
    return dict(u) if u else None


async def create_user(
    email: str,
    password_hash: str,
    role: str,
    display_name: str = "",
    phone: str = "",
) -> dict:
    """Demo stub: create a new tenant user."""
    user_id = str(uuid.uuid4())
    row = {
        "id": user_id,
        "tenant_id": "default",
        "email": email,
        "display_name": display_name,
        "phone": phone,
        "role": role,
        "active": True,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "password_hash": password_hash,
    }
    with _lock:
        _users[user_id] = row
    return dict(row)


async def list_users(limit: int = 100) -> list[dict]:
    """Demo stub: list all users in the demo tenant."""
    with _lock:
        rows = []
        for u in list(_users.values())[:limit]:
            row = dict(u)
            row.setdefault("display_name", "")
            row.setdefault("phone", "")
            rows.append(row)
        return rows


async def update_user_role(user_id: str, new_role: str) -> bool:
    """Demo stub: change user role."""
    with _lock:
        if user_id not in _users:
            return False
        _users[user_id]["role"] = new_role
    return True


async def deactivate_user_by_id(user_id: str) -> bool:
    """Demo stub: deactivate user."""
    with _lock:
        if user_id not in _users or not _users[user_id].get("active"):
            return False
        _users[user_id]["active"] = False
    return True


async def reactivate_user(user_id: str) -> bool:
    """Demo stub: reactivate user."""
    with _lock:
        if user_id not in _users or _users[user_id].get("active"):
            return False
        _users[user_id]["active"] = True
    return True


async def update_user_password(user_id: str, new_hash: str) -> bool:
    """Demo stub: update password hash."""
    with _lock:
        if user_id not in _users:
            return False
        _users[user_id]["password_hash"] = new_hash
    return True


async def revoke_all_user_tokens(user_id: str) -> None:
    """Demo stub: no-op (no persistent tokens in memory store)."""


async def update_last_login(user_id: str) -> None:
    """Demo stub: update last_login timestamp."""
    with _lock:
        if user_id in _users:
            _users[user_id]["last_login"] = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tenant management stubs (Sprint 7)
# ---------------------------------------------------------------------------

async def list_tenants() -> list[dict]:
    """Demo stub: list all tenants."""
    with _lock:
        return [dict(t) for t in _tenants.values()]


async def get_tenant_by_id(tenant_id: str) -> dict | None:
    """Demo stub: fetch tenant by ID."""
    with _lock:
        t = _tenants.get(tenant_id)
    return dict(t) if t else None


async def create_tenant(tenant_id: str, name: str, plan: str = "free") -> dict:
    """Demo stub: create a new tenant."""
    row = {
        "id": tenant_id,
        "name": name,
        "plan": plan,
        "active": True,
        "settings": {},
        "created_at": datetime.now(timezone.utc),
    }
    with _lock:
        if tenant_id in _tenants:
            raise ValueError(f"unique constraint: tenant '{tenant_id}' already exists")
        _tenants[tenant_id] = row
    return dict(row)


async def update_tenant(
    tenant_id: str,
    name: str | None = None,
    active: bool | None = None,
) -> bool:
    """Demo stub: update tenant fields."""
    with _lock:
        if tenant_id not in _tenants:
            return False
        if name is not None:
            _tenants[tenant_id]["name"] = name
        if active is not None:
            _tenants[tenant_id]["active"] = active
    return True


# ---------------------------------------------------------------------------
# API key management stubs (Sprint 7)
# ---------------------------------------------------------------------------

async def list_api_keys_for_tenant() -> list[dict]:
    """Demo stub: list all API keys for the demo tenant."""
    with _lock:
        return [dict(k) for k in _admin_api_keys if k.get("active", True)]


async def revoke_api_key_by_prefix(prefix: str) -> bool:
    """Demo stub: deactivate API keys matching the given prefix."""
    found = False
    with _lock:
        for k in _admin_api_keys:
            if k.get("hash_prefix", "").startswith(prefix):
                k["active"] = False
                found = True
    return found


# ---------------------------------------------------------------------------
# Mission Config (V3-F4) — in-memory fallback for /satellites/{sat}/context
# ---------------------------------------------------------------------------

async def upsert_mission_config(
    satellite_id: str,
    launch_epoch: float,
    design_life_days: int,
) -> dict:
    """In-memory upsert matching db.queries.upsert_mission_config."""
    if design_life_days <= 0:
        raise ValueError(f"design_life_days must be positive, got {design_life_days!r}")
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    tenant = get_tenant() or "default"
    now = datetime.now(timezone.utc)
    row = {
        "satellite_id": satellite_id,
        "launch_epoch": float(launch_epoch),
        "design_life_days": int(design_life_days),
        "updated_at": now,
    }
    with _lock:
        _mission_configs[(tenant, satellite_id)] = dict(row)
    return row


async def get_mission_config(satellite_id: str) -> dict | None:
    """In-memory lookup matching db.queries.get_mission_config."""
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    tenant = get_tenant() or "default"
    with _lock:
        row = _mission_configs.get((tenant, satellite_id))
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Calibration hot/cold (V3-B3) — in-memory fallbacks
# ---------------------------------------------------------------------------

_calibration_hot:  dict[tuple[str, str, str], dict] = {}  # (tenant, sat, param) → hot stats
_calibration_cold: dict[tuple[str, str, str], dict] = {}  # (tenant, sat, param) → cold JSON


async def upsert_calibration_hot(
    satellite_id: str,
    parameter: str,
    running_sum: float,
    running_sumsq: float,
    sample_count: int,
    last_value: float | None = None,
    last_value_epoch: float | None = None,
) -> dict:
    if sample_count < 0:
        raise ValueError(f"sample_count must be ≥ 0, got {sample_count!r}")
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    tenant = get_tenant() or "default"
    row = {
        "satellite_id":     satellite_id,
        "parameter":        parameter,
        "running_sum":      float(running_sum),
        "running_sumsq":    float(running_sumsq),
        "sample_count":     int(sample_count),
        "last_value":       None if last_value is None else float(last_value),
        "last_value_epoch": None if last_value_epoch is None else float(last_value_epoch),
        "updated_at":       datetime.now(timezone.utc),
    }
    with _lock:
        _calibration_hot[(tenant, satellite_id, parameter)] = dict(row)
    return row


async def get_calibration_hot(
    satellite_id: str,
    parameter: str,
) -> dict | None:
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    tenant = get_tenant() or "default"
    with _lock:
        row = _calibration_hot.get((tenant, satellite_id, parameter))
        return dict(row) if row else None


async def upsert_calibration_cold(
    satellite_id: str,
    parameter: str,
    cold_params: dict,
) -> None:
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    tenant = get_tenant() or "default"
    with _lock:
        _calibration_cold[(tenant, satellite_id, parameter)] = dict(cold_params)


async def get_calibration_cold(
    satellite_id: str,
    parameter: str,
) -> dict | None:
    from aria.dsremo.core.tenant import get_tenant  # noqa: PLC0415
    tenant = get_tenant() or "default"
    with _lock:
        row = _calibration_cold.get((tenant, satellite_id, parameter))
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Suppression persistence (Sprint 19 / P1-H) — in-memory fallbacks
# ---------------------------------------------------------------------------
# `detector.suppress_channel()` fires-and-forgets `queries.upsert_suppression`.
# In test_mode, `queries` is swapped to this module, so these stubs must
# exist — otherwise `asyncio.create_task(queries.upsert_suppression(...))`
# raises AttributeError and taints the event loop for subsequent tests in
# the same pytest session.

_suppressions_persisted: dict[tuple[str, str, str], dict] = {}


async def upsert_suppression(
    tenant_id: str, satellite_id: str, parameter: str,
    until_epoch: float, reason: str = "",
) -> None:
    with _lock:
        _suppressions_persisted[(tenant_id, satellite_id, parameter)] = {
            "tenant_id":    tenant_id,
            "satellite_id": satellite_id,
            "parameter":    parameter,
            "until_epoch":  float(until_epoch),
            "reason":       reason,
        }


async def delete_suppression(
    tenant_id: str, satellite_id: str, parameter: str,
) -> bool:
    with _lock:
        return _suppressions_persisted.pop(
            (tenant_id, satellite_id, parameter), None
        ) is not None


async def load_active_suppressions(tenant_id: str | None = None) -> list[dict]:
    import time as _time  # noqa: PLC0415
    now = _time.time()
    with _lock:
        if tenant_id:
            return [
                dict(v) for k, v in _suppressions_persisted.items()
                if k[0] == tenant_id and v["until_epoch"] > now
            ]
        return [
            dict(v) for v in _suppressions_persisted.values()
            if v["until_epoch"] > now
        ]
