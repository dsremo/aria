"""Linear Energy Transfer (LET) calculations and radiation quality modeling.

LET describes the energy deposited per unit path length by a charged particle.
High-LET radiation (HZE ions) causes clustered DNA/protein damage.
Low-LET radiation (protons, gamma) causes distributed single-strand damage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LETProfile:
    """LET characteristics for a particle type and energy."""

    particle: str
    energy_mev_per_nucleon: float
    let_kev_per_um: float  # unrestricted LET in water
    rbe_dna_dsb: float  # RBE for DNA double-strand breaks
    track_structure: str  # "thin_down" or "penumbra"
    damage_type: str  # "isolated" or "clustered"


# Reference LET values for common space radiation particles
# Source: ICRP Publication 103, NASA-STD-3001 Vol 1
PARTICLE_LET_TABLE: dict[str, list[LETProfile]] = {
    "proton": [
        LETProfile("proton", 100, 0.77, 1.1, "thin_down", "isolated"),
        LETProfile("proton", 50, 1.25, 1.3, "thin_down", "isolated"),
        LETProfile("proton", 10, 4.6, 2.0, "thin_down", "isolated"),
    ],
    "helium": [
        LETProfile("He-4", 100, 2.2, 2.5, "thin_down", "isolated"),
        LETProfile("He-4", 10, 25.0, 8.0, "penumbra", "clustered"),
    ],
    "carbon": [
        LETProfile("C-12", 100, 13.0, 5.0, "penumbra", "clustered"),
        LETProfile("C-12", 10, 70.0, 15.0, "penumbra", "clustered"),
    ],
    "iron": [
        LETProfile("Fe-56", 1000, 150.0, 25.0, "penumbra", "clustered"),
        LETProfile("Fe-56", 300, 200.0, 30.0, "penumbra", "clustered"),
    ],
}


def estimate_let(particle_type: str, energy_mev_per_nucleon: float | None = None) -> float:
    """Estimate LET for a given particle type and energy.

    If energy is not provided, returns the median LET for that particle
    in the GCR spectrum.
    """
    profiles = PARTICLE_LET_TABLE.get(particle_type, [])

    if not profiles:
        # Default estimates for unknown particles
        defaults = {"proton": 1.0, "hze_ion": 100.0, "neutron": 10.0, "mixed": 5.0}
        return defaults.get(particle_type, 5.0)

    if energy_mev_per_nucleon is None:
        # Return median LET
        lets = [p.let_kev_per_um for p in profiles]
        return sorted(lets)[len(lets) // 2]

    # Interpolate between known energies
    sorted_profiles = sorted(profiles, key=lambda p: p.energy_mev_per_nucleon)
    energies = [p.energy_mev_per_nucleon for p in sorted_profiles]
    lets = [p.let_kev_per_um for p in sorted_profiles]

    if energy_mev_per_nucleon <= energies[0]:
        return lets[0]
    if energy_mev_per_nucleon >= energies[-1]:
        return lets[-1]

    # Linear interpolation in log-log space
    for i in range(len(energies) - 1):
        if energies[i] <= energy_mev_per_nucleon <= energies[i + 1]:
            log_e = math.log(energy_mev_per_nucleon)
            log_e0 = math.log(energies[i])
            log_e1 = math.log(energies[i + 1])
            log_l0 = math.log(lets[i])
            log_l1 = math.log(lets[i + 1])

            frac = (log_e - log_e0) / (log_e1 - log_e0)
            return math.exp(log_l0 + frac * (log_l1 - log_l0))

    return lets[-1]


def classify_damage_type(let_kev_per_um: float) -> str:
    """Classify expected damage type based on LET.

    Low LET (< 10 keV/μm): Isolated damage, repairable
    Medium LET (10-100 keV/μm): Mix of isolated and clustered
    High LET (> 100 keV/μm): Clustered damage, difficult to repair

    Clustered damage = multiple lesions within ~10 nm, characteristic
    of HZE ions. Much harder for cellular repair machinery to handle.
    """
    if let_kev_per_um < 10:
        return "isolated"
    if let_kev_per_um < 100:
        return "mixed"
    return "clustered"
