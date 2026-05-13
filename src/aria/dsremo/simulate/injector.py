"""Fault injection engine — creates realistic satellite failures for testing.

Each scenario models a real failure mode documented in satellite operations literature.
The anomaly detector must catch these. If it can't, we have a bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from aria.dsremo.simulate.spacecraft import SpacecraftSimulator


@dataclass(frozen=True, slots=True)
class FaultScenario:
    """A pre-defined fault scenario with realistic parameters."""

    name: str
    description: str
    faults: tuple[dict, ...]  # each dict has: type, subsystem, parameter, intensity, duration


# --- Pre-built scenarios based on real satellite failure modes ---

BATTERY_DEGRADATION = FaultScenario(
    name="battery_degradation",
    description=(
        "Gradual battery capacity loss over time — one of the most common "
        "CubeSat failures. Battery voltage slowly drops below nominal range."
    ),
    faults=(
        {"type": "degradation", "subsystem": "eps", "parameter": "battery_voltage",
         "intensity": 0.6, "duration": 300},
    ),
)

REACTION_WHEEL_FRICTION = FaultScenario(
    name="reaction_wheel_friction",
    description=(
        "Bearing friction increase in X-axis reaction wheel. Speed drops, "
        "pointing error increases. If uncaught, leads to attitude loss."
    ),
    faults=(
        {"type": "degradation", "subsystem": "adcs", "parameter": "wheel_speed_x",
         "intensity": 0.7, "duration": 240},
        {"type": "drift", "subsystem": "adcs", "parameter": "pointing_error",
         "intensity": 0.4, "duration": 240},
    ),
)

THERMAL_RUNAWAY = FaultScenario(
    name="thermal_runaway",
    description=(
        "Battery temperature rising uncontrolled — could be caused by "
        "internal short or failed thermal regulation. Cross-parameter: "
        "affects EPS and thermal subsystems simultaneously."
    ),
    faults=(
        {"type": "drift", "subsystem": "thermal", "parameter": "battery_temp",
         "intensity": 0.8, "duration": 180},
        {"type": "drift", "subsystem": "eps", "parameter": "battery_voltage",
         "intensity": -0.3, "duration": 180},
    ),
)

SOLAR_PANEL_FAILURE = FaultScenario(
    name="solar_panel_failure",
    description=(
        "Sudden solar array current drop — could be panel damage from debris, "
        "wiring failure, or regulator fault. Cascades to battery and bus voltage."
    ),
    faults=(
        {"type": "spike", "subsystem": "eps", "parameter": "solar_array_current",
         "intensity": -0.9, "duration": 120},
    ),
)

SENSOR_SPIKE = FaultScenario(
    name="sensor_spike",
    description=(
        "Transient sensor spike on battery voltage — may be noise or a real "
        "issue. The detector must distinguish this from genuine anomalies."
    ),
    faults=(
        {"type": "spike", "subsystem": "eps", "parameter": "battery_voltage",
         "intensity": 0.5, "duration": 10},
    ),
)

COMMS_DEGRADATION = FaultScenario(
    name="comms_degradation",
    description=(
        "Gradual signal strength degradation — could indicate antenna "
        "misalignment, amplifier degradation, or interference."
    ),
    faults=(
        {"type": "degradation", "subsystem": "comms", "parameter": "signal_strength",
         "intensity": 0.6, "duration": 300},
        {"type": "drift", "subsystem": "comms", "parameter": "bit_error_rate",
         "intensity": 0.5, "duration": 300},
    ),
)

# Registry of all available scenarios
SCENARIOS: dict[str, FaultScenario] = {
    s.name: s for s in [
        BATTERY_DEGRADATION,
        REACTION_WHEEL_FRICTION,
        THERMAL_RUNAWAY,
        SOLAR_PANEL_FAILURE,
        SENSOR_SPIKE,
        COMMS_DEGRADATION,
    ]
}


def apply_scenario(sim: SpacecraftSimulator, scenario_name: str) -> FaultScenario:
    """Apply a named fault scenario to a running simulator.

    Raises KeyError if the scenario doesn't exist.
    """
    scenario = SCENARIOS[scenario_name]
    for fault in scenario.faults:
        sim.inject_fault(
            fault_type=fault["type"],
            subsystem=fault["subsystem"],
            parameter=fault["parameter"],
            intensity=fault["intensity"],
            duration_seconds=fault["duration"],
        )
    return scenario


def list_scenarios() -> list[dict[str, str]]:
    """Return all available fault scenarios for API/CLI display."""
    return [
        {"name": s.name, "description": s.description}
        for s in SCENARIOS.values()
    ]
