"""DsremoAnomalyMixin — gives any agent direct Dsremo anomaly detection.

Usage:
    class PowerAgent(SubsystemAgent, DsremoAnomalyMixin):
        ...
        async def _update_battery(self, payload):
            soc = payload["soc_percent"]
            # Domain check (fast, threshold-based)
            if soc < 10:
                await self._raise_critical_alert(...)

            # ML check (statistical, catches subtle anomalies)
            score = await self.dsremo_score("power", "battery", "soc_percent", soc)
            if score and score >= 0.65:
                await self._raise_alert(Severity.WARNING, f"Dsremo: battery SoC anomalous (score={score:.2f})")

Why both layers?
  - Domain rules: deterministic, fast, catch obvious violations (SoC=0%)
  - Dsremo ML: statistical, catch subtle drift, cross-channel patterns
    e.g. SoC at 45% is "fine" by threshold rules, but if it's dropping
    3x faster than usual AND temperature is rising, Dsremo catches it.
"""

from __future__ import annotations

from typing import Any

import structlog


logger = structlog.get_logger()


class DsremoAnomalyMixin:
    """Mixin that adds direct Dsremo score lookup to any SubsystemAgent.

    Assumes the mixing class has:
      - self._tools: ToolRegistry
      - self.name: str (used as default subsystem)
    """

    async def dsremo_score(
        self,
        subsystem: str,
        component: str,
        metric: str,
        value: float,
        satellite_id: str = "sat-01",
    ) -> float | None:
        """Ingest a single value and return the Dsremo anomaly score (0-1).

        Returns None if Dsremo is unavailable (circuit breaker open, timeout, etc.).
        The agent should treat None as "no ML verdict available — rely on rules only".

        Args:
            subsystem: e.g. "power", "thermal", "eclss", "nav"
            component: e.g. "battery", "battery_pack", "atmosphere"
            metric: e.g. "soc_percent", "temperature_c", "co2_mmhg"
            value: the numeric measurement
        """
        channel_id = f"{subsystem}.{component}.{metric}"
        tools = getattr(self, "_tools", None)
        if tools is None:
            return None

        result = await tools.invoke(
            "dsremo_ingest_telemetry",
            {
                "satellite_id": satellite_id,
                "channel_id": channel_id,
                "value": value,
            },
        )

        if not result.success or not result.data:
            return None

        score = result.data.get("anomaly_score", 0.0)
        return float(score) if score > 0 else 0.0

    async def dsremo_score_batch(
        self,
        readings: list[dict[str, Any]],
        satellite_id: str = "sat-01",
    ) -> dict[str, float]:
        """Ingest multiple readings at once and return {channel_id: score}.

        Args:
            readings: list of {"subsystem", "component", "metric", "value"}

        Returns:
            dict of {channel_id: anomaly_score} — missing channels scored 0.0
        """
        if not readings:
            return {}

        tools = getattr(self, "_tools", None)
        if tools is None:
            return {}

        batch = [
            {
                "satellite_id": satellite_id,
                "channel_id": f"{r['subsystem']}.{r['component']}.{r['metric']}",
                "value": r["value"],
            }
            for r in readings
        ]

        result = await tools.invoke("dsremo_ingest_batch", {"readings": batch})

        if not result.success or not result.data:
            # Fall back to single ingest for each
            scores = {}
            for r in readings:
                score = await self.dsremo_score(
                    r["subsystem"], r["component"], r["metric"], r["value"], satellite_id
                )
                channel_id = f"{r['subsystem']}.{r['component']}.{r['metric']}"
                scores[channel_id] = score or 0.0
            return scores

        # Parse batch response
        results_list = result.data.get("results", [])
        return {
            res["channel_id"]: float(res.get("anomaly_score", 0.0))
            for res in results_list
            if "channel_id" in res
        }

    def dsremo_classify(self, score: float) -> str:
        """Map a Dsremo score to a human-readable severity string."""
        if score >= 0.85:
            return "CRITICAL"
        elif score >= 0.65:
            return "WARNING"
        elif score >= 0.50:
            return "WATCH"
        return "NOMINAL"
