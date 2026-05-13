"""Subsystem health API routes (Sprint 18 — NASA/ISRO-style health scoring).

Operators think in subsystems (EPS, ADCS, Thermal, TT&C), not individual
channels.  These endpoints aggregate per-channel anomaly state from the
incident grouper into a single health score per subsystem.

Endpoints
---------
GET /satellites/{satellite_id}/subsystem-health
    Returns a list of SubsystemHealth entries, one per subsystem registered
    in channel_registry for this satellite.

    health = 1.0 − (channels_with_open_incidents / total_channels_in_subsystem)

    Example response:
        [
            {"subsystem": "eps",     "total_channels": 4, "anomalous_channels": 0, "health": 1.0},
            {"subsystem": "thermal", "total_channels": 6, "anomalous_channels": 3, "health": 0.5},
        ]
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aria.dsremo.api.dependencies import require_viewer
from aria.dsremo.api.schemas import SubsystemHealth
from aria.dsremo.db import queries

health_router = APIRouter(tags=["health"])


@health_router.get(
    "/satellites/{satellite_id}/subsystem-health",
    response_model=list[SubsystemHealth],
)
async def subsystem_health(
    satellite_id: str,
    _auth=Depends(require_viewer),
) -> list[SubsystemHealth]:
    """Return per-subsystem health scores for a satellite.

    Sorted worst-first (ascending health).  A subsystem not in
    channel_registry simply does not appear in the list.
    """
    rows = await queries.get_subsystem_health(satellite_id)
    return [
        SubsystemHealth(
            subsystem=r["subsystem"],
            total_channels=int(r["total_channels"]),
            anomalous_channels=int(r["anomalous_channels"]),
            health=float(r["health"]),
        )
        for r in rows
    ]
