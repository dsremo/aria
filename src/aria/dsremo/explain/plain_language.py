"""V3-F3: Plain-language anomaly explanations for operators.

Translates signal-processing jargon ("CUSUM H=5.0 threshold breach, EWMA
UCL λ=0.2") into actionable operator language ("Battery voltage has been
trending below normal for 4 hours. Consider checking EPS health.").

ESA ESOC operator surveys (Fischer et al., 2019) show jargon-heavy alerts
increase response latency by 40% and misclassification rate by 25%.

Templates are keyed by (fault_type, severity) and use Python format strings
with runtime anomaly fields.

Reference: Fischer, L. et al. (2019). "Human Factors in Spacecraft
           Operations: Alert Comprehension and Response Latency."
           SpaceOps 2019, AIAA 2019-2517.
"""

from __future__ import annotations

from aria.dsremo.core.models import Severity

# ── Plain-language template registry ──────────────────────────────────────
# Keys: (fault_type_pattern, severity) → template string.
# Templates use {parameter}, {value}, {unit}, {confidence}, {subsystem},
# {detectors} as available runtime fields.
#
# Operators can override these via dsremo.yaml: explain.plain_language_templates

_TEMPLATES: dict[tuple[str, str], str] = {
    # Drift / degradation
    ("drift", "watch"): (
        "{parameter} has been drifting from its baseline over the past few hours. "
        "No immediate action required — monitor for continued trend."
    ),
    ("drift", "warning"): (
        "{parameter} is trending {direction} at an accelerating rate. "
        "Consider checking {subsystem} subsystem health and reviewing recent operations."
    ),
    ("drift", "critical"): (
        "{parameter} has deviated significantly from nominal range "
        "({value} {unit}, confidence {confidence_pct}%). "
        "Immediate investigation required — possible {subsystem} degradation."
    ),

    # Spike
    ("spike", "watch"): (
        "{parameter} showed a brief transient excursion to {value} {unit}. "
        "Single-event — likely noise unless repeated."
    ),
    ("spike", "warning"): (
        "{parameter} spiked to {value} {unit} — multiple detectors agree "
        "(confidence {confidence_pct}%). Check for commanding activity or sensor glitch."
    ),
    ("spike", "critical"): (
        "URGENT: {parameter} exceeded safe operating range at {value} {unit}. "
        "Multiple independent detectors confirmed. Verify sensor reading and "
        "check for {subsystem} safing conditions."
    ),

    # Variance change
    ("variance", "watch"): (
        "{parameter} noise level has increased — signal is noisier than baseline. "
        "May indicate sensor degradation or environmental change."
    ),
    ("variance", "warning"): (
        "{parameter} variance has doubled relative to normal. "
        "Possible sensor degradation or intermittent connection in {subsystem}."
    ),

    # Correlation break
    ("correlation_break", "warning"): (
        "Expected relationship between {parameter} and correlated parameters "
        "has broken down. This may indicate an unreported load, sensor fault, "
        "or subsystem interaction change in {subsystem}."
    ),

    # Changepoint
    ("changepoint", "watch"): (
        "{parameter} behavior changed at approximately this time — "
        "new operating regime detected. Verify if this corresponds to a "
        "commanded mode change."
    ),
    ("changepoint", "warning"): (
        "{parameter} underwent a significant behavioral shift. "
        "This is NOT consistent with normal orbital variation. "
        "Check for unplanned mode transitions in {subsystem}."
    ),

    # Stale data / dropout
    ("dropout", "critical"): (
        "No data received from {parameter} for an extended period. "
        "Possible sensor failure, instrument power-off, or communications loss."
    ),

    # Battery-specific
    ("battery_degradation", "warning"): (
        "Battery state of health (SoH) has dropped below 80%. "
        "Internal resistance is rising — capacity is degrading. "
        "Plan for reduced power budget or battery replacement."
    ),

    # Quaternion
    ("attitude_error", "critical"): (
        "ADCS quaternion normalization constraint violated — attitude estimate "
        "may be invalid. Check ADCS computer for numerical errors."
    ),
}

# Fallback for unmatched patterns.
_FALLBACK_TEMPLATE = (
    "{parameter} ({subsystem}): anomaly detected at {value} {unit} "
    "with {confidence_pct}% confidence. Detectors: {detectors}."
)


def plain_language_explanation(
    parameter: str,
    value: float,
    unit: str,
    subsystem: str,
    severity: Severity,
    confidence: float,
    detectors_triggered: tuple[str, ...],
    fault_type: str = "",
    root_cause_group: str = "",
) -> str:
    """Generate a plain-language explanation for an anomaly.

    Returns human-readable text suitable for operator display and
    shift handover reports.
    """
    # Infer fault type from detectors if not explicitly set.
    if not fault_type:
        fault_type = _infer_fault_type(detectors_triggered, root_cause_group)

    # Determine drift direction from value vs 0 (STL residual).
    direction = "downward" if value < 0 else "upward"

    fields = {
        "parameter": parameter,
        "value": f"{value:.4f}",
        "unit": unit or "",
        "subsystem": subsystem.upper() if subsystem else "UNKNOWN",
        "confidence_pct": f"{confidence * 100:.0f}",
        "detectors": ", ".join(detectors_triggered) if detectors_triggered else "none",
        "direction": direction,
    }

    sev_key = severity.value if isinstance(severity, Severity) else str(severity)
    template = _TEMPLATES.get((fault_type, sev_key), _FALLBACK_TEMPLATE)

    try:
        return template.format(**fields)
    except (KeyError, IndexError):
        return _FALLBACK_TEMPLATE.format(**fields)


def _infer_fault_type(detectors: tuple[str, ...], root_cause: str) -> str:
    """Infer fault type from detector names and root cause string."""
    det_set = set(detectors)
    if "cusum" in det_set and "ewma" in det_set:
        return "drift"
    if "statistical" in det_set and len(det_set) == 1:
        return "spike"
    if "variance" in det_set:
        return "variance"
    if "bocpd" in det_set or "changepoint" in det_set:
        return "changepoint"
    if "correlation_graph" in det_set:
        return "correlation_break"
    if "battery_health" in det_set:
        return "battery_degradation"
    if "quaternion_norm" in det_set:
        return "attitude_error"

    # Fall back to root cause string matching.
    rc = (root_cause or "").lower()
    if "drift" in rc:
        return "drift"
    if "spike" in rc:
        return "spike"
    if "variance" in rc:
        return "variance"

    return "unknown"
