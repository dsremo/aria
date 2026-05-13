"""Alert delivery config + alert history routes.

Per-tenant alert configuration (webhook URL, SMTP settings, severity filter).
Alert history comes from the alerts table populated by AlertService.dispatch().

Routes:
  GET    /alerts/config              — get current tenant alert config
  PUT    /alerts/config              — create/update alert config (partial update)
  DELETE /alerts/config              — remove alert config
  GET    /alerts/history             — list dispatched alerts (filterable)
  POST   /alerts/{alert_id}/acknowledge — acknowledge a specific alert
"""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

import aria.dsremo.db.queries as queries
from aria.dsremo.alerts.service import AlertService
from aria.dsremo.api.dependencies import require_operator, require_viewer
from aria.dsremo.api.schemas import AlertConfigIn, AlertConfigOut, AlertHistoryItem
from aria.dsremo.core.tenant import get_tenant

logger = structlog.get_logger()
alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])


# ---------------------------------------------------------------------------
# Alert config endpoints
# ---------------------------------------------------------------------------

@alerts_router.get("/config", response_model=AlertConfigOut)
async def get_alert_config(
    _user: dict = Depends(require_viewer),
) -> AlertConfigOut:
    """Get the current tenant's alert delivery configuration."""
    row = await queries.get_alert_config()
    if not row:
        raise HTTPException(status_code=404, detail="No alert config set for this tenant")
    return AlertConfigOut(**_sanitize_config(row))


@alerts_router.put("/config", response_model=AlertConfigOut)
async def upsert_alert_config(
    body: AlertConfigIn,
    _user: dict = Depends(require_operator),
) -> AlertConfigOut:
    """Create or partially update the current tenant's alert config.

    Omit any field to keep its existing value.
    Partial update uses COALESCE — only provided (non-None) fields are changed.
    """
    tenant_id = get_tenant()
    row = await queries.upsert_alert_config(
        tenant_id,
        webhook_url=body.webhook_url,
        webhook_secret=body.webhook_secret,
        email_to=body.email_to,
        smtp_host=body.smtp_host,
        smtp_port=body.smtp_port,
        smtp_user=body.smtp_user,
        smtp_password=body.smtp_password,
        min_severity=body.min_severity,
        dedup_window_s=body.dedup_window_s,
        escalation_delay_s=body.escalation_delay_s,
        enabled=body.enabled,
    )

    # Hot-reload AlertService cache so changes take effect immediately
    AlertService.update_config(tenant_id, row)

    logger.info(
        "alert_config_updated",
        tenant_id=tenant_id,
        by=_user.get("user_id"),
        webhook=bool(row.get("webhook_url")),
        email=bool(row.get("email_to")),
    )
    return AlertConfigOut(**_sanitize_config(row))


@alerts_router.delete("/config")
async def delete_alert_config(
    _user: dict = Depends(require_operator),
) -> dict:
    """Remove the current tenant's alert config.

    After deletion, no alerts are dispatched until a new config is set.
    """
    tenant_id = get_tenant()
    deleted = await queries.delete_alert_config(tenant_id)
    AlertService.remove_config(tenant_id)
    logger.info("alert_config_deleted", tenant_id=tenant_id, by=_user.get("user_id"))
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Alert history endpoint
# ---------------------------------------------------------------------------

@alerts_router.get("/history", response_model=list[AlertHistoryItem])
async def get_alert_history(
    satellite_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    acknowledged: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    _user: dict = Depends(require_viewer),
) -> list[AlertHistoryItem]:
    """List dispatched alerts for the current tenant.

    Supports filtering by satellite_id, severity, since (datetime), acknowledged.
    Results are ordered by dispatched_at DESC (most recent first).
    """
    rows = await queries.get_alerts(
        satellite_id=satellite_id,
        severity=severity,
        since=since,
        acknowledged=acknowledged,
        limit=limit,
    )
    return [AlertHistoryItem(**r) for r in rows]


# ---------------------------------------------------------------------------
# Acknowledge endpoint
# ---------------------------------------------------------------------------

@alerts_router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    _user: dict = Depends(require_operator),
) -> dict:
    """Acknowledge a specific alert (marks it as reviewed by an operator)."""
    found = await queries.acknowledge_alert(alert_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Alert not found or already acknowledged",
        )
    logger.info("alert_acknowledged", alert_id=alert_id, by=_user.get("user_id"))
    return {"acknowledged": True, "alert_id": alert_id}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_config(row: dict) -> dict:
    """Strip SMTP password from API response (never returned to clients)."""
    out = dict(row)
    out.pop("smtp_password", None)
    out.pop("webhook_secret", None)
    return out
