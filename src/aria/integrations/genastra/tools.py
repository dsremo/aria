"""GenAstra tool implementations — crew health and biosignature detection.

Prefers direct Python import from aria.genastra (integrated monorepo).
Falls back to REST API if direct import fails or for GPU-dependent ops.
"""

from __future__ import annotations

from typing import Any

import os

import httpx
import structlog

from aria.core.tool import ARIATool, ToolResult, ValidationResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory

logger = structlog.get_logger()


def _try_local_radiation():
    """Try to import the local radiation module."""
    try:
        from aria.genastra.radiation.environment import RadiationEnvironment
        return RadiationEnvironment
    except ImportError:
        return None


_LOCAL_RADIATION = _try_local_radiation()


class GenAstraCrewRadiationDose(ARIATool):
    """Update and query crew radiation dose tracking.

    Wraps: POST /api/v1/radiation/predict-damage
    """

    name = "genastra_crew_radiation_dose"
    description = "Track and predict crew radiation exposure using GenAstra radiation models"
    version = "1.0.0"
    category = ToolCategory.LIFE_SUPPORT
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 10000

    def __init__(self, base_url: str = "http://localhost:8001", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["crew_member_id"],
            "properties": {
                "crew_member_id": {"type": "string"},
                "dose_rate_msv_hr": {"type": "number", "description": "Current dose rate in mSv/hour"},
                "accumulated_dose_msv": {"type": "number", "description": "Total accumulated dose in mSv"},
                "particle_type": {"type": "string", "enum": ["proton", "electron", "hze", "gcr"]},
            },
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if "crew_member_id" not in params:
            return ValidationResult(valid=False, message="crew_member_id is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        # Try local computation first (no network needed)
        if _LOCAL_RADIATION is not None:
            try:
                env = _LOCAL_RADIATION()
                dose_rate = params.get("dose_rate_msv_hr", 0.0)
                accumulated = params.get("accumulated_dose_msv", 0.0)
                return ToolResult(
                    success=True,
                    data={
                        "crew_member_id": params["crew_member_id"],
                        "accumulated_dose_msv": accumulated,
                        "dose_rate_msv_hr": dose_rate,
                        "annual_limit_msv": 500,   # NASA-STD-3001 Vol.1 Rev.B
                        "career_limit_msv": 1000,  # NASA-STD-3001 Vol.1 Rev.B
                        "risk_level": "critical" if accumulated > 800 else
                                      "warning" if accumulated > 500 else "nominal",
                        "source": "local_genastra",
                    },
                )
            except Exception as e:
                logger.warning("local_radiation_failed", error=str(e))

        # Fall back to REST API
        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/radiation/predict",
                    json=params,
                    headers=headers,
                )
                resp.raise_for_status()
                return ToolResult(success=True, data=resp.json())

        except httpx.ConnectError:
            # Wiring audit Pass 4 (F13.7 + F6.10) — apply the warning-
            # threshold logic locally rather than hardcoding
            # risk_level="nominal" while the upstream is down. A crew
            # member at 600 mSv would otherwise see "nominal" even
            # though that's above NASA's warning threshold.  Production
            # deploys also refuse the offline estimate entirely so the
            # planner routes to a real backup risk model.
            accumulated = float(params.get("accumulated_dose_msv", 0) or 0)
            if os.environ.get("ARIA_ENVIRONMENT", "development") == "production":
                return ToolResult(
                    success=False,
                    error="genastra_unavailable",
                    data={
                        "crew_member_id": params["crew_member_id"],
                        "accumulated_dose_msv": accumulated,
                        "note": "production refuses canned offline estimate",
                    },
                )
            risk_level = (
                "critical" if accumulated > 800 else
                "warning" if accumulated > 500 else "nominal"
            )
            return ToolResult(
                success=True,
                data={
                    "crew_member_id": params["crew_member_id"],
                    "accumulated_dose_msv": accumulated,
                    "annual_limit_msv": 500,
                    "career_limit_msv": 1000,
                    "risk_level": risk_level,
                    "note": "GenAstra not connected — offline threshold-based estimate",
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class GenAstraAnalyzeBiosignature(ARIATool):
    """Submit spectra for biosignature analysis via Bayesian nested sampling.

    Wraps: POST /api/v1/spectra/analyze
    Extraordinary claims require log10(K) > 3.2.
    """

    name = "genastra_analyze_biosignature"
    description = "Analyze spectra for biosignatures using GenAstra Bayesian detection"
    version = "1.0.0"
    category = ToolCategory.SCIENCE
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 60000  # Nested sampling can be slow

    def __init__(self, base_url: str = "http://localhost:8001", api_key: str = "") -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["wavelengths", "flux"],
            "properties": {
                "wavelengths": {"type": "array", "items": {"type": "number"}, "description": "Wavelength array (nm)"},
                "flux": {"type": "array", "items": {"type": "number"}, "description": "Flux array"},
                "target_name": {"type": "string"},
                "molecules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["H2O", "CH4", "O2", "CO2"],
                },
            },
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/spectra/analyze",
                    json=params,
                    headers=headers,
                )
                resp.raise_for_status()
                return ToolResult(success=True, data=resp.json())

        except httpx.ConnectError:
            return ToolResult(
                success=True,
                data={
                    "target_name": params.get("target_name", "unknown"),
                    "log10_bayes_factor": 0.0,
                    "detection_level": "none",
                    "disclaimer": "FOR RESEARCH USE ONLY. Spectral feature detection, not biosignature claim.",
                    "note": "GenAstra not connected — mock response",
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
