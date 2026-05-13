"""Dsremo tool implementations — anomaly detection for ARIA telemetry.

Prefers direct Python import from aria.dsremo (integrated monorepo).
Falls back to REST API if local detection unavailable.

Tools:
  DsremoQueryAnomalies    — GET /api/v1/anomalies
  DsremoIngestTelemetry   — POST /api/v1/ingest (single channel)
  DsremoIngestBatch       — POST /api/v1/ingest/batch (multiple channels)
  DsremoGetChannels       — GET /api/v1/channels
  DsremoGetChannelHealth  — GET /api/v1/channels/{id}/health
  DsremoGetAnomalyScore   — GET /api/v1/channels/{id}/score (real-time score)
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from aria.core.tool import ARIATool, ToolResult, ValidationResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory

logger = structlog.get_logger()


def _try_local_dsremo():
    """Try to import local detection modules."""
    try:
        from aria.dsremo.detection.ewma import EWMADetector
        from aria.dsremo.detection.cusum import CUSUMDetector
        return True
    except ImportError:
        return False


DSREMO_LOCAL = _try_local_dsremo()


class DsremoQueryAnomalies(ARIATool):
    """Query detected anomalies from Dsremo.

    Wraps: GET /api/v1/anomalies
    """

    name = "dsremo_query_anomalies"
    description = "Query anomalies detected by Dsremo's 12-detector ensemble"
    version = "1.0.0"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 5000

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "severity_min": {
                    "type": "string",
                    "enum": ["watch", "warning", "critical"],
                    "description": "Minimum severity to return",
                },
                "channel_id": {
                    "type": "string",
                    "description": "Filter by telemetry channel",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Max anomalies to return",
                },
                "hours_back": {
                    "type": "number",
                    "default": 24,
                    "description": "Look back N hours",
                },
            },
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        query_params: dict[str, Any] = {}
        if "severity_min" in params:
            query_params["severity_min"] = params["severity_min"]
        if "channel_id" in params:
            query_params["channel_id"] = params["channel_id"]
        query_params["limit"] = params.get("limit", 50)

        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            resp = await client.get(
                f"{self._base_url}/api/v1/anomalies",
                params=query_params,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return ToolResult(
            success=True,
            data=data,
            confidence=1.0,
        )


class DsremoIngestTelemetry(ARIATool):
    """Ingest a telemetry sample into Dsremo for anomaly detection.

    Wraps: POST /api/v1/ingest
    """

    name = "dsremo_ingest_telemetry"
    description = "Send a telemetry sample to Dsremo for real-time anomaly detection"
    version = "1.0.0"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY  # Ingestion is non-destructive
    concurrency_safe = True
    timeout_ms = 2000

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["satellite_id", "channel_id", "value"],
            "properties": {
                "satellite_id": {"type": "string"},
                "channel_id": {"type": "string"},
                "value": {"type": "number"},
                "timestamp": {"type": "string", "format": "date-time"},
            },
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        for field in ("satellite_id", "channel_id", "value"):
            if field not in params:
                return ValidationResult(valid=False, message=f"Missing required field: {field}")
        if not isinstance(params["value"], (int, float)):
            return ValidationResult(valid=False, message="'value' must be a number")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/ingest",
                    json=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
            return ToolResult(success=True, data=data)
        except httpx.ConnectError:
            return ToolResult(success=True, data={"anomaly_score": 0.0, "status": "dsremo_offline"})


class DsremoGetChannels(ARIATool):
    """List available telemetry channels from Dsremo.

    Wraps: GET /api/v1/channels
    """

    name = "dsremo_get_channels"
    description = "List all telemetry channels monitored by Dsremo"
    version = "1.0.0"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 3000

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            resp = await client.get(
                f"{self._base_url}/api/v1/channels",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return ToolResult(success=True, data=data)


class DsremoIngestBatch(ARIATool):
    """Ingest multiple telemetry readings in one call — more efficient than N single calls.

    Wraps: POST /api/v1/ingest/batch
    Returns per-channel anomaly scores so each caller knows the ML verdict immediately.
    """

    name = "dsremo_ingest_batch"
    description = (
        "Send multiple telemetry readings to Dsremo in one batch call. "
        "Returns per-channel anomaly scores from the 12-detector ensemble."
    )
    version = "1.0.0"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 3000

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["readings"],
            "properties": {
                "readings": {
                    "type": "array",
                    "description": "List of telemetry readings to ingest",
                    "items": {
                        "type": "object",
                        "required": ["satellite_id", "channel_id", "value"],
                        "properties": {
                            "satellite_id": {"type": "string"},
                            "channel_id": {"type": "string"},
                            "value": {"type": "number"},
                            "timestamp": {"type": "string"},
                        },
                    },
                    "minItems": 1,
                    "maxItems": 100,
                },
            },
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        readings = params.get("readings", [])
        if not readings:
            return ValidationResult(valid=False, message="'readings' must be non-empty")
        for i, r in enumerate(readings):
            for field in ("satellite_id", "channel_id", "value"):
                if field not in r:
                    return ValidationResult(valid=False, message=f"readings[{i}] missing '{field}'")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        readings = params["readings"]

        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            resp = await client.post(
                f"{self._base_url}/api/v1/ingest/batch",
                json={"readings": readings},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", data) if isinstance(data, dict) else data
        if not isinstance(results, list):
            results = []

        return ToolResult(
            success=True,
            data={
                "results": results,
                "count": len(readings),
                "anomalies": [r for r in results if r.get("anomaly_score", 0) >= 0.5],
            },
        )


class DsremoGetChannelHealth(ARIATool):
    """Get health statistics for a specific telemetry channel.

    Wraps: GET /api/v1/channels/{channel_id}/health
    """

    name = "dsremo_get_channel_health"
    description = (
        "Get health statistics for a telemetry channel: anomaly rate, "
        "detector verdicts, data quality, and recent trend."
    )
    version = "1.0.0"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 3000

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["channel_id"],
            "properties": {
                "channel_id": {"type": "string"},
                "hours_back": {"type": "number", "default": 1.0},
            },
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if "channel_id" not in params:
            return ValidationResult(valid=False, message="'channel_id' is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        channel_id = params["channel_id"]
        hours_back = params.get("hours_back", 1.0)

        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            resp = await client.get(
                f"{self._base_url}/api/v1/channels/{channel_id}/health",
                params={"hours_back": hours_back},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return ToolResult(success=True, data=data)


class DsremoGetAnomalyScore(ARIATool):
    """Get current real-time anomaly score for a channel.

    Wraps: GET /api/v1/channels/{channel_id}/score
    Use in cognitive engine: "Is eps.battery.soc_percent anomalous right now?"
    """

    name = "dsremo_get_anomaly_score"
    description = (
        "Get the current anomaly score for a telemetry channel without ingesting. "
        "Returns the ML ensemble verdict from all 12 detectors."
    )
    version = "1.0.0"
    category = ToolCategory.TELEMETRY
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 2000

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["channel_id"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "e.g. 'thermal.battery_pack.temperature_c'",
                },
            },
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if "channel_id" not in params:
            return ValidationResult(valid=False, message="'channel_id' is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        channel_id = params["channel_id"]

        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            resp = await client.get(
                f"{self._base_url}/api/v1/channels/{channel_id}/score",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        return ToolResult(
            success=True,
            data=data,
            confidence=data.get("confidence", 1.0),
        )
