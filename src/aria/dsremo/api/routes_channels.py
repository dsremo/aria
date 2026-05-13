"""Channel registry + per-channel threshold config routes.

Operators can inspect the channel registry (what parameters exist, how many
data points, calibration state) and set per-channel threshold overrides that
take effect immediately in the detection pipeline.

Routes:
  GET    /channels                              — List all channels (+ effective thresholds)
  GET    /channels/{satellite_id}/{param}/config — Get per-channel override config
  PUT    /channels/{satellite_id}/{param}/config — Set / partial-update threshold overrides
  DELETE /channels/{satellite_id}/{param}/config — Remove all overrides (revert to global)
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

import aria.dsremo.db.queries as queries
from aria.dsremo.api.dependencies import require_operator, require_viewer
from aria.dsremo.api.schemas import ChannelConfigIn, ChannelConfigOut, ChannelOut
from aria.dsremo.detection.detector import get_effective_thresholds, load_channel_configs

logger = structlog.get_logger()
channels_router = APIRouter(prefix="/channels", tags=["channels"])

# Overlay columns in channel_config (everything except PK + updated_at)
_OVERRIDE_FIELDS = (
    "z_threshold", "cusum_h", "cusum_k",
    "ewma_lambda", "ewma_sigma_mult",
    "min_confidence", "alert_cooldown_s",
    "variance_z_threshold",
    "hard_limit_high", "hard_limit_low", "velocity_threshold",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_channel_out(row: dict) -> ChannelOut:
    """Convert a get_channel_stats() row into a ChannelOut schema."""
    satellite_id = row["satellite_id"]
    parameter = row["parameter"]

    has_overrides = any(row.get(f) is not None for f in _OVERRIDE_FIELDS)
    eff = get_effective_thresholds(satellite_id, parameter)

    return ChannelOut(
        satellite_id=satellite_id,
        parameter=parameter,
        subsystem=row.get("subsystem") or "",
        unit=row.get("unit") or "",
        total_points=row.get("total_points") or 0,
        first_seen=row.get("first_seen_at"),
        last_seen=row.get("last_seen_at"),
        calibration_state=row.get("calibration_state"),
        has_overrides=has_overrides,
        effective_z_threshold=eff["z_threshold"],
        effective_min_confidence=eff["min_confidence"],
        effective_alert_cooldown_s=int(eff["alert_cooldown_s"]),
    )


async def _refresh_channel_config_cache() -> None:
    """Reload the in-memory detector cache from DB after any config change."""
    load_channel_configs(await queries.load_all_channel_configs())


def _to_config_out(satellite_id: str, parameter: str, row: dict | None) -> ChannelConfigOut:
    """Build a ChannelConfigOut from a get_channel_config() row (or None)."""
    if row is None:
        overrides: dict = {}
        updated_at = None
    else:
        overrides = {f: row[f] for f in _OVERRIDE_FIELDS if row.get(f) is not None}
        updated_at = row.get("updated_at")

    eff = get_effective_thresholds(satellite_id, parameter)

    return ChannelConfigOut(
        satellite_id=satellite_id,
        parameter=parameter,
        overrides=overrides,
        effective=eff,
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@channels_router.get("", response_model=list[ChannelOut])
async def list_channels(
    satellite_id: str | None = Query(default=None, description="Filter by satellite ID"),
    _user: dict = Depends(require_viewer),
) -> list[ChannelOut]:
    """List all known channels with calibration state and current effective thresholds.

    Optionally filter by satellite_id.  Returns an empty list in demo mode
    (no channels exist until telemetry is ingested).
    """
    rows = await queries.get_channel_stats(satellite_id)
    return [_row_to_channel_out(r) for r in rows]


@channels_router.get("/{satellite_id}/{parameter}/config", response_model=ChannelConfigOut)
async def get_channel_config(
    satellite_id: str,
    parameter: str,
    _user: dict = Depends(require_viewer),
) -> ChannelConfigOut:
    """Return per-channel threshold overrides and the resulting effective thresholds.

    `overrides` contains only the fields that have been explicitly set.
    `effective` shows the merged result (what the detection pipeline actually uses).
    If no override row exists, `overrides` is empty and `effective` shows global defaults.
    """
    row = await queries.get_channel_config(satellite_id, parameter)
    return _to_config_out(satellite_id, parameter, row)


@channels_router.put("/{satellite_id}/{parameter}/config", response_model=ChannelConfigOut)
async def put_channel_config(
    satellite_id: str,
    parameter: str,
    body: ChannelConfigIn,
    _user: dict = Depends(require_operator),
) -> ChannelConfigOut:
    """Set or partial-update per-channel threshold overrides.

    This is a PATCH-style PUT: only fields present in the request body (non-null)
    are written.  Omit a field entirely to leave the existing override unchanged.
    Send `null` explicitly to clear that override and revert to the global default.

    The in-memory detector cache is refreshed immediately, so the new thresholds
    take effect on the next detection cycle without a server restart.
    """
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(
            status_code=422,
            detail="Request body must contain at least one non-null field",
        )

    row = await queries.upsert_channel_config(satellite_id, parameter, **fields)

    # Refresh in-memory detector cache so new thresholds apply immediately.
    await _refresh_channel_config_cache()

    logger.info(
        "channel_config_updated",
        satellite_id=satellite_id,
        parameter=parameter,
        fields=list(fields.keys()),
        by=_user.get("user_id"),
    )
    return _to_config_out(satellite_id, parameter, row)


@channels_router.delete("/{satellite_id}/{parameter}/config", status_code=200)
async def delete_channel_config(
    satellite_id: str,
    parameter: str,
    _user: dict = Depends(require_operator),
) -> dict:
    """Remove all per-channel threshold overrides, reverting this channel to global defaults.

    The in-memory detector cache is refreshed immediately.
    Returns `{"deleted": true}` if an override row existed, `{"deleted": false}` if not.
    """
    deleted = await queries.delete_channel_config(satellite_id, parameter)

    # Refresh cache regardless of whether a row was deleted.
    await _refresh_channel_config_cache()

    logger.info(
        "channel_config_deleted",
        satellite_id=satellite_id,
        parameter=parameter,
        deleted=deleted,
        by=_user.get("user_id"),
    )
    return {"deleted": deleted}
