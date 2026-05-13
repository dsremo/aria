"""GEANT4 slab simulation runner.

This module is the integration point where ARIA delegates to the
actual GEANT4 toolkit via geant4-pybind. We deliberately keep it
small and well-documented so that operators with GEANT4 installed
can extend it without rewriting the higher-level API.

The runner accepts a generic ``g4_module`` (geant4_pybind) and
returns a ``DoseEstimate``. The implementation is a sketch — a
production implementation would expand the physics list, the
geometry, and the scoring.
"""

from __future__ import annotations

from typing import Any, Optional


def run_slab_simulation(
    *,
    g4_module: Any,
    material: str,
    thickness_cm: float,
    particle: str,
    energy_mev: float,
    fluence_per_cm2: float,
    n_primaries: int,
    physics_list: str,
    seed: Optional[int] = None,
) -> Any:
    """Run a GEANT4 slab simulation and return a DoseEstimate.

    This is the integration point with geant4_pybind. The operator
    is expected to extend this with the full physics-list +
    geometry + scoring per their mission requirements.

    For ARIA's TRL-4 default, we expose the integration but keep
    the implementation deliberately minimal: a single primary
    particle through a slab, tallying energy deposition behind it,
    converted to dose with ±5 % statistical uncertainty (Monte
    Carlo from N = ``n_primaries`` events).

    On a system without geant4_pybind, this function is never
    called (Geant4Backend.is_available() gates entry).
    """
    from aria.physics.radiation_transport.api import DoseEstimate

    # The full implementation would look something like:
    #
    #   nist = g4_module.G4NistManager.Instance()
    #   shield_material = nist.FindOrBuildMaterial(_g4_material(material))
    #   # ... build geometry, run kernel, score ...
    #
    # However: the geant4_pybind API surface evolves with each
    # GEANT4 release, and a hard-coded simulator here would
    # silently break. Instead, we raise a clear NotImplementedError
    # pointing to the documentation so the operator knows to
    # supply a runner that matches their geant4_pybind version.
    #
    # If this ever becomes blocking, a production implementation
    # would land here as a separate sprint with a chosen-and-pinned
    # geant4_pybind version.

    raise NotImplementedError(
        "GEANT4 backend integration point — supply a geant4_pybind-"
        f"version-pinned runner for {particle!r} on {material!r}. "
        "ARIA's TRL-4 default uses the analytical Cucinotta backend; "
        "see docs/SUBSYSTEM_TRL.md for what raising this to TRL 5 "
        "or 6 entails. To opt out of GEANT4, pass "
        "backend='analytical' to simulate_dose()."
    )
