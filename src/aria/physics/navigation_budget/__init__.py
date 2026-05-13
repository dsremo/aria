"""Mission navigation uncertainty budget (Phase 4 deliverable).

Pure consumer of the Phase 2/3 physics primitives: given a ship
configuration (mass, cross-section, cruise velocity, leg distance),
produce a full :class:`NavigationBudget` report listing each bounded
physical effect, its accumulated position-error contribution, and
the quadrature total.

This module is a bridge layer — it imports from the physics
primitives but does NOT import from the simulator engine, so it can
be called by any consumer (engine, CLI, notebook, regression test)
without creating a cycle or dragging in the heavier simulation
state machine.
"""

from __future__ import annotations

from .mission_profile import MissionProfile, mars_transit_profile, proxima_cruise_profile
from .report import NavigationBudget, build_navigation_budget

__all__ = [
    "MissionProfile",
    "NavigationBudget",
    "build_navigation_budget",
    "mars_transit_profile",
    "proxima_cruise_profile",
]
