"""YAMCSConnector — pull archived parameter data from a YAMCS Mission Control System.

YAMCS (Yet Another Mission Control System) is the most widely deployed
open-source MCS, used by ESA, NASA GSFC, commercial operators, and
university CubeSat programs.

REST API v2 reference:
  Archive parameters:
    GET /api/archive/{instance}/parameters/{namespace}/{name}
    Params: start, stop, limit (500 max), order (asc/desc)
    Response JSON: { "parameter": [ { "generationTime": "...", "engValue": {...} } ], ... }
    Pagination: response root includes "continuationToken" field.

  Parameter MDB info (for unit discovery):
    GET /api/mdb/{instance}/parameters/{namespace}/{name}
    Response: { "engType": { "unitSet": [ { "unit": "V" } ] }, ... }

Authentication: optional Bearer token via Authorization header.

Usage::

    connector = YAMCSConnector(
        base_url="http://localhost:8090",
        instance="simulator",
        parameters=["/YSS/SIMULATOR/BatteryVoltage", "/YSS/SIMULATOR/BatteryCurrent"],
        satellite_id="YAMCS-SIM",
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    totals = await connector.bulk_load_to_db(resample_minutes=1)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import structlog

from aria.dsremo.ingest.bulk_loader import load_channels_from_series
from aria.dsremo.ingest.connector import HTTPConnector

logger = structlog.get_logger()

# YAMCS archive endpoint page size (server-enforced max varies; 500 is safe)
_PAGE_SIZE = 500


class YAMCSConnector(HTTPConnector):
    """Fetch archived engineering-value parameters from a YAMCS instance.

    Handles:
      - Pagination via continuationToken
      - Rate-limit retry (HTTP 429 → inherited from HTTPConnector._get)
      - Optional Bearer token authentication
      - Unit discovery from the YAMCS MDB endpoint

    Args:
        base_url:       YAMCS server root, e.g. "http://localhost:8090"
        instance:       YAMCS instance name, e.g. "simulator"
        parameters:     Fully-qualified parameter paths, e.g.
                        ["/YSS/SIMULATOR/BatteryVoltage"]
        satellite_id:   Dsremo satellite ID written to every DB row.
        start:          Archive start time (UTC-aware). Defaults to 30 days ago.
        stop:           Archive end time (UTC-aware). Defaults to now.
        api_key:        Optional Bearer token for authenticated YAMCS instances.
        timeout:        HTTP request timeout in seconds (default 60).
        subsystem:      Subsystem label for all parameters (default "yamcs").
    """

    source_name = "yamcs"

    def __init__(
        self,
        base_url: str,
        instance: str,
        parameters: list[str],
        satellite_id: str,
        start: datetime | None = None,
        stop: datetime | None = None,
        api_key: str = "",
        timeout: float = 60.0,
        subsystem: str = "yamcs",
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        super().__init__(base_url=base_url, timeout=timeout, headers=headers)

        self._instance = instance
        self._parameters = parameters
        self._satellite_id = satellite_id
        self._subsystem = subsystem

        now = datetime.now(timezone.utc)
        self._start = start or now.replace(
            day=now.day - min(now.day - 1, 29)
        )
        self._stop = stop or now

    async def bulk_load_to_db(
        self,
        *,
        resample_minutes: int = 1,
        skip_if_rows_gte: int = 50_000,
    ) -> dict[str, int]:
        """Fetch all configured parameters from YAMCS and load into Dsremo DB.

        For each parameter:
          1. Fetch all pages from the archive endpoint.
          2. Discover engineering unit from the MDB endpoint.
          3. Collect into a pandas Series.
        Then bulk-insert all channels via load_channels_from_series().
        """
        channels: dict[str, pd.Series] = {}
        unit_map: dict[str, str] = {}

        for param_path in self._parameters:
            param_name = param_path.split("/")[-1]  # short name for DB column

            try:
                series = await self._fetch_parameter(param_path)
                if series.empty:
                    logger.warning(
                        "yamcs_param_empty",
                        path=param_path,
                        satellite_id=self._satellite_id,
                    )
                    continue

                unit = await self._fetch_unit(param_path)
                channels[param_name] = series
                unit_map[param_name] = unit

                logger.info(
                    "yamcs_param_fetched",
                    path=param_path,
                    points=len(series),
                    unit=unit,
                )
            except Exception as exc:
                logger.error(
                    "yamcs_param_failed",
                    path=param_path,
                    error=str(exc),
                )

        return await load_channels_from_series(
            self._satellite_id,
            channels,
            subsystem_map={k: self._subsystem for k in channels},
            unit_map=unit_map,
            resample_minutes=resample_minutes,
            skip_if_rows_gte=skip_if_rows_gte,
            source_name=self.source_name,
        )

    async def _fetch_parameter(self, param_path: str) -> pd.Series:
        """Fetch all archive pages for a single parameter, returning a Series."""
        timestamps: list[datetime] = []
        values: list[float] = []
        continuation_token: str | None = None

        start_iso = self._start.isoformat().replace("+00:00", "Z")
        stop_iso = self._stop.isoformat().replace("+00:00", "Z")

        while True:
            params: dict[str, Any] = {
                "start": start_iso,
                "stop": stop_iso,
                "limit": _PAGE_SIZE,
                "order": "asc",
            }
            if continuation_token:
                params["next"] = continuation_token

            path = f"/api/archive/{self._instance}/parameters{param_path}"
            try:
                resp = await self._get(path, params=params)
            except Exception as exc:
                logger.error("yamcs_fetch_page_failed", path=path, error=str(exc))
                break

            data = resp.json()
            for entry in data.get("parameter", []):
                ts = _parse_yamcs_time(entry.get("generationTime", ""))
                val = _extract_eng_value(entry.get("engValue", {}))
                if ts is not None and val is not None:
                    timestamps.append(ts)
                    values.append(val)

            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break

        if not timestamps:
            return pd.Series(dtype=float)

        idx = pd.DatetimeIndex(timestamps, tz="UTC")
        return pd.Series(values, index=idx, dtype=float)

    async def _fetch_unit(self, param_path: str) -> str:
        """Discover engineering unit from the YAMCS MDB endpoint."""
        try:
            path = f"/api/mdb/{self._instance}/parameters{param_path}"
            resp = await self._get(path)
            data = resp.json()
            unit_set = (
                data.get("engType", {}).get("unitSet", [])
            )
            return unit_set[0].get("unit", "") if unit_set else ""
        except Exception:
            return ""


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------

def _parse_yamcs_time(ts_str: str) -> datetime | None:
    """Parse ISO-8601 timestamp returned by YAMCS → UTC-aware datetime."""
    if not ts_str:
        return None
    try:
        ts = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _extract_eng_value(eng_value: dict) -> float | None:
    """Extract a float from YAMCS engValue dict.

    YAMCS uses typed fields: floatValue, doubleValue, sint64Value, etc.
    """
    for key in ("floatValue", "doubleValue", "sint64Value", "uint64Value",
                "sint32Value", "uint32Value"):
        if key in eng_value:
            try:
                return float(eng_value[key])
            except (TypeError, ValueError):
                return None
    return None
