"""Parameter management routes.

POST /parameters/import-xtce
    Upload an XTCE XML file for a satellite.  The parser extracts every
    parameter definition (name, unit, subsystem, alarm ranges) and
    pre-registers each channel in the channels_seen registry.

    This lets customers import their YAMCS Mission Database once and have
    Dsremo automatically classify incoming telemetry with the correct
    subsystem and unit — without manual channel registration.

Requires operator role (same as telemetry upload).
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from aria.dsremo.api.dependencies import require_operator
from aria.dsremo.api.errors import bad_request
from aria.dsremo.api.schemas import AlarmRangeOut, ParameterDefOut, XTCEImportResult
from aria.dsremo.db import queries
from aria.dsremo.ingest.xtce_parser import AlarmRange, ParameterDef, parse_xtce
from aria.dsremo.ingest.utils import validated_satellite_id

logger = structlog.get_logger()

parameters_router = APIRouter(prefix="/parameters", tags=["parameters"])

# Maximum XTCE file size: 10 MB (mission databases are typically < 2 MB)
_MAX_XTCE_BYTES: int = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alarm_range_out(r: AlarmRange | None) -> AlarmRangeOut | None:
    if r is None or not r.is_set():
        return None
    return AlarmRangeOut(low=r.low, high=r.high)


def _param_to_out(p: ParameterDef) -> ParameterDefOut:
    return ParameterDefOut(
        name=p.name,
        subsystem=p.subsystem,
        unit=p.unit,
        watch_range=_alarm_range_out(p.watch_range),
        warning_range=_alarm_range_out(p.warning_range),
        description=p.description,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@parameters_router.post(
    "/import-xtce",
    response_model=XTCEImportResult,
    summary="Import parameter definitions from an XTCE XML file",
    description=(
        "Upload an XTCE (CCSDS 660.1) XML Mission Database file.  "
        "Dsremo parses the ParameterSet + ParameterTypeSet, pre-registers "
        "each telemetry parameter in the channel registry with its correct "
        "unit and subsystem label, and returns the full list of imported "
        "parameter definitions including any alarm ranges.  "
        "Re-importing the same file is idempotent (upsert, no duplicates).  "
        "Supports XTCE 1.1, 1.2, and no-namespace variants."
    ),
)
async def import_xtce(
    satellite_id: str = Form(
        ...,
        min_length=1,
        max_length=128,
        description="Satellite identifier to associate with these parameters.",
    ),
    file: UploadFile = File(
        ...,
        description="XTCE XML file (.xml). Maximum 10 MB.",
    ),
    _user: dict = Depends(require_operator),
) -> XTCEImportResult:
    """Parse XTCE XML and pre-register all parameters in the channel registry."""

    # --- Validate satellite_id ---
    try:
        satellite_id = validated_satellite_id(satellite_id)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc

    # --- Read and size-check file ---
    content = await file.read()
    if len(content) > _MAX_XTCE_BYTES:
        raise bad_request(
            f"XTCE file too large: {len(content):,} bytes (max {_MAX_XTCE_BYTES:,})"
        )

    # --- Parse XTCE ---
    try:
        params: list[ParameterDef] = parse_xtce(content)
    except ET.ParseError as exc:
        raise bad_request(f"Invalid XML: {exc}") from exc
    except ValueError as exc:
        raise bad_request(str(exc)) from exc

    if not params:
        raise bad_request("No parameters found in the XTCE document.")

    # --- Register satellite + channels (idempotent upserts) ---
    now = datetime.now(timezone.utc)
    await queries.upsert_satellite_seen(satellite_id, now)

    for p in params:
        await queries.upsert_channel_seen(satellite_id, p.name, p.subsystem, p.unit)

    logger.info(
        "xtce_import_complete",
        satellite_id=satellite_id,
        parameters=len(params),
        filename=file.filename,
    )

    return XTCEImportResult(
        satellite_id=satellite_id,
        parameters_imported=len(params),
        parameters=[_param_to_out(p) for p in params],
    )
