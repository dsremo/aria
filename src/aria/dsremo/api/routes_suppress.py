"""Alert suppression window API (Sprint 19).

Operators can mute anomaly alerts for a specific channel during planned
maintenance, calibration events, or known maneuvers — without stopping
the detection pipeline.  Detection continues; alerts are silently dropped
while suppression is active.

NASA/ESA standard: every telemetry ops system supports maintenance windows.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from aria.dsremo.api.dependencies import get_current_user, require_operator
from aria.dsremo.api.schemas import SuppressionIn, SuppressionOut
from aria.dsremo.detection.detector import (
    lift_suppression,
    list_suppressions,
    suppress_channel,
)

suppress_router = APIRouter(tags=["suppression"])


@suppress_router.post(
    "/satellites/{satellite_id}/suppress",
    response_model=SuppressionOut,
    status_code=201,
)
async def create_suppression(
    satellite_id: str,
    body: SuppressionIn,
    _user: dict = Depends(require_operator),
) -> SuppressionOut:
    """Suppress anomaly alerts for one channel for *duration_min* minutes.

    Detection continues normally — only alert insertion is muted.
    Overwrites any existing suppression for the same channel.
    """
    until = suppress_channel(satellite_id, body.parameter, body.duration_min)
    return SuppressionOut(
        satellite_id=satellite_id,
        parameter=body.parameter,
        duration_min=body.duration_min,
        reason=body.reason,
        until_epoch=until,
    )


@suppress_router.delete(
    "/satellites/{satellite_id}/suppress/{parameter}",
    status_code=204,
    response_model=None,
    response_class=Response,
)
async def delete_suppression(
    satellite_id: str,
    parameter: str,
    _user: dict = Depends(require_operator),
) -> None:
    """Lift an active suppression window early."""
    lifted = lift_suppression(satellite_id, parameter)
    if not lifted:
        raise HTTPException(
            status_code=404,
            detail=f"No active suppression for {satellite_id}/{parameter}",
        )


@suppress_router.get(
    "/satellites/{satellite_id}/suppress",
    response_model=list[SuppressionOut],
)
async def get_suppressions(
    satellite_id: str,
    _user: dict = Depends(get_current_user),
) -> list[SuppressionOut]:
    """List all active (non-expired) suppression windows for a satellite."""
    items = list_suppressions(satellite_id)
    return [
        SuppressionOut(
            satellite_id=satellite_id,
            parameter=item["parameter"],
            duration_min=item["remaining_min"],
            reason=None,
            until_epoch=item["until_epoch"],
        )
        for item in items
    ]
