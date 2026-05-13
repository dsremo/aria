"""Pydantic schemas — the API contract.

These define exactly what goes in and out of every endpoint.
Strict validation here is our first line of defense.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class TelemetryIn(BaseModel):
    """Single telemetry point from a customer."""

    satellite_id: str = Field(..., min_length=1, max_length=128, examples=["SAT-01"])
    timestamp: datetime | float | str
    subsystem: str = Field(..., min_length=1, max_length=32, examples=["eps"])
    parameter: str = Field(..., min_length=1, max_length=128, examples=["battery_voltage"])
    value: float
    unit: str = Field(default="", max_length=16, examples=["V"])
    quality: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("satellite_id", "subsystem", "parameter")
    @classmethod
    def no_control_chars(cls, v: str) -> str:
        if any(ord(c) < 32 for c in v):
            raise ValueError("control characters not allowed")
        return v


class TelemetryBatchIn(BaseModel):
    """Batch of telemetry points — up to 500 per request."""

    points: list[TelemetryIn] = Field(..., min_length=1, max_length=500)
    hmac_signature: str | None = Field(default=None, max_length=128)


class TelemetryOut(BaseModel):
    """Telemetry point as returned by the API."""

    satellite_id: str
    timestamp: datetime
    subsystem: str
    parameter: str
    value: float
    unit: str
    quality: float


class AnomalyOut(BaseModel):
    """Anomaly record as returned by the API."""

    id: str
    satellite_id: str
    timestamp: datetime
    subsystem: str
    parameter: str
    value: float
    severity: str
    confidence: float
    detectors_triggered: list[str]
    explanation: str
    root_cause_group: str | None
    contributing_params: dict[str, float]
    # Sprint 12: operator feedback + ML visibility
    reviewed: bool = False
    false_positive: bool = False
    ml_only: bool = False  # True when lstm was the sole detector triggered


class FeedbackIn(BaseModel):
    """Operator feedback on an anomaly — marks it as TP or FP."""

    verdict: Literal["true_positive", "false_positive"]
    note: str | None = Field(default=None, max_length=500)


# ── Incident schemas (Sprint 17 — Hierarchical Alert Routing) ────────────────

class IncidentOut(BaseModel):
    """One incident as returned by the API.

    An incident groups all correlated anomalies on the same satellite within
    the correlation window.  Operators see incidents, not raw anomaly rows.
    """

    id: str
    satellite_id: str
    severity: str
    status: str                           # open / resolved / false_positive
    confidence: float
    channels: list[str]                   # all affected parameters
    root_cause_summary: str
    anomaly_count: int
    first_anomaly_at: Any
    last_anomaly_at: Any
    closed_at: Any | None = None


class IncidentStatusIn(BaseModel):
    """Operator sets incident status."""

    status: Literal["resolved", "false_positive"]


class IncidentSummary(BaseModel):
    """Open incident count + severity breakdown for a satellite."""

    satellite_id: str
    open_count: int
    critical: int = 0
    warning: int = 0
    watch: int = 0


class SubsystemHealth(BaseModel):
    """Per-subsystem health score for a satellite (Sprint 18).

    health = 1.0 − (anomalous_channels / total_channels).
    1.0 = fully nominal, 0.0 = all channels in open incidents.
    """

    subsystem: str
    total_channels: int
    anomalous_channels: int
    health: float  # 0.0 – 1.0


class SuppressionIn(BaseModel):
    """Request body for POST /satellites/{sat}/suppress."""

    parameter: str = Field(description="Channel to suppress (e.g. 'TEMP_PANEL_3')")
    duration_min: float = Field(
        gt=0, le=1440,
        description="Suppression duration in minutes (max 24h = 1440 min)"
    )
    reason: str | None = Field(
        default=None, max_length=256,
        description="Optional reason (e.g. 'planned momentum dump at 14:30 UTC')"
    )


class SuppressionOut(BaseModel):
    """Active suppression window for one channel."""

    satellite_id: str
    parameter: str
    duration_min: float
    reason: str | None
    until_epoch: float   # UTC epoch when suppression expires


class IngestResponse(BaseModel):
    """Response after telemetry ingestion."""

    accepted: int
    rejected: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


class CsvUploadResult(BaseModel):
    """Result of a CSV telemetry file upload."""

    satellite_id: str
    channels_loaded: int
    channels_skipped: int        # channels that already had >= skip_if_rows_gte rows
    total_rows_inserted: int
    rows_per_channel: dict[str, int]
    source_name: str


class HealthResponse(BaseModel):
    """System health check response."""

    status: str
    version: str
    db_connected: bool
    uptime_seconds: float


class SimulateRequest(BaseModel):
    """Request to start the simulator."""

    satellite_id: str = Field(default="DEMO-SAT-01", max_length=128)
    duration_seconds: int = Field(default=300, ge=10, le=86400)
    rate_hz: float = Field(default=1.0, ge=0.1, le=10.0)


class InjectRequest(BaseModel):
    """Request to inject a fault into the simulator."""

    fault_type: str = Field(..., examples=["drift", "spike", "dropout", "degradation"])
    subsystem: str = Field(..., examples=["eps", "thermal"])
    parameter: str = Field(..., examples=["battery_voltage"])
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    duration_seconds: int = Field(default=60, ge=1, le=3600)


class PaginatedResponse(BaseModel):
    """Wrapper for paginated list responses."""

    data: list[Any]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Auth schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Email + password login. tenant_id scopes the lookup (B2B pattern)."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    tenant_id: str = Field(default="default", min_length=1, max_length=64)


class RefreshRequest(BaseModel):
    """Opaque refresh token sent by the client to obtain a new access token."""

    refresh_token: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the access token expires


class UserOut(BaseModel):
    """Current user info (GET /auth/me)."""

    user_id: str
    email: str
    role: str
    tenant_id: str
    scope: str = ""   # "dsremo" for Dsremo staff users, "" for tenant users
    display_name: str = ""
    phone: str = ""


# ---------------------------------------------------------------------------
# Tenant management schemas
# ---------------------------------------------------------------------------

class TenantIn(BaseModel):
    """Create a new tenant."""

    id: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-z0-9\-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    plan: str = Field(default="free", max_length=32)


class TenantPatch(BaseModel):
    """Partial update for a tenant (name and/or active)."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    active: bool | None = None


