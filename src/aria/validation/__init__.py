"""ARIA Physics/Engineering Validation Suite.

Validates physical consistency of generation ship simulations:
  - Energy conservation (power budget, RTG decay, fuel energy density)
  - Mass conservation (no mass creation in interstellar void)
  - Velocity constraints (0.1c cap, magsail deceleration only)
  - Population constraints (non-negative, biological feasibility)
  - Resource non-negativity (fuel, water, food, spares, health values)
  - Thermal balance (Stefan-Boltzmann radiator capacity vs waste heat)
  - Shield erosion (monotonic decrease, Hoang et al. erosion model)
"""

from aria.validation.physics_validator import (
    PhysicsValidator,
    ValidationReport,
    Violation,
    ViolationSeverity,
)

__all__ = [
    "PhysicsValidator",
    "ValidationReport",
    "Violation",
    "ViolationSeverity",
]
