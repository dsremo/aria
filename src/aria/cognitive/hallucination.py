"""Hallucination Detection — verifies LLM outputs against known facts.

Per CENTRAL_AI_MASTER_PLAN Part 10 (AI/ML Pipeline):

When ARIA's LLM produces a response, we need to verify it doesn't:
  1. Claim a subsystem status that contradicts sensor data
  2. Recommend an action that violates safety constraints
  3. Report values that are physically impossible
  4. Suggest using tools that don't exist in the registry
  5. Reference procedures that aren't in the knowledge base

This is critical because:
  - A hallucinated "all clear" during an actual emergency could kill crew
  - A hallucinated maneuver recommendation could waste fuel
  - A fabricated sensor value could cause incorrect decisions

Verification Strategy:
  - Cross-reference claimed values against recent telemetry
  - Verify recommended actions exist in the tool registry
  - Check physical plausibility of any numeric claims
  - Flag any response that contradicts active alerts
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class VerificationResult:
    """Result of hallucination check on an LLM response."""
    verified: bool  # True = no hallucinations detected
    flags: list[str] = field(default_factory=list)
    confidence: float = 1.0  # 0-1, how confident we are in the verification
    corrected_response: str = ""  # Suggested correction if hallucination found


# Physical plausibility bounds for common spacecraft values
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "temperature_c": (-270.0, 500.0),  # Above absolute zero, below most material limits
    "pressure_psi": (0.0, 1000.0),
    "voltage_v": (0.0, 120.0),
    "soc_percent": (0.0, 100.0),
    "o2_percent": (0.0, 100.0),
    "co2_mmhg": (0.0, 100.0),
    "altitude_km": (0.0, 1_000_000.0),
    "velocity_ms": (0.0, 100_000.0),
    "dose_rate_usv_hr": (0.0, 100_000.0),
    "heart_rate_bpm": (0.0, 300.0),
    "spo2_percent": (0.0, 100.0),
    "propellant_kg": (0.0, 100_000.0),
}


class HallucinationDetector:
    """Detects potential hallucinations in LLM responses.

    Checks:
      1. Contradicts active alerts (claims "nominal" when CRITICAL alert active)
      2. References non-existent tools
      3. Claims physically impossible values
      4. Contradicts recent sensor readings
    """

    def __init__(
        self,
        tool_names: set[str] | None = None,
    ) -> None:
        self._tool_names = tool_names or set()

    def verify(
        self,
        response_text: str,
        active_alerts: list[dict[str, Any]] | None = None,
        recent_readings: dict[str, float] | None = None,
    ) -> VerificationResult:
        """Verify an LLM response for potential hallucinations.

        Args:
            response_text: the LLM's text response
            active_alerts: current active alert payloads
            recent_readings: latest sensor readings {channel_id: value}

        Returns:
            VerificationResult with flags for any detected issues
        """
        flags: list[str] = []
        text_lower = response_text.lower()

        # Check 1: Contradicts active alerts
        if active_alerts:
            flags.extend(self._check_alert_contradiction(text_lower, active_alerts))

        # Check 2: References non-existent tools
        if self._tool_names:
            flags.extend(self._check_tool_references(response_text))

        # Check 3: Physically impossible values
        flags.extend(self._check_physical_plausibility(response_text))

        # Check 4: Contradicts sensor readings
        if recent_readings:
            flags.extend(self._check_reading_contradiction(response_text, recent_readings))

        verified = len(flags) == 0
        confidence = 1.0 - min(0.3 * len(flags), 0.9)

        if flags:
            logger.warning(
                "hallucination.detected",
                flags=flags,
                response_sample=response_text[:200],
            )

        return VerificationResult(
            verified=verified,
            flags=flags,
            confidence=confidence,
        )

    def _check_alert_contradiction(
        self, text: str, alerts: list[dict[str, Any]]
    ) -> list[str]:
        """Check if response claims "nominal" while alerts are active."""
        flags = []

        has_critical = any(
            a.get("severity") in ("CRITICAL", "EMERGENCY") for a in alerts
        )

        # If CRITICAL/EMERGENCY alerts active but response says all is fine
        if has_critical:
            calm_phrases = [
                "all systems nominal",
                "everything is normal",
                "no issues detected",
                "all clear",
                "no anomalies",
                "operating normally",
            ]
            for phrase in calm_phrases:
                if phrase in text:
                    flags.append(
                        f"CONTRADICTION: Response claims '{phrase}' but "
                        f"CRITICAL/EMERGENCY alerts are active"
                    )

        return flags

    def _check_tool_references(self, text: str) -> list[str]:
        """Check if response references tools that don't exist."""
        flags = []

        # Look for tool-name-like patterns (snake_case identifiers after "using" or "tool")
        tool_patterns = re.findall(r'(?:using|tool|invoke|calling)\s+(\w+_\w+)', text, re.IGNORECASE)
        for name in tool_patterns:
            if name not in self._tool_names and len(name) > 5:
                flags.append(f"UNKNOWN_TOOL: Response references '{name}' which is not in the tool registry")

        return flags

    def _check_physical_plausibility(self, text: str) -> list[str]:
        """Check any numeric values in the response for physical plausibility."""
        flags = []

        # Look for "value = X" or "X%" or "X degrees" patterns with context
        for metric, (lo, hi) in PHYSICAL_BOUNDS.items():
            # Convert metric to common text patterns
            patterns = {
                "temperature_c": [r"(-?\d+\.?\d*)\s*°?C", r"temperature.*?(-?\d+\.?\d*)"],
                "soc_percent": [r"SoC.*?(\d+\.?\d*)\s*%", r"battery.*?(\d+\.?\d*)\s*%"],
                "o2_percent": [r"O2.*?(\d+\.?\d*)\s*%", r"oxygen.*?(\d+\.?\d*)\s*%"],
                "altitude_km": [r"altitude.*?(\d+\.?\d*)\s*km"],
            }

            for p in patterns.get(metric, []):
                matches = re.findall(p, text, re.IGNORECASE)
                for match in matches:
                    try:
                        val = float(match)
                        if val < lo or val > hi:
                            flags.append(
                                f"IMPLAUSIBLE: {metric}={val} outside physical bounds [{lo}, {hi}]"
                            )
                    except ValueError:
                        pass

        return flags

    def _check_reading_contradiction(
        self, text: str, readings: dict[str, float]
    ) -> list[str]:
        """Check if response contradicts recent sensor readings."""
        flags = []

        # Check for significant contradictions
        # e.g., response says "battery at 85%" but recent reading is 15%
        for channel, value in readings.items():
            if "battery" in channel and "soc" in channel:
                # Look for battery percentage claims
                matches = re.findall(r"battery.*?(\d+\.?\d*)\s*%", text, re.IGNORECASE)
                for match in matches:
                    claimed = float(match)
                    if abs(claimed - value) > 20:  # More than 20% off
                        flags.append(
                            f"READING_MISMATCH: Claims battery at {claimed}% "
                            f"but sensor reads {value:.1f}%"
                        )

        return flags