class TenantOut(BaseModel):
    """Tenant record as returned by the API."""

    id: str
    name: str
    plan: str
    active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# User management schemas
# ---------------------------------------------------------------------------

_VALID_TENANT_ROLES = frozenset({"admin", "tenant_manager", "operator", "viewer", "report_only"})


class UserCreateRequest(BaseModel):
    """Create a new user within the current tenant."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="viewer")
    display_name: str = Field(default="", max_length=128)
    phone: str = Field(default="", max_length=32)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_TENANT_ROLES:
            raise ValueError(f"Invalid role. Choose from: {', '.join(sorted(_VALID_TENANT_ROLES))}")
        return v


class UpdateRoleRequest(BaseModel):
    """Change the role of a tenant user."""

    role: str = Field(..., min_length=1)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _VALID_TENANT_ROLES:
            raise ValueError(f"Invalid role. Choose from: {', '.join(sorted(_VALID_TENANT_ROLES))}")
        return v


class UserDetailOut(BaseModel):
    """Full user record returned by user management endpoints."""

    id: str
    email: str
    role: str
    active: bool
    created_at: datetime
    last_login: datetime | None = None
    display_name: str = ""
    phone: str = ""


# ---------------------------------------------------------------------------
# Password management schemas
# ---------------------------------------------------------------------------

class ChangePasswordRequest(BaseModel):
    """Authenticated user changes their own password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class AdminResetPasswordRequest(BaseModel):
    """Admin sets a new password for any user in their scope (no current password needed)."""

    new_password: str = Field(..., min_length=8, max_length=128)


# ---------------------------------------------------------------------------
# API key management schemas
# ---------------------------------------------------------------------------

class ApiKeyCreateRequest(BaseModel):
    """Request to generate a new API key for the current tenant."""

    label: str = Field(..., min_length=1, max_length=64)


class ApiKeyCreateResponse(BaseModel):
    """Returned once on key creation — key plaintext shown ONCE."""

    key: str          # full plaintext key (never stored)
    label: str
    hash_prefix: str  # first 16 chars of hash for identification
    tenant_id: str


class ApiKeyOut(BaseModel):
    """API key record as returned by the list endpoint."""

    label: str
    hash_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    active: bool


# ---------------------------------------------------------------------------
# Channel registry + per-channel threshold config schemas
# ---------------------------------------------------------------------------

class ChannelOut(BaseModel):
    """Channel metadata, calibration state, and current effective thresholds."""

    satellite_id: str
    parameter: str
    subsystem: str
    unit: str
    total_points: int
    first_seen: datetime | None
    last_seen: datetime | None
    # Calibration
    calibration_state: str | None   # "warming_up" | "calibrated" | "recalibrating" | None
    has_overrides: bool             # True if a channel_config row exists for this channel
    # Effective thresholds (per-channel override merged with global defaults)
    effective_z_threshold: float
    effective_min_confidence: float
    effective_alert_cooldown_s: int


