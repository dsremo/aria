"""Top-level radiation-transport API.

Exposes a single ``simulate_dose()`` function that auto-selects
the best available backend (GEANT4 if installed, else analytical),
plus a ``DoseEstimate`` result type that's identical regardless
of which backend produced it.

Operator usage:

    from aria.physics.radiation_transport import simulate_dose

    result = simulate_dose(
        material="aluminum",
        thickness_cm=2.0,
        particle="proton",
        energy_mev=100.0,
        fluence_per_cm2=1e10,
    )
    print(f"dose: {result.dose_mgy_central:.3f} mGy "
          f"[{result.dose_mgy_low:.3f}, {result.dose_mgy_high:.3f}]")
    print(f"backend: {result.backend_name}; confidence: {result.confidence}")
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Literal, Optional

import structlog

from aria.physics.radiation_transport.analytical import AnalyticalBackend
from aria.physics.radiation_transport.geant4_backend import Geant4Backend

logger = structlog.get_logger()


# Type alias for the public surface.
BackendChoice = Literal["auto", "analytical", "geant4"]


@dataclass(frozen=True)
class DoseResult:
    """Public result type returned by simulate_dose().

    Identical regardless of which backend produced it.  The
    ``backend_name`` field tells the operator which backend was
    actually used (important when ``backend='auto'`` falls back
    to analytical because GEANT4 isn't installed).
    """

    dose_mgy_central: float       # central dose estimate, milligray
    dose_mgy_low: float           # ±band lower bound
    dose_mgy_high: float           # ±band upper bound
    attenuation_factor: float    # 0..1; 1 = no attenuation
    backend_name: str            # "analytical" | "geant4" | "geant4-fallback"
    particle: str
    energy_mev: float
    material: str
    thickness_cm: float
    notes: str = ""              # backend-specific note (e.g. "fully stopped")
    confidence: str = ""         # e.g. "±20% screening", "Monte Carlo n=10000"


# Internal alias used by the backends so they don't have to import
# the public dataclass directly (avoids a circular import).
DoseEstimate = DoseResult


def available_backends() -> tuple[str, ...]:
    """Return a tuple of backend names currently installable on
    this machine. Always includes ``'analytical'``; includes
    ``'geant4'`` only if geant4-pybind is installed."""
    out = ["analytical"]
    if Geant4Backend().is_available():
        out.append("geant4")
    return tuple(out)


def preferred_backend() -> str:
    """Return the backend ``simulate_dose(backend='auto')`` would
    pick on this machine."""
    return "geant4" if "geant4" in available_backends() else "analytical"


def simulate_dose(
    *,
    material: str,
    thickness_cm: float,
    particle: str,
    energy_mev: float,
    fluence_per_cm2: float,
    backend: BackendChoice = "auto",
    geant4_n_primaries: int = 10_000,
) -> DoseResult:
    """Estimate radiation dose deposited behind a shield.

    ``backend='auto'`` (default) picks GEANT4 if installed, else
    falls back to the analytical proxy with a structured warning.
    ``backend='analytical'`` always uses the analytical proxy.
    ``backend='geant4'`` raises ImportError if geant4-pybind isn't
    installed.

    Returns a ``DoseResult`` with central dose + confidence band +
    backend identifier so the operator knows the provenance of
    every number.
    """
    if backend not in ("auto", "analytical", "geant4"):
        raise ValueError(
            f"backend must be 'auto'|'analytical'|'geant4'; got {backend!r}"
        )

    if backend == "geant4":
        chosen = Geant4Backend(n_primaries=geant4_n_primaries)
        if not chosen.is_available():
            raise ImportError(
                "GEANT4 backend explicitly requested but geant4-pybind is "
                "not installed; either pip install geant4-pybind, or pass "
                "backend='analytical' to use the always-available "
                "Cucinotta-class proxy."
            )
    elif backend == "analytical":
        chosen = AnalyticalBackend()
    else:
        # auto: prefer GEANT4 if available, else fall back to analytical.
        g4 = Geant4Backend(n_primaries=geant4_n_primaries)
        if g4.is_available():
            chosen = g4
        else:
            logger.info(
                "radiation.geant4_unavailable_using_analytical",
                hint="pip install geant4-pybind for Monte Carlo accuracy",
            )
            chosen = AnalyticalBackend()

    return chosen.compute_dose(
        material=material,
        thickness_cm=thickness_cm,
        particle=particle,
        energy_mev=energy_mev,
        fluence_per_cm2=fluence_per_cm2,
    )
