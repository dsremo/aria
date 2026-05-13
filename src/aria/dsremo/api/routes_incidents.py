"""Incident API routes — hierarchical alert routing (Sprint 17).

Incidents group related per-channel anomalies into operator-visible events.
No single raw anomaly reaches an operator without first being correlated into
an incident by the IncidentGrouper (detection/incident_grouper.py).

Endpoints
---------
GET  /incidents                        — list incidents (filter by sat/status)
GET  /incidents/{incident_id}          — detail + member anomaly count
PATCH /incidents/{incident_id}/status  — operator marks resolved/false_positive
GET  /satellites/{satellite_id}/incidents/summary — open count + severity breakdown
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from aria.dsremo.api.dependencies import require_operator, require_viewer
from aria.dsremo.api.schemas import IncidentOut, IncidentStatusIn, IncidentSummary
from aria.dsremo.db import queries

incidents_router = APIRouter(tags=["incidents"])


@incidents_router.get("/incidents", response_model=list[IncidentOut])
async def list_incidents(
    satellite_id: str | None = Query(default=None),
    status:       str | None = Query(default=None, pattern="^(open|resolved|false_positive)$"),
    limit:        int         = Query(default=50, ge=1, le=500),
    _auth=Depends(require_viewer),
):
    """List incidents, newest first.

    Filter by `satellite_id` and/or `status`.  Operators see incidents, not
    raw anomalies — each incident groups all correlated channel alerts for one
    fault event.
    """
    rows = await queries.get_incidents_v2(satellite_id=satellite_id, status=status, limit=limit)
    return [_row_to_incident(r) for r in rows]


@incidents_router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: str,
    _auth=Depends(require_viewer),
):
    """Get one incident by ID."""
    rows = await queries.get_incidents_v2(limit=1)  # TODO: add get_incident_by_id
    # Filter in-memory for now (tiny result sets expected).
    match = [r for r in await queries.get_incidents_v2(limit=500) if r["id"] == incident_id]
    if not match:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _row_to_incident(match[0])


@incidents_router.patch("/incidents/{incident_id}/status")
async def update_incident_status(
    incident_id: str,
    body: IncidentStatusIn,
    _auth=Depends(require_operator),
):
    """Operator marks an incident as resolved or false_positive.

    Resolved incidents stay visible for audit but are removed from the open
    incident count.  false_positive additionally feeds back to ML models.
    """
    ok = await queries.update_incident_status(incident_id, body.status)
    if not ok:
        raise HTTPException(status_code=404, detail="Incident not found")
    return {"ok": True, "incident_id": incident_id, "status": body.status}


@incidents_router.get(
    "/satellites/{satellite_id}/incidents/summary",
    response_model=IncidentSummary,
)
async def incident_summary(
    satellite_id: str,
    _auth=Depends(require_viewer),
):
    """Open incident count + severity breakdown for a satellite.

    Used by the dashboard header to show operator-level alert state:
      "2 open incidents — 1 warning, 1 watch"
    """
    all_open = await queries.get_incidents_v2(
        satellite_id=satellite_id, status="open", limit=500
    )
    counts: dict[str, int] = {"critical": 0, "warning": 0, "watch": 0, "nominal": 0}
    for inc in all_open:
        sev = inc.get("severity", "watch")
        counts[sev] = counts.get(sev, 0) + 1
    return IncidentSummary(
        satellite_id=satellite_id,
        open_count=len(all_open),
        critical=counts["critical"],
        warning=counts["warning"],
        watch=counts["watch"],
    )


def _row_to_incident(row: dict) -> IncidentOut:
    return IncidentOut(
        id=row["id"],
        satellite_id=row["satellite_id"],
        severity=row["severity"],
        status=row["status"],
        confidence=float(row.get("confidence") or 0.0),
        channels=list(row.get("channels") or []),
        root_cause_summary=row.get("root_cause_summary") or "",
        anomaly_count=int(row.get("anomaly_count") or 1),
        first_anomaly_at=row["first_anomaly_at"],
        last_anomaly_at=row["last_anomaly_at"],
        closed_at=row.get("closed_at"),
    )
