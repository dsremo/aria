"""Space radiator physics bridge (Phase 4 consumer layer).

Replaces the lumped Stefan-Boltzmann `P = ε σ A T⁴` calculation in
`simulation/thermal_management.py` with a first-principles module
that captures:

  - The cold-space sink temperature (CMB 2.7 K by default, or a
    higher effective sky T for near-Sun missions via the Planck
    radiation law modified by solar albedo).
  - Gardner 1945 rectangular-fin efficiency for radiator panels
    with finite thermal conductivity — honest radiator panels are
    not isothermal, so the naïve area × T⁴ calculation overstates
    capacity by 10-30 %.
  - Reactor-to-radiator Carnot ceiling (so downstream consumers
    know the thermodynamic cost of running a hot radiator: higher
    T_radiator means smaller A but a larger reactor-waste heat
    fraction via the Carnot limit).

References:
  - Incropera et al. 2011 *Fundamentals of Heat and Mass Transfer*
    7th ed Ch 3 (fin analysis), Ch 12 (radiation).
  - Gardner 1945 *Trans ASME* 67 621 — extended-surface fin
    efficiency.
  - Fixsen 2009 *ApJ* 707 916 — CMB temperature 2.72548 K.
  - Planck 1901 *Annalen der Physik* 4 553 — spectral radiance.
  - Callen 1985 *Thermodynamics* 2nd ed §4.2 — Carnot limit.
"""

from __future__ import annotations

from .radiator import (
    CMB_TEMPERATURE_K,
    STEFAN_BOLTZMANN_W_M2_K4,
    RadiatorPanelReport,
    carnot_ceiling_efficiency,
    fin_efficiency_gardner,
    radiator_net_rejection_w,
    sky_sink_temperature_k,
    solve_radiator_area_m2,
)

__all__ = [
    "CMB_TEMPERATURE_K",
    "STEFAN_BOLTZMANN_W_M2_K4",
    "RadiatorPanelReport",
    "carnot_ceiling_efficiency",
    "fin_efficiency_gardner",
    "radiator_net_rejection_w",
    "sky_sink_temperature_k",
    "solve_radiator_area_m2",
]
