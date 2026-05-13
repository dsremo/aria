"""Published dark-sector experimental bounds (§5 of M1/M2/M3 scopes).

Every constant is tagged with its primary reference in a per-line
comment. Values are frozen at the publication date in the comment;
the module should be re-audited annually against the latest PDG
review.
"""

from __future__ import annotations

from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────────────
#  Universal constants (CODATA 2018 / SI 2019)
# ──────────────────────────────────────────────────────────────────────
SPEED_OF_LIGHT_M_S: float = 299792458.0  # SI 2019 (exact)
MEGAPARSEC_M: float = 3.0856775814913673e22  # IAU 2015 (1 Mpc)


# ──────────────────────────────────────────────────────────────────────
#  M1 — dark matter + dark energy
# ──────────────────────────────────────────────────────────────────────

# Read 2014 *J Phys G* 41 063101: local DM density 0.4 ± 0.2 GeV/cm³.
# Converted: 1 GeV/c² = 1.7827e-27 kg; 1 cm³ = 1e-6 m³
#   0.4 GeV/cm³ × 1.7827e-27 kg × 1e6 /m³ = 7.13e-22 kg/m³.
# Scope note §5 rounds to 6.4e-22; we use the Read 2014 calculation.
DARK_MATTER_DENSITY_READ_2014_KG_M3: float = 7.13e-22

# Bland-Hawthorn & Gerhard 2016 *Annu Rev A&A* 54 529: v_sun through
# the galactic halo ≈ 232 km/s.
DARK_MATTER_LOCAL_VELOCITY_M_S: float = 232.0e3

# Aprile et al. 2023 *PRL* 131 041003 XENONnT 90 % CL WIMP-nucleon
# spin-independent bound at m_DM ≈ 30 GeV/c²: σ_SI ≤ 2.6e-47 cm²
# = 2.6e-51 m².
XENONNT_SIGMA_SI_30GEV_M2: float = 2.6e-51

# ADMX 2018 *PRL* 120 151301: axion-photon coupling 90 % CL bound
# g_aγγ ≤ 3×10⁻¹⁵ GeV⁻¹ at m_a ≈ 2.66 µeV/c².
ADMX_G_A_GAMMA_BOUND_GEV_INV: float = 3.0e-15

# Planck Collaboration 2020 *A&A* 641 A6 Planck 2018 VI.
HUBBLE_H0_KM_S_MPC: float = 67.4  # Planck 2018 base-ΛCDM
HUBBLE_OMEGA_LAMBDA: float = 0.6847  # Planck 2018
LAMBDA_COSMO_M2: float = 1.1056e-52  # derived from Planck 2018

# Fixsen 2009 *ApJ* 707 916.
PLANCK_2018_CMB_TEMPERATURE_K: float = 2.7255


# ──────────────────────────────────────────────────────────────────────
#  M2 — equivalence-principle bounds
# ──────────────────────────────────────────────────────────────────────

# Touboul et al. 2017 *PRL* 119 231101 MICROSCOPE final result.
MICROSCOPE_ETA_BOUND: float = 1.5e-15

# Wagner et al. 2012 *Class Quantum Grav* 29 184002 — Eöt-Wash torsion
# balance, η ≤ 2×10⁻¹³ for Earth-source field.
EOT_WASH_ETA_BOUND: float = 2.0e-13

# Williams, Turyshev & Boggs 2012 *Class Quantum Grav* 29 184004 —
# Lunar Laser Ranging SEP bound η ≤ 3×10⁻¹⁴.
LLR_ETA_SEP_BOUND: float = 3.0e-14


# ──────────────────────────────────────────────────────────────────────
#  M3 — varying fundamental constants
# ──────────────────────────────────────────────────────────────────────

# Webb et al. 2011 *PRL* 107 191101: |Δα/α| ≤ 10⁻⁶ over 10 Gyr.
# Converting: 10 Gyr = 3.1557e17 s → |α̇/α| ≤ 3.17e-24 /s.
VARYING_ALPHA_FRAC_PER_S: float = 3.17e-24

# Ubachs et al. 2016 *Rev Mod Phys* 88 021003: H₂ QSO absorption
# bound |Δμ/μ| ≤ 10⁻⁵ over 10 Gyr → |μ̇/μ| ≤ 3.17e-23 /s.
VARYING_MU_FRAC_PER_S: float = 3.17e-23

# Hofmann & Müller 2018 *Class Quantum Grav* 35 035015 LLR
# |Ġ/G| ≤ 1.1×10⁻¹³ /yr = 3.49×10⁻²¹ /s.
VARYING_G_FRAC_PER_S: float = 3.49e-21


@dataclass(frozen=True)
class ClockSensitivity:
    """Sensitivity coefficient K_α for an atomic-clock transition.

    dν/ν = K_α · dα/α (Dzuba, Flambaum & Webb 1999 *PRL* 82 888).

    Attributes:
        name: clock identifier.
        k_alpha: dimensionless sensitivity of the transition to α.
        source: citation string.
    """

    name: str
    k_alpha: float
    source: str


# Canonical K_α values from Dzuba, Flambaum & Webb 1999 *PRL* 82 888
# and later optical-clock reviews (Ludlow et al. 2015 *Rev Mod Phys*
# 87 637).
CLOCK_SENSITIVITY_TABLE: dict[str, ClockSensitivity] = {
    "Cs-133-hfs": ClockSensitivity(
        name="Cs-133 ground-state hyperfine",
        k_alpha=2.83,
        source="Dzuba, Flambaum & Webb 1999 PRL 82 888",
    ),
    "Sr-87-optical": ClockSensitivity(
        name="Sr-87 optical lattice",
        k_alpha=0.06,
        source="Ludlow et al. 2015 RMP 87 637",
    ),
    "Al-27-plus-optical": ClockSensitivity(
        name="Al+ ion optical",
        k_alpha=0.008,
        source="Rosenband et al. 2008 Science 319 1808",
    ),
}
