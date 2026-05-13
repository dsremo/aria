"""Pion/muon decay chain and muon stopping power (§4.5 of E2 scope).

Charged pions from high-energy nucleon-nucleus collisions decay to
muons with lifetime τ_π± = 26.033 ns, and the resulting muons decay
to electrons with lifetime τ_μ = 2.196 981 1 μs (Workman et al.
2022 *Prog. Theor. Exp. Phys.* 2022 083C01 — Particle Data Group
review).

    π±(26 ns) → μ± + ν_μ
    μ±(2.2 μs) → e± + 2ν

During their short lifetime, fast muons travel macroscopic distances
in matter because the relativistic γ factor extends their proper-time
lifetime dramatically. A 1 GeV muon (γ ≈ 10) has a lab-frame lifetime
of ~22 μs, enough to traverse ~6.6 km of vacuum before decaying — but
in matter they lose energy by ionisation and stop after 4-5 meters in
water (Groom, Mokhov & Striganov 2001 *Atomic Data and Nuclear Data
Tables* 78 183-356). The Groom 2001 tables are the canonical
reference for muon stopping power and range.

This module provides:

  1. PDG-referenced lifetimes (exact, no parameters needed).
  2. Survival-fraction formulas for a muon or pion beam at given time.
  3. A small interpolation table of muon CSDA range in water from
     Groom 2001 Table 1 (the standard reference numbers that every
     shield designer uses).
"""

from __future__ import annotations

import bisect
import math

# ──────────────────────────────────────────────────────────────────────
#  PDG 2022 lifetimes (Workman 2022 PTEP 2022 083C01)
# ──────────────────────────────────────────────────────────────────────

# Charged pion mean lifetime. PDG 2022 gives τ = (2.6033 ± 0.0005)e-8 s.
PDG_PION_LIFETIME_S: float = 2.6033e-8  # s (PDG 2022)

# Charged muon mean lifetime. PDG 2022 gives τ = 2.1969811(22)e-6 s.
PDG_MUON_LIFETIME_S: float = 2.1969811e-6  # s (PDG 2022)

# Rest masses (PDG 2022).
PION_MASS_MEV_C2: float = 139.57039  # MeV/c² (PDG 2022 charged pion)
MUON_MASS_MEV_C2: float = 105.6583755  # MeV/c² (PDG 2022)

# Speed of light (SI 2019 exact).
SPEED_OF_LIGHT_M_S: float = 2.99792458e8


# ──────────────────────────────────────────────────────────────────────
#  Decay survival fractions
# ──────────────────────────────────────────────────────────────────────


def pion_to_muon_decay_fraction(
    time_s: float, gamma: float = 1.0
) -> float:
    """Fraction of a pion population that has decayed after lab-frame
    time `t`.

    N/N₀ = 1 − exp(−t / (γ τ_π))                          [dimensionless]

    Args:
        time_s: lab-frame elapsed time (s). Non-negative.
        gamma: relativistic Lorentz factor of the pion beam.
            Defaults to 1 (rest frame). A 1 GeV pion has γ ≈ 7.2.

    Returns:
        Decayed fraction in [0, 1].
    """
    if time_s < 0.0:
        raise ValueError("time_s must be non-negative")
    if gamma < 1.0:
        raise ValueError("gamma must be >= 1 (rest frame minimum)")
    return 1.0 - math.exp(-time_s / (gamma * PDG_PION_LIFETIME_S))


def muon_to_electron_decay_fraction(
    time_s: float, gamma: float = 1.0
) -> float:
    """Fraction of a muon population that has decayed after lab-frame
    time `t`.

    N/N₀ = 1 − exp(−t / (γ τ_μ))                           [dimensionless]

    Args:
        time_s: lab-frame elapsed time (s).
        gamma: Lorentz factor of the muon beam.

    Returns:
        Decayed fraction in [0, 1].
    """
    if time_s < 0.0:
        raise ValueError("time_s must be non-negative")
    if gamma < 1.0:
        raise ValueError("gamma must be >= 1")
    return 1.0 - math.exp(-time_s / (gamma * PDG_MUON_LIFETIME_S))


# ──────────────────────────────────────────────────────────────────────
#  Muon CSDA range in water — Groom 2001 Table 1
# ──────────────────────────────────────────────────────────────────────

# Selected rows from Groom, Mokhov, Striganov 2001 *Atomic Data and
# Nuclear Data Tables* 78 183-356, Table 1 ("Muon range and energy
# loss in selected materials; water"). Each entry is
# (kinetic energy MeV, CSDA range in g/cm²).
#
# Because water has ρ = 1 g/cm³ at 293 K (NIST SRD 69), the range in
# g/cm² equals the range in cm. The extracted canonical values:
GROOM_2001_MUON_RANGE_TABLE: tuple[tuple[float, float], ...] = (
    (10.0, 4.71),  # T=10 MeV   → R = 4.71 g/cm² (Groom 2001 Table 1)
    (100.0, 43.1),  # T=100 MeV  → 43 g/cm²
    (1_000.0, 430.6),  # T=1 GeV    → 430 g/cm²  (the canonical ~4 m figure)
    (10_000.0, 4_350.0),  # T=10 GeV   → 4350 g/cm²
    (100_000.0, 40_000.0),  # T=100 GeV → 40 000 g/cm²  (extrapolated)
)


def muon_csda_range_water(kinetic_energy_mev: float) -> float:
    """CSDA muon range in water (g/cm²) from the Groom 2001 table.

    Uses log-log piecewise-linear interpolation between the Groom
    2001 canonical rows above. For kinetic energies outside the
    table range, extrapolates at the same log-log slope.

    Args:
        kinetic_energy_mev: muon kinetic energy in MeV (positive).

    Returns:
        CSDA range in g/cm². At water density 1 g/cm³ this equals
        the range in cm.
    """
    if kinetic_energy_mev <= 0.0:
        raise ValueError("kinetic_energy_mev must be positive")

    energies = [row[0] for row in GROOM_2001_MUON_RANGE_TABLE]
    ranges = [row[1] for row in GROOM_2001_MUON_RANGE_TABLE]

    # Log-log interpolation (range ~ E^p with p ≈ 1 in the CSDA regime).
    log_e = math.log(kinetic_energy_mev)
    log_es = [math.log(e) for e in energies]
    log_rs = [math.log(r) for r in ranges]

    if log_e <= log_es[0]:
        # Extrapolate left with the first-segment slope.
        slope = (log_rs[1] - log_rs[0]) / (log_es[1] - log_es[0])
        log_r = log_rs[0] + slope * (log_e - log_es[0])
    elif log_e >= log_es[-1]:
        # Extrapolate right with the last-segment slope.
        slope = (log_rs[-1] - log_rs[-2]) / (log_es[-1] - log_es[-2])
        log_r = log_rs[-1] + slope * (log_e - log_es[-1])
    else:
        i = bisect.bisect_left(log_es, log_e) - 1
        i = max(0, min(i, len(log_es) - 2))
        x0, x1 = log_es[i], log_es[i + 1]
        y0, y1 = log_rs[i], log_rs[i + 1]
        t = (log_e - x0) / (x1 - x0)
        log_r = y0 + t * (y1 - y0)
    return math.exp(log_r)
