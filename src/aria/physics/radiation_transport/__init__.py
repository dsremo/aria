"""Radiation transport — analytical proxy with optional GEANT4 upgrade path.

Replaces the standalone Cucinotta 2014 analytical proxy that lived
inside ARIA's existing radiation modules with a clean abstraction
that defers to a GEANT4 Monte Carlo backend when one is installed,
and falls back to the analytical model otherwise.

Why two backends:

  * The **analytical backend** (Cucinotta 2014 + NIST PSTAR stopping
    powers + NCRP-153 GCR/SPE flux) is cheap, always available, but
    is a screening tool — not validated for shielding-design TRL > 4.
  * The **GEANT4 backend** is the canonical Monte Carlo radiation-
    transport tool used by NASA, ESA, and CERN; gives validated dose
    + LET + secondary-particle distributions but is slow + heavy
    (multi-GB install + multi-minute compute per scenario).

Operator usage:

  # Default: picks GEANT4 if installed, else analytical with warning
  result = simulate_dose(
      material="aluminum",
      thickness_cm=2.0,
      particle="proton",
      energy_mev=100.0,
      fluence_per_cm2=1e10,
  )

  # Explicit analytical (always works):
  result = simulate_dose(..., backend="analytical")

  # Explicit GEANT4 (raises ImportError if not installed):
  result = simulate_dose(..., backend="geant4")

To install the GEANT4 backend:

  pip install geant4-pybind   # ~2 GB binary; expect ~10 min install

Citations:
  * Cucinotta et al. 2014 'Space Radiation Cancer Risk Projections'
    NASA TP-2013-217375 §6 (analytical GCR LET model)
  * NCRP-153 'Information Needed to Make Radiation Protection
    Recommendations for Space Missions Beyond Low-Earth Orbit'
  * NIST PSTAR / ASTAR proton + alpha stopping-power tables
  * Allison et al. 2016 'Recent developments in GEANT4'
    Nucl. Instrum. Methods A 835: 186-225
"""

__all__ = (
    "DoseResult",
    "simulate_dose",
    "AnalyticalBackend",
    "Geant4Backend",
    "available_backends",
    "preferred_backend",
)

from aria.physics.radiation_transport.analytical import AnalyticalBackend
from aria.physics.radiation_transport.geant4_backend import Geant4Backend
from aria.physics.radiation_transport.api import (
    DoseResult,
    simulate_dose,
    available_backends,
    preferred_backend,
)
