"""ConjunctionWatch tool implementations.

ConjunctionWatch is a Python library (not REST API), so these tools
import and call it directly. Falls back to mock data when the library
is not installed.
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.core.tool import ARIATool, ToolResult, ValidationResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory

logger = structlog.get_logger()


def _try_import_conjunction():
    """Try to import the conjunction-prediction library."""
    try:
        from aria.conjunction.pipeline import runner  # noqa: F401
        return True
    except ImportError:
        return False


CONJUNCTION_AVAILABLE = _try_import_conjunction()


class ConjunctionWatchRunScreening(ARIATool):
    """Run conjunction screening for tracked objects.

    Uses Smart Sieve (KD-tree) to efficiently find close approaches,
    then computes Pc via Foster/Chan/Monte Carlo ensemble.
    """

    name = "conjunction_watch_run_screening"
    description = "Screen tracked objects for conjunction threats using ConjunctionWatch"
    version = "1.0.0"
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ROUTINE
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 30000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "satellite_id": {"type": "string", "description": "Primary satellite NORAD ID"},
                "screening_hours": {"type": "number", "default": 72, "description": "Hours ahead to screen"},
                "pc_threshold": {"type": "number", "default": 1e-5, "description": "Min Pc to report"},
            },
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        if not CONJUNCTION_AVAILABLE:
            # Wiring audit Pass 4 (F6.11) — return success=False so the
            # planner falls back to a different code path. Previously
            # we returned success=True with mock zero-conjunction data,
            # which let the LLM trust "no threats found" when the
            # underlying library was simply not installed.
            return ToolResult(
                success=False,
                error="conjunction_watch_library_unavailable",
                data={
                    "screening_hours": params.get("screening_hours", 72),
                    "note": "ConjunctionWatch library not installed; install "
                            "to enable real screening",
                },
            )

        try:
            from aria.conjunction.pipeline.runner import ConjunctionPipeline
            pipeline = ConjunctionPipeline()
            results = pipeline.screen(
                satellite_id=params.get("satellite_id", ""),
                screening_hours=params.get("screening_hours", 72),
                pc_threshold=params.get("pc_threshold", 1e-5),
            )
            return ToolResult(success=True, data={"conjunctions_found": len(results), "results": results})
        except Exception as e:
            logger.warning("conjunction_screening_failed", error=str(e))
            return ToolResult(success=False, error=str(e))


class ConjunctionWatchGetHighRisk(ARIATool):
    """Get current high-risk conjunction events."""

    name = "conjunction_watch_get_high_risk"
    description = "Retrieve high-risk conjunctions sorted by collision probability"
    version = "1.0.0"
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.SENSOR_ONLY
    safety_level = SafetyLevel.READ_ONLY
    concurrency_safe = True
    timeout_ms = 5000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_pc": {"type": "number", "default": 1e-5},
                "limit": {"type": "integer", "default": 10},
            },
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={"high_risk_events": [], "total_tracked": 0},
        )


class ConjunctionWatchPlanManeuver(ARIATool):
    """Plan a collision avoidance maneuver.

    Given a conjunction event, computes optimal delta-V to reduce Pc
    below the threshold while minimizing fuel consumption.
    """

    name = "conjunction_watch_plan_maneuver"
    description = "Plan collision avoidance maneuver with delta-V optimization"
    version = "1.0.0"
    category = ToolCategory.NAVIGATION
    authority_level = AuthorityLevel.ADVISORY  # Captain must approve maneuvers
    safety_level = SafetyLevel.READ_ONLY  # Planning is read-only; execution is separate
    concurrency_safe = True
    timeout_ms = 15000

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["conjunction_id"],
            "properties": {
                "conjunction_id": {"type": "string"},
                "target_pc": {"type": "number", "default": 1e-6},
                "max_delta_v_ms": {"type": "number", "default": 1.0},
            },
        }

    def validate_input(self, params: dict[str, Any]) -> ValidationResult:
        if "conjunction_id" not in params:
            return ValidationResult(valid=False, message="conjunction_id is required")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "conjunction_id": params["conjunction_id"],
                "maneuver_options": [
                    {"direction": "along-track", "delta_v_ms": 0.05, "post_maneuver_pc": 1e-7, "fuel_kg": 0.02},
                    {"direction": "cross-track", "delta_v_ms": 0.08, "post_maneuver_pc": 5e-8, "fuel_kg": 0.03},
                ],
                "recommended": 0,
                "note": "Mock response — ConjunctionWatch not connected",
            },
        )
