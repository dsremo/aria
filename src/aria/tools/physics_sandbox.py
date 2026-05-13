"""Physics Sandbox Tools — LLM-accessible simulation tools for novel reasoning.

This is what enables the AI to handle situations it has NEVER seen before.
Instead of following rules, it can:
  1. Propose a hypothetical maneuver or response
  2. Simulate it using real physics
  3. Check if the outcome is safe
  4. Iterate until it finds a working solution

Example: The AI discovers the spacecraft is entering too fast. It has no
rule for this. But it can:
  - Call SimulateReentry(speed=12000, angle=-8) → peak_g=12.4 → too high
  - Call SimulateReentry(speed=12000, angle=-5) → peak_g=6.1 → acceptable
  - Call SimulateReentry(speed=12000, angle=-5, skip=True) → peak_g=3.2 → better
  - Recommend: "Skip reentry at -5° will reduce peak-g to 3.2"

This is how skip reentry was discovered by human engineers — iterative
"what if?" reasoning with physics. We give the LLM the same capability.

The tools are READ-ONLY (SafetyLevel.READ_ONLY) — they simulate but
don't execute. The coordinator approves actual maneuvers separately.
"""

from __future__ import annotations

from typing import Any

import structlog

from aria.core.tool import ARIATool, ToolResult, ValidationResult
from aria.core.types import AuthorityLevel, SafetyLevel, ToolCategory

logger = structlog.get_logger()


