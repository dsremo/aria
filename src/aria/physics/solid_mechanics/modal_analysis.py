"""Structural modal analysis: natural frequencies for beams, plates, and shells.

Fills the physics audit gap: "Resonant frequencies / vibration fatigue — no
modal analysis; fatigue life 10-100× overestimated."

Without resonant frequency knowledge, fatigue life estimates are wrong because:
  1. If an excitation frequency matches a structural mode → amplification ≫ 1×,
     turning a low-amplitude load into a large-cycle fatigue driver.
  2. Harmonic response near resonance multiplies stress amplitude by Q = f/(2ζ),
     the quality factor, where ζ is the structural damping ratio.
  3. A 100 Hz engine vibration at a panel mode at 98 Hz can amplify stress 50×,
     reducing predicted fatigue life from years to minutes.

Implemented models:
  1. **Euler-Bernoulli beam** — flexural natural frequencies for common
     boundary conditions (clamped-free, clamped-clamped, pinned-pinned).
  2. **Cylindrical shell ring (breathing) frequency** — hoop mode that couples
     to pressure oscillations (Donnell 1933 / Leissa 1973).
  3. **Simply-supported plate** — Kirchhoff plate first mode and Rayleigh quotient.
  4. **Critical spin frequency** — rotating shaft critical speed (Campbell diagram).
  5. **Mode shape amplification** — stress amplification at resonance from Q factor.

References:
    Leissa, A. W. (1969) "Vibration of Plates." NASA SP-160.
    Leissa, A. W. (1973) "Vibration of Shells." NASA SP-288.
    Blevins, R. D. (1979) "Formulas for Natural Frequency and Mode Shape."
        Van Nostrand Reinhold. (ISBN 978-1575241845)
    Timoshenko, S. P. & Young, D. H. (1955) "Vibration Problems in
        Engineering." 3rd ed. Van Nostrand.
    Harris, C. M. & Crede, C. E. (eds.) (1976) "Shock and Vibration Handbook."
        2nd ed. McGraw-Hill.
    Rao, S. S. (2011) "Mechanical Vibrations." 5th ed. Pearson. (ISBN 978-0132128193)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence


# ── Beam natural frequencies (Euler-Bernoulli) ────────────────────────────────

# Eigenvalue coefficients (β_n L) for the first three flexural modes.
# Source: Blevins 1979 Table 8-1; Rao 2011 Table 8.4.
_BEAM_BETA_L: dict[str, List[float]] = {
    "clamped-free":      [1.8751, 4.6941, 7.8548],   # cantilever (C-F)
    "clamped-clamped":   [4.7300, 7.8532, 10.9956],  # C-C beam
    "pinned-pinned":     [math.pi, 2 * math.pi, 3 * math.pi],  # P-P (exact: nπ)
    "clamped-pinned":    [3.9266, 7.0686, 10.2102],  # C-P
    "free-free":         [4.7300, 7.8532, 10.9956],  # symmetric to C-C for interior
}


def beam_flexural_frequency_hz(
    youngs_modulus_pa: float,
    second_moment_area_m4: float,
    linear_mass_density_kg_m: float,
    length_m: float,
    mode: int = 1,
    boundary: str = "clamped-free",
) -> float:
    """Natural frequency of n-th flexural mode of an Euler-Bernoulli beam.

    f_n = (β_n L)² / (2π L²) × √(EI / (ρA))     [Hz]

    where ρA = linear_mass_density_kg_m is the mass per unit length.

    Args:
        youngs_modulus_pa: Young's modulus E [Pa].
        second_moment_area_m4: Area moment of inertia I [m⁴].
        linear_mass_density_kg_m: Mass per unit length ρA [kg/m].
        length_m: Beam length [m].
        mode: Mode number (1 = fundamental, 2 = first harmonic, ...).
        boundary: Boundary condition string from _BEAM_BETA_L keys.

    Returns:
        Natural frequency f_n [Hz].

    Raises:
        ValueError: If mode > 3, length ≤ 0, or boundary not recognized.

    Reference: Blevins 1979 Table 8-1; Rao 2011 Eq. (8.20).
    """
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    if mode < 1 or mode > 3:
        raise ValueError("mode must be 1, 2, or 3 (higher modes not tabulated here)")
    if boundary not in _BEAM_BETA_L:
        raise ValueError(f"boundary {boundary!r} not in {list(_BEAM_BETA_L)}")

    beta_l = _BEAM_BETA_L[boundary][mode - 1]
    # EI / (ρA L⁴) = flexural rigidity / (mass × L³)
    # ω² = (β_n L)⁴ × EI / (ρA L⁴)
    omega_sq = (beta_l / length_m) ** 4 * youngs_modulus_pa * second_moment_area_m4 / linear_mass_density_kg_m
    return math.sqrt(omega_sq) / (2.0 * math.pi)


def beam_axial_frequency_hz(
    youngs_modulus_pa: float,
    density_kg_m3: float,
    length_m: float,
    boundary: str = "clamped-free",
) -> float:
    """Fundamental axial (longitudinal) natural frequency of a bar.

    For clamped-free:  f₁ = c / (4 L)
    For clamped-clamped / pinned-pinned:  f₁ = c / (2 L)

    where c = √(E/ρ) is the longitudinal wave speed.

    Args:
        youngs_modulus_pa: Young's modulus [Pa].
        density_kg_m3: Material density [kg/m³].
        length_m: Bar length [m].
        boundary: "clamped-free" or "clamped-clamped".

    Returns:
        Fundamental axial frequency [Hz].

    Reference: Blevins 1979 Table 11-1; Rao 2011 §9.3.
    """
    if length_m <= 0.0:
        raise ValueError("length_m must be positive")
    c = math.sqrt(youngs_modulus_pa / density_kg_m3)   # longitudinal wave speed [m/s]
    if boundary == "clamped-free":
        return c / (4.0 * length_m)   # quarter-wave resonance
    return c / (2.0 * length_m)       # half-wave (clamped-clamped / P-P)


# ── Cylindrical shell natural frequencies ─────────────────────────────────────

def cylindrical_shell_ring_frequency_hz(
    youngs_modulus_pa: float,
    density_kg_m3: float,
    radius_m: float,
    poisson_ratio: float = 0.3,
) -> float:
    """Cylindrical shell ring (breathing / hoop) natural frequency.

    The ring frequency f_ring is the frequency at which the shell
    circumference fits one longitudinal wavelength. It sets a critical
    frequency above which axial waves are cut off and below which shell
    stiffening is radius-dominated:

        f_ring = (1/2π) × √(E / (ρ R² (1−ν²)))     [Hz]

    This is the fundamental in-plane mode (n=0, m=0 breathing mode).
    Above this frequency, ring stiffness dominates the axial response
    (Donnell 1933).

    Args:
        youngs_modulus_pa: Young's modulus E [Pa].
        density_kg_m3: Shell material density ρ [kg/m³].
        radius_m: Mid-surface radius R [m].
        poisson_ratio: Poisson ratio ν (default 0.3 for metals).

    Returns:
        Ring frequency [Hz].

    Reference: Leissa 1973 NASA SP-288 §1.1; Donnell 1933.
    """
    return (1.0 / (2.0 * math.pi)) * math.sqrt(
        youngs_modulus_pa / (density_kg_m3 * radius_m ** 2 * (1.0 - poisson_ratio ** 2))
    )


def cylindrical_shell_flexural_frequency_hz(
    youngs_modulus_pa: float,
    density_kg_m3: float,
    radius_m: float,
    thickness_m: float,
    length_m: float,
    n_circ: int = 2,
    m_long: int = 1,
    poisson_ratio: float = 0.3,
) -> float:
    """Flexural (bending) natural frequency of a simply-supported cylindrical shell.

    Uses the Donnell-Mushtari simplified frequency equation:

        ω² ≈ ω_m² + ω_bend²

    where:
        ω_m = m π c_long / L   (longitudinal axial standing wave)
        ω_bend = n² c_bend / R  (circumferential bending, Leissa SP-288)

    This gives the decoupled approximation. For coupled bending-axial
    modes, use the full Donnell 8th-order characteristic equation.

    Args:
        youngs_modulus_pa: E [Pa].
        density_kg_m3: ρ [kg/m³].
        radius_m: R [m].
        thickness_m: Shell wall thickness h [m].
        length_m: Shell length L [m].
        n_circ: Circumferential wave number n (≥ 2 for bending; n=0 breathing, n=1 beam).
        m_long: Longitudinal half-wave number m (≥ 1).
        poisson_ratio: ν.

    Returns:
        Approximate natural frequency [Hz].

    Reference: Leissa 1973 NASA SP-288 §1.2, Eq. 1.2.6 (simplified).
    """
    if n_circ < 0 or m_long < 1:
        raise ValueError("n_circ must be ≥ 0, m_long must be ≥ 1")

    c_long = math.sqrt(youngs_modulus_pa / (density_kg_m3 * (1.0 - poisson_ratio ** 2)))
    # Longitudinal standing wave frequency
    omega_long = m_long * math.pi * c_long / length_m

    # Bending frequency component: ω_n = n² × c_bend / R²
    # c_bend = √(E/(12ρ(1-ν²))) × h = thin-wall flexural wave speed × h/R²
    D = youngs_modulus_pa * thickness_m ** 3 / (12.0 * (1.0 - poisson_ratio ** 2))
    mass_per_area = density_kg_m3 * thickness_m
    # Plate bending frequency for wavenumber k=n/R
    k_circ = n_circ / radius_m
    omega_bend = k_circ ** 2 * math.sqrt(D / mass_per_area)

    omega_total = math.sqrt(omega_long ** 2 + omega_bend ** 2)
    return omega_total / (2.0 * math.pi)


# ── Simply-supported rectangular plate ───────────────────────────────────────

def plate_natural_frequency_hz(
    youngs_modulus_pa: float,
    density_kg_m3: float,
    thickness_m: float,
    length_x_m: float,
    length_y_m: float,
    mode_m: int = 1,
    mode_n: int = 1,
    poisson_ratio: float = 0.3,
) -> float:
    """Natural frequency of a simply-supported rectangular plate (Kirchhoff).

    f_{mn} = (π/2) × √(D / (ρ h)) × ((m/a)² + (n/b)²)    [Hz]

    where D = Eh³ / (12(1−ν²)) is the flexural rigidity.

    Args:
        youngs_modulus_pa: E [Pa].
        density_kg_m3: ρ [kg/m³].
        thickness_m: Plate thickness h [m].
        length_x_m: Plate length in x direction a [m].
        length_y_m: Plate length in y direction b [m].
        mode_m: Mode number in x direction (m=1 = fundamental in x).
        mode_n: Mode number in y direction (n=1 = fundamental in y).
        poisson_ratio: ν.

    Returns:
        Natural frequency f_{mn} [Hz].

    Reference: Leissa 1969 NASA SP-160 Table 4.1; Blevins 1979 Table 11-4.
    """
    if thickness_m <= 0 or length_x_m <= 0 or length_y_m <= 0:
        raise ValueError("dimensions must be positive")
    D = youngs_modulus_pa * thickness_m ** 3 / (12.0 * (1.0 - poisson_ratio ** 2))
    rho_h = density_kg_m3 * thickness_m
    factor = (mode_m / length_x_m) ** 2 + (mode_n / length_y_m) ** 2
    return (math.pi / 2.0) * math.sqrt(D / rho_h) * factor


# ── Critical speed (Campbell diagram) ────────────────────────────────────────

def critical_spin_speed_rpm(
    natural_frequency_hz: float,
    harmonic_order: int = 1,
) -> float:
    """Rotating speed at which n-th engine harmonic equals a structural mode.

    N_crit = 60 × f_n / k     [RPM]

    where f_n is the structural natural frequency [Hz] and k is the harmonic
    order (engine firing order, propeller blade number, etc.).

    Args:
        natural_frequency_hz: Structural natural frequency [Hz].
        harmonic_order: Engine excitation harmonic order (integer ≥ 1).

    Returns:
        Critical rotation speed [RPM] to avoid for this mode-harmonic pair.

    Reference: Harris & Crede 1976 §38-3 (Campbell diagram).
    """
    if harmonic_order < 1:
        raise ValueError("harmonic_order must be ≥ 1")
    return 60.0 * natural_frequency_hz / harmonic_order


# ── Resonance stress amplification ───────────────────────────────────────────

@dataclass
class ResonanceAmplification:
    """Dynamic magnification factor (DMF) at and near resonance."""
    frequency_ratio: float      # Ω/ω₀  (excitation / natural frequency)
    damping_ratio: float        # ζ (dimensionless, 0.01–0.1 for metals)
    dmf: float                  # Dynamic magnification factor |H(Ω)|
    is_resonant: bool           # True if Ω/ω₀ within ±ζ of 1 (damping bandwidth)
    quality_factor: float       # Q = 1/(2ζ): stress amp at resonance


def dynamic_magnification_factor(
    excitation_freq_hz: float,
    natural_freq_hz: float,
    damping_ratio: float = 0.02,
) -> ResonanceAmplification:
    """Dynamic Magnification Factor (DMF) for linear SDOF system.

    For a harmonically excited spring-mass-damper:
        |H(Ω)| = 1 / √((1 − r²)² + (2ζr)²)

    where r = Ω/ω₀ (frequency ratio), ζ = damping ratio.
    At resonance (r = 1): DMF = 1/(2ζ) = Q (quality factor).

    Typical structural damping ratios:
      - Welded steel: ζ ≈ 0.01–0.02
      - Bolted joints: ζ ≈ 0.03–0.05
      - Composite panels: ζ ≈ 0.01–0.03
      - Resonance at ζ=0.02 → Q=25, stress amplification factor = 25×

    Args:
        excitation_freq_hz: Forcing frequency Ω [Hz].
        natural_freq_hz: Structural natural frequency ω₀ [Hz].
        damping_ratio: ζ (dimensionless).

    Returns:
        ResonanceAmplification with DMF and resonance flag.

    Reference: Rao 2011 §3.6; Harris & Crede 1976 §2-21.
    """
    if damping_ratio <= 0.0 or damping_ratio > 1.0:
        raise ValueError("damping_ratio must be in (0, 1]")
    if natural_freq_hz <= 0.0:
        raise ValueError("natural_freq_hz must be positive")

    r = excitation_freq_hz / natural_freq_hz
    q = 1.0 / (2.0 * damping_ratio)
    dmf = 1.0 / math.sqrt((1.0 - r ** 2) ** 2 + (2.0 * damping_ratio * r) ** 2)
    # Resonant bandwidth: |r - 1| < ζ (half-power bandwidth approximation)
    is_resonant = abs(r - 1.0) < damping_ratio

    return ResonanceAmplification(
        frequency_ratio=r,
        damping_ratio=damping_ratio,
        dmf=dmf,
        is_resonant=is_resonant,
        quality_factor=q,
    )


# ── Hull panel frequency audit ────────────────────────────────────────────────

@dataclass
class HullModalBudget:
    """Modal audit of hull cylindrical sections and truss panels."""
    ring_breathing_hz: float
    truss_panel_hz: float
    beam_mode1_hz: float
    notes: list


def hull_modal_budget(
    hull_radius_m: float = 12.6,
    hull_thickness_m: float = 0.05,
    hull_length_m: float = 100.0,
    youngs_modulus_pa: float = 113.8e9,   # Ti-6Al-4V (MMPDS-17)
    density_kg_m3: float = 4430.0,        # Ti-6Al-4V (MMPDS-17)
    poisson_ratio: float = 0.342,         # Ti-6Al-4V (MMPDS-17)
    panel_size_m: float = 2.0,
) -> HullModalBudget:
    """Compute key natural frequencies for the ARIA hull geometry.

    Uses default Ti-6Al-4V properties and ARIA generation-ship geometry
    (R=12.6 m radius, t=50 mm wall, 100 m hull section).

    Args:
        hull_radius_m: Mid-surface radius [m].
        hull_thickness_m: Wall thickness [m].
        hull_length_m: Hull section length [m].
        youngs_modulus_pa: E [Pa].
        density_kg_m3: ρ [kg/m³].
        poisson_ratio: ν.
        panel_size_m: Characteristic panel dimension [m] for simply-supported plate.

    Returns:
        HullModalBudget with key frequencies.

    Reference: Blevins 1979; Leissa 1973 NASA SP-288.
    """
    f_ring = cylindrical_shell_ring_frequency_hz(
        youngs_modulus_pa, density_kg_m3, hull_radius_m, poisson_ratio
    )

    f_panel = plate_natural_frequency_hz(
        youngs_modulus_pa, density_kg_m3, hull_thickness_m,
        panel_size_m, panel_size_m, poisson_ratio=poisson_ratio
    )

    # Beam: treat the hull section as a clamped-clamped column
    # I = π(R_o⁴ - R_i⁴)/4; R_i = R - t; R_o = R + t/2 for mid-surface radius
    R_o = hull_radius_m + hull_thickness_m / 2.0
    R_i = hull_radius_m - hull_thickness_m / 2.0
    I_m4 = math.pi * (R_o ** 4 - R_i ** 4) / 4.0
    # Linear mass density: ρ × 2πR × t (thin-wall approximation)
    rho_a = density_kg_m3 * 2.0 * math.pi * hull_radius_m * hull_thickness_m
    f_beam = beam_flexural_frequency_hz(
        youngs_modulus_pa, I_m4, rho_a, hull_length_m,
        mode=1, boundary="clamped-clamped"
    )

    notes = []
    if f_ring < 10.0:
        notes.append(f"Ring breathing mode {f_ring:.2f} Hz: check for acoustic excitation")
    if f_panel < 50.0:
        notes.append(f"Panel mode {f_panel:.1f} Hz: check for mechanical pump vibration")
    if f_beam < 1.0:
        notes.append(f"Beam mode {f_beam:.3f} Hz: check for attitude control coupling")

    return HullModalBudget(
        ring_breathing_hz=f_ring,
        truss_panel_hz=f_panel,
        beam_mode1_hz=f_beam,
        notes=notes,
    )
