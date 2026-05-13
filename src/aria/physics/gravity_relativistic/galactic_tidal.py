"""Galactic tidal tensor at the local galactic neighborhood
(§4.9 of docs/pods/A2_tidal_tensor.md).

The galactic potential in the Sun's local neighborhood is
parameterised by Oort's constants `A` and `B` (Binney & Tremaine
*Galactic Dynamics* 2nd ed §3.2, ISBN 978-0691130279). In the locally
rotating, locally flat approximation, the tidal tensor in the
galactocentric cylindrical basis (R, φ, z) is diagonal with

    E^{RR} = −(A − B)(3A + B)                           [1/s²]
    E^{φφ} = +(A² − B²)
    E^{zz} = +4π G ρ_local                              (vertical pinch)

where ρ_local is the local total mass density (stars + gas + dark
matter).

Modern values:
  - Oort A = 15.3 ± 0.4 km s⁻¹ kpc⁻¹
  - Oort B = −11.9 ± 0.4 km s⁻¹ kpc⁻¹
    (Bovy 2017 MNRAS 468 L63 DOI 10.1093/mnrasl/slx027)
  - ρ_local ≈ 0.1 M_☉ pc⁻³
    (Bienaymé 2014 A&A 571 A92 DOI 10.1051/0004-6361/201423496)

The magnitudes are ~10⁻³⁰ s⁻², so the galactic tide stretches a 1 km
ship by ~10⁻²¹ m/s² — negligible for mission dynamics but audited for
the M1 bookkeeping pod.
"""

from __future__ import annotations

import math

import numpy as np

# ──────────────────────────────────────────────────────────────────────
#  Constants (every row has a published citation)
# ──────────────────────────────────────────────────────────────────────

# Oort A, B (Bovy 2017 MNRAS 468 L63 DOI 10.1093/mnrasl/slx027).
OORT_A_KM_S_KPC: float = 15.3  # km s⁻¹ kpc⁻¹  (Bovy 2017)
OORT_B_KM_S_KPC: float = -11.9  # km s⁻¹ kpc⁻¹  (Bovy 2017)

# Local total density — Bienaymé 2014 A&A 571 A92
# DOI 10.1051/0004-6361/201423496 (RAVE red-clump determination).
# 0.1 M_sun per pc³ converts to kg/m³ as:
#   0.1 × 1.98892e30 kg / (3.0857e16 m)³
# = 0.1 × 1.98892e30 / 2.938e49
# = 6.77e-21 kg/m³
RHO_LOCAL_KG_M3: float = 6.77e-21  # derived from Bienaymé 2014

# CODATA 2018 G.
_G: float = 6.67430e-11  # m³ kg⁻¹ s⁻²

# Unit conversions.
_KM_PER_KPC: float = 3.0857e16 / 1.0e3  # km per kpc
# 1 km/s/kpc = 1000 m/s / (3.0857e19 m) ≈ 3.2408e-17 s⁻¹
_KM_S_KPC_TO_INV_S: float = 1.0e3 / 3.0857e19


def oort_galactic_tidal_tensor(
    oort_a_km_s_kpc: float = OORT_A_KM_S_KPC,
    oort_b_km_s_kpc: float = OORT_B_KM_S_KPC,
    local_density_kg_m3: float = RHO_LOCAL_KG_M3,
) -> np.ndarray:
    """Local galactic tidal tensor in cylindrical (R̂, φ̂, ẑ) basis.

    Returns a (3, 3) diagonal tensor in 1/s². The basis is the
    galactocentric cylindrical frame at the Sun's location: R̂
    pointing radially outward from the Galactic Center, φ̂ along the
    direction of Galactic rotation, ẑ toward the Galactic North Pole.

    Note: the exact sign convention here follows Binney & Tremaine
    eq. 3-83 — a *positive* diagonal entry denotes a stretch (the
    tidal tensor convention of this module is E^i_j = ∂²Φ/∂x^i∂x^j
    with E < 0 along the radial stretch axis).
    """
    A = oort_a_km_s_kpc * _KM_S_KPC_TO_INV_S  # 1/s
    B = oort_b_km_s_kpc * _KM_S_KPC_TO_INV_S  # 1/s
    E_RR = -(A - B) * (3.0 * A + B)
    E_pp = A * A - B * B
    E_zz = 4.0 * math.pi * _G * local_density_kg_m3
    return np.array(
        [[E_RR, 0.0, 0.0],
         [0.0, E_pp, 0.0],
         [0.0, 0.0, E_zz]],
        dtype=float,
    )