class ChannelConfigIn(BaseModel):
    """Per-channel threshold overrides — all fields optional (partial update via PUT).

    Omit any field to keep the existing DB value.  Set to null explicitly to
    clear an override and revert that field to the global default.
    """

    z_threshold: float | None = Field(
        default=None, gt=0, description="z-score alarm threshold (> 0)"
    )
    cusum_h: float | None = Field(
        default=None, gt=0, description="CUSUM alarm level H (> 0)"
    )
    cusum_k: float | None = Field(
        default=None, gt=0, description="CUSUM allowance k (> 0)"
    )
    ewma_lambda: float | None = Field(
        default=None, gt=0, le=1.0,
        description="EWMA smoothing factor λ (0 < λ ≤ 1)"
    )
    ewma_sigma_mult: float | None = Field(
        default=None, gt=0,
        description="EWMA UCL/LCL sigma multiplier (> 0)"
    )
    min_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Minimum ensemble confidence to emit an anomaly (0.0–1.0)"
    )
    alert_cooldown_s: int | None = Field(
        default=None, ge=0,
        description="Per-channel alert cooldown in seconds (≥ 0)"
    )
    variance_z_threshold: float | None = Field(
        default=None, gt=0,
        description="Variance detector ratio threshold (> 0). Default: 2.5. "
                    "Lower for high-noise oscillatory channels; higher for stable DC channels."
    )
    hard_limit_high: float | None = Field(
        default=None,
        description="Absolute redline (high). Value > limit fires CRITICAL immediately, "
                    "bypassing ensemble confidence scoring."
    )
    hard_limit_low: float | None = Field(
        default=None,
        description="Absolute redline (low). Value < limit fires CRITICAL immediately."
    )
    velocity_threshold: float | None = Field(
        default=None, gt=0,
        description="Per-channel trend velocity alarm threshold (engineering units/s). "
                    "Overrides the global calibrated threshold."
    )


class ChannelConfigOut(BaseModel):
    """Current per-channel config: raw DB overrides + effective merged thresholds."""

    satellite_id: str
    parameter: str
    overrides: dict[str, Any]   # non-None DB fields (empty dict if no row exists)
    effective: dict[str, Any]   # full merged thresholds as used by detection pipeline
    updated_at: datetime | None


# ---------------------------------------------------------------------------
# Alert delivery schemas
# ---------------------------------------------------------------------------

class AlertConfigIn(BaseModel):
    """Per-tenant alert delivery settings — all fields optional (partial update)."""

    webhook_url: str | None = Field(default=None, max_length=2048)
    webhook_secret: str | None = Field(default=None, max_length=256)
    email_to: list[str] | None = None
    smtp_host: str | None = Field(default=None, max_length=256)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_user: str | None = Field(default=None, max_length=256)
    smtp_password: str | None = Field(default=None, max_length=256)
    min_severity: Literal["warning", "critical"] | None = None
    dedup_window_s: int | None = Field(default=None, ge=0)
    escalation_delay_s: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class AlertConfigOut(BaseModel):
    """Current per-tenant alert config as returned by the API."""

    tenant_id: str
    webhook_url: str | None
    email_to: list[str] | None
    smtp_host: str | None
    smtp_port: int | None
    smtp_user: str | None
    min_severity: str
    dedup_window_s: int
    escalation_delay_s: int
    enabled: bool
    updated_at: datetime | None


class AlertHistoryItem(BaseModel):
    """Single alert record from the alerts history endpoint."""

    id: str
    satellite_id: str
    severity: str
    acknowledged: bool
    dispatched_at: datetime
    title: str
    message: str
    # Enriched from anomaly JOIN (may be None if anomaly was deleted)
    subsystem: str | None = None
    parameter: str | None = None
    value: float | None = None
    confidence: float | None = None
    anomaly_timestamp: datetime | None = None
    explanation: str | None = None


# ---------------------------------------------------------------------------
# Sprint 6 — XTCE Parameter Import
# ---------------------------------------------------------------------------

class AlarmRangeOut(BaseModel):
    """Inclusive [low, high] alarm boundary extracted from XTCE."""
    low: float | None
    high: float | None


class ParameterDefOut(BaseModel):
    """One XTCE parameter definition as returned by the import endpoint."""
    name: str
    subsystem: str
    unit: str
    watch_range: AlarmRangeOut | None = None
    warning_range: AlarmRangeOut | None = None
    description: str = ""


