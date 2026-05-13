"""InfluxDBConnector — pull time-series data from InfluxDB v2 via Flux API.

InfluxDB is the most widely used time-series database at ground stations
(ATLAS MCS, SatNOGS backend, Gpredict, DIY mission control setups).
InfluxDB v2 uses Flux query language instead of InfluxQL.

API:
  POST /api/v2/query?org={org}
  Headers: Authorization: Token {token}, Content-Type: application/vnd.flux, Accept: application/csv
  Body: Flux query string
  Response: annotated CSV (RFC 4180 with InfluxDB comment lines beginning with #)

No external InfluxDB client library required — uses httpx (already a dep)
and the stdlib csv module for response parsing.

Usage::

    connector = InfluxDBConnector(
        base_url="http://localhost:8086",
        org="myorg",
        bucket="telemetry",
        token="my-influx-token",
        measurement="satellite",
        fields=["battery_voltage", "panel_current", "temperature"],
        satellite_id="MYSAT-1",
        start="-30d",
    )
    totals = await connector.bulk_load_to_db(resample_minutes=1)
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

import pandas as pd
import structlog

from aria.dsremo.ingest.bulk_loader import load_channels_from_series
from aria.dsremo.ingest.connector import HTTPConnector

logger = structlog.get_logger()

# Flux query template — parameterized at runtime (no string interpolation of user data)
_FLUX_TEMPLATE = (
    'from(bucket: "{bucket}")\n'
    "  |> range(start: {start}, stop: {stop})\n"
    '  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}")\n'
    '  |> keep(columns: ["_time", "_value"])\n'
)


class InfluxDBConnector(HTTPConnector):
    """Fetch engineering telemetry from an InfluxDB v2 instance via Flux.

    Each field name in ``fields`` is fetched as a separate Flux query.
    Results are collected into pandas Series and bulk-inserted via
    load_channels_from_series().

    Args:
        base_url:     InfluxDB server root, e.g. "http://localhost:8086"
        org:          InfluxDB organization name or ID.
        bucket:       Source bucket name.
        token:        InfluxDB v2 API token.
        measurement:  Measurement name to filter on (InfluxDB equivalent of a table).
        fields:       List of field keys to fetch; each becomes one Dsremo parameter.
        satellite_id: Dsremo satellite ID written to every DB row.
        start:        Flux time range start. Accepts Flux duration literals ("-30d",
                      "-7d") or ISO-8601 strings. Default: "-30d".
        stop:         Flux time range stop. Default: "now()".
        subsystem:    Subsystem label for all parameters (default "influxdb").
        timeout:      HTTP request timeout in seconds (default 60).
    """

    source_name = "influxdb"

    def __init__(
        self,
        base_url: str,
        org: str,
        bucket: str,
        token: str,
        measurement: str,
        fields: list[str],
        satellite_id: str,
        start: str = "-30d",
        stop: str = "now()",
        subsystem: str = "influxdb",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            headers={"Authorization": f"Token {token}"},
        )
        self._org = org
        self._bucket = bucket
        self._measurement = measurement
        self._fields = fields
        self._satellite_id = satellite_id
        self._start = start
        self._stop = stop
        self._subsystem = subsystem

    async def bulk_load_to_db(
        self,
        *,
        resample_minutes: int = 1,
        skip_if_rows_gte: int = 50_000,
    ) -> dict[str, int]:
        """Execute one Flux query per field, parse CSV, then bulk-insert.

        Each field is fetched independently to keep Flux queries simple and
        results predictable (no pivot required).
        """
        channels: dict[str, pd.Series] = {}

        for field in self._fields:
            try:
                series = await self._fetch_field(field)
                if series.empty:
                    logger.warning(
                        "influxdb_field_empty",
                        field=field,
                        satellite_id=self._satellite_id,
                    )
                    continue
                channels[field] = series
                logger.info(
                    "influxdb_field_fetched",
                    field=field,
                    points=len(series),
                    satellite_id=self._satellite_id,
                )
            except Exception as exc:
                logger.error(
                    "influxdb_field_failed",
                    field=field,
                    error=str(exc),
                )

        return await load_channels_from_series(
            self._satellite_id,
            channels,
            subsystem_map={f: self._subsystem for f in channels},
            resample_minutes=resample_minutes,
            skip_if_rows_gte=skip_if_rows_gte,
            source_name=self.source_name,
        )

    async def _fetch_field(self, field: str) -> pd.Series:
        """Run a Flux query for one field and return a UTC-indexed Series."""
        flux = _FLUX_TEMPLATE.format(
            bucket=self._bucket,
            start=self._start,
            stop=self._stop,
            measurement=self._measurement,
            field=field,
        )

        resp = await self._post(
            f"/api/v2/query?org={self._org}",
            content=flux.encode(),
            extra_headers={
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            },
        )

        return _parse_influx_csv(resp.text, field)


# ---------------------------------------------------------------------------
# CSV response parser (module-private)
# ---------------------------------------------------------------------------

def _parse_influx_csv(text: str, field: str) -> pd.Series:
    """Parse InfluxDB annotated CSV response into a UTC-indexed float Series.

    InfluxDB v2 wraps the data in annotation rows starting with '#'.
    This parser skips those rows and reads only the data rows.
    """
    # Strip InfluxDB annotation rows (lines starting with '#' or empty) before parsing
    data_lines = [
        line for line in text.splitlines()
        if line and not line.startswith("#")
    ]
    if len(data_lines) < 2:  # need header + at least one data row
        return pd.Series(dtype=float)

    reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
    timestamps: list[datetime] = []
    values: list[float] = []

    for row in reader:
        time_str = row.get("_time") or row.get("result") or ""
        val_str = row.get("_value", "")

        if not time_str or not val_str:
            continue

        try:
            ts = datetime.fromisoformat(
                time_str.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            val = float(val_str)
            timestamps.append(ts)
            values.append(val)
        except (ValueError, TypeError):
            continue

    if not timestamps:
        return pd.Series(dtype=float)

    idx = pd.DatetimeIndex(timestamps, tz="UTC")
    return pd.Series(values, index=idx, dtype=float, name=field)
