"""GEANT4 radiation-transport backend (optional dependency).

This backend is only available when the ``geant4-pybind`` Python
bindings are installed. ``geant4-pybind`` itself ships pre-built
GEANT4 libraries (~2 GB) and may take ~10 minutes to install on
first invocation.

When unavailable, ``Geant4Backend.is_available()`` returns False
and ``compute_dose()`` raises a clear ImportError. The API-layer
``simulate_dose()`` automatically falls back to the analytical
backend in that case.

When available, the backend builds a minimal slab geometry of the
chosen shield material, runs a configurable number of primary
particles through it, tallies energy deposition in a 1-cm-thick
'tally' volume behind the shield, and converts to dose.

This module is **deliberately minimal** — it does not exercise
GEANT4's full physics list, secondary particle production, or
field configuration. Real shielding-design work needs to go beyond
this skeleton (custom physics list, voxelised tally, secondary-
particle accounting, statistical-uncertainty diagnostics).

Citations:
  * Allison et al. 2016 'Recent developments in GEANT4'
    Nucl. Instrum. Methods A 835: 186-225
  * GEANT4 Physics Reference Manual (geant4.web.cern.ch)
  * geant4-pybind PyPI package (https://pypi.org/project/geant4-pybind/)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Optional-dependency probe ───────────────────────────────────


def _try_import_geant4() -> Optional[Any]:
    """Attempt to import geant4_pybind. Return module or None."""
    try:
        import geant4_pybind as g4   # type: ignore
        return g4
    except ImportError:
        return None
    except Exception:
        # geant4_pybind may raise non-ImportError on broken installs;
        # treat that the same as unavailable.
        return None


# ── Backend dataclass ──────────────────────────────────────────


@dataclass
class Geant4Backend:
    """Monte Carlo radiation-transport backend (optional).

    Construction does not import GEANT4; the import is lazy so that
    instantiating the dataclass on a system without GEANT4 doesn't
    raise. Use ``is_available()`` to gate calls into ``compute_dose``.
    """

    name: str = "geant4"
    n_primaries: int = 10_000     # default Monte Carlo events
    physics_list: str = "QGSP_BIC_HP"   # standard nuclear + neutron
    seed: Optional[int] = None
    _g4_module: Optional[Any] = field(default=None, repr=False)

    def is_available(self) -> bool:
        if self._g4_module is None:
            object.__setattr__(self, "_g4_module", _try_import_geant4())
        return self._g4_module is not None

    def compute_dose(
        self,
        *,
        material: str,
        thickness_cm: float,
        particle: str,
        energy_mev: float,
        fluence_per_cm2: float,
    ) -> "DoseEstimate":
        """Run a small Monte Carlo against a slab geometry.

        Raises ImportError if geant4-pybind isn't installed. The API
        layer catches that and falls back to the analytical backend.
        """
        from aria.physics.radiation_transport.api import DoseEstimate

        if not self.is_available():
            raise ImportError(
                "GEANT4 backend requires `geant4-pybind`; install via "
                "`pip install geant4-pybind` (~2 GB binary, ~10 min install). "
                "Or pass backend='analytical' for the always-available "
                "Cucinotta-class proxy."
            )

        # The actual GEANT4 simulation is intentionally NOT inlined
        # here. A real implementation would:
        #   1. Build a G4Box mother volume of the shield material
        #   2. Place a 1-cm-thick scoring slab behind it
        #   3. Define a beam of `n_primaries` `particle`s at energy_mev
        #   4. Run the event loop with the chosen physics list
        #   5. Read back energy deposition per event in the scorer
        #   6. Compute mean + std-error → return DoseEstimate
        # The full implementation is ~200 LOC of GEANT4 Python and
        # depends on which version of geant4-pybind is installed.
        # We expose the integration point but don't ship the full
        # simulator inline; instead we delegate to a helper module
        # that the operator can extend.
        from aria.physics.radiation_transport._geant4_runner import (
            run_slab_simulation,
        )
        return run_slab_simulation(
            g4_module=self._g4_module,
            material=material,
            thickness_cm=thickness_cm,
            particle=particle,
            energy_mev=energy_mev,
            fluence_per_cm2=fluence_per_cm2,
            n_primaries=self.n_primaries,
            physics_list=self.physics_list,
            seed=self.seed,
        )