class XTCEImportResult(BaseModel):
    """Response from POST /parameters/import-xtce."""
    satellite_id: str
    parameters_imported: int
    parameters: list[ParameterDefOut]


class AnalyzeResult(BaseModel):
    """Result of running anomaly detection on a satellite's stored telemetry."""

    satellite_id: str
    channels_analyzed: int
    total_anomalies: int
    anomalies_per_channel: dict[str, int]
    elapsed_s: float


# ---------------------------------------------------------------------------
# Data-source connector schemas (YAMCS, InfluxDB)
# ---------------------------------------------------------------------------

class YAMCSConnectRequest(BaseModel):
    """Request to pull telemetry from a YAMCS mission control server."""

    satellite_id: str = Field(..., min_length=1, max_length=128)
    yamcs_url: str = Field(..., min_length=1, max_length=512,
                           examples=["http://localhost:8090"])
    instance: str = Field(..., min_length=1, max_length=128,
                          examples=["simulator"])
    parameters: list[str] = Field(..., min_length=1,
                                  examples=[["/YSS/SIMULATOR/BatteryVoltage"]])
    subsystem: str = Field(default="yamcs", max_length=32)
    api_key: str = Field(default="", max_length=512)
    start: str | None = Field(default=None,
                              description="ISO-8601 start time. Defaults to 30 days ago.",
                              examples=["2024-01-01T00:00:00Z"])
    stop: str | None = Field(default=None,
                             description="ISO-8601 stop time. Defaults to now.",
                             examples=["2024-02-01T00:00:00Z"])
    resample_minutes: int = Field(default=1, ge=1, le=1440)


class InfluxDBConnectRequest(BaseModel):
    """Request to pull telemetry from an InfluxDB v2 instance."""

    satellite_id: str = Field(..., min_length=1, max_length=128)
    influxdb_url: str = Field(..., min_length=1, max_length=512,
                              examples=["http://localhost:8086"])
    org: str = Field(..., min_length=1, max_length=256)
    bucket: str = Field(..., min_length=1, max_length=256)
    token: str = Field(..., min_length=1, max_length=512)
    measurement: str = Field(..., min_length=1, max_length=256)
    fields: list[str] = Field(..., min_length=1,
                              examples=[["battery_voltage", "panel_current"]])
    subsystem: str = Field(default="influxdb", max_length=32)
    start: str = Field(default="-30d",
                       description="Flux duration (e.g. '-30d') or ISO-8601 timestamp.")
    stop: str = Field(default="now()",
                      description="'now()' or ISO-8601 timestamp.")
    resample_minutes: int = Field(default=1, ge=1, le=1440)


class ConnectorResult(BaseModel):
    """Result of a YAMCS or InfluxDB pull-and-analyze operation."""

    satellite_id: str
    source: str
    channels_loaded: int
    total_rows_inserted: int
    total_anomalies: int
    elapsed_s: float


# ── Mission Context (V3-F4) ──────────────────────────────────────────────────

class EventSummaryOut(BaseModel):
    """One upcoming orbital event (eclipse / GS pass / maneuver / SAA / custom)."""

    event_type: str
    start_epoch: float
    duration_s: float
    description: str = ""
    starts_in_s: float


class MissionContextOut(BaseModel):
    """Satellite mission context for the operator dashboard sidebar."""

    satellite_id: str
    launch_epoch: float | None
    design_life_s: float | None
    mission_elapsed_s: float
    design_life_pct_consumed: float | None
    now_epoch: float
    horizon_s: float
    next_eclipse: EventSummaryOut | None
    next_contact: EventSummaryOut | None
    next_maneuver: EventSummaryOut | None
    upcoming_events: list[EventSummaryOut] = Field(default_factory=list)


class MissionConfigIn(BaseModel):
    """Operator-set mission config (launch date + design lifetime)."""

    launch_epoch: float = Field(..., description="UTC epoch seconds of launch")
    design_life_days: int = Field(..., gt=0, le=365 * 30,
                                  description="Planned mission duration in days (≤30 y)")


class OrbitalEventIn(BaseModel):
    """Register a single orbital event."""

    event_type: str = Field(..., min_length=1, max_length=64)
    start_epoch: float
    duration_s: float = Field(default=300.0, gt=0.0, le=365 * 86_400.0)
    description: str = Field(default="", max_length=256)
    suppress_detectors: list[str] = Field(default_factory=list, max_length=32)
