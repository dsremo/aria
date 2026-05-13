"""V3-F4: Mission context + orbital-events API for the operator dashboard.

Exposes:
  GET  /satellites/{sat}/context           → MissionContextOut
  GET  /satellites/{sat}/orbital_events    → list[EventSummaryOut]
  PUT  /satellites/{sat}/mission_config    → upsert launch + design life
  POST /satellites/{sat}/orbital_events    → register a single event
  DELETE /satellites/{sat}/orbital_events  → clear all events for a satellite

Reference: ECSS-E-ST-70C §5.4.2 (mission timeline integration).
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from aria.dsremo.api.dependencies import get_current_user, require_operator
from aria.dsremo.api.schemas import (
    EventSummaryOut,
    MissionConfigIn,
    MissionContextOut,
    OrbitalEventIn,
)
from aria.dsremo.db import queries
from aria.dsremo.detection.orbital_events import OrbitalEvent, get_orbital_timeline
from aria.dsremo.detection.satellite_context import (
    DEFAULT_HORIZON_S,
    build_context,
)

SECONDS_PER_DAY = 86_400.0  # SI definition


mission_context_router = APIRouter(tags=["mission_context"])


def _event_summary_to_out(summary) -> EventSummaryOut:
    return EventSummaryOut(
        event_type=summary.event_type,
        start_epoch=summary.start_epoch,
        duration_s=summary.duration_s,
        description=summary.description,
        starts_in_s=summary.starts_in_s,
    )


@mission_context_router.get(
    "/satellites/{satellite_id}/context",
    response_model=MissionContextOut,
)
async def get_satellite_context(
    satellite_id: str,
    horizon_s: Annotated[float, Query(gt=0.0, le=30 * SECONDS_PER_DAY)] = DEFAULT_HORIZON_S,
    _user: dict = Depends(get_current_user),
) -> MissionContextOut:
    """Mission context block for the /ops dashboard sidebar (V3-F4)."""
    cfg = await queries.get_mission_config(satellite_id)
    launch_epoch = float(cfg["launch_epoch"]) if cfg else None
    design_life_s = (
        float(cfg["design_life_days"]) * SECONDS_PER_DAY if cfg else None
    )

    ctx = build_context(
        satellite_id=satellite_id,
        launch_epoch=launch_epoch,
        design_life_s=design_life_s,
        timeline=get_orbital_timeline(),
        now_epoch=time.time(),
        horizon_s=horizon_s,
    )

    return MissionContextOut(
        satellite_id=ctx.satellite_id,
        launch_epoch=ctx.launch_epoch,
        design_life_s=ctx.design_life_s,
        mission_elapsed_s=ctx.mission_elapsed_s,
        design_life_pct_consumed=ctx.design_life_pct_consumed,
        now_epoch=ctx.now_epoch,
        horizon_s=ctx.horizon_s,
        next_eclipse=_event_summary_to_out(ctx.next_eclipse) if ctx.next_eclipse else None,
        next_contact=_event_summary_to_out(ctx.next_contact) if ctx.next_contact else None,
        next_maneuver=_event_summary_to_out(ctx.next_maneuver) if ctx.next_maneuver else None,
        upcoming_events=[_event_summary_to_out(e) for e in ctx.upcoming_events],
    )


@mission_context_router.get(
    "/satellites/{satellite_id}/orbital_events",
    response_model=list[EventSummaryOut],
)
async def list_orbital_events(
    satellite_id: str,
    from_epoch: Annotated[float | None, Query()] = None,
    to_epoch: Annotated[float | None, Query()] = None,
    _user: dict = Depends(get_current_user),
) -> list[EventSummaryOut]:
    """Raw event list for the Gantt. Defaults to now ±24 h when bounds omitted."""
    now = time.time()
    lo = from_epoch if from_epoch is not None else now - DEFAULT_HORIZON_S
    hi = to_epoch if to_epoch is not None else now + DEFAULT_HORIZON_S
    if hi < lo:
        raise HTTPException(status_code=400, detail="to_epoch must be >= from_epoch")

    events = get_orbital_timeline().events_in_window(satellite_id, lo, hi)
    events.sort(key=lambda e: e.start_epoch)

    return [
        EventSummaryOut(
            event_type=e.event_type,
            start_epoch=e.start_epoch,
            duration_s=e.duration_s,
            description=e.description,
            starts_in_s=e.start_epoch - now,
        )
        for e in events
    ]


@mission_context_router.put(
    "/satellites/{satellite_id}/mission_config",
    response_model=dict,
)
async def put_mission_config(
    satellite_id: str,
    body: MissionConfigIn,
    _user: dict = Depends(require_operator),
) -> dict:
    """Upsert launch_epoch + design_life_days (V3-F4)."""
    row = await queries.upsert_mission_config(
        satellite_id=satellite_id,
        launch_epoch=body.launch_epoch,
        design_life_days=body.design_life_days,
    )
    return {
        "satellite_id": row["satellite_id"],
        "launch_epoch": float(row["launch_epoch"]),
        "design_life_days": int(row["design_life_days"]),
    }


@mission_context_router.post(
    "/satellites/{satellite_id}/orbital_events",
    status_code=201,
    response_model=EventSummaryOut,
)
async def register_orbital_event(
    satellite_id: str,
    body: OrbitalEventIn,
    _user: dict = Depends(require_operator),
) -> EventSummaryOut:
    """Register a single orbital event on the per-sat timeline."""
    ev = OrbitalEvent(
        event_type=body.event_type,
        start_epoch=body.start_epoch,
        duration_s=body.duration_s,
        description=body.description,
        suppress_detectors=list(body.suppress_detectors),
    )
    get_orbital_timeline().register(satellite_id, ev)
    now = time.time()
    return EventSummaryOut(
        event_type=ev.event_type,
        start_epoch=ev.start_epoch,
        duration_s=ev.duration_s,
        description=ev.description,
        starts_in_s=ev.start_epoch - now,
    )


@mission_context_router.delete(
    "/satellites/{satellite_id}/orbital_events",
    status_code=204,
    response_model=None,
    response_class=Response,
)
async def clear_orbital_events(
    satellite_id: str,
    _user: dict = Depends(require_operator),
) -> None:
    """Clear every registered orbital event for a satellite."""
    get_orbital_timeline().clear(satellite_id)
