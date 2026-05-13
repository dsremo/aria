"""Hull fatigue bridge (Phase 4 consumer layer).

Combines the pressure-vessel closed forms (F1), Goodman mean-stress
correction + Basquin S-N life (F2), Miner cumulative damage (F2),
and the constrained thermal-stress primitive (F5) into a single
:class:`HullFatigueReport` that callers can use to replace the
simulator's hard-coded fatigue placeholder.

The bridge handles the common "docking event + day-night thermal
cycle" load case:

  1. Pressure cycles — hoop and axial stress from internal cabin
     pressure cycling (0 → 101 325 Pa for depressurisation events).
  2. Thermal cycles — constrained E α ΔT stress from day-night
     temperature swings on the radiator-side panels or from habitat
     HVAC transients.
  3. Combined loading — both stress ranges are summed and passed
     through a Goodman mean-stress correction before Basquin life.

References:
  - Suresh 1998 *Fatigue of Materials* 2nd ed §7 (ISBN 978-0521578479).
  - Dowling 2007 *Mechanical Behavior of Materials* 3rd ed Ch 9-10.
  - MMPDS-17 / ASM Handbook — Ti-6Al-4V S-N and thermal data.
"""

from __future__ import annotations

from .bridge import (
    CycleBlock,
    HullFatigueReport,
    HullGeometry,
    ThermalCycleBlock,
    build_hull_fatigue_report,
)

__all__ = [
    "CycleBlock",
    "HullFatigueReport",
    "HullGeometry",
    "ThermalCycleBlock",
    "build_hull_fatigue_report",
]