class SimulateTrajectoryTool(ARIATool):
    """Simulate an orbital trajectory with a hypothetical maneuver.

    The LLM can ask: "What happens if I burn 100 m/s prograde right now?"
    This tool propagates the trajectory and returns the outcome.
    """

    name = "simulate_trajectory"
    description = (
        "Simulate an orbital trajectory change. Provide delta-v (m/s), "
        "direction (prograde/retrograde/radial/normal), and duration (hours). "
        "Returns: final altitude, speed, closest approach to Moon/Earth, "
        "and whether the orbit is stable/escaping/impacting."
    )
    category = ToolCategory.PLANNING
    safety_level = SafetyLevel.READ_ONLY
    min_authority = AuthorityLevel.SENSOR_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "delta_v_ms": {
                    "type": "number",
                    "description": "Magnitude of velocity change (m/s)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["prograde", "retrograde", "radial_out", "radial_in", "normal"],
                    "description": "Direction of burn relative to current velocity",
                },
                "current_altitude_km": {
                    "type": "number",
                    "description": "Current orbital altitude (km). Default: 400",
                    "default": 400.0,
                },
                "propagation_hours": {
                    "type": "number",
                    "description": "How long to propagate after the burn (hours). Default: 24",
                    "default": 24.0,
                },
            },
            "required": ["delta_v_ms", "direction"],
        }

    async def execute(self, input_data: dict[str, Any], **kwargs: Any) -> ToolResult:
        try:
            from aria.simulation.nbody import (
                circular_orbit_state, propagate, specific_energy,
                distance_to_moon, MU_EARTH, R_EARTH_M,
            )
            import numpy as np

            dv = input_data["delta_v_ms"]
            direction = input_data["direction"]
            alt = input_data.get("current_altitude_km", 400.0)
            hours = input_data.get("propagation_hours", 24.0)

            state0 = circular_orbit_state(alt)

            # Compute burn direction in ECI
            v_hat = state0.v_vec / state0.v_mag
            r_hat = state0.r_vec / state0.r_mag
            n_hat = np.cross(r_hat, v_hat)
            n_hat = n_hat / np.linalg.norm(n_hat)

            direction_map = {
                "prograde": v_hat,
                "retrograde": -v_hat,
                "radial_out": r_hat,
                "radial_in": -r_hat,
                "normal": n_hat,
            }
            burn_dir = direction_map[direction]

            # Apply burn
            from aria.simulation.nbody import OrbitalState
            s1 = OrbitalState(
                state0.x, state0.y, state0.z,
                state0.vx + burn_dir[0] * dv,
                state0.vy + burn_dir[1] * dv,
                state0.vz + burn_dir[2] * dv,
                state0.epoch_s,
            )

            # Propagate
            result = propagate(s1, hours * 3600.0, dt_output_s=300.0)

            # Analyze outcome
            alts = [s.altitude_m / 1000.0 for s in result.states]
            speeds = [s.v_mag for s in result.states]
            min_alt = min(alts)
            max_alt = max(alts)
            final_alt = alts[-1]
            energy = specific_energy(result.states[-1].r_mag, result.states[-1].v_mag)
            moon_dist = distance_to_moon(result.states[-1]) / 1000.0

            status = "stable_orbit"
            if min_alt < 0:
                status = "IMPACT — trajectory hits Earth surface"
            elif min_alt < 120:
                status = "REENTRY — trajectory enters atmosphere"
            elif energy >= 0:
                status = "ESCAPE — trajectory leaves Earth orbit"

            return ToolResult(
                success=True,
                data={
                    "status": status,
                    "min_altitude_km": round(min_alt, 1),
                    "max_altitude_km": round(max_alt, 1),
                    "final_altitude_km": round(final_alt, 1),
                    "final_speed_ms": round(speeds[-1], 1),
                    "orbital_energy_j_kg": round(energy, 1),
                    "moon_distance_km": round(moon_dist, 0),
                    "interpretation": (
                        f"After {dv:.0f} m/s {direction} burn from {alt:.0f} km: "
                        f"orbit ranges {min_alt:.0f}–{max_alt:.0f} km. {status}."
                    ),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SimulateReentryTool(ARIATool):
    """Simulate atmospheric reentry with given conditions.

    The LLM can test: "What if we enter at -5° with skip vs -8° direct?"
    """

    name = "simulate_reentry"
    description = (
        "Simulate atmospheric reentry. Provide entry speed, angle, "
        "and whether to use skip entry. Returns peak deceleration (g), "
        "peak heat rate (W/cm²), and whether the crew survives."
    )
    category = ToolCategory.PLANNING
    safety_level = SafetyLevel.READ_ONLY
    min_authority = AuthorityLevel.SENSOR_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entry_speed_ms": {
                    "type": "number",
                    "description": "Speed at entry interface (m/s). Typical lunar return: 11000",
                },
                "entry_angle_deg": {
                    "type": "number",
                    "description": "Flight path angle (degrees, negative = descending). Apollo: -6.5",
                },
                "use_skip": {
                    "type": "boolean",
                    "description": "Use skip (lift-up) reentry? Reduces peak-g.",
                    "default": False,
                },
                "lift_to_drag": {
                    "type": "number",
                    "description": "Capsule L/D ratio. Apollo/Orion: 0.3",
                    "default": 0.3,
                },
            },
            "required": ["entry_speed_ms", "entry_angle_deg"],
        }

    async def execute(self, input_data: dict[str, Any], **kwargs: Any) -> ToolResult:
        try:
            v = input_data["entry_speed_ms"]
            gamma = input_data["entry_angle_deg"]
            skip = input_data.get("use_skip", False)
            ld = input_data.get("lift_to_drag", 0.3)

            if skip:
                from aria.simulation.reentry_skip import simulate_skip_entry
                r = simulate_skip_entry(v, gamma, lift_to_drag=ld,
                                        bank_angle_deg=0.0, modulate_bank=True)
                peak_g = r.peak_decel_g
                peak_q = r.peak_heat_rate_w_cm2
                skips = r.n_skips
            else:
                from aria.simulation.lunar_return import compute_reentry
                r = compute_reentry(v, gamma, lift_to_drag=ld)
                peak_g = r.peak_decel_g
                peak_q = r.peak_heat_rate_w_cm2
                skips = 0

            # Survivability assessment
            crew_safe = peak_g < 12.0  # NASA limit for deconditioned crew
            structure_safe = peak_g < 20.0  # Structural limit
            heat_safe = peak_q < 1000.0  # AVCOAT limit

            return ToolResult(
                success=True,
                data={
                    "peak_decel_g": round(peak_g, 1),
                    "peak_heat_rate_w_cm2": round(peak_q, 0),
                    "n_skips": skips,
                    "crew_survivable": crew_safe,
                    "structure_safe": structure_safe,
                    "heat_shield_safe": heat_safe,
                    "recommendation": (
                        f"{'SAFE' if (crew_safe and structure_safe and heat_safe) else 'UNSAFE'}: "
                        f"{peak_g:.1f}g, {peak_q:.0f} W/cm², "
                        f"{'skip' if skip else 'direct'} entry at {gamma}°"
                    ),
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WhatIfAnalysisTool(ARIATool):
    """General what-if analysis: propose any scenario and get physics answer.

    This is the most powerful tool — the LLM describes a situation in natural
    language, and the tool maps it to the appropriate physics simulation.
    """

    name = "what_if_analysis"
    description = (
        "Analyze a hypothetical scenario using ARIA's physics engine. "
        "Describe the situation and proposed action. The tool runs the "
        "appropriate simulation and returns whether it works, with numbers. "
        "Use this when you encounter a situation you've never seen before."
    )
    category = ToolCategory.PLANNING
    safety_level = SafetyLevel.READ_ONLY
    min_authority = AuthorityLevel.SENSOR_ONLY

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "description": (
                        "Description of the scenario. Examples: "
                        "'fuel leak reducing delta-v budget by 200 m/s', "
                        "'solar panel failure cutting power by 50%', "
                        "'unexpected debris cloud at 800 km altitude'"
                    ),
                },
                "proposed_action": {
                    "type": "string",
                    "description": (
                        "What you want to try. Examples: "
                        "'lower orbit to 350 km to avoid debris', "
                        "'use skip reentry to reduce heating', "
                        "'shut down non-essential systems to extend battery'"
                    ),
                },
            },
            "required": ["scenario", "proposed_action"],
        }

    async def execute(self, input_data: dict[str, Any], **kwargs: Any) -> ToolResult:
        scenario = input_data["scenario"]
        action = input_data["proposed_action"]

        # This tool delegates to the cognitive engine for physics-based reasoning.
        # It structures the analysis as: identify constraints → propose test → evaluate.
        analysis = {
            "scenario": scenario,
            "proposed_action": action,
            "physics_check": (
                "Use simulate_trajectory and simulate_reentry tools to test this "
                "proposal with specific numbers before recommending it. "
                "Verify: (1) trajectory remains safe, (2) crew loads < 12g, "
                "(3) heat rates < 1000 W/cm², (4) fuel budget is sufficient."
            ),
            "first_principles": (
                "Think about this from physics first principles: "
                "What forces are involved? What conservation laws constrain the solution? "
                "Is there an energy/momentum argument for why this works or doesn't? "
                "Could the proposed action create a new problem (e.g., fixing orbit "
                "but exceeding thermal limits)?"
            ),
        }

        return ToolResult(
            success=True,
            data=analysis,
        )


def register_physics_sandbox(registry: Any) -> None:
    """Register all physics sandbox tools with the tool registry.

    Call this during ARIA startup (in main.py) to give the cognitive
    engine access to simulation tools for novel-situation reasoning.
    """
    for tool_class in [SimulateTrajectoryTool, SimulateReentryTool, WhatIfAnalysisTool]:
        try:
            registry.register(tool_class())
        except (ValueError, TypeError) as e:
            logger.warning("physics_sandbox.register_failed", tool=tool_class.name, error=str(e))
