"""Flow-regime classification (§4.8 of H1 scope).

Canonical pipe-flow transition thresholds (Kundu 2016 *Fluid
Mechanics* 6th ed §10):
    Re < 2000          laminar
    2000 < Re < 4000   transitional
    Re > 4000          turbulent

Flat-plate boundary layer (Schlichting & Gersten 2017 §6.2):
    Re_x < 5·10⁵       laminar
    Re_x > 5·10⁵       turbulent
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FlowRegime(str, Enum):
    LAMINAR = "laminar"
    TRANSITIONAL = "transitional"
    TURBULENT = "turbulent"


@dataclass(frozen=True)
class RegimeThresholds:
    laminar_upper: float
    turbulent_lower: float


# Kundu 2016 §10 (pipe / duct internal flow).
PIPE_THRESHOLDS: RegimeThresholds = RegimeThresholds(
    laminar_upper=2000.0, turbulent_lower=4000.0
)

# Schlichting & Gersten 2017 §6.2 (flat-plate boundary layer).
PLATE_THRESHOLDS: RegimeThresholds = RegimeThresholds(
    laminar_upper=5.0e5, turbulent_lower=5.0e5
)


def _classify(reynolds: float, thresholds: RegimeThresholds) -> FlowRegime:
    if reynolds < 0.0:
        raise ValueError("reynolds must be non-negative")
    if reynolds <= thresholds.laminar_upper:
        return FlowRegime.LAMINAR
    if reynolds >= thresholds.turbulent_lower:
        return FlowRegime.TURBULENT
    return FlowRegime.TRANSITIONAL


def classify_pipe_flow(reynolds: float) -> FlowRegime:
    """Classify Re into laminar/transitional/turbulent for pipe flow."""
    return _classify(reynolds, PIPE_THRESHOLDS)


def classify_plate_flow(reynolds_x: float) -> FlowRegime:
    """Classify Re_x for a zero-pressure-gradient flat plate."""
    return _classify(reynolds_x, PLATE_THRESHOLDS)
